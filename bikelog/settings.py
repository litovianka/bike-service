import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _strip_quotes(value: str) -> str:
    v = (value or "").strip()
    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        return v[1:-1]
    return v


def _load_dotenv_simple():
    """
    Načíta .env bez závislostí.
    Priorita je vždy OS env. .env dopĺňa len chýbajúce kľúče.
    """
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = _strip_quotes(value)

            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


_load_dotenv_simple()


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key, "")
    if v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(key: str, default: int) -> int:
    raw = (os.getenv(key, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_csv(key: str) -> list[str]:
    raw = (os.getenv(key, "") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    raise RuntimeError("Chýba DJANGO_SECRET_KEY. Daj ho do .env alebo do systémových premenných.")

DEBUG = _env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = _env_csv("DJANGO_ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

if not DEBUG and not ALLOWED_HOSTS:
    raise RuntimeError("Pri DEBUG=0 musíš mať nastavené DJANGO_ALLOWED_HOSTS v .env")

CSRF_TRUSTED_ORIGINS = _env_csv("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "service",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bikelog.urls"

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
                "service.context_processors.admin_ticket_badge",
            ],
        },
    }
]

WSGI_APPLICATION = "bikelog.wsgi.application"

DATABASE_URL = (os.getenv("DATABASE_URL", "") or "").strip()


def _database_from_url(url: str):
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme in {"postgres", "postgresql"}:
        db_conf = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": (parsed.path or "/").lstrip("/") or "postgres",
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "127.0.0.1",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": _env_int("DJANGO_DB_CONN_MAX_AGE", 60),
        }
        if _env_bool("DJANGO_DB_SSL_REQUIRE", default=False):
            db_conf["OPTIONS"] = {"sslmode": "require"}
        return db_conf

    if scheme == "sqlite":
        path = (parsed.path or "").lstrip("/")
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / path) if path else str(BASE_DIR / "db.sqlite3"),
        }

    return None


parsed_db = _database_from_url(DATABASE_URL) if DATABASE_URL else None
if parsed_db:
    DATABASES = {"default": parsed_db}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "sk"
TIME_ZONE = "Europe/Bratislava"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "servis@mojbike.sk").strip() or "servis@mojbike.sk"
EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "customer_home"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_MANIFEST_STATIC = _env_bool("DJANGO_MANIFEST_STATIC", default=False)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
            if USE_MANIFEST_STATIC
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

CACHE_BACKEND = (os.getenv("DJANGO_CACHE_BACKEND", "locmem") or "locmem").strip().lower()
if CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "redis://127.0.0.1:6379/1"),
            "TIMEOUT": _env_int("DJANGO_CACHE_TIMEOUT", 300),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "bike-service-local",
            "TIMEOUT": _env_int("DJANGO_CACHE_TIMEOUT", 300),
        }
    }

SERVICE_DASHBOARD_CACHE_TTL = _env_int("SERVICE_DASHBOARD_CACHE_TTL", 60)

CELERY_BROKER_URL = (os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0") or "").strip()
CELERY_RESULT_BACKEND = (os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL) or "").strip()
CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = _env_bool("CELERY_TASK_EAGER_PROPAGATES", default=False)

BEHIND_PROXY = _env_bool("DJANGO_BEHIND_PROXY", default=False)
SECURE_COOKIES = _env_bool("DJANGO_SECURE_COOKIES", default=False)
FORCE_HTTPS = _env_bool("DJANGO_FORCE_HTTPS", default=False)

if BEHIND_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

if FORCE_HTTPS:
    SECURE_SSL_REDIRECT = True
else:
    SECURE_SSL_REDIRECT = False

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

    if SECURE_COOKIES:
        SECURE_HSTS_SECONDS = _env_int("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 7)
        SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=True)
        SECURE_HSTS_PRELOAD = _env_bool("DJANGO_HSTS_PRELOAD", default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s %(name)s %(message)s"},
        "verbose": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if not DEBUG else "simple",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "service": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

_raw_admins = _env_csv("DJANGO_ADMINS")
ADMINS = []
for item in _raw_admins:
    if ":" in item:
        name, email = item.split(":", 1)
        ADMINS.append((name.strip() or email.strip(), email.strip()))
    elif item:
        email = item.strip()
        ADMINS.append((email, email))
ADMINS = tuple(ADMINS)
MANAGERS = ADMINS

if not DEBUG and ADMINS:
    LOGGING["handlers"]["mail_admins"] = {
        "class": "django.utils.log.AdminEmailHandler",
        "include_html": True,
        "level": "ERROR",
    }
    LOGGING["loggers"]["django.request"] = {
        "handlers": ["console", "mail_admins"],
        "level": "ERROR",
        "propagate": False,
    }
    LOGGING["root"]["handlers"] = ["console", "mail_admins"]

SENTRY_DSN = (os.getenv("SENTRY_DSN", "") or "").strip()
if SENTRY_DSN:
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.django import DjangoIntegration  # type: ignore

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            send_default_pii=False,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        )
    except Exception:
        pass
