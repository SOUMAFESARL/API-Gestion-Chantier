"""Backend d'envoi d'emails SMTP configurable pour CCD Digital.

Hérite du backend SMTP standard de Django en ajoutant le support pour
désactiver la vérification du certificat SSL (EMAIL_SSL_CERT_VERIFY=False)
en développement ou sous des environnements protégés par un antivirus (ex. Avast)
qui intercepte le trafic SSL/TLS.
"""

from __future__ import annotations

import ssl

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.utils.functional import cached_property


class ConfigurableEmailBackend(EmailBackend):
    """Backend SMTP étendant le backend officiel de Django.

    Permet d'ajuster le contexte SSL/TLS selon `EMAIL_SSL_CERT_VERIFY`.
    En production, la vérification stricte reste active par défaut.
    """

    @cached_property
    def ssl_context(self):
        verify = getattr(settings, "EMAIL_SSL_CERT_VERIFY", True)
        if not verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

        return super().ssl_context
