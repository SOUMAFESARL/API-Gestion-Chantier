"""Service de réinitialisation du mot de passe Super Admin — Control Plane CCD Digital.

Règles de gestion :
- Seul un compte présent dans le schéma `public` avec `is_superuser=True` et `is_active=True`
  peut réinitialiser son mot de passe par ce canal.
- Toute demande pour un compte inexistant ou non superuser renvoie 202 Accepted
  sans émettre d'email, pour empêcher l'énumération d'adresses (silence défensif).
- Traçabilité complète dans `JournalPlateforme` (schéma `public`) pour :
  - La demande de réinitialisation (action `DEMANDE_REINITIALISATION_SUPER_ADMIN`).
  - La réinitialisation effective (action `REINITIALISATION_MOT_DE_PASSE_SUPER_ADMIN`).
- Vérification du jeton sans le consommer (règle R-32).
- Consommation atomique du jeton et révocation de toutes les sessions actives.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name, schema_context

from apps.accounts.models import (
    DUREE_JETON_REINITIALISATION,
    JetonReinitialisation,
    Utilisateur,
)
from apps.accounts.services.liste_noire import revoquer_utilisateur
from apps.accounts.services.reinitialisation import JetonExpire
from apps.core.emails import envoyer
from apps.platform_admin.models import JournalPlateforme

logger = logging.getLogger(__name__)

TTL_REVOCATION = 24 * 3600

__all__ = [
    "demander_reinitialisation_super_admin",
    "reinitialiser_mot_de_passe_super_admin",
    "verifier_jeton_super_admin",
]


def demander_reinitialisation_super_admin(
    email: str,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> dict[str, object]:
    """Initie la demande de réinitialisation pour un Super Admin.

    Répond toujours avec succès (202) pour éviter l'énumération d'adresses.
    Seuls les comptes ayant `is_superuser=True` dans `public` reçoivent un email.
    """
    adresse = (email or "").strip().lower()
    public_schema = get_public_schema_name()

    with schema_context(public_schema):
        candidat = Utilisateur.objects.filter(email__iexact=adresse).first()

        super_admin_valide = (
            candidat is not None
            and candidat.is_superuser
            and candidat.is_active
            and not candidat.est_bloque
        )

        if super_admin_valide and candidat is not None:
            jeton = uuid.uuid4()
            with transaction.atomic():
                # Invalider les jetons vivants antérieurs
                JetonReinitialisation.objects.filter(
                    utilisateur=candidat,
                    utilise_le__isnull=True,
                    invalide_le__isnull=True,
                ).update(invalide_le=timezone.now())

                JetonReinitialisation.objects.create(
                    utilisateur=candidat,
                    empreinte=JetonReinitialisation.empreinte_de(jeton),
                    motif=JetonReinitialisation.Motif.OUBLI,
                    expire_le=timezone.now() + DUREE_JETON_REINITIALISATION,
                    ip_demande=adresse_ip,
                )

                JournalPlateforme.objects.create(
                    utilisateur_id=candidat.id,
                    action="DEMANDE_REINITIALISATION_SUPER_ADMIN",
                    detail={
                        "email": candidat.email,
                        "statut": "SUCCES",
                    },
                    adresse_ip=adresse_ip,
                    appareil=appareil[:255] if appareil else "",
                )

            # Envoi de l'email hors transaction
            transaction.on_commit(lambda: _envoyer_email_reinitialisation(candidat, jeton))
        else:
            # Traçabilité d'une tentative sur compte inexistant ou inéligible
            try:
                JournalPlateforme.objects.create(
                    action="DEMANDE_REINITIALISATION_SUPER_ADMIN",
                    detail={
                        "email": adresse,
                        "statut": "IGNORE",
                        "motif": "compte_inexistant_ou_ineligible",
                    },
                    adresse_ip=adresse_ip,
                    appareil=appareil[:255] if appareil else "",
                )
            except Exception:
                logger.exception(
                    "Échec d'enregistrement de l'audit pour demande mot de passe admin ignorée."
                )

    return {
        "message": _(
            "Si cette adresse correspond à un compte administrateur, un email vient d'être envoyé."
        ),
        "expire_dans": int(DUREE_JETON_REINITIALISATION.total_seconds()),
    }


def _envoyer_email_reinitialisation(super_admin: Utilisateur, jeton: uuid.UUID) -> None:
    """Envoie l'email contenant le lien sécurisé avec fragment pour le Super Admin."""
    base_frontend = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    lien = f"{base_frontend}/admin/mot-de-passe/definir#jeton={jeton}"

    sujet = "Réinitialisation de votre mot de passe d'administration CCD Digital"
    envoyer(
        "reinitialisation",
        sujet,
        super_admin.email,
        {"motif": "oubli", "lien": lien},
    )


def verifier_jeton_super_admin(jeton_clair: str) -> JetonReinitialisation:
    """Vérifie la validité du jeton Super Admin sans le consommer (règle R-32)."""
    public_schema = get_public_schema_name()
    empreinte = JetonReinitialisation.empreinte_de(jeton_clair)

    with schema_context(public_schema):
        jeton = (
            JetonReinitialisation.objects.select_related("utilisateur")
            .filter(empreinte=empreinte)
            .first()
        )

        if jeton is None or not jeton.est_utilisable:
            raise JetonExpire()

        utilisateur = jeton.utilisateur
        if not (utilisateur.is_superuser and utilisateur.is_active):
            raise JetonExpire()

        return jeton


def reinitialiser_mot_de_passe_super_admin(
    jeton_clair: str,
    mot_de_passe: str,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> Utilisateur:
    """Consomme le jeton, applique le nouveau mot de passe et révoque les sessions existantes."""
    jeton = verifier_jeton_super_admin(jeton_clair)
    public_schema = get_public_schema_name()

    with schema_context(public_schema):
        super_admin = jeton.utilisateur

        # Validation de la robustesse du mot de passe selon règles Django
        validate_password(mot_de_passe, super_admin)

        with transaction.atomic():
            super_admin.set_password(mot_de_passe)
            super_admin.tentatives_echouees = 0
            super_admin.bloque_le = None
            if super_admin.doit_changer_mot_de_passe:
                super_admin.doit_changer_mot_de_passe = False

            super_admin.save(
                update_fields=[
                    "password",
                    "tentatives_echouees",
                    "bloque_le",
                    "doit_changer_mot_de_passe",
                    "modifie_le",
                ]
            )

            jeton.utilise_le = timezone.now()
            jeton.save(update_fields=["utilise_le", "modifie_le"])

            # Invalider d'autres éventuels jetons en cours
            JetonReinitialisation.objects.filter(
                utilisateur=super_admin,
                utilise_le__isnull=True,
                invalide_le__isnull=True,
            ).update(invalide_le=timezone.now())

            # Audit dans JournalPlateforme
            JournalPlateforme.objects.create(
                utilisateur_id=super_admin.id,
                action="REINITIALISATION_MOT_DE_PASSE_SUPER_ADMIN",
                detail={
                    "email": super_admin.email,
                    "statut": "SUCCES",
                },
                adresse_ip=adresse_ip,
                appareil=appareil[:255] if appareil else "",
            )

        # Révocation de toutes les sessions actives dans Redis
        revoquer_utilisateur(super_admin.pk, ttl=TTL_REVOCATION)

        # Notification de confirmation par email
        transaction.on_commit(
            lambda: envoyer(
                "mot_de_passe_modifie",
                "Votre mot de passe d'administration CCD Digital a été modifié",
                super_admin.email,
                {},
            )
        )

        return super_admin
