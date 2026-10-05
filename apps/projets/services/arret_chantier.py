"""Services métier pour la gestion des arrêts de chantier (MLD §6.5, C2, C8).

Schéma : tenant.
Chaque déclaration, fin ou suppression d'arrêt de chantier planifie un recalcul de santé.
"""

from datetime import date
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.exceptions import ErreurMetier
from apps.projets.models import ArretChantier, Projet
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

__all__ = [
    "declarer_arret_chantier",
    "supprimer_arret_chantier",
    "terminer_arret_chantier",
]


@transaction.atomic
def declarer_arret_chantier(
    *,
    projet: Projet,
    date_debut: date,
    motif: str,
    auteur: Utilisateur,
    date_fin: date | None = None,
    commentaire: str = "",
    cree_par: Utilisateur | None = None,
) -> ArretChantier:
    """Déclare un arrêt de chantier sur le projet.

    Unicité : un seul arrêt ouvert (date_fin is None) par projet à la fois.
    """
    if date_fin is not None and date_fin < date_debut:
        raise ValidationError({"date_fin": "La date de fin ne peut pas être antérieure à la date de début."})

    # Vérification d'absence d'arrêt ouvert existant si le nouvel arrêt est ouvert
    if date_fin is None:
        arret_ouvert = projet.arrets_chantier.filter(
            supprime_le__isnull=True,
            date_fin__isnull=True,
        ).exists()
        if arret_ouvert:
            raise ErreurMetier("Un arrêt de chantier est déjà en cours sur ce projet.")

    arret = ArretChantier.objects.create(
        projet=projet,
        date_debut=date_debut,
        date_fin=date_fin,
        motif=motif,
        commentaire=commentaire,
        declare_par=auteur,
        cree_par=cree_par or auteur,
    )

    declencher_recalcul_sante(
        projet_id=projet.id,
        declencheur_type="ARRET_DECLARATION",
        declencheur_id=arret.id,
    )
    return arret


@transaction.atomic
def terminer_arret_chantier(
    *,
    arret: ArretChantier,
    date_fin: date,
    utilisateur: Utilisateur,
) -> ArretChantier:
    """Termine un arrêt de chantier en renseignant sa date de fin."""
    if date_fin < arret.date_debut:
        raise ValidationError({"date_fin": "La date de fin ne peut pas précéder la date de début de l'arrêt."})

    arret.date_fin = date_fin
    arret.modifie_par = utilisateur
    arret.save(update_fields=["date_fin", "modifie_par", "modifie_le"])

    declencher_recalcul_sante(
        projet_id=arret.projet_id,
        declencheur_type="ARRET_FIN",
        declencheur_id=arret.id,
    )
    return arret


@transaction.atomic
def supprimer_arret_chantier(
    *,
    arret: ArretChantier,
    utilisateur: Utilisateur,
) -> ArretChantier:
    """Suppression logique d'un arrêt de chantier."""
    arret.supprime_le = timezone.now()
    arret.modifie_par = utilisateur
    arret.save(update_fields=["supprime_le", "modifie_par", "modifie_le"])

    declencher_recalcul_sante(
        projet_id=arret.projet_id,
        declencheur_type="ARRET_SUPPRESSION",
        declencheur_id=arret.id,
    )
    return arret
