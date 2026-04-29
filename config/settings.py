from pathlib import Path
from decouple import config

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Security settings
SECRET_KEY = config("SECRET_KEY")

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="").split(",")

SITE_URL = config("SITE_URL", default="http://localhost:8000")

# Applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "crispy_forms",
    "crispy_bootstrap5",

    "accounts",
    "appointments",
    "notifications",
]

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database (SQLite)
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": config("DB_NAME", default=BASE_DIR / "db.sqlite3"),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default=""),
        "PORT": config("DB_PORT", default=""),
    }
}

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Localization
LANGUAGE_CODE = "pt-pt"
TIME_ZONE = "Europe/Lisbon"

USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Crispy forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Auth redirects
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

# Email configuration
# Email configuration
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

EMAIL_HOST = config(
    "EMAIL_HOST",
    default="smtp.hostinger.com",
)

EMAIL_PORT = config(
    "EMAIL_PORT",
    default=465,
    cast=int,
)

EMAIL_USE_SSL = config(
    "EMAIL_USE_SSL",
    default=True,
    cast=bool,
)

EMAIL_USE_TLS = config(
    "EMAIL_USE_TLS",
    default=False,
    cast=bool,
)

EMAIL_HOST_USER = config(
    "EMAIL_HOST_USER",
    default="",
)

EMAIL_HOST_PASSWORD = config(
    "EMAIL_HOST_PASSWORD",
    default="",
)

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default=EMAIL_HOST_USER,
)

SITE_URL = config(
    "SITE_URL",
    default="http://localhost:8000",
)