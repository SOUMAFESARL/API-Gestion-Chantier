"""Services métier pour la gestion des blocages de chantier (MLD §6.6, CDC Module 2).

Schéma : tenant.
Chaque mutation déclenche un recalcul réactif asynchrone de l'indice de santé (C8).
"""

from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.chantier.models import Blocage
from apps.core.enums import SeveriteBlocage, StatutBlocage
from apps.core.exceptions import ErreurMetier
from apps.projets.models import Activite, Lot, Projet
from apps.projets.services.sante_declencheur import declencher_recalcul_sante

__all__ = [
    "cloturer_blocage",
    "creer_blocage",
    "modifier_blocage",
    "prendre_en_charge_blocage",
    "resoudre_blocage",
]


@transaction.atomic
def creer_blocage(
    *,
    projet: Projet,
    titre: str,
    severite: str,
    auteur: Utilisateur,
    description: str = "",
    lot: Lot | None = None,
    activite: Activite | None = None,
    cree_par: Utilisateur | None = None,
) -> Blocage:
    """Crée un nouveau blocage de chantier et planifie le recalcul de santé."""
    if lot is not None and lot.projet_id != projet.id:
        raise ValidationError({"lot": "Le lot sélectionné n'appartient pas au projet spécifié."})

    blocage = Blocage.objects.create(
        projet=projet,
        lot=lot,
        titre=titre,
        description=description,
        severite=severite,
        statut=StatutBlocage.OUVERT,
        ouvert_le=timezone.now(),
        ouvert_par=auteur,
        cree_par=cree_par or auteur,
    )

    declencher_recalcul_sante(
        projet_id=projet.id,
        declencheur_type="BLOCAGE_CREATION",
        declencheur_id=blocage.id,
    )
    return blocage


@transaction.atomic
def modifier_blocage(
    *,
    blocage: Blocage,
    modifie_par: Utilisateur,
    **champs: Any,
) -> Blocage:
    """Modifie les informations d'un blocage et planifie le recalcul de santé si la sévérité change."""
    champs_modifiables = [
        "titre",
        "description",
        "severite",
        "impact_delai_jours",
        "action_attendue",
        "responsable_action",
    ]
    severite_changee = False
    statut_change = False
    for champ in champs_modifiables:
        if champ in champs:
            if champ == "severite" and champs[champ] != blocage.severite:
                severite_changee = True
            if champ == "statut" and champs[champ] != blocage.statut:
                statut_change = True
            setattr(blocage, champ, champs[champ])

    blocage.save()

    if severite_changee or statut_change:
        declencher_recalcul_sante(
            projet_id=blocage.projet_id,
            declencheur_type="BLOCAGE_MODIFICATION",
            declencheur_id=blocage.id,
        )
    return blocage


@transaction.atomic
def prendre_en_charge_blocage(
    *,
    blocage: Blocage,
    utilisateur: Utilisateur,
) -> Blocage:
    """Passe un blocage au statut PRIS_EN_CHARGE."""
    if blocage.statut not in {StatutBlocage.OUVERT, StatutBlocage.PRIS_EN_CHARGE}:
        raise ErreurMetier("Ce blocage ne peut pas être pris en charge dans son état actuel.")

    blocage.statut = StatutBlocage.PRIS_EN_CHARGE
    blocage.save(update_fields=["statut", "modifie_le"])

    # Le statut reste actif pour le calcul de santé, mais on notifie le recalcul
    declencher_recalcul_sante(
        projet_id=blocage.projet_id,
        declencheur_type="BLOCAGE_PRISE_EN_CHARGE",
        declencheur_id=blocage.id,
    )
    return blocage


@transaction.atomic
def resoudre_blocage(
    *,
    blocage: Blocage,
    utilisateur: Utilisateur,
    commentaire_resolution: str = "",
) -> Blocage:
    """Résout un blocage : retire le blocage de l'assiette de pénalité de santé."""
    if blocage.statut == StatutBlocage.RESOLU:
        raise ErreurMetier("Ce blocage est déjà résolu.")

    blocage.statut = StatutBlocage.RESOLU
    blocage.resolu_le = timezone.now()
    blocage.resolu_par = utilisateur
    blocage.save(
        update_fields=[
            "statut",
            "resolu_le",
            "resolu_par",
            "modifie_le",
        ]
    )

    declencher_recalcul_sante(
        projet_id=blocage.projet_id,
        declencheur_type="BLOCAGE_RESOLUTION",
        declencheur_id=blocage.id,
    )
    return blocage


@transaction.atomic
def cloturer_blocage(
    *,
    blocage: Blocage,
    utilisateur: Utilisateur,
) -> Blocage:
    """Clôture définitivement un blocage."""
    if blocage.statut == StatutBlocage.CLOTURE:
        return blocage

    blocage.statut = StatutBlocage.CLOTURE
    if not blocage.resolu_le:
        blocage.resolu_le = timezone.now()
        blocage.resolu_par = utilisateur
    blocage.save(update_fields=["statut", "resolu_le", "resolu_par", "modifie_le"])

    declencher_recalcul_sante(
        projet_id=blocage.projet_id,
        declencheur_type="BLOCAGE_CLOTURE",
        declencheur_id=blocage.id,
    )
    return blocage
