"""Service centralisé de notification et de traçabilité des actions Super Admin (A-14, H-01).

Règles de gestion :
- A-14 & H-01 : Notification par courriel du Directeur Général (DG) de l'entreprise.
  * Sujet assistance : "Session d'assistance ouverte sur votre espace"
  * Sujet modifications : "Modification de votre espace par l'administration de la plateforme"
  * Un seul courriel par entreprise et par action, envoyé après validation de transaction
    (transaction.on_commit).
  * Aucun courriel si la transaction échoue ou si l'entreprise n'a aucun DG actif.
- H-02 : Chaque action d'écriture du Super Admin crée exactement une entrée dans
  JournalPlateforme (table de plateforme).
- L9-1 : Chaque action modifiant l'espace d'une entreprise crée exactement une entrée dans
  JournalAudit (table d'entreprise).
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.core.contexte import contexte_entreprise
from apps.accounts.models import Utilisateur
from apps.audit.models import JournalAudit
from apps.core.droits import est_dg
from apps.core.emails import envoyer
from apps.core.enums import ActionAudit, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.entreprises.models import Entreprise

logger = logging.getLogger(__name__)

SUJET_ASSISTANCE = "Session d'assistance ouverte sur votre espace"
SUJET_MODIFICATION_PLATEFORME = "Modification de votre espace par l'administration de la plateforme"
SUJET_SUPPRESSION_ENTREPRISE = "Suppression de votre espace CCD Digital"


def trouver_dg_actif_entreprise(entreprise: Entreprise) -> Utilisateur | None:
    """Trouve l'utilisateur actif faisant office de DG dans l'entreprise."""
    with contexte_entreprise(entreprise):
        candidats = Utilisateur.objects.filter(
            supprime_le__isnull=True,
            is_active=True,
            statut=StatutUtilisateur.ACTIF,
        ).order_by("-is_owner", "cree_le")
        for u in candidats:
            if est_dg(u):
                return u
    return None


def notifier_dg_action_plateforme(
    entreprise: Entreprise,
    sujet: str,
    message: str,
    super_admin_email: str = "",
) -> None:
    """Planifie l'envoi d'un courriel au DG de l'entreprise après commit (A-14, H-01)."""
    dg = trouver_dg_actif_entreprise(entreprise)
    if not dg or not dg.email:
        logger.info(
            "Aucun DG actif trouvé pour l'entreprise %s : aucun e-mail envoyé.",
            entreprise.slug,
        )
        return

    destinataire = dg.email

    def _envoyer():
        # L'expéditeur est `DEFAULT_FROM_EMAIL` : l'ancien `support@plateforme.local` n'existait
        # nulle part, et un relais SMTP authentifié refuse un expéditeur qui n'est pas le sien.
        envoye = envoyer(
            "notification_plateforme",
            sujet,
            destinataire,
            {"sujet": sujet, "message": message, "raison_sociale": entreprise.raison_sociale},
        )
        if envoye:
            logger.info(
                "Courriel envoyé au DG de l'entreprise %s : %s",
                entreprise.slug,
                sujet,
            )
        else:
            logger.error(
                "Courriel au DG de l'entreprise %s NON envoyé : %s",
                entreprise.slug,
                sujet,
            )

    transaction.on_commit(_envoyer)


def journaliser_plateforme(
    action: str,
    acteur: Utilisateur | None = None,
    entreprise: Entreprise | None = None,
    detail: dict[str, Any] | None = None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> JournalPlateforme:
    """Crée exactement une entrée dans le JournalPlateforme (plateforme, H-02)."""
    user_id = getattr(acteur, "id", None)
    ent_id = getattr(entreprise, "id", None)
    return JournalPlateforme.objects.create(
        utilisateur_id=user_id,
        entreprise_id=ent_id,
        action=action,
        detail=detail or {},
        adresse_ip=adresse_ip,
        appareil=appareil[:255] if appareil else "",
    )


def journaliser_entreprise(
    entreprise: Entreprise,
    action: ActionAudit | str,
    type_entite: str,
    entite_id: Any,
    valeur_apres: dict[str, Any] | None = None,
    acteur: Utilisateur | None = None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> None:
    """Crée exactement une entrée dans le JournalAudit de l'entreprise (L9-1)."""
    with contexte_entreprise(entreprise):
        user_id = getattr(acteur, "id", None)
        JournalAudit.objects.create(
            utilisateur_id=user_id,
            action=str(action),
            type_entite=type_entite,
            entite_id=entite_id,
            valeur_apres=valeur_apres or {},
            adresse_ip=adresse_ip,
            appareil=appareil[:255] if appareil else "",
        )
