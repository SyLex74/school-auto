"""Модели приложения: школы, профили, расписания, справочники."""

import random
import string
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone


# ─────────────────────────────────────────────────────────────
# Общие константы
# ─────────────────────────────────────────────────────────────

DAY_CHOICES = [
    ('monday', 'Понедельник'),
    ('tuesday', 'Вторник'),
    ('wednesday', 'Среда'),
    ('thursday', 'Четверг'),
    ('friday', 'Пятница'),
    ('saturday', 'Суббота'),
]

EMAIL_CODE_TTL_SECONDS = 600  # 10 минут


# ─────────────────────────────────────────────────────────────
# Школы и профили
# ─────────────────────────────────────────────────────────────

class School(models.Model):
    """Учебное заведение с привязкой к городу и главному учителю."""

    name = models.CharField(max_length=200, verbose_name='Название школы')
    city = models.ForeignKey(
        'cities_light.City',
        on_delete=models.CASCADE,
        related_name='schools',
        verbose_name='Город',
    )
    address = models.CharField(max_length=255, blank=True, verbose_name='Адрес')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    main_teacher = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='main_teacher_school',
        verbose_name='Главный учитель',
    )

    class Meta:
        verbose_name = 'Школа'
        verbose_name_plural = 'Школы'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.city.name})'

    @property
    def is_main_teacher_assigned(self) -> bool:
        """Назначен ли главный учитель."""
        return self.main_teacher_id is not None

    def get_main_teacher_name(self) -> str:
        """Человекочитаемое имя главного учителя или строка-заглушка."""
        if not self.main_teacher:
            return 'Не назначен'

        profile = getattr(self.main_teacher, 'profile', None)
        if profile and profile.full_name:
            return profile.full_name

        return self.main_teacher.username


class Profile(models.Model):
    """Расширение стандартной модели User."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Пользователь',
    )
    full_name = models.CharField(
        max_length=150,
        verbose_name='ФИО',
        help_text='Полное имя пользователя',
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name='Email подтверждён',
    )

    region = models.ForeignKey(
        'cities_light.Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Регион',
    )
    city = models.ForeignKey(
        'cities_light.City',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Город',
    )
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teachers',
        verbose_name='Школа',
    )
    position = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Должность',
    )
    registration_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата регистрации',
    )

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'

    def __str__(self):
        return self.full_name or self.user.username

    def is_main_teacher(self) -> bool:
        """Является ли пользователь главным учителем своей школы."""
        return bool(self.school and self.school.main_teacher_id == self.user_id)


# ─────────────────────────────────────────────────────────────
# Подтверждение email
# ─────────────────────────────────────────────────────────────

class EmailVerification(models.Model):
    """Одноразовый код подтверждения email при регистрации."""

    email = models.EmailField(verbose_name='Email')
    code = models.CharField(max_length=6, verbose_name='Код подтверждения')
    user_data = models.JSONField(default=dict, verbose_name='Данные пользователя')
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False, verbose_name='Использован')

    class Meta:
        verbose_name = 'Подтверждение email'
        verbose_name_plural = 'Подтверждения email'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} — {self.code}'

    @staticmethod
    def generate_code() -> str:
        """Шестизначный цифровой код."""
        return ''.join(random.choices(string.digits, k=6))

    def is_expired(self, timeout_seconds: int = EMAIL_CODE_TTL_SECONDS) -> bool:
        """Истёк ли срок действия кода."""
        return timezone.now() > self.created_at + timedelta(seconds=timeout_seconds)


# ─────────────────────────────────────────────────────────────
# Сохранённые расписания
# ─────────────────────────────────────────────────────────────

class SavedSchedule(models.Model):
    """Сохранённое расписание на день для пользователя или анонимной сессии."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Пользователь',
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name='Сессия',
    )
    day = models.CharField(max_length=20, choices=DAY_CHOICES, verbose_name='День недели')
    schedule_data = models.JSONField(verbose_name='Данные расписания')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Сохранённое расписание'
        verbose_name_plural = 'Сохранённые расписания'
        ordering = ['-updated_at']

    def __str__(self):
        owner = self.user or 'Аноним'
        return f'{self.get_day_display()} — {owner}'


# ─────────────────────────────────────────────────────────────
# Сигналы
# ─────────────────────────────────────────────────────────────

@receiver(pre_save, sender=User)
def sync_profile_full_name(sender, instance: User, **kwargs) -> None:
    """Синхронизирует Profile.full_name при изменении имени/фамилии User."""
    if not instance.pk:
        return

    try:
        old = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return

    name_changed = (
        old.first_name != instance.first_name
        or old.last_name != instance.last_name
    )
    if not name_changed:
        return

    full_name = f'{instance.first_name} {instance.last_name}'.strip()
    profile = getattr(instance, 'profile', None)
    if profile:
        profile.full_name = full_name
        profile.save(update_fields=['full_name'])


# ─────────────────────────────────────────────────────────────
# VK-ученики
# ─────────────────────────────────────────────────────────────

class VkUser(models.Model):
    """Профиль ученика в VK-боте."""

    vk_id = models.BigIntegerField(unique=True, verbose_name='VK ID')
    region = models.ForeignKey(
        'cities_light.Region',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Регион',
    )
    city = models.ForeignKey(
        'cities_light.City',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Город',
    )
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Школа',
    )
    class_name = models.CharField(max_length=10, blank=True, verbose_name='Класс')

    notifications_enabled = models.BooleanField(
        default=True,
        verbose_name='Уведомления включены',
    )
    show_bell_times = models.BooleanField(
        default=True,
        verbose_name='Показывать расписание звонков',
    )
    strike_past_lessons = models.BooleanField(
        default=True,
        verbose_name='Зачёркивать прошедшие уроки',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ученик (VK)'
        verbose_name_plural = 'Ученики (VK)'

    def __str__(self):
        school_name = self.school.name if self.school else '—'
        return f'VK {self.vk_id}: {school_name} {self.class_name}'.strip()


# ─────────────────────────────────────────────────────────────
# Изменения расписания (для рассылки)
# ─────────────────────────────────────────────────────────────

class ScheduleChange(models.Model):
    """Запись об изменении расписания для последующей рассылки уведомлений.

    Если `class_name` пуст — изменение касается всех классов школы;
    иначе — только учеников указанного класса.
    """

    CHANGE_CREATED = 'created'
    CHANGE_UPDATED = 'updated'
    CHANGE_DELETED = 'deleted'
    CHANGE_TYPES = [
        (CHANGE_CREATED, 'Добавлено'),
        (CHANGE_UPDATED, 'Изменено'),
        (CHANGE_DELETED, 'Удалено'),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='changes',
        verbose_name='Школа',
    )
    class_name = models.CharField(
        max_length=10,
        blank=True,
        default='',
        verbose_name='Класс',
        help_text='Пусто — все классы школы',
    )
    day = models.CharField(max_length=20, choices=DAY_CHOICES, verbose_name='День недели')
    change_type = models.CharField(
        max_length=20,
        choices=CHANGE_TYPES,
        default=CHANGE_UPDATED,
        verbose_name='Тип изменения',
    )
    notified = models.BooleanField(default=False, verbose_name='Уведомление отправлено')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Изменение расписания'
        verbose_name_plural = 'Изменения расписания'
        ordering = ['-created_at']

    def __str__(self):
        klass = f' [{self.class_name}]' if self.class_name else ''
        return f'{self.school.name}{klass} — {self.get_day_display()} ({self.get_change_type_display()})'


# ─────────────────────────────────────────────────────────────
# Справочники
# ─────────────────────────────────────────────────────────────

class Subject(models.Model):
    """Справочник учебных предметов."""

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Название предмета',
    )
    short_name = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Сокращение',
        help_text='Например: МАТЕМ, РУСС ЯЗ, ФИЗ-РА',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Предмет'
        verbose_name_plural = 'Предметы'
        ordering = ['name']

    def __str__(self):
        return self.short_name or self.name


class Classroom(models.Model):
    """Справочник кабинетов."""

    ROOM_REGULAR = ''
    ROOM_PRACTICE = 'п'
    ROOM_EXAM = 'э'
    ROOM_BASIC = 'б'
    ROOM_GYM = 'спорт'
    ROOM_POOL = 'бассейн'
    ROOM_TYPES = [
        (ROOM_REGULAR, 'Обычный'),
        (ROOM_PRACTICE, 'Практика'),
        (ROOM_EXAM, 'Экзамен'),
        (ROOM_BASIC, 'Базовый'),
        (ROOM_GYM, 'Спортзал'),
        (ROOM_POOL, 'Бассейн'),
    ]

    number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Номер/название кабинета',
        help_text='Например: 12, 24, Спортзал, Бассейн',
    )
    room_type = models.CharField(
        max_length=20,
        choices=ROOM_TYPES,
        blank=True,
        default=ROOM_REGULAR,
        verbose_name='Тип кабинета',
    )
    building = models.CharField(max_length=100, blank=True, verbose_name='Корпус/здание')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Кабинет'
        verbose_name_plural = 'Кабинеты'
        ordering = ['number']

    def __str__(self):
        if self.room_type:
            return f'{self.number} ({self.get_room_type_display()})'
        return self.number