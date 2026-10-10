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

    def __init__(self, *args, **kwargs):
        # Le serveur SMTP saisi par le superviseur (paramètres de la plateforme) l'emporte sur le
        # `.env` : changer un mot de passe d'application ne doit pas exiger l'accès au panneau
        # d'hébergement. Sans réglage saisi, rien ne change. Jamais d'exception ici.
        try:
            from apps.platform_admin.services.messagerie import configuration_base

            base = configuration_base()
        except Exception:  # noqa: BLE001
            base = None
        if base:
            kwargs.setdefault("host", base["host"])
            kwargs.setdefault("port", base["port"])
            kwargs.setdefault("username", base["username"])
            kwargs.setdefault("password", base["password"])
            kwargs.setdefault("use_tls", base["use_tls"])
            kwargs.setdefault("use_ssl", base["use_ssl"])
        super().__init__(*args, **kwargs)

    @cached_property
    def ssl_context(self):
        verify = getattr(settings, "EMAIL_SSL_CERT_VERIFY", True)
        if not verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

        return super().ssl_context
