"""Exécution des tests."""

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["*"]

# Hachage rapide : bcrypt rendrait la suite de tests interminable.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# La limitation de débit est désactivée par défaut en test : son état est
# partagé par le cache entre les tests, et une suite qui enchaîne dix
# connexions tomberait sur un 429 sans rapport avec ce qu'elle vérifie.
# Le test qui la vérifie la réactive lui-même, par override_settings.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": None,
        "user": None,
        "connexion": None,
        "connexion_email": None,
        # Un barème ajouté ici sans son pendant dans `base.py` lève
        # `ImproperlyConfigured` à la première requête, pas au démarrage :
        # l'oubli se paie en tests rouges qui accusent le mauvais coupable.
        "mdp_demande": None,
        "mdp_demande_email": None,
        "mdp_demande_rapprochee": None,
        "mdp_reinitialiser": None,
        "mdp_verifier": None,
        "inscription": None,
        "inscription_renvoi": None,
        "inscription_verifier": None,
        "inscription_activer": None,
        "inscription_etat": None,
        "invitation_verifier": None,
        "invitation_accepter": None,
    },
}

# CinetPay : simulation par défaut dans la suite de tests
CINETPAY_API_KEY = ""
CINETPAY_SITE_ID = ""
CINETPAY_SECRET_KEY = "test_secret_key"

