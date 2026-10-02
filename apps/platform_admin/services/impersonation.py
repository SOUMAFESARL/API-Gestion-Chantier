"""Service d'assistance Super Admin (Impersonification) — Socle Commun & R-128.

Règles de sécurité appliquées :
- R-128 : L'impersonification est en lecture seule stricte et tracée des deux côtés.
- Durée : Session limitée à 1 heure (3600 s), non renouvelable.
- Traçabilité double :
  1. Schéma `public` dans `JournalPlateforme`
  2. Schéma client `tenant_x` dans `JournalAudit`
- Garde-fou d'écriture : Interception et rejet de toute mutation en mode assistance.
"""

import logging
import uuid
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Utilisateur
from apps.accounts.services.authentification import profil_de_connexion
from apps.audit.services import journaliser
from apps.core.enums import ActionAudit, RoleGlobal, StatutUtilisateur
from apps.core.exceptions import ErreurMetier
from apps.platform_admin.models import JournalPlateforme
from apps.tenants.models import Entreprise

logger = logging.getLogger(__name__)

DUREE_SESSION_ASSISTANCE = timedelta(hours=1)


class ActionInterditeAssistance(ErreurMetier):
    """Refus lors d'une tentative d'action interdite en mode assistance."""

    status_code = 403
    code_metier = "ecriture_interdite_assistance"
    default_detail = _(
        "Les modifications sont strictement interdites en mode assistance Super Admin (lecture seule)."
    )


def verifier_super_admin(utilisateur: Utilisateur) -> None:
    """Vérifie que l'utilisateur appelant a bien les prérogatives Super Admin."""
    if not utilisateur or not utilisateur.is_authenticated:
        raise PermissionDenied(_("Authentification requise."))

    # Le super admin doit vivre dans le schéma public
    schema_courant = getattr(connection, "schema_name", "public")
    public_schema = get_public_schema_name()

    est_super_admin = (
        schema_courant == public_schema or getattr(utilisateur, "is_staff", False)
    ) and (
        utilisateur.role_global == RoleGlobal.ADMIN
        or getattr(utilisateur, "is_superuser", False)
        or getattr(utilisateur, "is_staff", False)
    )

    if not est_super_admin:
        raise PermissionDenied(
            _("Seul un Super Administrateur peut démarrer une session d'assistance.")
        )


def lister_utilisateurs_entreprise(entreprise_id: uuid.UUID | str) -> list[dict]:
    """Liste les utilisateurs d'une entreprise cliente pour permettre le ciblage d'assistance."""
    entreprise = Entreprise.objects.filter(pk=entreprise_id).first()
    if not entreprise:
        raise ErreurMetier("entreprise_introuvable", _("Entreprise cliente introuvable."))

    utilisateurs = []
    with schema_context(entreprise.schema_name):
        qs = Utilisateur.objects.filter(supprime_le__isnull=True).order_by(
            "-is_owner", "nom", "prenom"
        )
        for u in qs:
            utilisateurs.append(
                {
                    "id": str(u.id),
                    "nom": u.nom,
                    "prenom": u.prenom,
                    "email": u.email,
                    "role_global": u.role_global,
                    "role_libelle": u.get_role_global_display(),
                    "is_owner": u.is_owner,
                    "is_dg": u.is_dg,
                    "statut": u.statut,
                }
            )
    return utilisateurs


def demarrer_session_assistance(
    super_admin: Utilisateur,
    entreprise_id: uuid.UUID | str,
    motif: str,
    utilisateur_id: uuid.UUID | str | None = None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> dict:
    """Ouvre une session d'assistance Super Admin (impersonification en lecture seule).

    - Vérifie les droits Super Admin
    - Valide le motif (min 5 caractères)
    - Sélectionne l'utilisateur cible dans le tenant
    - Émet le jeton JWT d'assistance (1h, non renouvelable, lecture seule)
    - Trace l'accès dans `JournalPlateforme` (schéma public) et `JournalAudit` (schéma client)
    """
    verifier_super_admin(super_admin)

    motif_nettoye = (motif or "").strip()
    if len(motif_nettoye) < 5:
        raise ErreurMetier(
            "motif_assistance_invalide",
            _("Le motif d'intervention doit contenir au moins 5 caractères."),
        )

    entreprise = Entreprise.objects.filter(pk=entreprise_id).first()
    if not entreprise:
        raise ErreurMetier("entreprise_introuvable", _("Entreprise cliente introuvable."))

    target_user: Utilisateur | None = None
    with schema_context(entreprise.schema_name):
        if utilisateur_id:
            target_user = Utilisateur.objects.filter(
                pk=utilisateur_id, supprime_le__isnull=True
            ).first()
        else:
            # DG ou propriétaire par défaut, sinon premier utilisateur actif
            target_user = (
                Utilisateur.objects.filter(is_owner=True, supprime_le__isnull=True).first()
                or Utilisateur.objects.filter(
                    role_global=RoleGlobal.DIRECTEUR_GENERAL, supprime_le__isnull=True
                ).first()
                or Utilisateur.objects.filter(
                    statut=StatutUtilisateur.ACTIF, supprime_le__isnull=True
                ).first()
            )

        if not target_user:
            raise ErreurMetier(
                "utilisateur_introuvable",
                _("Aucun utilisateur disponible pour cette entreprise cliente."),
            )

        # Construction du profil de l'utilisateur assisté
        profil_client = profil_de_connexion(target_user)

    # Création du jeton JWT d'accès spécifique pour l'assistance (1 heure stricte)
    token = AccessToken.for_user(target_user)
    token.set_exp(lifetime=DUREE_SESSION_ASSISTANCE)
    token["schema"] = entreprise.schema_name
    token["role_global"] = target_user.role_global
    token["is_impersonation"] = True
    token["read_only"] = True
    token["impersonateur_id"] = str(super_admin.id)
    token["impersonateur_email"] = super_admin.email
    token["impersonateur_nom"] = f"{super_admin.nom} {super_admin.prenom}".strip()
    token["motif"] = motif_nettoye
    token["sid"] = str(uuid.uuid4())

    token_str = str(token)
    duree_secondes = int(DUREE_SESSION_ASSISTANCE.total_seconds())

    # 1. Écriture dans le Journal de Plateforme (schéma `public` — MLD §4.6)
    with schema_context(get_public_schema_name()):
        JournalPlateforme.objects.create(
            utilisateur_id=super_admin.id,
            entreprise_id=entreprise.id,
            action="CONNEXION_ASSISTANCE",
            detail={
                "super_admin_id": str(super_admin.id),
                "super_admin_email": super_admin.email,
                "super_admin_nom": f"{super_admin.nom} {super_admin.prenom}".strip(),
                "cible_utilisateur_id": str(target_user.id),
                "cible_email": target_user.email,
                "cible_nom": f"{target_user.nom} {target_user.prenom}".strip(),
                "entreprise_nom": entreprise.nom_commercial or entreprise.raison_sociale,
                "entreprise_schema": entreprise.schema_name,
                "motif": motif_nettoye,
                "mode": "LECTURE_SEULE",
                "expire_dans_secondes": duree_secondes,
            },
            adresse_ip=adresse_ip,
            appareil=appareil[:255] if appareil else "",
        )

    # 2. Écriture dans le Journal d'Audit Client (schéma `tenant_x` — R-128)
    with schema_context(entreprise.schema_name):
        journaliser(
            action=ActionAudit.ASSISTANCE,
            type_entite="Entreprise",
            entite_id=entreprise.id,
            utilisateur_id=target_user.id,
            valeur_apres={
                "evenement": "Ouverture de session d'assistance Super Admin",
                "super_admin_id": str(super_admin.id),
                "super_admin_email": super_admin.email,
                "super_admin_nom": f"{super_admin.nom} {super_admin.prenom}".strip(),
                "motif": motif_nettoye,
                "mode": "LECTURE_SEULE",
                "duree_secondes": duree_secondes,
            },
            adresse_ip=adresse_ip,
            appareil=appareil[:255] if appareil else "",
        )

    logger.info(
        "Session d'assistance ouverte : super_admin=%s entreprise=%s cible=%s motif=%s",
        super_admin.email,
        entreprise.schema_name,
        target_user.email,
        motif_nettoye,
    )

    return {
        "access": token_str,
        "expire_dans": duree_secondes,
        "impersonation": {
            "actif": True,
            "mode": "LECTURE_SEULE",
            "super_admin": {
                "id": str(super_admin.id),
                "email": super_admin.email,
                "nom": f"{super_admin.nom} {super_admin.prenom}".strip(),
            },
            "entreprise": {
                "id": str(entreprise.id),
                "raison_sociale": entreprise.raison_sociale,
                "nom_commercial": entreprise.nom_commercial or entreprise.raison_sociale,
                "schema_name": entreprise.schema_name,
            },
            "utilisateur": {
                "id": str(target_user.id),
                "nom": target_user.nom,
                "prenom": target_user.prenom,
                "email": target_user.email,
                "role_global": target_user.role_global,
                "role_libelle": target_user.get_role_global_display(),
            },
            "motif": motif_nettoye,
        },
        "utilisateur": profil_client,
        "url_redirection": "/tableau-de-bord",
    }


def clore_session_assistance(
    super_admin_id: uuid.UUID | str | None,
    super_admin_email: str = "",
    entreprise_id: uuid.UUID | str | None = None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> None:
    """Journalise la fermeture volontaire d'une session d'assistance."""
    # 1. Schéma public
    with schema_context(get_public_schema_name()):
        JournalPlateforme.objects.create(
            utilisateur_id=super_admin_id if super_admin_id else None,
            entreprise_id=entreprise_id if entreprise_id else None,
            action="DECONNEXION_ASSISTANCE",
            detail={
                "super_admin_id": str(super_admin_id) if super_admin_id else "",
                "super_admin_email": super_admin_email,
                "statut": "TERMINE",
            },
            adresse_ip=adresse_ip,
            appareil=appareil[:255] if appareil else "",
        )

    # 2. Schéma client si l'entreprise est connue
    if entreprise_id:
        entreprise = Entreprise.objects.filter(pk=entreprise_id).first()
        if entreprise:
            with schema_context(entreprise.schema_name):
                journaliser(
                    action=ActionAudit.DECONNEXION,
                    type_entite="SessionAssistance",
                    entite_id=entreprise.id,
                    utilisateur_id=super_admin_id if super_admin_id else None,
                    valeur_apres={
                        "evenement": "Fermeture de session d'assistance Super Admin",
                        "super_admin_id": str(super_admin_id) if super_admin_id else "",
                        "super_admin_email": super_admin_email,
                    },
                    adresse_ip=adresse_ip,
                    appareil=appareil[:255] if appareil else "",
                )
