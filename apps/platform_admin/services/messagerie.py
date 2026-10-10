"""La messagerie de la plateforme : chiffrement du mot de passe, réglage actif, diagnostic d'envoi.

**Ce module ne doit jamais faire échouer un envoi.** `configuration_base()` est lue à chaque
ouverture de connexion SMTP, y compris pendant les migrations et dans une transaction : toute
erreur de lecture se traduit par « pas de réglage saisi », donc par le repli sur le `.env`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import smtplib
import socket
import ssl
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

from apps.platform_admin.models.messagerie import ParametresMessagerie

logger = logging.getLogger(__name__)

_PREFIXE = "v1:"
_TAILLE_NONCE = 16
_TAILLE_TAG = 32


# ---------------------------------------------------------------------------
# Chiffrement du mot de passe
# ---------------------------------------------------------------------------
# Chiffrement authentifié construit sur la bibliothèque standard : aucune dépendance de plus à
# installer sur l'hébergement. Flux = HMAC-SHA256(clé, nonce ‖ compteur) (mode compteur), puis
# étiquette HMAC-SHA256 sur nonce ‖ chiffré (chiffrer puis authentifier). La clé dérive de
# `SECRET_KEY` : la base seule ne suffit pas à lire le mot de passe. Si `SECRET_KEY` change, le
# mot de passe devient illisible — il suffit de le ressaisir, et le `.env` sert de repli.


def _cles() -> tuple[bytes, bytes]:
    base = hashlib.sha256(("ccd-messagerie-v1|" + settings.SECRET_KEY).encode()).digest()
    return (
        hmac.new(base, b"chiffrement", hashlib.sha256).digest(),
        hmac.new(base, b"authentification", hashlib.sha256).digest(),
    )


def _flux(cle: bytes, nonce: bytes, longueur: int) -> bytes:
    blocs = (longueur + 31) // 32
    flux = b"".join(
        hmac.new(cle, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(blocs)
    )
    return flux[:longueur]


def chiffrer(clair: str) -> str:
    cle_chiffrement, cle_auth = _cles()
    nonce = os.urandom(_TAILLE_NONCE)
    donnees = clair.encode("utf-8")
    chiffre = bytes(a ^ b for a, b in zip(donnees, _flux(cle_chiffrement, nonce, len(donnees))))
    etiquette = hmac.new(cle_auth, nonce + chiffre, hashlib.sha256).digest()
    return _PREFIXE + base64.urlsafe_b64encode(nonce + chiffre + etiquette).decode("ascii")


def dechiffrer(valeur: str) -> str | None:
    """Le texte clair, ou `None` si la valeur est absente, altérée ou chiffrée avec une autre clé."""
    if not valeur or not valeur.startswith(_PREFIXE):
        return None
    try:
        brut = base64.urlsafe_b64decode(valeur[len(_PREFIXE):].encode("ascii"))
    except Exception:  # noqa: BLE001
        return None
    if len(brut) < _TAILLE_NONCE + _TAILLE_TAG:
        return None
    nonce, chiffre, etiquette = brut[:_TAILLE_NONCE], brut[_TAILLE_NONCE:-_TAILLE_TAG], brut[-_TAILLE_TAG:]
    cle_chiffrement, cle_auth = _cles()
    attendue = hmac.new(cle_auth, nonce + chiffre, hashlib.sha256).digest()
    if not hmac.compare_digest(etiquette, attendue):
        return None
    clair = bytes(a ^ b for a, b in zip(chiffre, _flux(cle_chiffrement, nonce, len(chiffre))))
    return clair.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Le réglage actif
# ---------------------------------------------------------------------------
def lire_parametres() -> ParametresMessagerie | None:
    """La ligne unique du schéma public, ou `None`. Ne lève jamais."""
    try:
        # Point de sauvegarde : une table absente (avant migration) ne doit pas invalider la
        # transaction de l'appelant — PostgreSQL refuse toute requête après une erreur.
        with transaction.atomic(), schema_context(get_public_schema_name()):
            return ParametresMessagerie.objects.filter(pk=1).first()
    except Exception:  # noqa: BLE001
        return None


def configuration_base() -> dict[str, Any] | None:
    """Le réglage saisi par le superviseur, prêt pour le backend SMTP — ou `None` (repli `.env`)."""
    parametres = lire_parametres()
    if parametres is None or not parametres.est_complete:
        return None
    mot_de_passe = dechiffrer(parametres.mot_de_passe_chiffre)
    if mot_de_passe is None:
        logger.error(
            "Le mot de passe de messagerie enregistré est illisible (SECRET_KEY modifiée ?) : "
            "repli sur le .env. Ressaisissez-le dans les paramètres de la plateforme."
        )
        return None
    return {
        "host": parametres.hote,
        "port": parametres.port,
        "username": parametres.identifiant,
        "password": mot_de_passe,
        "use_tls": parametres.chiffrement == ParametresMessagerie.Chiffrement.STARTTLS,
        "use_ssl": parametres.chiffrement == ParametresMessagerie.Chiffrement.SSL,
        "expediteur": parametres.expediteur or f"CCD Digital <{parametres.identifiant}>",
    }


def expediteur_actif() -> str:
    """L'adresse d'expédition : celle du réglage saisi, sinon `DEFAULT_FROM_EMAIL`."""
    configuration = configuration_base()
    return configuration["expediteur"] if configuration else settings.DEFAULT_FROM_EMAIL


def reglage_effectif() -> dict[str, Any]:
    """Ce qui sert réellement à envoyer, **sans le mot de passe** — pour l'écran et le diagnostic."""
    configuration = configuration_base()
    if configuration:
        chiffrement = (
            ParametresMessagerie.Chiffrement.SSL
            if configuration["use_ssl"]
            else ParametresMessagerie.Chiffrement.STARTTLS
            if configuration["use_tls"]
            else ParametresMessagerie.Chiffrement.AUCUN
        )
        return {
            "source": "application",
            "hote": configuration["host"],
            "port": configuration["port"],
            "chiffrement": str(chiffrement),
            "identifiant": configuration["username"],
            "expediteur": configuration["expediteur"],
        }
    chiffrement = (
        ParametresMessagerie.Chiffrement.SSL
        if settings.EMAIL_USE_SSL
        else ParametresMessagerie.Chiffrement.STARTTLS
        if settings.EMAIL_USE_TLS
        else ParametresMessagerie.Chiffrement.AUCUN
    )
    return {
        "source": "serveur",
        "hote": settings.EMAIL_HOST,
        "port": settings.EMAIL_PORT,
        "chiffrement": str(chiffrement),
        "identifiant": settings.EMAIL_HOST_USER,
        "expediteur": settings.DEFAULT_FROM_EMAIL,
    }


def serialiser(parametres: ParametresMessagerie | None) -> dict[str, Any]:
    """La représentation de l'API : le réglage saisi, le réglage effectif, jamais le mot de passe."""
    from apps.core.emails import adresse_frontend

    adresse = adresse_frontend()
    return {
        "saisi": {
            "hote": parametres.hote if parametres else "",
            "port": parametres.port if parametres else 587,
            "chiffrement": parametres.chiffrement if parametres else "STARTTLS",
            "identifiant": parametres.identifiant if parametres else "",
            "expediteur": parametres.expediteur if parametres else "",
            "mot_de_passe_defini": bool(parametres and parametres.mot_de_passe_chiffre),
            "modifie_le": parametres.modifie_le if parametres else None,
        },
        "effectif": reglage_effectif(),
        "frontend_url": adresse,
        "frontend_url_locale": "localhost" in adresse or "127.0.0.1" in adresse,
    }


# ---------------------------------------------------------------------------
# Diagnostic d'envoi
# ---------------------------------------------------------------------------
def _conseil(exception: Exception, reglage: dict[str, Any]) -> str:
    adresse = f"{reglage['hote']}:{reglage['port']}"
    if isinstance(exception, smtplib.SMTPAuthenticationError):
        return (
            "Le serveur refuse l'identifiant ou le mot de passe. Avec Gmail, il faut un mot de "
            "passe d'application, qui n'existe que si la validation en deux étapes est active : "
            "si elle a été supprimée, créez un nouveau mot de passe d'application."
        )
    if isinstance(exception, (smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused)):
        return (
            "Le serveur refuse l'adresse d'expédition ou du destinataire. L'expéditeur doit être "
            "l'adresse du compte SMTP ou un alias que ce compte a le droit d'utiliser."
        )
    if isinstance(exception, ssl.SSLError):
        return (
            "La connexion sécurisée a échoué (certificat ou chiffrement). Vérifiez le port : "
            "587 va avec STARTTLS, 465 avec SSL/TLS."
        )
    if isinstance(exception, (socket.timeout, TimeoutError, ConnectionRefusedError, socket.gaierror)):
        return (
            f"Le serveur ne peut pas joindre {adresse}. Vérifiez l'adresse et le port ; si c'est "
            "correct, l'hébergeur bloque peut-être les envois sortants vers ce serveur."
        )
    if isinstance(exception, (smtplib.SMTPServerDisconnected, ConnectionError, OSError)):
        return (
            f"La connexion à {adresse} a été coupée. Une coupure à ce stade vient souvent d'un "
            "pare-feu ou d'un antivirus (côté serveur ou côté poste) qui bloque le courrier sortant."
        )
    return "Consultez le message d'erreur ci-dessus ; il vient du serveur de messagerie."


def _nettoyer(message: str) -> str:
    """Retire un éventuel mot de passe du message d'erreur avant de le montrer."""
    configuration = configuration_base()
    secret = (configuration or {}).get("password") or settings.EMAIL_HOST_PASSWORD
    return message.replace(secret, "••••••") if secret else message


def _contexte_ssl() -> ssl.SSLContext:
    contexte = ssl.create_default_context()
    if not getattr(settings, "EMAIL_SSL_CERT_VERIFY", True):
        contexte.check_hostname = False
        contexte.verify_mode = ssl.CERT_NONE
    return contexte


def sonder_connexion(
    hote: str,
    port: int,
    chiffrement: str,
    identifiant: str = "",
    mot_de_passe: str = "",
    delai: int = 12,
) -> dict[str, Any]:
    """Teste la connexion SMTP **étape par étape** pour dire laquelle casse.

    Étapes : `tcp` (le port répond), `banniere` (le serveur dit bonjour), `chiffrement`
    (STARTTLS / SSL), `authentification` (identifiant + mot de passe). « Connexion coupée »
    seul ne dit rien ; « coupée juste après le bonjour » désigne un pare-feu.
    """
    etape = "tcp"
    smtp = None
    try:
        socket.create_connection((hote, port), timeout=delai).close()
        etape = "banniere"
        if chiffrement == ParametresMessagerie.Chiffrement.SSL:
            smtp = smtplib.SMTP_SSL(hote, port, timeout=delai, context=_contexte_ssl())
        else:
            smtp = smtplib.SMTP(hote, port, timeout=delai)
            etape = "chiffrement"
            smtp.ehlo()
            if chiffrement == ParametresMessagerie.Chiffrement.STARTTLS:
                smtp.starttls(context=_contexte_ssl())
                smtp.ehlo()
        if identifiant and mot_de_passe:
            etape = "authentification"
            smtp.login(identifiant, mot_de_passe)
        return {"ok": True, "etape": None, "detail": None}
    except Exception as exception:  # noqa: BLE001
        return {"ok": False, "etape": etape, "detail": _nettoyer(f"{type(exception).__name__} : {exception}")}
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass


def _alternatives(reglage: dict[str, Any]) -> list[dict[str, Any]]:
    """Les deux modes usuels de Gmail, quand celui qu'on utilise ne passe pas."""
    resultats = []
    for port, chiffrement in ((587, "STARTTLS"), (465, "SSL")):
        if port == reglage["port"] and chiffrement == reglage["chiffrement"]:
            continue
        sonde = sonder_connexion(reglage["hote"], port, chiffrement)
        resultats.append({"port": port, "chiffrement": chiffrement, **sonde})
    return resultats


def diagnostiquer_envoi(destinataire: str) -> dict[str, Any]:
    """Envoie un message de test et dit **où** ça casse — connexion ou envoi — et pourquoi."""
    from apps.core.emails import adresse_frontend

    from apps.core.email_backend import nom_ehlo

    reglage = reglage_effectif()
    connexion = get_connection(fail_silently=False)
    etape = "connexion"
    try:
        connexion.open()
        etape = "envoi"
        message = EmailMultiAlternatives(
            subject="[CCD Digital] Test de la messagerie de la plateforme",
            body=(
                "Ce message confirme que la messagerie de la plateforme CCD Digital envoie "
                "correctement.\n\nAdresse du frontend utilisée dans les liens : "
                f"{adresse_frontend()}\n"
            ),
            from_email=expediteur_actif(),
            to=[destinataire],
            connection=connexion,
        )
        message.send(fail_silently=False)
        return {
            "succes": True,
            "etape": None,
            "erreur": None,
            "conseil": None,
            "sonde": None,
            "alternatives": [],
            "reglage": reglage,
        }
    except Exception as exception:  # noqa: BLE001 — c'est précisément ce qu'on veut montrer
        logger.warning("Diagnostic de messagerie en échec à l'étape %s : %s", etape, type(exception).__name__)
        conseil = _conseil(exception, reglage)
        sonde, alternatives = None, []
        # Le serveur a répondu et refusé (identifiant, expéditeur) : ce n'est pas une panne réseau,
        # la sonde et ses alternatives n'ont rien à apprendre.
        refus = isinstance(
            exception,
            (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused),
        )
        if etape == "connexion" and not refus:
            configuration = configuration_base()
            sonde = sonder_connexion(
                reglage["hote"],
                reglage["port"],
                reglage["chiffrement"],
                (configuration or {}).get("username") or settings.EMAIL_HOST_USER,
                (configuration or {}).get("password") or settings.EMAIL_HOST_PASSWORD,
            )
            alternatives = _alternatives(reglage)
            ouverts = [a for a in alternatives if a["ok"]]
            if ouverts:
                autre = ouverts[0]
                conseil = (
                    f"Le port {reglage['port']} ne passe pas, mais le port {autre['port']} "
                    f"({autre['chiffrement']}) répond : essayez ce réglage."
                )
            elif sonde and sonde["etape"] == "tcp":
                conseil = (
                    f"Le serveur n'atteint même pas {reglage['hote']}:{reglage['port']} : "
                    "l'hébergeur bloque probablement les envois sortants. Demandez-lui d'ouvrir "
                    "les ports SMTP sortants (465 et 587), ou utilisez un service d'envoi par API."
                )
        return {
            "succes": False,
            "etape": etape,
            "erreur": _nettoyer(f"{type(exception).__name__} : {exception}"),
            "conseil": conseil,
            "sonde": sonde,
            "alternatives": alternatives,
            "nom_ehlo": nom_ehlo(),
            "reglage": reglage,
        }
    finally:
        try:
            connexion.close()
        except Exception:  # noqa: BLE001
            pass
