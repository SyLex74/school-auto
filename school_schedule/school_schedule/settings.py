"""
Django settings for school_schedule project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


# ==================== ХЕЛПЕРЫ ДЛЯ .env ====================

def env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def env_list(key: str, default: str = '') -> list:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


def env_str(key: str, default: str = '') -> str:
    return os.environ.get(key, default)


# ==================== БЕЗОПАСНОСТЬ ====================

SECRET_KEY = os.environ['SECRET_KEY']

# Ротация без разлогина: пока есть старые сессии — держим старый ключ здесь,
# затем удаляем переменную и перезапускаем контейнеры.
_old_keys = env_list('SECRET_KEY_FALLBACKS', '')
SECRET_KEY_FALLBACKS = _old_keys if _old_keys else []

DEBUG = env_bool('DEBUG', False)

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '127.0.0.1,localhost')

CSRF_TRUSTED_ORIGINS = env_list(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost,http://127.0.0.1',
)

if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# ==================== ПРИЛОЖЕНИЯ ====================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'schedule_app',
    'captcha',
    'cities_light',
]

CITIES_LIGHT_INCLUDE_COUNTRIES = ['RU']
CITIES_LIGHT_TRANSLATION_LANGUAGES = ['ru']
CITIES_LIGHT_DATA_DIR = BASE_DIR / 'data' / 'cities_light'


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'school_schedule.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'school_schedule.wsgi.application'


# ==================== БАЗА ДАННЫХ (PostgreSQL) ====================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env_str('POSTGRES_DB', 'school_schedule'),
        'USER': env_str('POSTGRES_USER', 'school_user'),
        'PASSWORD': env_str('POSTGRES_PASSWORD', ''),
        'HOST': env_str('POSTGRES_HOST', 'db'),
        'PORT': env_int('POSTGRES_PORT', 5432),
        'CONN_MAX_AGE': 60,
    }
}


# ==================== АУТЕНТИФИКАЦИЯ ====================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ==================== КАСТОМНЫЕ СТРАНИЦЫ ОШИБОК ====================

handler404 = 'schedule_app.views.custom_404'
handler500 = 'schedule_app.views.custom_500'
handler403 = 'schedule_app.views.custom_403'


# ==================== ЛОКАЛИЗАЦИЯ ====================

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True


# ==================== СТАТИКА ====================

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SESSION_ENGINE = 'django.contrib.sessions.backends.db'


# ==================== EMAIL ====================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env_str('EMAIL_HOST', 'smtp.mail.ru')
EMAIL_PORT = env_int('EMAIL_PORT', 465)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', True)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_HOST_USER = os.environ['EMAIL_HOST_USER']
EMAIL_HOST_PASSWORD = os.environ['EMAIL_HOST_PASSWORD']
DEFAULT_FROM_EMAIL = env_str('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

VERIFICATION_CODE_TIMEOUT = env_int('VERIFICATION_CODE_TIMEOUT', 600)


# ==================== VK BOT ====================

VK_TOKEN = os.environ['VK_TOKEN']
VK_GROUP_ID = env_int('VK_GROUP_ID', 0)
SITE_URL = env_str('SITE_URL', 'http://127.0.0.1:8000')
COMMUNITY_LINK = env_str('COMMUNITY_LINK', '')

BOT_API_KEY = os.environ['BOT_API_KEY']