"""Développement local."""

from .base import *
from .base import DATABASES, INSTALLED_APPS, config

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS += ["django_extensions"]

# La branche du schéma unique a sa propre base : la base multi-schéma reste intacte, pour
# comparer les deux modèles sur le même jeu de test (`peupler_donnees_test`).
DATABASES["default"]["NAME"] = config("POSTGRES_DB_SCHEMA_UNIQUE", default="ccd_schema_unique")

CORS_ALLOW_ALL_ORIGINS = True

# Les emails en environnement local :
# 1. Si EMAIL_BACKEND est explicitement défini dans .env, l'utiliser.
# 2. Si EMAIL_MAILPIT=True, utiliser Mailpit local.
# 3. Si un utilisateur SMTP est configuré (SYSTEM_SMTP_USER ou EMAIL_HOST_USER),
#    utiliser le SMTP réel (ex: Gmail).
# 4. Sinon, afficher les emails dans la console.
_email_backend_env = config("EMAIL_BACKEND", default=None)
if _email_backend_env:
    EMAIL_BACKEND = _email_backend_env
elif config("EMAIL_MAILPIT", default=False, cast=bool):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = config("MAILPIT_HOST", default="localhost")
    EMAIL_PORT = config("MAILPIT_PORT", default=1025, cast=int)
    EMAIL_USE_TLS = False
    EMAIL_HOST_USER = ""
    EMAIL_HOST_PASSWORD = ""
elif EMAIL_HOST_USER:
    EMAIL_BACKEND = "apps.core.email_backend.ConfigurableEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Exécution synchrone des tâches Celery : pratique tant que Redis n'est pas lancé.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)

# La liste noire des jetons (T-008 §3) vit dans le cache. `LocMemCache` est
# **par processus** : avec `runserver` cela suffit, avec plusieurs travailleurs
# gunicorn un jeton révoqué par l'un resterait valable chez les autres.
# Lancer Redis dès qu'on teste à plusieurs processus — `CACHE_LOCMEM=False`.
if config("CACHE_LOCMEM", default=True, cast=bool):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
