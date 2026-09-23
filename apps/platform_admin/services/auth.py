"""Service d'authentification Super Admin — Plateforme CCD Digital (Control Plane).

Règles de gestion :
- Seul un compte présent dans le schéma `public` avec `is_superuser=True` peut s'authentifier.
- Toute tentative infructueuse (compte inexistant, mot de passe erroné, utilisateur non superuser)
  renvoie 401 IdentifiantsInvalides avec une égalité temporelle stricte.
- Traçabilité complète des connexions et déconnexions dans `JournalPlateforme` (schéma `public`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Utilisateur
from apps.accounts.services.authentification import (
    IdentifiantsInvalides,
    duree_acces_en_secondes,
    emettre_jetons,
)
from apps.accounts.services.deconnexion import deconnecter
from apps.accounts.services.renouvellement import renouveler
from apps.core.exceptions import ErreurMetier
from apps.platform_admin.models import JournalPlateforme

logger = logging.getLogger(__name__)

__all__ = [
    "authentifier_super_admin",
    "deconnecter_super_admin",
    "renouveler_super_admin",
]


def authentifier_super_admin(
    email: str,
    mot_de_passe: str,
    adresse_ip: str | None = None,
    appareil: str = "",
    origine: str = "WEB",
) -> dict[str, object]:
    """Authentifie un Super Administrateur et émet ses jetons JWT.

    Vérifie impérativement que l'utilisateur appartient au schéma `public`
    et possède l'attribut `is_superuser=True`.
    """
    from apps.platform_admin.services.provisioning import auto_provisionner_super_admin

    auto_provisionner_super_admin()

    email_nettoye = email.strip().lower()
    public_schema = get_public_schema_name()
    echec: ErreurMetier | None = None
    super_admin: Utilisateur | None = None

    with schema_context(public_schema):
        with transaction.atomic():
            candidat = (
                Utilisateur.objects.select_for_update()
                .filter(email__iexact=email_nettoye)
                .first()
            )

            if candidat is None:
                # Égalité temporelle : hachage défensif contre l'énumération
                Utilisateur().set_password(mot_de_passe)
                echec = IdentifiantsInvalides()
            else:
                mot_de_passe_valide = candidat.check_password(mot_de_passe)
                est_valide = (
                    mot_de_passe_valide
                    and candidat.is_superuser
                    and candidat.is_active
                    and not candidat.est_bloque
                )

                if not est_valide:
                    candidat.enregistrer_echec_connexion()
                    echec = IdentifiantsInvalides()
                else:
                    candidat.reinitialiser_echecs()
                    Utilisateur.objects.filter(pk=candidat.pk).update(
                        last_login=timezone.now()
                    )
                    super_admin = candidat

    # En cas d'échec d'authentification
    if echec is not None or super_admin is None:
        try:
            with schema_context(public_schema):
                JournalPlateforme.objects.create(
                    action="ECHEC_CONNEXION_SUPER_ADMIN",
                    detail={
                        "email": email_nettoye,
                        "motif": "identifiants_invalides",
                        "statut": "ECHEC",
                    },
                    adresse_ip=adresse_ip,
                    appareil=appareil[:255] if appareil else "",
                )
        except Exception:
            logger.exception("Échec de journalisation d'audit pour tentative de connexion Super Admin.")
        raise echec or IdentifiantsInvalides()

    # Émission des jetons JWT standard SimpleJWT
    jetons = emettre_jetons(super_admin, origine=origine)

    # Profil compact Super Admin
    profil = {
        "id": str(super_admin.id),
        "email": super_admin.email,
        "nom": super_admin.nom,
        "prenom": super_admin.prenom,
        "role_global": super_admin.role_global,
        "role_libelle": super_admin.get_role_global_display(),
        "is_superuser": True,
        "is_staff": super_admin.is_staff,
        "langue": super_admin.langue,
        "schema": "public",
    }

    # Journalisation de l'accès réussi dans JournalPlateforme
    try:
        with schema_context(public_schema):
            JournalPlateforme.objects.create(
                utilisateur_id=super_admin.id,
                action="CONNEXION_SUPER_ADMIN",
                detail={
                    "email": super_admin.email,
                    "nom": f"{super_admin.nom} {super_admin.prenom}".strip(),
                    "role_global": super_admin.role_global,
                    "origine": origine,
                    "statut": "SUCCES",
                },
                adresse_ip=adresse_ip,
                appareil=appareil[:255] if appareil else "",
            )
    except Exception:
        logger.exception("Échec d'enregistrement de la connexion Super Admin dans JournalPlateforme.")

    return {
        "access": jetons["access"],
        "refresh": jetons["refresh"],
        "expire_dans": duree_acces_en_secondes(),
        "utilisateur": profil,
    }


def deconnecter_super_admin(
    refresh_token: str | None = None,
    utilisateur: Utilisateur | None = None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> None:
    """Clôture la session Super Admin et révoque le jeton de renouvellement."""
    public_schema = get_public_schema_name()

    # Révocation côté serveur via la liste noire Redis si jeton fourni
    if refresh_token:
        try:
            deconnecter(
                refresh_token,
                adresse_ip=adresse_ip,
                appareil=appareil,
            )
        except Exception as exc:
            logger.warning("Révocation refresh token lors de la déconnexion Super Admin : %s", exc)

    # Journalisation de la déconnexion dans JournalPlateforme
    try:
        user_id = None
        user_email = None
        if utilisateur and getattr(utilisateur, "is_authenticated", False):
            user_id = getattr(utilisateur, "id", None)
            user_email = getattr(utilisateur, "email", None)
        elif refresh_token:
            try:
                import jwt
                payload = jwt.decode(refresh_token, options={"verify_signature": False})
                token_uid = payload.get("user_id")
                if token_uid:
                    with schema_context(public_schema):
                        u = Utilisateur.objects.filter(pk=token_uid).first()
                        if u:
                            user_id = u.id
                            user_email = u.email
            except Exception:
                pass

        with schema_context(public_schema):
            JournalPlateforme.objects.create(
                utilisateur_id=user_id,
                action="DECONNEXION_SUPER_ADMIN",
                detail={
                    "email": user_email,
                    "statut": "SUCCES",
                },
                adresse_ip=adresse_ip,
                appareil=appareil[:255] if appareil else "",
            )
    except Exception:
        logger.exception("Échec d'enregistrement de la déconnexion Super Admin dans JournalPlateforme.")


def renouveler_super_admin(refresh_token: str) -> dict[str, str]:
    """Renouvelle la paire de jetons d'accès pour le Super Admin."""
    return renouveler(refresh_token)
