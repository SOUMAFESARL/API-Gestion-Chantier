"""Service d'envoi d'alerte email lors de la dégradation de l'indice de santé vers le ROUGE (C8, C9).

Règles de gouvernance :
- Déclenchement UNIQUEMENT lors d'une transition vers le badge ROUGE (ancien != ROUGE et nouveau == ROUGE).
- Destinataires : Chef de Projet du projet + Direction Générale & Administrateurs du tenant.
- Déduplication stricte des adresses emails.
- Traitement en tâche / fonction exécutée dans le contexte du tenant.
"""

import logging
from typing import Any
from uuid import UUID

from django.db.models import Q
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.core.emails import envoyer
from apps.core.enums import RoleGlobal
from apps.projets.models import Projet, SanteProjetSnapshot

logger = logging.getLogger(__name__)

__all__ = ["envoyer_alerte_sante_rouge", "obtenir_destinataires_alerte_rouge"]


def obtenir_destinataires_alerte_rouge(projet: Projet) -> list[str]:
    """Récupère la liste dédupliquée des destinataires (Chef de Projet + DG uniquement - F3)."""
    emails: set[str] = set()

    # 1. Chef de projet
    chef = getattr(projet, "chef_projet", None)
    if chef and getattr(chef, "email", None) and chef.is_active and chef.supprime_le is None:
        emails.add(chef.email.strip().lower())

    # 2. Direction Générale uniquement (retrait des ADMIN et autres rôles selon spécification F3)
    dgs = Utilisateur.objects.filter(
        supprime_le__isnull=True,
        is_active=True,
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
    )
    for u in dgs:
        if u.email:
            emails.add(u.email.strip().lower())

    return sorted(emails)


def envoyer_alerte_sante_rouge(
    schema_name: str,
    projet_id: UUID | str,
    snapshot_id: UUID | str | None = None,
) -> int:
    """Envoie l'email d'alerte de transition vers le ROUGE."""
    def _envoyer() -> int:
        projet = Projet.objects.filter(id=projet_id, supprime_le__isnull=True).first()
        if not projet:
            logger.warning("Alerte santé rouge annulée : projet %s introuvable.", projet_id)
            return 0

        snapshot = None
        if snapshot_id:
            snapshot = SanteProjetSnapshot.objects.filter(id=snapshot_id).first()
        if not snapshot:
            snapshot = projet.snapshots_sante.first()

        destinataires = obtenir_destinataires_alerte_rouge(projet)
        if not destinataires:
            logger.info(
                "Aucun destinataire trouvé pour l'alerte santé rouge du projet %s (%s).",
                projet.reference,
                schema_name,
            )
            return 0

        score = snapshot.score if snapshot else projet.indice_sante
        contexte = {
            "projet_nom": projet.nom,
            "projet_reference": projet.reference,
            "score": score,
            "avancement_physique": snapshot.avancement_physique if snapshot else projet.avancement_reel,
            "avancement_temporel": snapshot.avancement_temporel if snapshot else projet.avancement_theorique,
            "retard_pts": snapshot.delta if snapshot else 0,
            "p_delais": snapshot.p_delais if snapshot else 0,
            "p_blocages": snapshot.p_blocages if snapshot else 0,
            "p_reporting": snapshot.p_reporting if snapshot else 0,
            "plancher_applique": snapshot.plancher_applique if snapshot else False,
            "blocages_critiques": (snapshot.blocages_ouverts_par_severite.get("CRITIQUE", 0) if snapshot else 0),
        }

        sujet = f"🔴 Alerte Santé Projet : Passage au ROUGE (Score {score}/100) — {projet.nom}"
        succes = envoyer(
            gabarit="alerte_sante_rouge",
            sujet=sujet,
            destinataires=destinataires,
            contexte=contexte,
        )
        if succes:
            logger.info(
                "Alerte santé rouge envoyée avec succès à %d destinataires pour le projet %s.",
                len(destinataires),
                projet.reference,
            )
            return len(destinataires)
        return 0

    if schema_name:
        with schema_context(schema_name):
            return _envoyer()
    return _envoyer()
