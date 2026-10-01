# schedule_app/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.conf import settings

from .models import (
    Profile, SavedSchedule, EmailVerification,
    School, VkUser, ScheduleChange,
    Subject, Classroom,
)


# ==================== INLINE ПРОФИЛЯ В USER ====================

class ProfileInline(admin.StackedInline):
    """Профиль пользователя в админке (встроенный в User)"""
    model = Profile
    can_delete = False
    verbose_name_plural = 'Профиль'
    fields = ('full_name', 'is_verified')
    readonly_fields = ('full_name',)


class CustomUserAdmin(UserAdmin):
    """Расширенная админка для пользователя с профилем"""
    inlines = [ProfileInline]
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'is_staff', 'is_active', 'get_full_name', 'is_verified',
    )
    list_filter = ('is_staff', 'is_active', 'profile__is_verified')
    search_fields = (
        'username', 'email', 'first_name', 'last_name', 'profile__full_name',
    )

    def get_full_name(self, obj):
        return obj.profile.full_name if hasattr(obj, 'profile') else ''
    get_full_name.short_description = 'ФИО'
    get_full_name.admin_order_field = 'profile__full_name'

    def is_verified(self, obj):
        return obj.profile.is_verified if hasattr(obj, 'profile') else False
    is_verified.boolean = True
    is_verified.short_description = 'Email подтверждён'
    is_verified.admin_order_field = 'profile__is_verified'

    fieldsets = UserAdmin.fieldsets + (
        ('Дополнительная информация', {'fields': ()}),
    )


# ==================== ШКОЛЫ ====================

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    """Админка для школ."""
    list_display = (
        'id', 'name', 'city', 'address', 'phone',
        'main_teacher', 'get_main_teacher_name',
    )
    list_filter = ('city__region', 'city')
    search_fields = ('name', 'address', 'city__name')
    raw_id_fields = ('city',)
    autocomplete_fields = ()

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'city', 'address', 'phone'),
        }),
        ('Управление', {
            'fields': ('main_teacher',),
            'description': 'Главный учитель — тот, кто может загружать расписание для этой школы.',
        }),
    )

    def get_main_teacher_name(self, obj):
        return obj.get_main_teacher_name() if obj.has_main_teacher() else '—'
    get_main_teacher_name.short_description = 'Главный учитель (ФИО)'


# ==================== ПРОФИЛЬ ====================

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Отдельная админка для профилей"""
    list_display = (
        'user', 'full_name', 'school', 'position',
        'is_verified', 'get_email',
    )
    list_filter = ('is_verified', 'school__city__region', 'school')
    search_fields = ('user__username', 'user__email', 'full_name')
    list_editable = ('is_verified',)
    raw_id_fields = ('user', 'region', 'city', 'school')

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'


# ==================== СОХРАНЁННЫЕ РАСПИСАНИЯ ====================

@admin.register(SavedSchedule)
class SavedScheduleAdmin(admin.ModelAdmin):
    """Админка для сохранённых расписаний"""
    list_display = ('id', 'user', 'session', 'day', 'created_at', 'updated_at')
    list_filter = ('day', 'created_at')
    search_fields = ('user__username', 'session__session_key')
    readonly_fields = ('schedule_data',)
    raw_id_fields = ('user', 'session')
    date_hierarchy = 'created_at'


# ==================== ПОДТВЕРЖДЕНИЕ EMAIL ====================

@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    """Админка для кодов подтверждения email"""
    list_display = (
        'email', 'code', 'created_at', 'is_used', 'is_expired_display',
    )
    list_filter = ('is_used', 'created_at')
    search_fields = ('email', 'code')
    readonly_fields = ('email', 'code', 'user_data', 'created_at')

    def is_expired_display(self, obj):
        return obj.is_expired(settings.VERIFICATION_CODE_TIMEOUT)
    is_expired_display.boolean = True
    is_expired_display.short_description = 'Истёк'


# ==================== УЧЕНИКИ (VK) ====================

@admin.register(VkUser)
class VkUserAdmin(admin.ModelAdmin):
    """Админка для учеников VK-бота."""
    list_display = (
        'vk_id', 'school', 'class_name',
        'notifications_enabled', 'created_at',
    )
    list_filter = ('notifications_enabled', 'school')
    search_fields = ('vk_id', 'class_name', 'school__name')
    raw_id_fields = ('region', 'city', 'school')
    readonly_fields = ('created_at', 'updated_at')


# ==================== ИЗМЕНЕНИЯ РАСПИСАНИЯ ====================

@admin.register(ScheduleChange)
class ScheduleChangeAdmin(admin.ModelAdmin):
    """Админка для изменений расписания (для уведомлений)."""
    list_display = (
        'id', 'school', 'class_name', 'day',
        'change_type', 'notified', 'created_at',
    )
    list_filter = ('notified', 'change_type', 'day', 'school')
    search_fields = ('school__name', 'class_name')
    raw_id_fields = ('school',)
    readonly_fields = ('created_at',)

    actions = ['mark_as_notified', 'mark_as_unnotified']

    @admin.action(description='Отметить как отправленные')
    def mark_as_notified(self, request, queryset):
        updated = queryset.update(notified=True)
        self.message_user(request, f'Отмечено: {updated}')

    @admin.action(description='Отметить как неотправленные')
    def mark_as_unnotified(self, request, queryset):
        updated = queryset.update(notified=False)
        self.message_user(request, f'Отмечено: {updated}')

# ==================== ПРЕДМЕТЫ ====================

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'short_name')
    list_editable = ('short_name', 'is_active')
    ordering = ('name',)
    


# ==================== КАБИНЕТЫ ====================

@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('number', 'room_type', 'building', 'is_active', 'created_at')
    list_filter = ('is_active', 'room_type', 'building')
    search_fields = ('number', 'building')
    list_editable = ('room_type', 'building', 'is_active')
    ordering = ('number',)
    
# ==================== USER С ПРОФИЛЕМ ====================

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)