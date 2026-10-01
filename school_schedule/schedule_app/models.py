from django.db import models
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
import random
import string


class School(models.Model):
    """Модель школы."""
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

    def has_main_teacher(self):
        return self.main_teacher is not None

    def get_main_teacher_name(self):
        if self.main_teacher:
            if hasattr(self.main_teacher, 'profile') and self.main_teacher.profile.full_name:
                return self.main_teacher.profile.full_name
            return self.main_teacher.username
        return 'Не назначен'


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

    def is_main_teacher(self):
        return bool(self.school and self.school.main_teacher == self.user)


class EmailVerification(models.Model):
    """Коды подтверждения email."""
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
        return f'{self.email} - {self.code}'

    @staticmethod
    def generate_code():
        return ''.join(random.choices(string.digits, k=6))

    def is_expired(self, timeout_seconds=600):
        from django.utils import timezone
        from datetime import timedelta
        expiration_time = self.created_at + timedelta(seconds=timeout_seconds)
        return timezone.now() > expiration_time


class SavedSchedule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, null=True, blank=True)
    day = models.CharField(max_length=20, choices=[
        ('monday', 'Понедельник'),
        ('tuesday', 'Вторник'),
        ('wednesday', 'Среда'),
        ('thursday', 'Четверг'),
        ('friday', 'Пятница'),
        ('saturday', 'Суббота'),
    ])
    schedule_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Сохранённое расписание'
        verbose_name_plural = 'Сохранённые расписания'

    def __str__(self):
        return f"{self.get_day_display()} - {self.user or 'Аноним'}"

    def get_day_display(self):
        return dict([
            ('monday', 'Понедельник'),
            ('tuesday', 'Вторник'),
            ('wednesday', 'Среда'),
            ('thursday', 'Четверг'),
            ('friday', 'Пятница'),
            ('saturday', 'Суббота'),
        ]).get(self.day, self.day)


from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User)
def update_profile_full_name(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = User.objects.get(pk=instance.pk)
            if old.first_name != instance.first_name or old.last_name != instance.last_name:
                full_name = f'{instance.first_name} {instance.last_name}'.strip()
                if hasattr(instance, 'profile'):
                    instance.profile.full_name = full_name
                    instance.profile.save()
        except User.DoesNotExist:
            pass


class VkUser(models.Model):
    """Профиль ученика в VK-боте."""
    vk_id = models.BigIntegerField(unique=True, verbose_name='VK ID')
    region = models.ForeignKey(
        'cities_light.Region',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Регион',
    )
    city = models.ForeignKey(
        'cities_light.City',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Город',
    )
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Школа',
    )
    class_name = models.CharField(
        max_length=10, blank=True, verbose_name='Класс',
    )
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


class ScheduleChange(models.Model):
    """Запись об изменении расписания для рассылки уведомлений.

    Если class_name пуст — изменение касается всех классов школы.
    Если class_name заполнен — уведомление уйдёт только ученикам этого класса.
    """
    CHANGE_TYPES = [
        ('created', 'Добавлено'),
        ('updated', 'Изменено'),
        ('deleted', 'Удалено'),
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
    day = models.CharField(max_length=20, verbose_name='День недели')
    change_type = models.CharField(
        max_length=20,
        choices=CHANGE_TYPES,
        default='updated',
        verbose_name='Тип изменения',
    )
    notified = models.BooleanField(
        default=False,
        verbose_name='Уведомление отправлено',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Изменение расписания'
        verbose_name_plural = 'Изменения расписания'
        ordering = ['-created_at']

    def __str__(self):
        klass = f' [{self.class_name}]' if self.class_name else ''
        return f'{self.school.name}{klass} — {self.get_day_display_display()} ({self.change_type})'

    def get_day_display_display(self):
        return dict([
            ('monday', 'Понедельник'),
            ('tuesday', 'Вторник'),
            ('wednesday', 'Среда'),
            ('thursday', 'Четверг'),
            ('friday', 'Пятница'),
            ('saturday', 'Суббота'),
        ]).get(self.day, self.day)


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
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Предмет'
        verbose_name_plural = 'Предметы'
        ordering = ['name']

    def __str__(self):
        return self.short_name or self.name


class Classroom(models.Model):
    """Справочник кабинетов."""
    ROOM_TYPES = [
        ('', 'Обычный'),
        ('п', 'Практика'),
        ('э', 'Экзамен'),
        ('б', 'Базовый'),
        ('спорт', 'Спортзал'),
        ('бассейн', 'Бассейн'),
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
        default='',
        verbose_name='Тип кабинета',
    )
    building = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Корпус/здание',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Кабинет'
        verbose_name_plural = 'Кабинеты'
        ordering = ['number']

    def __str__(self):
        if self.room_type:
            return f'{self.number} ({self.get_room_type_display()})'
        return self.number