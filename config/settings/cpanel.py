"""Production cPanel : Passenger sert aussi les fichiers statiques WhiteNoise."""

from .production import *  # noqa: F403
from .production import MIDDLEWARE

MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
