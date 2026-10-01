# bot.py
import os
import django
import json
import re
import time
import logging
import datetime
import threading
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env до django.setup(), чтобы переменные были доступны
load_dotenv(Path(__file__).resolve().parent / '.env')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_schedule.settings')
django.setup()

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id

from django.conf import settings as django_settings
from django.db import close_old_connections

from cities_light.models import Region, City
from schedule_app.models import School, SavedSchedule, VkUser, ScheduleChange
from schedule_app.forms import russian_name


# ==================== НАСТРОЙКИ ====================

VK_TOKEN = os.environ['VK_TOKEN']
GROUP_ID = int(os.environ['VK_GROUP_ID'])

SITE_URL = django_settings.SITE_URL
COMMUNITY_LINK = django_settings.COMMUNITY_LINK
PAGE_SIZE = 8
NOTIFY_INTERVAL = 120

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger('vk-bot')


DAY_NAMES = {
    'monday': 'Понедельник',
    'tuesday': 'Вторник',
    'wednesday': 'Среда',
    'thursday': 'Четверг',
    'friday': 'Пятница',
    'saturday': 'Суббота',
}
DAY_ORDER = list(DAY_NAMES.keys())

LESSON_TIMES = getattr(django_settings, 'LESSON_TIMES', [
    ('08:00', '08:45'),
    ('08:55', '09:40'),
    ('09:50', '10:35'),
    ('10:45', '11:30'),
    ('11:50', '12:35'),
    ('12:45', '13:30'),
    ('13:40', '14:25'),
    ('14:35', '15:20'),
])


# ==================== СОСТОЯНИЯ ====================

_pending = {}


def set_pending(vk_id, action, **payload):
    _pending[vk_id] = {'action': action, 'payload': payload}


def pop_pending(vk_id):
    return _pending.pop(vk_id, None)


def get_pending(vk_id):
    return _pending.get(vk_id)


# ==================== VkUser ====================

def get_vk_user(vk_id):
    user, _ = VkUser.objects.get_or_create(vk_id=vk_id)
    return user


def reset_vk_user(vk_id):
    VkUser.objects.filter(vk_id=vk_id).delete()


def is_profile_complete(u):
    return bool(u.region and u.city and u.school and u.class_name)


# ==================== УТИЛИТЫ ====================

def strikethrough(text):
    return ''.join(c + '\u0336' for c in text)


def _lesson_time_for_index(index):
    if 1 <= index <= len(LESSON_TIMES):
        return LESSON_TIMES[index - 1]
    return (None, None)


def _today_day_key():
    """Возвращает ключ сегодняшнего дня (monday..saturday) или None (вс)."""
    today_idx = datetime.date.today().weekday()
    if today_idx >= len(DAY_ORDER):
        return None
    return DAY_ORDER[today_idx]


def _is_lesson_past(index, day, now=None):
    """Прошёл ли урок № index в указанный день.

    Если day — не сегодня, всегда возвращает False.
    """
    if day is None:
        return False
    today = _today_day_key()
    if today != day:
        return False

    if now is None:
        now = datetime.datetime.now()

    _, end = _lesson_time_for_index(index)
    if not end:
        return False

    return now.strftime('%H:%M') > end


# ==================== ПОИСК ====================

def _matches(obj, query):
    q = query.lower().strip()
    if not q:
        return False
    if q in obj.name.lower():
        return True
    for alt in (obj.alternate_names or '').split(','):
        if q in alt.strip().lower():
            return True
    return False


def search_regions(query, limit=None):
    result = []
    for r in Region.objects.filter(country__code2='RU').only(
        'id', 'name', 'alternate_names'
    ).order_by('name'):
        if _matches(r, query):
            result.append(r)
            if limit and len(result) >= limit:
                break
    return result


def search_cities(query, region_id, limit=None):
    result = []
    for c in City.objects.filter(region_id=region_id, country__code2='RU').only(
        'id', 'name', 'alternate_names'
    ).order_by('name'):
        if _matches(c, query):
            result.append(c)
            if limit and len(result) >= limit:
                break
    return result


def search_schools(query, city_id, limit=None):
    q = query.lower().strip()
    result = []
    for s in School.objects.filter(city_id=city_id).only('id', 'name').order_by('name'):
        if q in s.name.lower():
            result.append(s)
            if limit and len(result) >= limit:
                break
    return result


def parse_class(text):
    cleaned = text.strip().upper().replace(' ', '').replace('-', '')
    if re.match(r'^[0-9]{1,2}[А-ЯЁ]$', cleaned):
        return cleaned
    return None


# ==================== КЛАВИАТУРЫ ====================

def kb_main():
    """Главное меню."""
    kb = VkKeyboard(one_time=False)
    kb.add_button('Расписание', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('Настройки', color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('Профиль', color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('Пригласить друга', color=VkKeyboardColor.SECONDARY)
    return kb


def kb_cancel():
    kb = VkKeyboard(one_time=False)
    kb.add_button('Отмена', color=VkKeyboardColor.NEGATIVE)
    return kb


def kb_days():
    """Кнопки со всеми днями недели (Пн–Сб)."""
    kb = VkKeyboard(one_time=False)
    for i, day in enumerate(DAY_ORDER):
        kb.add_button(DAY_NAMES[day], payload={'day': day},
                      color=VkKeyboardColor.SECONDARY)
        if (i + 1) % 2 == 0 and i != len(DAY_ORDER) - 1:
            kb.add_line()
    kb.add_line()
    kb.add_button('В меню', color=VkKeyboardColor.PRIMARY)
    return kb


def kb_back():
    kb = VkKeyboard(one_time=False)
    kb.add_button('В меню', color=VkKeyboardColor.PRIMARY)
    return kb


def kb_profile():
    kb = VkKeyboard(one_time=False)
    kb.add_button('Изменить', color=VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('Сбросить', color=VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button('В меню', color=VkKeyboardColor.SECONDARY)
    return kb


def kb_settings(u):
    """Настройки бота — переключатели."""
    kb = VkKeyboard(one_time=False)

    bell_label = 'Звонки: вкл' if u.show_bell_times else 'Звонки: выкл'
    strike_label = 'Зачёркивать: вкл' if u.strike_past_lessons else 'Зачёркивать: выкл'

    kb.add_button(
        bell_label,
        payload={'action': 'toggle_bells'},
        color=VkKeyboardColor.POSITIVE if u.show_bell_times else VkKeyboardColor.SECONDARY,
    )
    kb.add_line()
    kb.add_button(
        strike_label,
        payload={'action': 'toggle_strike'},
        color=VkKeyboardColor.POSITIVE if u.strike_past_lessons else VkKeyboardColor.SECONDARY,
    )
    kb.add_line()
    kb.add_button('В меню', color=VkKeyboardColor.PRIMARY)
    return kb


def kb_edit_what():
    kb = VkKeyboard(one_time=False)
    kb.add_button('1. Регион', color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('2. Город', color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('3. Школа', color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('4. Класс', color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('В меню', color=VkKeyboardColor.PRIMARY)
    return kb


def kb_confirm_reset():
    kb = VkKeyboard(one_time=True)
    kb.add_button('Да', color=VkKeyboardColor.NEGATIVE)
    kb.add_button('Нет', color=VkKeyboardColor.POSITIVE)
    return kb


def kb_paginated(prefix, page, total_pages, has_next=True, has_prev=True):
    kb = VkKeyboard(one_time=False)
    if has_prev:
        kb.add_button('<', payload={'action': f'{prefix}_page', 'page': page - 1},
                      color=VkKeyboardColor.SECONDARY)
    if total_pages > 1:
        kb.add_button(f'{page + 1}/{total_pages}', color=VkKeyboardColor.SECONDARY)
    if has_next:
        kb.add_button('>', payload={'action': f'{prefix}_page', 'page': page + 1},
                      color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('Отмена', color=VkKeyboardColor.NEGATIVE)
    return kb


# ==================== ОТПРАВКА ====================

def send(vk, user_id, text, keyboard=None):
    kwargs = {'user_id': user_id, 'message': text, 'random_id': get_random_id()}
    if keyboard:
        kwargs['keyboard'] = keyboard.get_keyboard()
    try:
        vk.messages.send(**kwargs)
    except Exception as e:
        log.exception('Ошибка отправки сообщения: %s', e)


# ==================== ГЛАВНЫЕ ОБРАБОТЧИКИ ====================

def handle_start(vk, user_id):
    user = get_vk_user(user_id)

    if is_profile_complete(user):
        send(
            vk, user_id,
            f'С возвращением!\n\n'
            f'Школа: {user.school.name}\n'
            f'Класс: {user.class_name}\n\n'
            'Выбери действие:',
            kb_main(),
        )
        return

    reset_vk_user(user_id)
    get_vk_user(user_id)
    send(
        vk, user_id,
        'Привет! Я бот "ШкольноеРасписание".\n\n'
        'Показываю расписание уроков для твоего класса.\n\n'
        'Давай заполним профиль. Это займёт минуту.',
    )
    begin_setup(vk, user_id)


def handle_invite(vk, user_id):
    send(
        vk, user_id,
        'ПРИГЛАСИТЬ ДРУГА\n'
        '━━━━━━━━━━━━━━━\n\n'
        'Отправь другу ссылку на сообщество — он тоже сможет '
        'смотреть расписание своего класса:\n\n'
        f'{COMMUNITY_LINK}',
        kb_main(),
    )


# ==================== НАСТРОЙКИ ====================

def handle_settings(vk, user_id):
    u = get_vk_user(user_id)
    bell_state = 'включено' if u.show_bell_times else 'выключено'
    strike_state = 'включено' if u.strike_past_lessons else 'выключено'

    send(
        vk, user_id,
        'НАСТРОЙКИ\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'Звонки: {bell_state}\n'
        f'Зачёркивание прошедших уроков: {strike_state}\n\n'
        '━━━━━━━━━━━━━━━\n'
        'Нажми на кнопку, чтобы переключить.\n\n'
        'Зачёркивание работает только для расписания на сегодня.',
        kb_settings(u),
    )


def handle_toggle_bells(vk, user_id):
    u = get_vk_user(user_id)
    u.show_bell_times = not u.show_bell_times
    u.save()
    state = 'включено' if u.show_bell_times else 'выключено'
    send(vk, user_id, f'Звонки: {state}', kb_settings(u))


def handle_toggle_strike(vk, user_id):
    u = get_vk_user(user_id)
    u.strike_past_lessons = not u.strike_past_lessons
    u.save()
    state = 'включено' if u.strike_past_lessons else 'выключено'
    send(vk, user_id, f'Зачёркивание прошедших уроков: {state}', kb_settings(u))


# ==================== МАСТЕР НАСТРОЙКИ ====================

def begin_setup(vk, user_id):
    set_pending(user_id, 'input_region')
    send(
        vk, user_id,
        'Шаг 1 из 4. Введи название региона (можно часть):\n'
        'Например: "Челябинская" или "Московская область".',
        kb_cancel(),
    )


# ---------- РЕГИОН ----------

def step_input_region(vk, user_id, text):
    matches = search_regions(text, limit=50)
    if not matches:
        send(
            vk, user_id,
            'Регион не найден.\n\nПопробуй другое название или нажми "Отмена".',
            kb_cancel(),
        )
        return

    if len(matches) == 1:
        apply_region(vk, user_id, matches[0], next_step='city')
        return

    items = [{'id': r.id, 'label': russian_name(r)} for r in matches]
    _render_options(vk, user_id, 'Выбери регион:', items, 'pick_region',
                    next_step='city')


def apply_region(vk, user_id, region, next_step='city', prompt_after=None):
    u = get_vk_user(user_id)
    u.region = region

    if u.city and u.city.region_id != region.id:
        u.city = None
        u.school = None
        u.class_name = ''
    u.save()
    pop_pending(user_id)

    if prompt_after:
        send(vk, user_id, prompt_after, kb_main())
        return

    send(
        vk, user_id,
        f'Регион: {russian_name(region)}\n\n'
        'Шаг 2 из 4. Введи город (можно часть).',
        kb_cancel(),
    )
    set_pending(user_id, 'input_city')


# ---------- ГОРОД ----------

def step_input_city(vk, user_id, text):
    u = get_vk_user(user_id)
    if not u.region:
        send(vk, user_id, 'Сначала выбери регион.', kb_cancel())
        set_pending(user_id, 'input_region')
        return

    matches = search_cities(text, u.region_id, limit=50)
    if not matches:
        send(
            vk, user_id,
            f'Город не найден в регионе "{russian_name(u.region)}".\n\n'
            'Попробуй другое название или нажми "Отмена".',
            kb_cancel(),
        )
        return

    if len(matches) == 1:
        apply_city(vk, user_id, matches[0], next_step='school')
        return

    items = [{'id': c.id, 'label': russian_name(c)} for c in matches]
    _render_options(vk, user_id, 'Выбери город:', items, 'pick_city',
                    next_step='school')


def apply_city(vk, user_id, city, next_step='school', prompt_after=None):
    u = get_vk_user(user_id)
    u.city = city

    if u.school and u.school.city_id != city.id:
        u.school = None
        u.class_name = ''
    u.save()
    pop_pending(user_id)

    if prompt_after:
        send(vk, user_id, prompt_after, kb_main())
        return

    send(
        vk, user_id,
        f'Город: {russian_name(city)}\n\n'
        'Шаг 3 из 4. Введи название или номер школы (можно часть).\n'
        'Например: "14", "СОШ 4", "Гимназия".',
        kb_cancel(),
    )
    set_pending(user_id, 'input_school')


# ---------- ШКОЛА ----------

def step_input_school(vk, user_id, text):
    u = get_vk_user(user_id)
    if not u.city:
        send(vk, user_id, 'Сначала выбери город.', kb_cancel())
        set_pending(user_id, 'input_city')
        return

    matches = search_schools(text, u.city_id, limit=20)
    if not matches:
        send(
            vk, user_id,
            f'Школа не найдена в городе "{russian_name(u.city)}".\n\n'
            'Попробуй другое название или нажми "Отмена".\n'
            'Например: "14", "СОШ 4", "Гимназия".',
            kb_cancel(),
        )
        return

    if len(matches) == 1:
        apply_school(vk, user_id, matches[0])
        return

    show_school_candidates(vk, user_id, matches)


def apply_school(vk, user_id, school, prompt_after=None):
    u = get_vk_user(user_id)
    u.school = school
    u.class_name = ''
    u.save()
    pop_pending(user_id)

    if prompt_after:
        send(vk, user_id, prompt_after, kb_main())
        return

    send(
        vk, user_id,
        f'Школа: {school.name}\n\n'
        'Шаг 4 из 4. Введи свой класс.\n'
        'Например: 5А, 11Б, 9В.',
        kb_cancel(),
    )
    set_pending(user_id, 'input_class')


def show_school_candidates(vk, user_id, schools, page=0):
    total = len(schools)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    chunk = schools[start:end]

    u = get_vk_user(user_id)
    lines = [
        'НАЙДЕННЫЕ ШКОЛЫ',
        '━━━━━━━━━━━━━━━',
        f'Город: {russian_name(u.city) if u.city else "—"}',
        '',
    ]
    for i, s in enumerate(chunk, start=start + 1):
        lines.append(f'{i}. {s.name}')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━')
    lines.append(f'Страница {page + 1} из {total_pages}')
    lines.append('')
    lines.append('Ответь номером, чтобы выбрать школу.')

    set_pending(
        user_id, 'pick_school',
        items=[{'id': s.id, 'label': s.name} for s in schools],
        page=page, total_pages=total_pages,
    )

    kb = VkKeyboard(one_time=False)
    if page > 0:
        kb.add_button('<', payload={'action': 'pick_school_page', 'page': page - 1},
                      color=VkKeyboardColor.SECONDARY)
    if total_pages > 1:
        kb.add_button(f'{page + 1}/{total_pages}', color=VkKeyboardColor.SECONDARY)
    if page < total_pages - 1:
        kb.add_button('>', payload={'action': 'pick_school_page', 'page': page + 1},
                      color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button('Отмена', color=VkKeyboardColor.NEGATIVE)

    send(vk, user_id, '\n'.join(lines), kb)


# ---------- КЛАСС ----------

def step_input_class(vk, user_id, text):
    klass = parse_class(text)
    if not klass:
        send(
            vk, user_id,
            'Неверный формат класса.\n\n'
            'Введи номер и букву, например: 5А, 11Б, 9В.',
            kb_cancel(),
        )
        return

    u = get_vk_user(user_id)
    u.class_name = klass
    u.save()
    pop_pending(user_id)

    if is_profile_complete(u):
        send(
            vk, user_id,
            'ПРОФИЛЬ УСПЕШНО СОЗДАН!\n'
            '━━━━━━━━━━━━━━━\n\n'
            f'{_profile_summary(u)}\n\n'
            '━━━━━━━━━━━━━━━\n'
            'Теперь можно смотреть расписание.',
            kb_main(),
        )
    else:
        send(
            vk, user_id,
            f'Класс: {klass}\n\n'
            'Что-то пошло не так — заполним профиль заново.',
            kb_main(),
        )
        begin_setup(vk, user_id)


# ==================== ПРОФИЛЬ ====================

def _profile_summary(u):
    region = russian_name(u.region) if u.region else '—'
    city = russian_name(u.city) if u.city else '—'
    school = u.school.name if u.school else '—'
    klass = u.class_name or '—'
    return (
        f'Регион: {region}\n'
        f'Город: {city}\n'
        f'Школа: {school}\n'
        f'Класс: {klass}'
    )


def handle_profile(vk, user_id):
    u = get_vk_user(user_id)
    send(
        vk, user_id,
        'ПРОФИЛЬ\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'{_profile_summary(u)}\n\n'
        '━━━━━━━━━━━━━━━\n'
        'Что хочешь сделать?',
        kb_profile(),
    )


# ==================== ИЗМЕНЕНИЕ ПРОФИЛЯ ====================

def handle_edit_menu(vk, user_id):
    u = get_vk_user(user_id)
    send(
        vk, user_id,
        'ЧТО ИЗМЕНИТЬ?\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'{_profile_summary(u)}\n\n'
        '━━━━━━━━━━━━━━━\n'
        'Введи номер пункта (1–4) или нажми кнопку:',
        kb_edit_what(),
    )
    set_pending(user_id, 'edit_choose')


def start_edit_region(vk, user_id):
    send(
        vk, user_id,
        'ИЗМЕНЕНИЕ РЕГИОНА\n'
        '━━━━━━━━━━━━━━━\n\n'
        'После смены региона нужно будет заново указать город, школу и класс.\n\n'
        'Введи название нового региона (можно часть).',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_region')


def start_edit_city(vk, user_id):
    u = get_vk_user(user_id)
    if not u.region:
        send(vk, user_id, 'Сначала выбери регион.', kb_main())
        return
    send(
        vk, user_id,
        'ИЗМЕНЕНИЕ ГОРОДА\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'Регион: {russian_name(u.region)}\n\n'
        'После смены города нужно будет заново указать школу и класс.\n\n'
        'Введи название нового города (можно часть).',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_city')


def start_edit_school(vk, user_id):
    u = get_vk_user(user_id)
    if not u.city:
        send(vk, user_id, 'Сначала выбери город.', kb_main())
        return
    send(
        vk, user_id,
        'ИЗМЕНЕНИЕ ШКОЛЫ\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'Город: {russian_name(u.city)}\n\n'
        'После смены школы нужно будет заново указать класс.\n\n'
        'Введи название или номер новой школы (можно часть).',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_school')


def start_edit_class(vk, user_id):
    u = get_vk_user(user_id)
    if not u.school:
        send(vk, user_id, 'Сначала выбери школу.', kb_main())
        return
    send(
        vk, user_id,
        'ИЗМЕНЕНИЕ КЛАССА\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'Школа: {u.school.name}\n'
        f'Сейчас: {u.class_name or "—"}\n\n'
        'Введи новый класс, например: 5А, 11Б, 9В.',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_class')


# ---------- Шаги изменения ----------

def step_edit_region(vk, user_id, text):
    matches = search_regions(text, limit=50)
    if not matches:
        send(vk, user_id, 'Регион не найден. Попробуй другое название.', kb_cancel())
        return

    if len(matches) == 1:
        apply_edit_region(vk, user_id, matches[0])
        return

    items = [{'id': r.id, 'label': russian_name(r)} for r in matches]
    _render_options(vk, user_id, 'Выбери регион:', items, 'pick_region_edit')


def apply_edit_region(vk, user_id, region):
    u = get_vk_user(user_id)
    u.region = region
    u.city = None
    u.school = None
    u.class_name = ''
    u.save()
    pop_pending(user_id)

    send(
        vk, user_id,
        f'Регион изменён: {russian_name(region)}\n\n'
        'Теперь укажи город.',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_city')


def step_edit_city(vk, user_id, text):
    u = get_vk_user(user_id)
    if not u.region:
        send(vk, user_id, 'Сначала выбери регион.', kb_main())
        return

    matches = search_cities(text, u.region_id, limit=50)
    if not matches:
        send(
            vk, user_id,
            f'Город не найден в регионе "{russian_name(u.region)}".',
            kb_cancel(),
        )
        return

    if len(matches) == 1:
        apply_edit_city(vk, user_id, matches[0])
        return

    items = [{'id': c.id, 'label': russian_name(c)} for c in matches]
    _render_options(vk, user_id, 'Выбери город:', items, 'pick_city_edit')


def apply_edit_city(vk, user_id, city):
    u = get_vk_user(user_id)
    u.city = city
    u.school = None
    u.class_name = ''
    u.save()
    pop_pending(user_id)

    send(
        vk, user_id,
        f'Город изменён: {russian_name(city)}\n\n'
        'Теперь укажи школу.',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_school')


def step_edit_school(vk, user_id, text):
    u = get_vk_user(user_id)
    if not u.city:
        send(vk, user_id, 'Сначала выбери город.', kb_main())
        return

    matches = search_schools(text, u.city_id, limit=20)
    if not matches:
        send(
            vk, user_id,
            f'Школа не найдена в городе "{russian_name(u.city)}".',
            kb_cancel(),
        )
        return

    if len(matches) == 1:
        apply_edit_school(vk, user_id, matches[0])
        return

    show_school_candidates(vk, user_id, matches)


def apply_edit_school(vk, user_id, school):
    u = get_vk_user(user_id)
    u.school = school
    u.class_name = ''
    u.save()
    pop_pending(user_id)

    send(
        vk, user_id,
        f'Школа изменена: {school.name}\n\n'
        'Теперь укажи класс.',
        kb_cancel(),
    )
    set_pending(user_id, 'edit_class')


def step_edit_class(vk, user_id, text):
    klass = parse_class(text)
    if not klass:
        send(
            vk, user_id,
            'Неверный формат класса.\n\n'
            'Введи номер и букву, например: 5А, 11Б, 9В.',
            kb_cancel(),
        )
        return

    u = get_vk_user(user_id)
    u.class_name = klass
    u.save()
    pop_pending(user_id)

    send(
        vk, user_id,
        f'Класс изменён: {klass}\n\n'
        f'{_profile_summary(u)}',
        kb_main(),
    )


# ==================== СБРОС ====================

def handle_reset_confirm(vk, user_id):
    send(
        vk, user_id,
        'Вы точно хотите удалить аккаунт?\n\n'
        'Все данные профиля будут удалены.',
        kb_confirm_reset(),
    )
    set_pending(user_id, 'confirm_reset')


def do_reset(vk, user_id):
    reset_vk_user(user_id)
    get_vk_user(user_id)
    pop_pending(user_id)
    send(
        vk, user_id,
        'Аккаунт удалён.\n\n'
        'Заполним профиль заново.',
    )
    begin_setup(vk, user_id)


# ==================== РАСПИСАНИЕ ====================

def _load_schedules(school_id):
    return list(
        SavedSchedule.objects
        .filter(user__profile__school_id=school_id)
        .select_related('user__profile')
        .only('id', 'day', 'schedule_data', 'user__profile__school_id')
    )


def _collect_lessons(schedules, day, class_name):
    best = []
    for sched in schedules:
        if sched.day != day:
            continue
        for class_data in sched.schedule_data:
            if (class_data.get('name') or '').upper() != class_name:
                continue
            lessons = class_data.get('lessons') or []
            if len(lessons) > len(best):
                best = lessons
    return best


def _format_lesson(index, lesson, day, now, show_bells, strike_enabled):
    """Форматирует урок.

    show_bells — показывать ли время звонков;
    strike_enabled — можно ли зачёркивать (учитывает настройку и день).
    """
    subject = (lesson.get('subject') or '').strip()
    if not subject or subject == '--|--':
        return None

    time_str = ''
    if show_bells:
        start, end = _lesson_time_for_index(index)
        if start and end:
            time_str = f'({start}–{end}) '

    classrooms = lesson.get('classrooms') or []
    cabs = [c.get('classroom', '').strip() for c in classrooms if c.get('classroom')]
    cab_str = f'  ·  каб. {", ".join(cabs)}' if cabs else ''

    line = f'{index}. {time_str}{subject}{cab_str}'

    if strike_enabled and _is_lesson_past(index, day, now):
        line = strikethrough(line)

    return line


def _format_day_schedule(user, schedules, day):
    lessons = _collect_lessons(schedules, day, user.class_name)
    now = datetime.datetime.now()

    show_bells = bool(getattr(user, 'show_bell_times', True))
    # Зачёркиваем только если настройка включена И день — сегодняшний
    today = _today_day_key()
    strike_enabled = (
        bool(getattr(user, 'strike_past_lessons', True))
        and today == day
    )

    lines = [
        'РАСПИСАНИЕ',
        '━━━━━━━━━━━━━━━',
        f'Школа: {user.school.name}',
        f'Класс: {user.class_name}',
        f'День: {DAY_NAMES[day]}',
    ]
    if today == day:
        lines.append('(сегодня)')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━')
    lines.append('')

    if not lessons:
        lines.append('Уроков нет.')
        return '\n'.join(lines)

    idx = 0
    for lesson in lessons:
        line = _format_lesson(
            idx + 1, lesson, day, now,
            show_bells=show_bells,
            strike_enabled=strike_enabled,
        )
        if line is None:
            continue
        idx += 1
        lines.append(line)

    if idx == 0:
        lines.append('Уроков нет.')

    return '\n'.join(lines)


def handle_schedule_menu(vk, user_id):
    u = get_vk_user(user_id)
    if not is_profile_complete(u):
        send(
            vk, user_id,
            'Профиль не заполнен.\n\n'
            'Нажми "Профиль" → "Изменить", чтобы завершить настройку.',
            kb_main(),
        )
        return

    send(
        vk, user_id,
        'ВЫБЕРИ ДЕНЬ\n'
        '━━━━━━━━━━━━━━━\n\n'
        f'Школа: {u.school.name}\n'
        f'Класс: {u.class_name}',
        kb_days(),
    )


def show_day(vk, user_id, day):
    u = get_vk_user(user_id)
    if not is_profile_complete(u):
        send(vk, user_id, 'Профиль не заполнен.', kb_main())
        return

    schedules = _load_schedules(u.school_id)
    text = _format_day_schedule(u, schedules, day)
    send(vk, user_id, text, kb_back())


# ==================== ВЫБОР ИЗ СПИСКА ====================

def _render_options(vk, user_id, title, items, action_prefix, page=0, next_step=None):
    total = len(items)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    chunk = items[start:end]

    lines = [f'{title}', '━━━━━━━━━━━━━━━', '']
    for i, item in enumerate(chunk, start=start + 1):
        lines.append(f'{i}. {item["label"]}')
    lines.append('')
    lines.append('━━━━━━━━━━━━━━━')
    lines.append(f'Страница {page + 1} из {total_pages}')
    lines.append('')
    lines.append(f'Ответь номером (1–{total}) или листай кнопками.')

    payload_extra = {'items': items, 'page': page, 'total_pages': total_pages}
    if next_step:
        payload_extra['next_step'] = next_step
    set_pending(user_id, action_prefix, **payload_extra)

    has_prev = page > 0
    has_next = page < total_pages - 1

    send(
        vk, user_id,
        '\n'.join(lines),
        kb_paginated(action_prefix, page, total_pages, has_next=has_next, has_prev=has_prev),
    )


# ==================== PAYLOAD ====================

def handle_payload(vk, user_id, payload):
    action = payload.get('action')
    if not action:
        if 'day' in payload:
            show_day(vk, user_id, payload['day'])
            return True
        return False

    if action == 'pick_region_page':
        return handle_pagination(vk, user_id, 'pick_region', payload.get('page', 0))

    if action == 'pick_city_page':
        return handle_pagination(vk, user_id, 'pick_city', payload.get('page', 0))

    if action == 'pick_school_page':
        return handle_pagination(vk, user_id, 'pick_school', payload.get('page', 0))

    if action == 'pick_region_edit_page':
        return handle_pagination(vk, user_id, 'pick_region_edit', payload.get('page', 0))

    if action == 'pick_city_edit_page':
        return handle_pagination(vk, user_id, 'pick_city_edit', payload.get('page', 0))

    if action == 'toggle_bells':
        handle_toggle_bells(vk, user_id)
        return True

    if action == 'toggle_strike':
        handle_toggle_strike(vk, user_id)
        return True

    return False


def handle_pagination(vk, user_id, action, page):
    state = get_pending(user_id)
    if not state or state['action'] != action:
        send(vk, user_id, 'Сессия устарела. Попробуй заново.', kb_main())
        return True

    items = state['payload'].get('items', [])
    next_step = state['payload'].get('next_step')
    titles = {
        'pick_region': 'Выбери регион:',
        'pick_city': 'Выбери город:',
        'pick_school': 'Выбери школу:',
        'pick_region_edit': 'Выбери регион:',
        'pick_city_edit': 'Выбери город:',
    }
    _render_options(vk, user_id, titles.get(action, 'Выбери:'), items, action,
                    page=page, next_step=next_step)
    return True


# ==================== ОБРАБОТКА ВЫБОРА НОМЕРА ====================

def _process_number_choice(vk, user_id, action, num, state):
    items = state['payload'].get('items', [])
    if not (1 <= num <= len(items)):
        send(
            vk, user_id,
            f'Такого номера нет. Введи от 1 до {len(items)}.',
            kb_paginated(action, state['payload'].get('page', 0),
                         max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)),
        )
        return True

    item = items[num - 1]
    obj_id = item['id']

    if action == 'pick_region':
        try:
            region = Region.objects.get(id=obj_id)
        except Region.DoesNotExist:
            send(vk, user_id, 'Регион не найден.', kb_main())
            return True
        pop_pending(user_id)
        apply_region(vk, user_id, region, next_step='city')
        return True

    if action == 'pick_city':
        try:
            city = City.objects.get(id=obj_id)
        except City.DoesNotExist:
            send(vk, user_id, 'Город не найден.', kb_main())
            return True
        pop_pending(user_id)
        apply_city(vk, user_id, city, next_step='school')
        return True

    if action == 'pick_school':
        try:
            school = School.objects.get(id=obj_id)
        except School.DoesNotExist:
            send(vk, user_id, 'Школа не найдена.', kb_main())
            return True
        pop_pending(user_id)
        apply_school(vk, user_id, school)
        return True

    if action == 'pick_region_edit':
        try:
            region = Region.objects.get(id=obj_id)
        except Region.DoesNotExist:
            send(vk, user_id, 'Регион не найден.', kb_main())
            return True
        pop_pending(user_id)
        apply_edit_region(vk, user_id, region)
        return True

    if action == 'pick_city_edit':
        try:
            city = City.objects.get(id=obj_id)
        except City.DoesNotExist:
            send(vk, user_id, 'Город не найден.', kb_main())
            return True
        pop_pending(user_id)
        apply_edit_city(vk, user_id, city)
        return True

    return False


# ==================== УВЕДОМЛЕНИЯ ====================

def notify_loop(vk):
    log.info('Фоновый поток уведомлений запущен')
    while True:
        try:
            close_old_connections()
            _process_pending_changes(vk)
        except Exception as e:
            log.exception('Ошибка в notify_loop: %s', e)
        time.sleep(NOTIFY_INTERVAL)


def _process_pending_changes(vk):
    changes = (
        ScheduleChange.objects
        .filter(notified=False)
        .select_related('school')
        .order_by('created_at')
    )
    if not changes:
        return

    processed_ids = []

    for change in changes:
        subscribers = VkUser.objects.filter(
            school=change.school,
            notifications_enabled=True,
        ).exclude(class_name='')

        if change.class_name:
            subscribers = subscribers.filter(class_name__iexact=change.class_name)

        day_name = change.get_day_display_display()

        kb = VkKeyboard(one_time=False)
        kb.add_button(
            'Посмотреть расписание',
            payload={'day': change.day},
            color=VkKeyboardColor.PRIMARY,
        )
        kb.add_line()
        kb.add_button('В меню', color=VkKeyboardColor.SECONDARY)

        klass_line = f'Класс: {change.class_name}\n' if change.class_name else ''

        text = (
            'ВНИМАНИЕ\n'
            '━━━━━━━━━━━━━━━\n\n'
            'Расписание изменилось!\n'
            f'{klass_line}'
            f'День: {day_name}\n\n'
            'Посмотрите, пожалуйста, актуальное расписание.'
        )

        for user in subscribers:
            try:
                send(vk, user.vk_id, text, kb)
            except Exception as e:
                log.warning('Не удалось отправить уведомление %s: %s', user.vk_id, e)

        processed_ids.append(change.id)

    if processed_ids:
        ScheduleChange.objects.filter(id__in=processed_ids).update(notified=True)
        log.info('Обработано изменений: %d', len(processed_ids))


# ==================== ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ====================

def _on_message(vk, event):
    user_id = event.obj.message['from_id']
    text = (event.obj.message.get('text') or '').strip()
    payload_raw = event.obj.message.get('payload')

    payload = None
    if payload_raw:
        try:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        except (json.JSONDecodeError, TypeError):
            payload = None

    log.info('MSG %s: %r | payload=%s', user_id, text, payload)

    if payload and handle_payload(vk, user_id, payload):
        return

    # --- системные команды ---
    if text in ('/start', 'start', 'Начать', 'Главное меню', 'Меню'):
        pop_pending(user_id)
        handle_start(vk, user_id)
        return

    if text in ('В меню', 'Назад'):
        pop_pending(user_id)
        send(vk, user_id, 'Главное меню:', kb_main())
        return

    if text == 'Отмена':
        pop_pending(user_id)
        send(vk, user_id, 'Отменено. Главное меню:', kb_main())
        return

    # --- главное меню ---
    if text == 'Расписание':
        pop_pending(user_id)
        handle_schedule_menu(vk, user_id)
        return

    if text == 'Настройки':
        pop_pending(user_id)
        handle_settings(vk, user_id)
        return

    if text == 'Профиль':
        pop_pending(user_id)
        handle_profile(vk, user_id)
        return

    if text == 'Пригласить друга':
        pop_pending(user_id)
        handle_invite(vk, user_id)
        return

    # --- профиль ---
    if text == 'Изменить':
        pop_pending(user_id)
        handle_edit_menu(vk, user_id)
        return

    if text == 'Сбросить':
        pop_pending(user_id)
        handle_reset_confirm(vk, user_id)
        return

    if text == 'Да':
        state = get_pending(user_id)
        if state and state['action'] == 'confirm_reset':
            do_reset(vk, user_id)
            return
        send(vk, user_id, 'Нечего подтверждать.', kb_main())
        return

    if text == 'Нет':
        state = get_pending(user_id)
        if state and state['action'] == 'confirm_reset':
            pop_pending(user_id)
            send(vk, user_id, 'Отменено. Главное меню:', kb_main())
            return
        send(vk, user_id, 'Отменено.', kb_main())
        return

    # --- меню изменения: выбор номером ---
    state = get_pending(user_id)
    if state and state['action'] == 'edit_choose':
        if text in ('1', '1. Регион', 'Регион'):
            pop_pending(user_id)
            start_edit_region(vk, user_id)
            return
        if text in ('2', '2. Город', 'Город'):
            pop_pending(user_id)
            start_edit_city(vk, user_id)
            return
        if text in ('3', '3. Школа', 'Школа'):
            pop_pending(user_id)
            start_edit_school(vk, user_id)
            return
        if text in ('4', '4. Класс', 'Класс'):
            pop_pending(user_id)
            start_edit_class(vk, user_id)
            return
        send(
            vk, user_id,
            'Введи номер от 1 до 4 или нажми кнопку.',
            kb_edit_what(),
        )
        return

    # --- мастер настройки и изменения: текстовые шаги ---
    if state:
        action = state['action']

        if action == 'input_region':
            step_input_region(vk, user_id, text)
            return
        if action == 'input_city':
            step_input_city(vk, user_id, text)
            return
        if action == 'input_school':
            step_input_school(vk, user_id, text)
            return
        if action == 'input_class':
            step_input_class(vk, user_id, text)
            return

        if action == 'edit_region':
            step_edit_region(vk, user_id, text)
            return
        if action == 'edit_city':
            step_edit_city(vk, user_id, text)
            return
        if action == 'edit_school':
            step_edit_school(vk, user_id, text)
            return
        if action == 'edit_class':
            step_edit_class(vk, user_id, text)
            return

        if action in ('pick_region', 'pick_city', 'pick_school',
                      'pick_region_edit', 'pick_city_edit'):
            try:
                num = int(text)
            except ValueError:
                send(vk, user_id, 'Введи номер из списка.', kb_main())
                return
            if _process_number_choice(vk, user_id, action, num, state):
                return
            return

        if action == 'confirm_reset':
            send(vk, user_id, 'Нажми "Да" или "Нет".', kb_confirm_reset())
            return

    # --- если ничего не подошло ---
    u = get_vk_user(user_id)
    if not is_profile_complete(u):
        send(
            vk, user_id,
            'Профиль не заполнен. Заполним заново.',
        )
        begin_setup(vk, user_id)
        return

    send(
        vk, user_id,
        'Не понимаю команду.\n\nВыбери действие на клавиатуре:',
        kb_main(),
    )


# ==================== ГЛАВНЫЙ ЦИКЛ ====================

def main():
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)

    notifier = threading.Thread(target=notify_loop, args=(vk,), daemon=True)
    notifier.start()

    log.info('Бот запущен. Группа: %s', GROUP_ID)

    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue
        try:
            _on_message(vk, event)
        except Exception as e:
            log.exception('Ошибка обработки: %s', e)
            try:
                send(vk, event.obj.message['from_id'], 'Произошла ошибка. Попробуй ещё раз.')
            except Exception:
                pass


if __name__ == '__main__':
    main()