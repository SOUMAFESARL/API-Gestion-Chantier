"""Production cPanel : Passenger sert aussi les fichiers statiques WhiteNoise."""

from .production import *
from .production import MIDDLEWARE

MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

# Sur cPanel, aucun worker Celery ne tourne en tâche de fond par défaut.
# Les tâches s'exécutent de façon synchrone sauf si explicitement désactivé dans .env.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = config("CELERY_TASK_EAGER_PROPAGATES", default=True, cast=bool)
