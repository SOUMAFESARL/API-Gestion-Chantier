"""Développement local."""

from .base import *
from .base import INSTALLED_APPS, config

DEBUG = True

# `.localhost` est résolu vers 127.0.0.1 par les navigateurs modernes :
# c'est ce qui permet de tester les sous-domaines de tenant sans toucher
# au fichier hosts (soumafe.localhost, demo.localhost, …).
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".localhost"]

INSTALLED_APPS += ["django_extensions"]

CORS_ALLOW_ALL_ORIGINS = True

# Les emails.
#
# **Par défaut, la console** : aucun service à lancer, et le lien s'y lit en
# clair. Suffisant pour vérifier qu'un message part, pénible dès qu'il faut en
# suivre le lien — c'est ce qui a fait naître deux raccourcis de développement.
#
# **Avec `docker compose up mailpit`, un vrai SMTP local** : les messages
# arrivent dans une interface web à http://localhost:8025, où le lien se clique.
# Mettre `EMAIL_MAILPIT=True` dans `.env`. Cela vaut pour **les six emails du
# parcours**, pas seulement pour la réinitialisation, et cela ressemble à la
# production — un fournisseur SMTP se substituera à Mailpit sans rien changer
# d'autre que l'hôte.
if config("EMAIL_MAILPIT", default=False, cast=bool):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    # Des variables **propres** à l'attrape-mail, et non `EMAIL_HOST` /
    # `EMAIL_PORT` : celles-là décrivent le fournisseur de production et sont
    # déjà posées dans `.env`, vides et sur le port 587. Les réutiliser faisait
    # pointer Mailpit vers nulle part, sur le mauvais port.
    EMAIL_HOST = config("MAILPIT_HOST", default="localhost")
    EMAIL_PORT = config("MAILPIT_PORT", default=1025, cast=int)
    EMAIL_USE_TLS = False
    EMAIL_HOST_USER = ""
    EMAIL_HOST_PASSWORD = ""
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="ne-pas-repondre@ccd-digital.ci")

# Exécution synchrone des tâches Celery : pratique tant que Redis n'est pas lancé.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)

# La liste noire des jetons (T-008 §3) vit dans le cache. `LocMemCache` est
# **par processus** : avec `runserver` cela suffit, avec plusieurs travailleurs
# gunicorn un jeton révoqué par l'un resterait valable chez les autres.
# Lancer Redis dès qu'on teste à plusieurs processus — `CACHE_LOCMEM=False`.
if config("CACHE_LOCMEM", default=True, cast=bool):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
