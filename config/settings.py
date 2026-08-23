import sys
from pathlib import Path

from decouple import Config, RepositoryEmpty, RepositoryEnv

BASE_DIR = Path(__file__).resolve().parent.parent


def _repositorio_de_variaveis():
    """O ficheiro de onde saem as variáveis, quando há um.

    Em produção elas chegam pelo ambiente — é o `env_file` do compose que as
    injeta — e o ambiente ganha sempre a quem estiver no ficheiro. Em
    desenvolvimento vêm de um ficheiro na raiz do projeto: `.env`, ou
    `.env.prod` quando é esse o que lá está. Sem nenhum dos dois, resta o
    ambiente, que é o suficiente em produção e falha cedo em desenvolvimento.
    """

    for nome in (".env", ".env.prod"):
        caminho = BASE_DIR / nome

        if caminho.is_file():
            return RepositoryEnv(caminho)

    return RepositoryEmpty()


config = Config(_repositorio_de_variaveis())


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

# Debaixo dos testes, o que fala com o exterior fica desligado: uma suite que
# chama serviços a sério é uma suite lenta, instável e — no caso da Google —
# paga. Cada sítio que a usa explica porquê.
RUNNING_TESTS = "test" in sys.argv or "pytest" in sys.modules

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

# Cartão 1200x630 gerado por scripts/optimize_public_images.py. Continua em PNG
# porque quem o lê são os robôs de pré-visualização do WhatsApp e do Facebook,
# e não o browser.
SEO_DEFAULT_IMAGE_PATH = config(
    "SEO_DEFAULT_IMAGE_PATH",
    default="/static/img/logo-og.png",
)

SEO_LOCALE = config("SEO_LOCALE", default="pt_PT")

SEO_THEME_COLOR = config("SEO_THEME_COLOR", default="#a8755f")

SEO_ROBOTS_DEFAULT = config("SEO_ROBOTS_DEFAULT", default="index,follow")

SEO_WHATSAPP_NUMBER = config("SEO_WHATSAPP_NUMBER", default="+351938594367")

SEO_BUSINESS_EMAIL = config("SEO_BUSINESS_EMAIL", default="atendimento@priarantes.com")

SEO_BUSINESS_STREET_ADDRESS = config(
    "SEO_BUSINESS_STREET_ADDRESS",
    default="Av. Sá da Bandeira 33, Loja 108",
)

SEO_BUSINESS_LOCALITY = config("SEO_BUSINESS_LOCALITY", default="Coimbra")

SEO_BUSINESS_POSTAL_CODE = config("SEO_BUSINESS_POSTAL_CODE", default="3000-351")

SEO_BUSINESS_COUNTRY = config("SEO_BUSINESS_COUNTRY", default="PT")

SEO_BUSINESS_AREA_SERVED = config("SEO_BUSINESS_AREA_SERVED", default="Coimbra")

SEO_BUSINESS_OPENS_AT = config("SEO_BUSINESS_OPENS_AT", default="08:00")

SEO_BUSINESS_CLOSES_AT = config("SEO_BUSINESS_CLOSES_AT", default="20:00")

# =============================================================================
# Livro de Reclamações
# =============================================================================
# O Decreto-Lei n.º 74/2017 obriga os estabelecimentos a divulgar o Livro de
# Reclamações Eletrónico. A reclamação é submetida no portal oficial, não aqui:
# este site só encaminha para lá.

COMPLAINTS_BOOK_URL = config(
    "COMPLAINTS_BOOK_URL",
    default="https://www.livroreclamacoes.pt/inicio",
).strip()


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
# Avaliações do Google
# =============================================================================
# A secção da página inicial mostra as avaliações do estabelecimento, lidas da
# Places API. Sem chave ou sem identificador do local, a secção não aparece e o
# site funciona na mesma.
#
# A API devolve no máximo cinco avaliações, escolhidas por ela: não há forma de
# pedir mais nem de paginar.

GOOGLE_PLACES_API_KEY = config("GOOGLE_PLACES_API_KEY", default="").strip()

# Sem chave, a secção não aparece e nada é pedido. É assim que os testes que
# desenham a página inicial deixam de chamar a Google: com a chave verdadeira
# no .env, cada um deles seria uma chamada externa, lenta e paga. Os testes das
# avaliações ligam-na de volta com override_settings e uma chave de mentira.
if RUNNING_TESTS:
    GOOGLE_PLACES_API_KEY = ""

# Identificador do local no Google. Encontra-se no Place ID Finder da Google ou
# no endereço do perfil da empresa; é o único dado do local que a Google
# permite guardar indefinidamente.
GOOGLE_PLACE_ID = config("GOOGLE_PLACE_ID", default="").strip()

GOOGLE_PLACES_API_URL = config(
    "GOOGLE_PLACES_API_URL",
    default="https://places.googleapis.com/v1/places",
).rstrip("/")

# Quantas mostrar, até ao limite de cinco que a Google devolve.
GOOGLE_REVIEWS_LIMIT = config("GOOGLE_REVIEWS_LIMIT", default=5, cast=int)

# Seis horas. A Google não permite guardar dados de um local por muito tempo, e
# as avaliações também não mudam de minuto a minuto.
GOOGLE_REVIEWS_CACHE_SECONDS = config(
    "GOOGLE_REVIEWS_CACHE_SECONDS",
    default=6 * 60 * 60,
    cast=int,
)

GOOGLE_REVIEWS_LANGUAGE = config("GOOGLE_REVIEWS_LANGUAGE", default="pt-PT").strip()

GOOGLE_REQUEST_TIMEOUT = config("GOOGLE_REQUEST_TIMEOUT", default=10, cast=int)


# =============================================================================
# Instagram
# =============================================================================
# As fotos do carrossel são registadas manualmente em Django Admin
# (Notifications > Publicações do Instagram) — não há integração automática.

INSTAGRAM_PROFILE_URL = config(
    "INSTAGRAM_PROFILE_URL",
    default="https://www.instagram.com/priarantespod",
).strip()


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
# Registos clínicos
# =============================================================================

# Prazo de conservação das fichas de anamnese e notas de evolução, em anos.
#
# A legislação da podologia não fixa um prazo único: tem de ser definido pela
# responsável, considerando a legislação de saúde e de proteção de dados. Zero
# significa "por definir" — nesse estado o sistema avisa na área interna e a
# política de privacidade não anuncia prazo nenhum, para não publicar um
# compromisso que não foi assumido.
#
# A eliminação nunca é automática: o comando report_clinical_retention apenas
# lista o que ultrapassou o prazo, para decisão caso a caso.
CLINICAL_RECORD_RETENTION_YEARS = config(
    "CLINICAL_RECORD_RETENTION_YEARS",
    default=0,
    cast=int,
)


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
    # Precisa vir depois da sessão e antes do CommonMiddleware para resolver o
    # idioma a partir do prefixo do URL, do cookie e do Accept-Language.
    "django.middleware.locale.LocaleMiddleware",
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
                "django.template.context_processors.i18n",
                "config.context_processors.seo_settings",
                "config.context_processors.instagram_settings",
                "config.context_processors.language_alternates",
                "config.context_processors.clinical_settings",
                "config.context_processors.before_after_gallery",
                "config.context_processors.opening_hours",
            ],
            "libraries": {
                # `config` não é uma app instalada, por isso a biblioteca de
                # tags tem de ser registada aqui à mão.
                "assets": "config.templatetags.assets",
            },
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
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
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

# Português continua na raiz do site e o inglês fica sob /en/, por causa de
# prefix_default_language=False em config/urls.py. Nenhum URL atual muda.
LANGUAGES = [
    ("pt-pt", "Português"),
    ("en", "English"),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

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

# WhiteNoise serve os ficheiros estáticos comprimidos direto pelo Django em produção.

# Quanto tempo o browser pode guardar um ficheiro estático. Por omissão o
# WhiteNoise diz 60 segundos, porque com nomes de ficheiro fixos não há como
# saber quando o conteúdo muda — passado esse minuto, cada visita volta a
# perguntar por cada ficheiro.
#
# Aqui há como: o `{% versioned_static %}` acrescenta `?v=<data do ficheiro>`
# ao endereço, portanto um ficheiro alterado passa a ter outro endereço e o
# que está guardado deixa de ser pedido. Isso torna seguro guardar durante um
# ano, que é o máximo que a norma recomenda.
#
# A exceção é o `apple-touch-icon`, que usa `{% static %}` sem versão: se um
# dia mudar, quem já a tiver visto fica com a antiga. É um ícone.
WHITENOISE_MAX_AGE = config("WHITENOISE_MAX_AGE", default=31536000, cast=int)

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

# Para onde seguem os avisos internos — pedido novo por confirmar, cancelamento.
# Por omissão é o mesmo endereço que o site publica, que é o que a profissional
# lê todos os dias.
PROFESSIONAL_EMAIL = config("PROFESSIONAL_EMAIL", default=SEO_BUSINESS_EMAIL)


# =============================================================================
# Entrega de notificações
# =============================================================================
# Emails e mensagens de WhatsApp saem depois de a marcação estar gravada, mas
# saíam dentro do mesmo pedido: quem marcava ficava à espera do SMTP e do
# WhatsApp antes de ver a página de sucesso. Com EMAIL_TIMEOUT a 30s e o
# WhatsApp a 15-20s, um fornecedor lento segurava um worker do gunicorn quase
# um minuto — e três marcações assim parariam o site inteiro.
#
# Agora a entrega passa para um punhado de threads e o pedido devolve logo. Não
# substitui uma fila (Celery): se o processo morrer com entregas a meio, elas
# perdem-se. Substitui, sim, o pior caso — o site parar por causa de um SMTP
# que não responde.

# Em testes o envio tem de ser imediato: quase 400 testes verificam o que foi
# enviado na linha a seguir à chamada, e numa thread isso passaria a corrida.
# O `and not RUNNING_TESTS` no fim é deliberado: nem um .env que ligue isto
# consegue pôr os testes a enviar em segundo plano. Quem precisa do contrário
# num teste concreto usa override_settings.
NOTIFICATIONS_IN_BACKGROUND = (
    config(
        "NOTIFICATIONS_IN_BACKGROUND",
        default=True,
        cast=bool,
    )
    and not RUNNING_TESTS
)

# Poucas e fixas de propósito: o que se quer é tirar a espera do pedido, não
# abrir uma thread por marcação.
NOTIFICATIONS_MAX_WORKERS = config(
    "NOTIFICATIONS_MAX_WORKERS",
    default=4,
    cast=int,
)


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
        "customer_name,service_name,appointment_date,appointment_time,reference_code"
    ),
)

WHATSAPP_REQUEST_TIMEOUT = config(
    "WHATSAPP_REQUEST_TIMEOUT",
    default=15,
    cast=int,
)


# =============================================================================
# Twilio (WhatsApp)
# =============================================================================
#
# Alternativa ao WhatsApp Cloud API acima. As duas podem coexistir: cada envio
# regista o fornecedor que usou, para não se confundirem no histórico.

TWILIO_ENABLED = config(
    "TWILIO_ENABLED",
    default=False,
    cast=bool,
)

TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="").strip()

TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="").strip()

# Número emissor, no formato que a Twilio espera: whatsapp:+14155238886. O
# número do sandbox serve para testar; em produção é o número aprovado.
TWILIO_WHATSAPP_FROM = config("TWILIO_WHATSAPP_FROM", default="").strip()

# Para onde vão os avisos dirigidos à profissional.
TWILIO_PROFESSIONAL_WHATSAPP = config(
    "TWILIO_PROFESSIONAL_WHATSAPP",
    default=SEO_WHATSAPP_NUMBER,
).strip()

TWILIO_REQUEST_TIMEOUT = config(
    "TWILIO_REQUEST_TIMEOUT",
    default=15,
    cast=int,
)


# =============================================================================
# Baileys (WhatsApp)
# =============================================================================
#
# O Baileys liga-se ao WhatsApp como um dispositivo emparelhado, tal como o
# WhatsApp Web: não há modelos para aprovar nem janela de 24 horas, mas também
# não há garantia de serviço — é o número da clínica que está a enviar.
#
# Corre num container à parte (ver `baileys/`), porque é uma biblioteca Node.
# O Django só fala com ele por HTTP, pela rede interna do Docker.

BAILEYS_ENABLED = config(
    "BAILEYS_ENABLED",
    default=False,
    cast=bool,
)

BAILEYS_API_URL = config(
    "BAILEYS_API_URL",
    default="http://baileys:3000",
).strip()

# O mesmo valor tem de estar no serviço Node. Sem ele, qualquer container da
# rede interna podia enviar mensagens em nome da clínica.
BAILEYS_API_TOKEN = config("BAILEYS_API_TOKEN", default="").strip()

# Para onde vão os avisos dirigidos à profissional. Por omissão segue o mesmo
# número que a Twilio usa, para não haver dois sítios a dizer coisas
# diferentes sobre o mesmo destinatário.
BAILEYS_PROFESSIONAL_WHATSAPP = config(
    "BAILEYS_PROFESSIONAL_WHATSAPP",
    default=TWILIO_PROFESSIONAL_WHATSAPP,
).strip()

BAILEYS_REQUEST_TIMEOUT = config(
    "BAILEYS_REQUEST_TIMEOUT",
    default=20,
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
