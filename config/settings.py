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
# SEO / public search configuration
# =============================================================================

SEO_SITE_NAME = config("SEO_SITE_NAME", default="Priscila Arantes PA")

SEO_DEFAULT_TITLE = config(
    "SEO_DEFAULT_TITLE",
    default="Priscila Arantes PA | Podologia, estética e enfermagem em Coimbra",
)

SEO_DEFAULT_DESCRIPTION = config(
    "SEO_DEFAULT_DESCRIPTION",
    default=(
        "Atendimento profissional em podologia, manicure, pedicure e enfermagem "
        "em Coimbra. Consulte serviços e marque o seu horário online."
    ),
)

SEO_DEFAULT_KEYWORDS = config(
    "SEO_DEFAULT_KEYWORDS",
    default=(
        "podologia Coimbra, manicure Coimbra, pedicure Coimbra, enfermagem Coimbra, "
        "tratamento pés diabéticos, unha em gel, troca de penso"
    ),
)

SEO_DEFAULT_IMAGE_PATH = config(
    "SEO_DEFAULT_IMAGE_PATH",
    default="/static/img/logo.png",
)

SEO_LOCALE = config("SEO_LOCALE", default="pt_PT")

SEO_THEME_COLOR = config("SEO_THEME_COLOR", default="#a8755f")

SEO_ROBOTS_DEFAULT = config("SEO_ROBOTS_DEFAULT", default="index,follow")

SEO_WHATSAPP_NUMBER = config("SEO_WHATSAPP_NUMBER", default="+351938594367")

SEO_BUSINESS_EMAIL = config("SEO_BUSINESS_EMAIL", default="atendimento@priarantes.com")

SEO_BUSINESS_STREET_ADDRESS = config(
    "SEO_BUSINESS_STREET_ADDRESS",
    default="R. Vale de São Miguel 5",
)

SEO_BUSINESS_LOCALITY = config("SEO_BUSINESS_LOCALITY", default="Coimbra")

SEO_BUSINESS_POSTAL_CODE = config("SEO_BUSINESS_POSTAL_CODE", default="3020-113")

SEO_BUSINESS_COUNTRY = config("SEO_BUSINESS_COUNTRY", default="PT")

SEO_BUSINESS_AREA_SERVED = config("SEO_BUSINESS_AREA_SERVED", default="Coimbra")

SEO_BUSINESS_OPENS_AT = config("SEO_BUSINESS_OPENS_AT", default="08:00")

SEO_BUSINESS_CLOSES_AT = config("SEO_BUSINESS_CLOSES_AT", default="20:00")

# =============================================================================
# Public homepage
# =============================================================================

HOME_HERO_LAYOUT_CHOICES = (
    "classic",
    "logo_top",
)

HOME_HERO_LAYOUT = config("HOME_HERO_LAYOUT", default="classic").strip().lower()

if HOME_HERO_LAYOUT not in HOME_HERO_LAYOUT_CHOICES:
    HOME_HERO_LAYOUT = "classic"


# =============================================================================
# Instagram (EmbedSocial)
# =============================================================================

# Valor do atributo "data-ref" gerado em https://embedsocial.com ao criar um
# widget de Instagram Feed (Dashboard > o widget > Embed Code > data-ref="...").
# Deixe em branco para ocultar o feed de fotos na homepage.
INSTAGRAM_EMBEDSOCIAL_REF = config("INSTAGRAM_EMBEDSOCIAL_REF", default="").strip()

INSTAGRAM_PROFILE_URL = config(
    "INSTAGRAM_PROFILE_URL",
    default="https://www.instagram.com/priarantespod",
).strip()


# =============================================================================
# Promotion
# =============================================================================

PROMO_ENABLED = config("PROMO_ENABLED", default=True, cast=bool)

PROMO_DISCOUNT_PERCENT = config("PROMO_DISCOUNT_PERCENT", default=25, cast=int)

PROMO_CODE = config("PROMO_CODE", default="BEMVINDA25")

# Formato AAAA-MM-DD. A promoção deixa de aparecer automaticamente após esta data.
PROMO_VALID_UNTIL = config("PROMO_VALID_UNTIL", default="2026-07-31")


# =============================================================================
# Public bookings
# =============================================================================

PUBLIC_BOOKING_MIN_ADVANCE_HOURS = config(
    "PUBLIC_BOOKING_MIN_ADVANCE_HOURS",
    default=3,
    cast=int,
)

if PUBLIC_BOOKING_MIN_ADVANCE_HOURS < 0:
    PUBLIC_BOOKING_MIN_ADVANCE_HOURS = 0


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
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
                "config.context_processors.seo_settings",
                "config.context_processors.promo_settings",
                "config.context_processors.instagram_settings",
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

PUBLIC_BOOKING_TIME_ZONE = config(
    "PUBLIC_BOOKING_TIME_ZONE",
    default=TIME_ZONE,
).strip()

USE_I18N = True

USE_TZ = True


# =============================================================================
# Static and media files
# =============================================================================

STATIC_URL = config("STATIC_URL", default="/static/")

STATIC_ROOT = BASE_DIR / config("STATIC_ROOT", default="staticfiles")

STATICFILES_DIRS = (
    [
        BASE_DIR / "static",
    ]
    if (BASE_DIR / "static").exists()
    else []
)

MEDIA_URL = config("MEDIA_URL", default="/media/")

MEDIA_ROOT = BASE_DIR / config("MEDIA_ROOT", default="media")

# WhiteNoise serve os arquivos estáticos comprimidos direto pelo Django em produção.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


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
# WhatsApp Cloud API
# =============================================================================

WHATSAPP_CLOUD_API_ENABLED = config(
    "WHATSAPP_CLOUD_API_ENABLED",
    default=False,
    cast=bool,
)

WHATSAPP_CLOUD_API_VERSION = config(
    "WHATSAPP_CLOUD_API_VERSION",
    default="v23.0",
).strip()

WHATSAPP_PHONE_NUMBER_ID = config(
    "WHATSAPP_PHONE_NUMBER_ID",
    default="",
).strip()

WHATSAPP_ACCESS_TOKEN = config(
    "WHATSAPP_ACCESS_TOKEN",
    default="",
).strip()

WHATSAPP_TEMPLATE_NAME = config(
    "WHATSAPP_TEMPLATE_NAME",
    default="marcacao",
).strip()

WHATSAPP_TEMPLATE_LANGUAGE_CODE = config(
    "WHATSAPP_TEMPLATE_LANGUAGE_CODE",
    default="pt_PT",
).strip()

WHATSAPP_TEMPLATE_BODY_PARAMETERS = env_list(
    "WHATSAPP_TEMPLATE_BODY_PARAMETERS",
    default=(
        "customer_name,service_name,appointment_date,"
        "appointment_time,reference_code"
    ),
)

WHATSAPP_REQUEST_TIMEOUT = config(
    "WHATSAPP_REQUEST_TIMEOUT",
    default=15,
    cast=int,
)


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
