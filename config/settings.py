"""Django settings. Everything environment-specific comes from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")
    SECRET_KEY = "dev-only-insecure-key"  # noqa: S105 - never used with DEBUG off
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "invoices",
]

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
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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


def database_config() -> dict:
    """DB_ENGINE=sqlite (default) | mysql | postgresql, plus DB_NAME/USER/PASSWORD/HOST/PORT."""
    engine = os.environ.get("DB_ENGINE", "sqlite").lower()
    if engine == "sqlite":
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
        }
    config = {
        "NAME": os.environ.get("DB_NAME", "nfe"),
        "USER": os.environ.get("DB_USER", "nfe"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", ""),
        "CONN_MAX_AGE": 60,
    }
    if engine == "mysql":
        config["ENGINE"] = "django.db.backends.mysql"
        config["OPTIONS"] = {
            "charset": "utf8mb4",  # company names have accents; utf8mb4 is real UTF-8
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }
        config["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}
    elif engine in {"postgres", "postgresql"}:
        config["ENGINE"] = "django.db.backends.postgresql"
    else:
        raise RuntimeError(f"unsupported DB_ENGINE {engine!r}")
    return config


DATABASES = {"default": database_config()}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploads: a single NF-e is a few KB; cap requests so nobody can post gigabytes.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 100

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "invoices.pagination.Pagination",
    "COERCE_DECIMAL_TO_STRING": True,  # money is never sent as a binary float
}
