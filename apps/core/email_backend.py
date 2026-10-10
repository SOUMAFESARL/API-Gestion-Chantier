"""Backend d'envoi d'emails SMTP configurable pour CCD Digital.

Hérite du backend SMTP standard de Django en ajoutant le support pour
désactiver la vérification du certificat SSL (EMAIL_SSL_CERT_VERIFY=False)
en développement ou sous des environnements protégés par un antivirus (ex. Avast)
qui intercepte le trafic SSL/TLS.
"""

from __future__ import annotations

import re
import socket
import ssl

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.core.mail.utils import DNS_NAME
from django.utils.functional import cached_property

_NOM_VALIDE = re.compile(r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+")


def nom_ehlo_valide(nom: str) -> bool:
    """Un nom de domaine complet, ASCII, sans souligné : ce que Gmail accepte après `EHLO`."""
    return bool(nom) and bool(_NOM_VALIDE.fullmatch(nom))


def nom_ehlo() -> str:
    """Le nom que ce serveur donne au serveur de messagerie pour se présenter (`EHLO`).

    Django le prend dans le nom d'hôte de la machine. Sur un hébergement mutualisé, ce nom est
    souvent un identifiant interne (`srv_42`, `localhost`, sans point) : Gmail **coupe alors la
    connexion** sans autre explication, alors qu'un client qui se présente par son adresse IP
    (comme `smtplib` par défaut) passe sans problème. Quand le nom n'est pas valide, on le
    remplace par le domaine de la plateforme, sinon par l'adresse IP entre crochets.
    """
    nom = DNS_NAME.get_fqdn()
    if nom_ehlo_valide(nom):
        return nom
    domaine = str(getattr(settings, "DOMAINE_PRINCIPAL", "") or "").strip().lower()
    if nom_ehlo_valide(domaine) and domaine != "localhost":
        return domaine
    try:
        return f"[{socket.gethostbyname(socket.gethostname())}]"
    except OSError:
        return "[127.0.0.1]"


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
        # Django met ce nom en cache à la première lecture : on le corrige à la source.
        DNS_NAME._fqdn = nom_ehlo()

    @cached_property
    def ssl_context(self):
        verify = getattr(settings, "EMAIL_SSL_CERT_VERIFY", True)
        if not verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

        return super().ssl_context
