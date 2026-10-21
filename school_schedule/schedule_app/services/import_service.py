"""Excel schedule import and parsing service.

This module contains parsing logic without HTTP or database concerns.
"""

import re
import zipfile

import openpyxl

try:
    import xlrd
    HAS_XLRD = True
except ImportError:
    HAS_XLRD = False


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


# Public service API
day_from_filename = _day_from_filename
read_excel_rows = _read_excel_rows
parse_schedule_rows = _parse_schedule_rows

