# schedule_app/views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.sessions.models import Session
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.models import User

import json
import re
import zipfile
import openpyxl

try:
    import xlrd
    HAS_XLRD = True
except ImportError:
    HAS_XLRD = False

from cities_light.models import Region, City
from .forms import (
    RegistrationForm, LoginForm, ProfileEditForm,
    CustomPasswordChangeForm, VerificationCodeForm,
    russian_name,
)
from .models import (
    Profile, School, SavedSchedule, EmailVerification, ScheduleChange,
)


# ==================== ХЕЛПЕРЫ УВЕДОМЛЕНИЙ ====================

def _log_schedule_change(user, day, change_type, class_name=''):
    """Создаёт ScheduleChange для школы пользователя.

    class_name — конкретный класс. Пусто — все классы школы.
    Дедупликация: одинаковые неотправленные записи за 5 минут не дублируются.
    """
    profile = getattr(user, 'profile', None)
    if not profile or not profile.school_id:
        return

    threshold = timezone.now() - timezone.timedelta(minutes=5)
    already = ScheduleChange.objects.filter(
        school=profile.school,
        class_name=class_name or '',
        day=day,
        change_type=change_type,
        notified=False,
        created_at__gte=threshold,
    ).exists()
    if already:
        return

    ScheduleChange.objects.create(
        school=profile.school,
        class_name=class_name or '',
        day=day,
        change_type=change_type,
    )


def _invalidate_school_cache(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.school_id:
        cache.delete(f'schedule_school_{profile.school_id}')


def _diff_changed_classes(old_data, new_data):
    """Список классов, чьё расписание изменилось."""
    def index_by_class(data):
        result = {}
        for cls in (data or []):
            name = (cls.get('name') or '').strip().upper()
            if name:
                result[name] = cls.get('lessons') or []
        return result

    def norm(lessons):
        out = []
        for lesson in lessons:
            subj = (lesson.get('subject') or '').strip()
            if not subj or subj == '--|--':
                out.append(None)
                continue
            cabs = tuple(sorted(
                (c.get('classroom') or '').strip()
                for c in (lesson.get('classrooms') or [])
                if c.get('classroom')
            ))
            out.append((subj, cabs))
        return out

    old_map = index_by_class(old_data)
    new_map = index_by_class(new_data)

    changed = set()
    for name in set(old_map) | set(new_map):
        if norm(old_map.get(name, [])) != norm(new_map.get(name, [])):
            changed.add(name)

    return sorted(changed)


def _class_names_from_data(data):
    return [
        (cls.get('name') or '').strip().upper()
        for cls in (data or [])
        if (cls.get('name') or '').strip()
    ]


# ==================== ВАЛИДАЦИЯ ИМЕНИ ФАЙЛА ====================

ALLOWED_FILE_DAY_NAMES = {
    # русские
    'понедельник': 'monday',
    'вторник': 'tuesday',
    'среда': 'wednesday',
    'четверг': 'thursday',
    'пятница': 'friday',
    'суббота': 'saturday',
    # английские
    'monday': 'monday',
    'tuesday': 'tuesday',
    'wednesday': 'wednesday',
    'thursday': 'thursday',
    'friday': 'friday',
    'saturday': 'saturday',
}


def _day_from_filename(filename):
    """Возвращает ключ дня из имени файла или None.

    Берёт имя без расширения, приводит к нижнему регистру,
    убирает всё кроме букв, ищет соответствие в ALLOWED_FILE_DAY_NAMES.
    """
    if not filename:
        return None
    base = filename.rsplit('.', 1)[0]
    key = base.strip().lower()
    key = re.sub(r'[^а-яёa-z]+', '', key)
    if not key:
        return None
    return ALLOWED_FILE_DAY_NAMES.get(key)


# ==================== ПАРСИНГ EXCEL ====================

DAY_ALIASES = {
    'понедельник': 'monday',
    'понеделльник': 'monday',
    'вторник': 'tuesday',
    'среда': 'wednesday',
    'четверг': 'thursday',
    'пятница': 'friday',
    'суббота': 'saturday',
    'воскресенье': 'sunday',
}

_NO_ROOM_SUBJECTS = {
    'БАССЕЙН', 'РОВ', 'ЧЕРЧЕНИЕ',
}

_STOP_VALUES = {'\\', '/', '-', '--', 'ПРОПУСК'}


def _normalize_day(text):
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    s = re.sub(r'[^а-яёa-z]+', '', s)
    if not s:
        return None
    for alias, key in DAY_ALIASES.items():
        if alias in s:
            return key
    return None


def _normalize_class_name(value):
    """5\"А\" -> 5А; 1а -> 1А; 9 Б -> 9Б."""
    if value is None:
        return None
    s = str(value)
    s = s.replace('"', '').replace("'", '').replace('«', '').replace('»', '')
    s = s.replace(' ', '').replace('-', '').replace('_', '').replace('.', '')
    s = s.upper()
    if not s:
        return None
    m = re.match(r'^([0-9]{1,2})([А-ЯЁ])$', s)
    if not m:
        return None
    return f'{m.group(1)}{m.group(2)}'


def _extract_lesson_number(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        n = int(float(s))
    except (ValueError, TypeError):
        return None
    if 1 <= n <= 20:
        return n
    return None


def _parse_lesson_cell(cell_value):
    """Возвращает {'subject': str, 'classrooms': [{'classroom', 'type'}]} или None.

    Правила:
      - пусто / None -> None (обрабатывается как пропуск вызывающим кодом)
      - '\\' / '/' / '-' / '--' / 'ПРОПУСК' -> пропуск ('--|--')
      - 'ФИЗ-РА', 'ФИЗРА', 'ФИЗКУЛЬТУРА' -> subject + Спортзал
      - 'БАССЕЙН', 'РОВ', 'ЧЕРЧЕНИЕ' -> subject без кабинета
      - 'МАТЕМ 5'             -> subject='МАТЕМ', classrooms=['5']
      - 'АНГ ЯЗ 11/18'        -> subject='АНГ ЯЗ', classrooms=['11','18']
      - 'АНГ ЯЗ(1) 20'        -> subject='АНГ ЯЗ', classrooms=['20']
      - 'АНГ(1)11/ИНФ7'       -> subject='АНГ/ИНФ', classrooms=['11','7']
      - 'АНГ20/ИНФ7'          -> subject='АНГ/ИНФ', classrooms=['20','7']
      - 'ТРУД 16/1'           -> subject='ТРУД', classrooms=['16','1']
      - 'IT-КУБ с 14-00 до 15-30' -> subject целиком, classrooms=[]
    """
    if cell_value is None:
        return None
    text = str(cell_value).strip()
    if not text:
        return None

    upper = text.upper()

    # Пропуски
    if text in _STOP_VALUES:
        return {'subject': '--|--', 'classrooms': []}

    # Физкультура — всегда спортзал
    if upper in ('ФИЗ-РА', 'ФИЗРА', 'ФИЗКУЛЬТУРА', 'ФИЗ-РА.', 'ФИЗКУЛЬТ.'):
        return {
            'subject': text,
            'classrooms': [{'classroom': 'Спортзал', 'type': ''}],
        }

    # Предметы без кабинета
    if upper in _NO_ROOM_SUBJECTS:
        return {'subject': text, 'classrooms': []}

    # IT-КУБ с временем
    if re.search(r'\d{1,2}[-:]\d{2}', text):
        return {'subject': text, 'classrooms': []}

    # Групповые уроки со склейкой: 'АНГ(1)11/ИНФ7', 'АНГ20/ИНФ7'
    if '/' in text and re.search(r'[А-ЯЁа-яё]\d', text):
        parts = re.split(r'\s*/\s*', text)
        subjects = []
        classrooms = []
        ok = True
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = re.match(r'^([^\d]+?)\s*\(?([пэбПЭБ0-9]*)\)?\s*(\d+)?$', part)
            if not m:
                ok = False
                break
            subj_raw = re.sub(r'[()]', '', m.group(1)).strip()
            subj_raw = re.sub(r'\s+', ' ', subj_raw)
            subjects.append(subj_raw)
            if m.group(3):
                classrooms.append(m.group(3))
        if ok and subjects:
            subject = '/'.join(s for s in subjects if s)
            cabs = [{'classroom': c, 'type': ''} for c in classrooms]
            return {'subject': subject, 'classrooms': cabs}

    # 'МАТЕМ 5', 'АНГ ЯЗ 11/18', 'ТРУД 16/1'
    m = re.match(
        r'^(?P<subject>.+?)\s+(?P<cab>\d+(?:/\d+)*(?:\([пэбПЭБ]\))?(?:\s*/\s*\d+(?:\([пэбПЭБ]\))?)*)$',
        text,
    )
    if m:
        subject = m.group('subject').strip()
        cab_raw = m.group('cab').strip()
        classrooms = []
        for c in re.split(r'\s*/\s*', cab_raw):
            c = c.strip()
            if not c:
                continue
            mm = re.match(r'^(\d+)\(([пэбПЭБ])\)$', c)
            if mm:
                classrooms.append({'classroom': mm.group(1), 'type': mm.group(2).lower()})
            elif re.match(r'^\d+$', c):
                classrooms.append({'classroom': c, 'type': ''})
        if classrooms:
            return {'subject': subject, 'classrooms': classrooms}

    # 'АНГ ЯЗ(1)' — предмет с типом, без кабинета
    m = re.match(r'^(?P<subject>.+?)\((?P<type>[пэбПЭБ0-9]+)\)$', text)
    if m:
        return {'subject': m.group('subject').strip(), 'classrooms': []}

    return {'subject': text, 'classrooms': []}


def _read_xlsx_rows(uploaded_file):
    wb = openpyxl.load_workbook(uploaded_file, data_only=True)
    sheet = wb.active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def _read_xls_rows(uploaded_file):
    if not HAS_XLRD:
        raise ValueError(
            'Для чтения .xls установите xlrd: pip install xlrd==2.0.1'
        )
    data = uploaded_file.read()
    book = xlrd.open_workbook(file_contents=data)
    sheet = book.sheet_by_index(0)
    return [sheet.row_values(r) for r in range(sheet.nrows)]


def _read_excel_rows(uploaded_file):
    name = (uploaded_file.name or '').lower()

    if name.endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        try:
            return _read_xlsx_rows(uploaded_file)
        except zipfile.BadZipFile:
            uploaded_file.seek(0)
            return _read_xls_rows(uploaded_file)
        except Exception as e:
            raise ValueError(f'Не удалось прочитать .xlsx: {e}')

    if name.endswith('.xls'):
        return _read_xls_rows(uploaded_file)

    try:
        uploaded_file.seek(0)
        return _read_xlsx_rows(uploaded_file)
    except Exception:
        uploaded_file.seek(0)
        return _read_xls_rows(uploaded_file)


# ---------- СЕТКА КООРДИНАТ ----------

def _detect_class_columns(row):
    """Возвращает [(col_idx, '5А'), ...] для строки-заголовка классов."""
    result = []
    for col_idx, cell in enumerate(row):
        cn = _normalize_class_name(cell)
        if cn:
            result.append((col_idx, cn))
    return result


def _find_day_in_rows(rows, start, end):
    """Ищет день недели в строках [start, end). Возвращает (day_key, row_idx)."""
    for r in range(start, end):
        row = rows[r]
        for cell in row:
            dk = _normalize_day(cell)
            if dk:
                return dk, r
    return None, None


def _parse_schedule_rows(rows):
    """Парсит расписание по координатной сетке.

    Возвращает {day_key: [{'id', 'name', 'lessons'}, ...]}.
    """
    # 1. Находим все строки-заголовки классов
    blocks = []
    for row_idx, row in enumerate(rows):
        if not row:
            continue
        classes = _detect_class_columns(row)
        if len(classes) >= 2:
            blocks.append({'row': row_idx, 'columns': classes})

    if not blocks:
        return {}

    # 2. Определяем для каждого блока день и границы
    result = {}
    last_known_day = None

    def ensure_class(day_key, class_name):
        result.setdefault(day_key, {})
        if class_name not in result[day_key]:
            result[day_key][class_name] = {'lessons': []}

    for b_idx, block in enumerate(blocks):
        row_idx = block['row']
        classes = block['columns']

        # Границы блока
        start_row = row_idx + 1
        if b_idx + 1 < len(blocks):
            end_row = blocks[b_idx + 1]['row']
        else:
            end_row = min(len(rows), row_idx + 1 + 200)

        # Ищем день выше блока
        search_start = blocks[b_idx - 1]['row'] + 1 if b_idx > 0 else 0
        day_key, _ = _find_day_in_rows(rows, search_start, row_idx + 1)

        if day_key:
            last_known_day = day_key
        else:
            day_key = last_known_day

        if not day_key:
            continue

        for _, cn in classes:
            ensure_class(day_key, cn)

        # 3. Читаем уроки
        lesson_counter = 0
        for r in range(start_row, end_row):
            row = rows[r]
            if not row:
                continue

            if all((c is None or str(c).strip() == '') for c in row):
                continue

            # Пропускаем, если это ещё один заголовок классов
            if len(_detect_class_columns(row)) >= 2:
                continue

            number = _extract_lesson_number(row[0]) if len(row) > 0 else None
            if number is not None:
                lesson_counter = number
            else:
                lesson_counter += 1

            if lesson_counter < 1 or lesson_counter > 20:
                continue

            any_lesson_in_row = False
            for col_idx, cn in classes:
                if col_idx >= len(row):
                    continue
                cell_value = row[col_idx]

                # Пустая ячейка при наличии номера урока = пропуск
                is_empty = (cell_value is None) or (str(cell_value).strip() == '')

                if is_empty:
                    lesson = {'subject': '--|--', 'classrooms': []}
                else:
                    lesson = _parse_lesson_cell(cell_value)
                    if lesson is None:
                        continue
                    any_lesson_in_row = True

                ensure_class(day_key, cn)
                lessons = result[day_key][cn]['lessons']
                while len(lessons) < lesson_counter:
                    lessons.append({'subject': '', 'classrooms': []})

                existing = lessons[lesson_counter - 1]
                if (existing.get('subject') or '').strip():
                    continue
                lessons[lesson_counter - 1] = lesson

            if not any_lesson_in_row:
                # В строке были только пустые ячейки — не считаем её уроком
                lesson_counter -= 1

        # Обрезаем хвостовые '--|--' и пустые
        for _, cn in classes:
            lessons = result[day_key][cn]['lessons']
            while lessons:
                last_subj = (lessons[-1].get('subject') or '').strip()
                if last_subj in ('', '--|--'):
                    lessons.pop()
                else:
                    break

    # 4. Формируем schedule_data
    final = {}
    for day_key, classes in result.items():
        schedule_data = []
        for cn, data in classes.items():
            lessons = data.get('lessons', [])
            # Класс включаем, если есть хотя бы один реальный урок
            if not any(
                (l.get('subject') or '').strip() not in ('', '--|--')
                for l in lessons
            ):
                continue
            schedule_data.append({
                'id': f'import_{cn}_{abs(hash(cn))}',
                'name': cn,
                'lessons': lessons,
            })

        def _class_sort_key(item):
            m = re.match(r'^(\d+)([А-ЯЁ])$', item['name'])
            if m:
                return (int(m.group(1)), m.group(2))
            return (999, item['name'])

        schedule_data.sort(key=_class_sort_key)
        final[day_key] = schedule_data

    return final


# ==================== СТАТИЧНЫЕ СТРАНИЦЫ ====================

def index(request):
    return render(request, 'index.html')


def choice_view(request):
    return render(request, 'choice.html')


def schedule_view(request):
    return render(request, 'schedule.html')


def auto_schedule_view(request):
    return render(request, 'auto_schedule.html')


def upload_schedule_view(request):
    return render(request, 'upload_schedule.html')


# ==================== ЗАГРУЗКА EXCEL ====================

def process_upload(request):
    if request.method != 'POST' or not request.FILES.get('excel_file'):
        return JsonResponse({'error': 'Файл не передан'}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse(
            {'error': 'Только авторизованные пользователи могут загружать расписания'},
            status=403,
        )

    uploaded_file = request.FILES['excel_file']

    # Проверка имени файла
    file_day = _day_from_filename(uploaded_file.name)
    if not file_day:
        return JsonResponse({
            'error': 'Имя файла должно соответствовать дню недели: '
                     'понедельник, вторник, среда, четверг, пятница, суббота '
                     '(или на английском: monday, tuesday, wednesday, '
                     'thursday, friday, saturday). '
                     f'Получено: "{uploaded_file.name}".'
        }, status=400)

    # Чтение файла
    try:
        rows = _read_excel_rows(uploaded_file)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Не удалось прочитать файл: {e}'}, status=400)

    if len(rows) < 3:
        return JsonResponse({'error': 'Файл не содержит достаточно строк'}, status=400)

    # Парсинг
    try:
        parsed = _parse_schedule_rows(rows)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Ошибка разбора расписания: {e}'}, status=500)

    if not parsed:
        return JsonResponse({
            'error': 'Не удалось найти расписание. Проверьте, что в файле есть '
                     'строка с классами и строки с уроками.'
        }, status=400)

    # Принудительно приводим день к file_day
    if len(parsed) == 1:
        only_key = next(iter(parsed))
        if only_key != file_day:
            parsed[file_day] = parsed.pop(only_key)
    elif len(parsed) > 1:
        merged = {}
        for day_key, schedule_data in parsed.items():
            for cls in schedule_data:
                name = cls['name']
                if name in merged:
                    if len(cls['lessons']) > len(merged[name]['lessons']):
                        merged[name] = cls
                else:
                    merged[name] = cls
        parsed = {file_day: list(merged.values())}

    # Сохранение
    all_changed_classes = set()
    days_updated = []
    summary = {}
    day_key = None

    for day_key, schedule_data in parsed.items():
        if not schedule_data:
            continue

        old = SavedSchedule.objects.filter(user=request.user, day=day_key).first()
        old_data = old.schedule_data if old else None

        SavedSchedule.objects.update_or_create(
            user=request.user,
            day=day_key,
            defaults={'schedule_data': schedule_data},
        )

        if old_data:
            changed_classes = _diff_changed_classes(old_data, schedule_data)
        else:
            changed_classes = _class_names_from_data(schedule_data)

        all_changed_classes.update(changed_classes)
        days_updated.append(day_key)
        summary[day_key] = {
            'classes': [c['name'] for c in schedule_data],
            'changed': changed_classes,
        }

        for cn in changed_classes:
            _log_schedule_change(
                request.user, day_key,
                'created' if old_data is None else 'updated',
                class_name=cn,
            )

    _invalidate_school_cache(request.user)

    return JsonResponse({
        'status': 'ok',
        'message': f'Расписание на {day_key} загружено',
        'days': days_updated,
        'changed_classes': sorted(all_changed_classes),
        'summary': summary,
    })


# ==================== АУТЕНТИФИКАЦИЯ ====================

def auth_view(request):
    if request.user.is_authenticated:
        return redirect('schedule_app:profile')

    login_form = LoginForm()
    register_form = RegistrationForm()

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'login':
            form = LoginForm(request, data=request.POST)
            if form.is_valid():
                user = form.get_user()
                if hasattr(user, 'profile') and not user.profile.is_verified:
                    messages.error(request, 'Подтвердите email перед входом.')
                    return redirect('schedule_app:auth')
                login(request, user)
                messages.success(request, 'Добро пожаловать!')
                return redirect('schedule_app:profile')
            login_form = form

        elif form_type == 'register':
            form = RegistrationForm(request.POST)
            if form.is_valid():
                registration_data = form.get_registration_data()
                verification_code = EmailVerification.generate_code()

                EmailVerification.objects.create(
                    email=registration_data['email'],
                    code=verification_code,
                    user_data=registration_data,
                )

                send_verification_email(
                    registration_data['email'],
                    verification_code,
                    registration_data['full_name'],
                )

                request.session['pending_verification_email'] = registration_data['email']
                messages.success(request, 'Код подтверждения отправлен на почту.')
                return redirect('schedule_app:verify_email')
            register_form = form
        else:
            messages.error(request, 'Неизвестный тип формы.')

    return render(request, 'auth.html', {
        'login_form': login_form,
        'register_form': register_form,
    })


def send_verification_email(email, code, full_name):
    subject = 'Подтверждение регистрации - ШкольноеРасписание'
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background: #f5f7fa; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto; background: #fff; border-radius: 16px; padding: 30px;">
            <h2 style="color: #0b3b5c; text-align: center;">ШкольноеРасписание</h2>
            <p>Здравствуйте, <strong>{full_name}</strong>!</p>
            <p>Для завершения регистрации введите код:</p>
            <div style="font-size: 36px; font-weight: bold; text-align: center; padding: 20px;
                        background: #f0f7ff; border-radius: 12px; letter-spacing: 5px; color: #0b3b5c;">
                {code}
            </div>
            <p>Код действителен в течение 10 минут.</p>
        </div>
    </body>
    </html>
    """
    plain_message = f'Здравствуйте, {full_name}!\n\nКод подтверждения: {code}\n\nКод действителен 10 минут.'

    send_mail(
        subject,
        plain_message,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school-schedule.ru'),
        [email],
        fail_silently=False,
        html_message=html_message,
    )


def verify_email_view(request):
    email = request.session.get('pending_verification_email')

    if not email:
        messages.error(request, 'Сессия истекла. Зарегистрируйтесь заново.')
        return redirect('schedule_app:auth')

    try:
        verification = EmailVerification.objects.filter(
            email=email, is_used=False
        ).latest('created_at')
    except EmailVerification.DoesNotExist:
        messages.error(request, 'Код не найден. Зарегистрируйтесь заново.')
        return redirect('schedule_app:auth')

    timeout = getattr(settings, 'VERIFICATION_CODE_TIMEOUT', 600)
    if verification.is_expired(timeout):
        verification.delete()
        messages.error(request, 'Срок действия кода истёк. Зарегистрируйтесь заново.')
        return redirect('schedule_app:auth')

    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid() and form.cleaned_data['code'] == verification.code:
            user_data = verification.user_data

            user = User.objects.create_user(
                username=user_data['username'],
                email=user_data['email'],
                password=user_data['password'],
            )

            full_name = user_data['full_name']
            parts = full_name.split()
            if len(parts) >= 2:
                user.last_name = parts[0]
                user.first_name = parts[1]
            user.save()

            region = None
            city = None
            school = None

            if user_data.get('region_id'):
                try:
                    region = Region.objects.get(id=user_data['region_id'])
                except Region.DoesNotExist:
                    pass
            if user_data.get('city_id'):
                try:
                    city = City.objects.get(id=user_data['city_id'])
                except City.DoesNotExist:
                    pass
            if user_data.get('school_id'):
                try:
                    school = School.objects.get(id=user_data['school_id'])
                except School.DoesNotExist:
                    pass

            if school and not school.has_main_teacher():
                school.main_teacher = user
                school.save()

            Profile.objects.create(
                user=user,
                full_name=full_name,
                region=region,
                city=city,
                school=school,
                position=user_data.get('position', ''),
                is_verified=True,
            )

            verification.is_used = True
            verification.save()
            del request.session['pending_verification_email']

            login(request, user)
            messages.success(request, 'Регистрация завершена! Добро пожаловать!')
            return redirect('schedule_app:profile')
        else:
            messages.error(request, 'Неверный код. Попробуйте снова.')
            form = VerificationCodeForm()
    else:
        form = VerificationCodeForm()

    expiration_time = verification.created_at + timezone.timedelta(seconds=timeout)
    expires_in = int((expiration_time - timezone.now()).total_seconds())

    return render(request, 'verify_email.html', {
        'form': form,
        'email': email,
        'expires_in': expires_in,
        'expected_code': verification.code,
    })


def resend_verification_code(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не разрешён'}, status=405)

    email = request.session.get('pending_verification_email')
    if not email:
        return JsonResponse({'error': 'Сессия истекла'}, status=400)

    try:
        old = EmailVerification.objects.filter(email=email).order_by('-created_at').first()
        user_data = old.user_data if old else {}
        full_name = user_data.get('full_name', 'Пользователь')

        EmailVerification.objects.filter(email=email, is_used=False).delete()

        new_code = EmailVerification.generate_code()
        EmailVerification.objects.create(email=email, code=new_code, user_data=user_data)

        send_verification_email(email, new_code, full_name)
        return JsonResponse({'status': 'ok', 'message': 'Новый код отправлен'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def logout_view(request):
    logout(request)
    messages.info(request, 'Вы вышли из системы.')
    return redirect('schedule_app:index')


# ==================== ПРОФИЛЬ ====================

@login_required
def profile_view(request):
    schedules = SavedSchedule.objects.filter(user=request.user).order_by('day')

    schedules_list = [{
        'id': s.id,
        'day': s.day,
        'day_display': s.get_day_display(),
        'schedule_data': s.schedule_data,
        'created_at': s.created_at.isoformat(),
        'updated_at': s.updated_at.isoformat(),
    } for s in schedules]

    return render(request, 'profile.html', {
        'schedules': schedules,
        'schedules_json': json.dumps(schedules_list, ensure_ascii=False),
    })


@login_required
def profile_edit_view(request):
    from django.contrib.auth import update_session_auth_hash

    password_error = None

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, instance=request.user)

        profile = request.user.profile

        region_id = request.POST.get('region')
        city_id = request.POST.get('city')
        school_id = request.POST.get('school')
        position = request.POST.get('position', '')

        profile.region = None
        if region_id:
            try:
                profile.region = Region.objects.get(id=region_id)
            except Region.DoesNotExist:
                pass

        profile.city = None
        if city_id:
            try:
                profile.city = City.objects.get(id=city_id)
            except City.DoesNotExist:
                pass

        profile.school = None
        if school_id:
            try:
                profile.school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                pass

        profile.position = position
        profile.save()

        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        password_changed = False

        if new_password1 or new_password2:
            password_form = CustomPasswordChangeForm(user=request.user, data={
                'old_password': old_password,
                'new_password1': new_password1,
                'new_password2': new_password2,
            })
            if password_form.is_valid():
                password_form.save()
                password_changed = True
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Пароль изменён!')
            else:
                for errors in password_form.errors.values():
                    password_error = errors[0]
                    break

        if form.is_valid() and not password_error:
            user = form.save()
            user.profile.full_name = f'{user.first_name} {user.last_name}'.strip()
            user.profile.save()
            messages.success(request, 'Профиль обновлён!')
            return redirect('schedule_app:profile')
        elif password_error:
            messages.error(request, password_error)
    else:
        form = ProfileEditForm(instance=request.user)

    regions = [
        {'id': r.id, 'name': russian_name(r)}
        for r in Region.objects.filter(country__code2='RU').order_by('name')
    ]

    current_region = request.user.profile.region
    current_city = request.user.profile.city
    current_school = request.user.profile.school

    cities = []
    if current_region:
        cities = [
            {'id': c.id, 'name': russian_name(c)}
            for c in City.objects.filter(region=current_region, country__code2='RU').order_by('name')
        ]

    schools = []
    if current_city:
        schools = [
            {'id': s.id, 'name': s.name}
            for s in School.objects.filter(city=current_city).order_by('name')
        ]

    return render(request, 'profile_edit.html', {
        'form': form,
        'password_error': password_error,
        'regions': regions,
        'cities': cities,
        'schools': schools,
        'current_region': current_region,
        'current_city': current_city,
        'current_school': current_school,
    })


# ==================== API РАСПИСАНИЙ (ручной редактор) ====================

@csrf_exempt
@require_http_methods(['POST'])
def save_schedule(request):
    try:
        data = json.loads(request.body)
        day = data.get('day')
        schedule_data = data.get('schedule')

        if not day or schedule_data is None:
            return JsonResponse({'error': 'Не указан день или данные'}, status=400)

        if request.user.is_authenticated:
            old = SavedSchedule.objects.filter(user=request.user, day=day).first()
            old_data = old.schedule_data if old else None

            SavedSchedule.objects.update_or_create(
                user=request.user, day=day,
                defaults={'schedule_data': schedule_data},
            )

            if old_data:
                changed_classes = _diff_changed_classes(old_data, schedule_data)
            else:
                changed_classes = _class_names_from_data(schedule_data)

            _invalidate_school_cache(request.user)

            for cn in changed_classes:
                _log_schedule_change(
                    request.user, day,
                    'created' if old_data is None else 'updated',
                    class_name=cn,
                )

            return JsonResponse({'status': 'ok', 'changed_classes': changed_classes})
        else:
            if not request.session.session_key:
                request.session.create()
            session_obj = Session.objects.get(session_key=request.session.session_key)
            SavedSchedule.objects.update_or_create(
                session=session_obj, day=day,
                defaults={'schedule_data': schedule_data},
            )
            return JsonResponse({'status': 'ok', 'changed_classes': []})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['GET'])
def load_schedule(request, day):
    if request.user.is_authenticated:
        try:
            saved = SavedSchedule.objects.get(user=request.user, day=day)
            return JsonResponse({'schedule': saved.schedule_data})
        except SavedSchedule.DoesNotExist:
            pass

    if request.session.session_key:
        try:
            session_obj = Session.objects.get(session_key=request.session.session_key)
            saved = SavedSchedule.objects.get(session=session_obj, day=day)
            return JsonResponse({'schedule': saved.schedule_data})
        except SavedSchedule.DoesNotExist:
            pass

    return JsonResponse({'schedule': None})


@login_required
@require_http_methods(['DELETE'])
def delete_schedule(request, schedule_id):
    try:
        schedule = SavedSchedule.objects.get(id=schedule_id, user=request.user)
        class_names = _class_names_from_data(schedule.schedule_data)

        _invalidate_school_cache(request.user)

        for cn in class_names:
            _log_schedule_change(request.user, schedule.day, 'deleted', class_name=cn)

        schedule.delete()
        return JsonResponse({'status': 'ok'})
    except SavedSchedule.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


# ==================== API ГОРОДОВ И ШКОЛ ====================

def get_cities(request):
    region_id = request.GET.get('region_id')
    if region_id:
        cities = City.objects.filter(region_id=region_id, country__code2='RU').order_by('name')
        data = [{'id': c.id, 'name': russian_name(c)} for c in cities]
        return JsonResponse({'cities': data})
    return JsonResponse({'cities': []})


def get_schools(request):
    city_id = request.GET.get('city_id')
    if city_id:
        schools = School.objects.filter(city_id=city_id).order_by('name')
        data = [{
            'id': s.id,
            'name': s.name,
            'main_teacher': s.main_teacher_id is not None,
            'main_teacher_name': s.get_main_teacher_name() if s.has_main_teacher() else None,
        } for s in schools]
        return JsonResponse({'schools': data})
    return JsonResponse({'schools': []})


# ==================== СТРАНИЦЫ ОШИБОК ====================

def custom_404(request, exception):
    return render(request, '404.html', status=404)


def custom_500(request):
    return render(request, '500.html', status=500)


def custom_403(request, exception):
    return render(request, '403.html', status=403)