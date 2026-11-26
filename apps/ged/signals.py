"""Signaux Django du module GED — ponts automatiques F1 & F2 vers F6.

Branchés dans `GedConfig.ready()` (`apps/ged/apps.py`).
Chaque récepteur diffère le travail via `transaction.on_commit(...)` pour garantir :
- la disponibilité des fichiers et relations validées en base ;
- le cloisonnement multi-entreprise D9 ;
- la non-interruption des workflows F1/F2 en cas d'anomalie documentaire.
"""

from __future__ import annotations

from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.chantier.models import RapportJournalier
from apps.core.enums import StatutRapport
from apps.ged.services.archivage_auto import (
    archiver_avenant_par_id,
    archiver_contrat_projet_par_id,
    archiver_ordre_service_projet_par_id,
    archiver_rapport_approuve_par_id,
)
from apps.projets.models import Avenant, Projet, ProjetContrat


@receiver(
    post_save,
    sender=ProjetContrat,
    dispatch_uid="ged_archiver_contrat_projet",
)
def archiver_contrat_projet_apres_save(
    sender, instance, created=False, update_fields=None, **kwargs
):
    """Archive automatiquement un contrat du marché dans la GED (F1 -> F6)."""
    if kwargs.get("raw"):
        return
    if getattr(instance, "supprime_le", None) is not None or not instance.fichier:
        return
    if (
        not created
        and update_fields is not None
        and "fichier" not in update_fields
        and "est_actif" not in update_fields
    ):
        return

    contrat_id = instance.pk
    entreprise_id = instance.entreprise_id or getattr(
        getattr(instance, "projet", None), "entreprise_id", None
    )
    if not contrat_id or not entreprise_id:
        return

    transaction.on_commit(
        partial(archiver_contrat_projet_par_id, contrat_id, entreprise_id)
    )


@receiver(
    post_save,
    sender=Projet,
    dispatch_uid="ged_archiver_ordre_service_projet",
)
def archiver_ordre_service_projet_apres_save(
    sender, instance, created=False, update_fields=None, **kwargs
):
    """Archive automatiquement l'ordre de service de démarrage d'un projet en GED."""
    if kwargs.get("raw"):
        return
    if getattr(instance, "supprime_le", None) is not None or not instance.ordre_service:
        return
    os_modifie = bool(getattr(instance, "_ordre_service_modifie", False))
    if not created and not os_modifie and (
        update_fields is None or "ordre_service" not in update_fields
    ):
        return

    projet_id = instance.pk
    entreprise_id = instance.entreprise_id
    if not projet_id or not entreprise_id:
        return

    auteur_os = getattr(instance, "_auteur_ordre_service", None)
    auteur_id = (
        getattr(auteur_os, "pk", None)
        if auteur_os is not None and getattr(auteur_os, "is_authenticated", True)
        else instance.cree_par_id
    )
    instance._ordre_service_modifie = False

    transaction.on_commit(
        partial(archiver_ordre_service_projet_par_id, projet_id, entreprise_id, auteur_id)
    )


@receiver(
    post_save,
    sender=Avenant,
    dispatch_uid="ged_archiver_avenant",
)
def archiver_avenant_apres_save(
    sender, instance, created=False, update_fields=None, **kwargs
):
    """Archive automatiquement le document signé et l'ordre de service d'un avenant."""
    if kwargs.get("raw"):
        return
    if getattr(instance, "supprime_le", None) is not None:
        return
    if not instance.document and not instance.ordre_service:
        return
    if (
        not created
        and update_fields is not None
        and "document" not in update_fields
        and "ordre_service" not in update_fields
    ):
        return

    avenant_id = instance.pk
    entreprise_id = instance.entreprise_id or getattr(
        getattr(instance, "projet", None), "entreprise_id", None
    )
    if not avenant_id or not entreprise_id:
        return

    transaction.on_commit(
        partial(archiver_avenant_par_id, avenant_id, entreprise_id)
    )


@receiver(
    post_save,
    sender=RapportJournalier,
    dispatch_uid="ged_archiver_rapport_approuve",
)
def archiver_rapport_approuve_apres_save(
    sender, instance, created=False, update_fields=None, **kwargs
):
    """Archive photos, pièces jointes et synthèse PDF dès qu'un rapport est approuvé."""
    if kwargs.get("raw"):
        return
    if (
        getattr(instance, "supprime_le", None) is not None
        or instance.statut != StatutRapport.APPROUVE
    ):
        return
    if not created and update_fields is not None and "statut" not in update_fields:
        return

    rapport_id = instance.pk
    entreprise_id = instance.entreprise_id or getattr(
        getattr(instance, "projet", None), "entreprise_id", None
    )
    if not rapport_id or not entreprise_id:
        return

    transaction.on_commit(
        partial(archiver_rapport_approuve_par_id, rapport_id, entreprise_id)
    )
