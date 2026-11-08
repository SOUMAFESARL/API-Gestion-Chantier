"""Aide aux commandes de gestion : retrouver une entreprise par son slug ou son identifiant."""

from __future__ import annotations

import uuid

from django.core.management.base import CommandError



def trouver_entreprise(identifiant: str):
    """Une entreprise par son identifiant, ou par son slug."""
    from apps.entreprises.models import Entreprise

    try:
        cle = uuid.UUID(str(identifiant))
    except ValueError:
        cle = None
    entreprise = (
        Entreprise.objects.filter(pk=cle).first()
        if cle
        else Entreprise.objects.filter(slug=str(identifiant).strip().lower()).first()
    )
    if entreprise is None:
        raise CommandError(f"Aucune entreprise « {identifiant} ».")
    return entreprise


