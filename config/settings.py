from pathlib import Path

from decouple import config


BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name: str, default: str = "") -> list[str]:
    """
    Reads comma-separated values from .env.

    Example:
    ALLOWED_HOSTS=localhost,127.0.0.1,example.com
    """
    raw_value = config(name, default=default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


# =============================================================================
# Core
# =============================================================================

SECRET_KEY = config("SECRET_KEY")

DEBUG = config("DEBUG", default=False, cast=bool)

ENVIRONMENT = config("ENVIRONMENT", default="development")

SITE_URL = config("SITE_URL", default="http://localhost:8000").rstrip("/")

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1" if DEBUG else "",
)

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", default="")

INTERNAL_IPS = env_list("INTERNAL_IPS", default="127.0.0.1") if DEBUG else []


# =============================================================================
# Applications
# =============================================================================

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


# =============================================================================
# Middleware
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =============================================================================
# URLs / WSGI / ASGI
# =============================================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"


# =============================================================================
# Templates
# =============================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
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


# =============================================================================
# Database
# =============================================================================

DB_ENGINE = config("DB_ENGINE", default="django.db.backends.sqlite3")
DB_NAME = config("DB_NAME", default="db.sqlite3")
DB_CONN_MAX_AGE = config("DB_CONN_MAX_AGE", default=60 if not DEBUG else 0, cast=int)
DB_CONN_HEALTH_CHECKS = config(
    "DB_CONN_HEALTH_CHECKS",
    default=not DEBUG,
    cast=bool,
)

if DB_ENGINE == "django.db.backends.sqlite3":
    sqlite_name = Path(DB_NAME)

    if not sqlite_name.is_absolute():
        sqlite_name = BASE_DIR / sqlite_name

    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": sqlite_name,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": DB_NAME,
            "USER": config("DB_USER", default=""),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default=""),
            "PORT": config("DB_PORT", default=""),
            "CONN_MAX_AGE": DB_CONN_MAX_AGE,
            "CONN_HEALTH_CHECKS": DB_CONN_HEALTH_CHECKS,
        }
    }

    if DB_ENGINE == "django.db.backends.postgresql" and config(
        "DB_SSL_REQUIRE",
        default=False,
        cast=bool,
    ):
        DATABASES["default"]["OPTIONS"] = {
            "sslmode": "require",
        }


# =============================================================================
# Custom user model
# =============================================================================

AUTH_USER_MODEL = "accounts.User"


# =============================================================================
# Password validation
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": config("PASSWORD_MIN_LENGTH", default=8, cast=int),
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# =============================================================================
# Localization
# =============================================================================

LANGUAGE_CODE = config("LANGUAGE_CODE", default="pt-pt")

TIME_ZONE = config("TIME_ZONE", default="Europe/Lisbon")

USE_I18N = True

USE_TZ = True


# =============================================================================
# Static and media files
# =============================================================================

STATIC_URL = config("STATIC_URL", default="/static/")

STATIC_ROOT = BASE_DIR / config("STATIC_ROOT", default="staticfiles")

STATICFILES_DIRS = [
    BASE_DIR / "static",
] if (BASE_DIR / "static").exists() else []

MEDIA_URL = config("MEDIA_URL", default="/media/")

MEDIA_ROOT = BASE_DIR / config("MEDIA_ROOT", default="media")


# =============================================================================
# Default primary key
# =============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =============================================================================
# Crispy Forms
# =============================================================================

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

CRISPY_TEMPLATE_PACK = "bootstrap5"


# =============================================================================
# Authentication redirects
# =============================================================================

LOGIN_URL = "accounts:login"

LOGIN_REDIRECT_URL = "dashboard"

LOGOUT_REDIRECT_URL = "home"


# =============================================================================
# Security
# =============================================================================

SECURE_SSL_REDIRECT = config(
    "SECURE_SSL_REDIRECT",
    default=not DEBUG,
    cast=bool,
)

# Enable only if Django is behind a trusted reverse proxy that sets:
# X-Forwarded-Proto: https
if config("SECURE_PROXY_SSL_HEADER", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

USE_X_FORWARDED_HOST = config(
    "USE_X_FORWARDED_HOST",
    default=False,
    cast=bool,
)

SESSION_COOKIE_SECURE = config(
    "SESSION_COOKIE_SECURE",
    default=not DEBUG,
    cast=bool,
)

CSRF_COOKIE_SECURE = config(
    "CSRF_COOKIE_SECURE",
    default=not DEBUG,
    cast=bool,
)

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = config(
    "CSRF_COOKIE_HTTPONLY",
    default=False,
    cast=bool,
)

SESSION_COOKIE_SAMESITE = config(
    "SESSION_COOKIE_SAMESITE",
    default="Lax",
)

CSRF_COOKIE_SAMESITE = config(
    "CSRF_COOKIE_SAMESITE",
    default="Lax",
)

SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS",
    default=0 if DEBUG else 31536000,
    cast=int,
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=not DEBUG,
    cast=bool,
)

SECURE_HSTS_PRELOAD = config(
    "SECURE_HSTS_PRELOAD",
    default=False,
    cast=bool,
)

SECURE_CONTENT_TYPE_NOSNIFF = True

SECURE_REFERRER_POLICY = config(
    "SECURE_REFERRER_POLICY",
    default="same-origin",
)

X_FRAME_OPTIONS = config(
    "X_FRAME_OPTIONS",
    default="DENY",
)


# =============================================================================
# Email
# =============================================================================

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

EMAIL_HOST = config("EMAIL_HOST", default="")

EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)

EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)

EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ValueError("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be True.")

EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")

EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default=EMAIL_HOST_USER or "webmaster@localhost",
)

SERVER_EMAIL = config(
    "SERVER_EMAIL",
    default=DEFAULT_FROM_EMAIL,
)

EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=30, cast=int)


# =============================================================================
# Logging
# =============================================================================

LOG_LEVEL = config("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
        "verbose": {
            "format": (
                "[{asctime}] {levelname} "
                "{name} {module}.{funcName}:{lineno} - {message}"
            ),
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "accounts": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "appointments": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "notifications": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}