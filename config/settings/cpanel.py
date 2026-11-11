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
