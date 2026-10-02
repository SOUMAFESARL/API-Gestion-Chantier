"""Production."""

from .base import *
from .base import config

DEBUG = False

# Socle Commun §2 — HTTPS forcé, cookies verrouillés, en-têtes de sécurité.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# Stockage objet — isolation {schema}/{module}/{uuid} (US-006).
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
_aws_endpoint = config("AWS_S3_ENDPOINT_URL", default=None)
AWS_S3_ENDPOINT_URL = _aws_endpoint if _aws_endpoint else None
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True  # URL signées, jamais de fichier public

if AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
# Les paramètres EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS,
# DEFAULT_FROM_EMAIL sont définis de manière centralisée dans base.py (avec support SYSTEM_SMTP_USER/PASS)
# et peuvent être surchargés individuellement dans .env si nécessaire.

