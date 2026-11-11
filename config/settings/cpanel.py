"""Production cPanel : Passenger sert aussi les fichiers statiques WhiteNoise."""

from .production import *
from .production import MIDDLEWARE


MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

# Sur cPanel mutualisé, aucun service Redis ni worker Celery ne tourne par défaut.
# Le cache utilise la mémoire locale (comme en dev local) sauf surcharge explicite dans .env.
CACHES = {
    "default": {
        "BACKEND": config(
            "CACHE_BACKEND",
            default="django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": config("CACHE_LOCATION", default="ccd-cpanel-cache"),
    }
}

# Les tâches s'exécutent de façon synchrone sauf si explicitement désactivé dans .env.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = config("CELERY_TASK_EAGER_PROPAGATES", default=False, cast=bool)

# Diagnostic : la cause d'une erreur 500 est renvoyée dans le message, et la trace complète est
# écrite dans `logs/erreurs.log` (lisible depuis le gestionnaire de fichiers cPanel).
# Mettre EXPOSER_CAUSE_ERREUR_INTERNE=False dans le .env une fois la panne comprise.
EXPOSER_CAUSE_ERREUR_INTERNE = config("EXPOSER_CAUSE_ERREUR_INTERNE", default=True, cast=bool)

import copy  # noqa: E402
from pathlib import Path  # noqa: E402

_DOSSIER_LOGS = Path(__file__).resolve().parent.parent.parent / "logs"
_DOSSIER_LOGS.mkdir(exist_ok=True)
LOGGING = copy.deepcopy(LOGGING)
LOGGING["handlers"]["fichier_erreurs"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": str(_DOSSIER_LOGS / "erreurs.log"),
    "maxBytes": 2 * 1024 * 1024,
    "backupCount": 3,
    "level": "ERROR",
    "formatter": "standard",
    "encoding": "utf-8",
}
LOGGING["root"]["handlers"] = [*LOGGING["root"]["handlers"], "fichier_erreurs"]
