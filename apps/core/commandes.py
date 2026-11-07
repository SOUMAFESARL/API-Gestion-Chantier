"""Aide aux commandes de gestion : `--entreprise`, ou une portée plateforme déclarée.

    class Command(CommandeEntrepriseMixin, BaseCommand):
        def handle(self, *args, **options):
            with self.contexte(options):
                ...

Sans `--entreprise`, la commande travaille en portée plateforme, nommée d'après la commande : elle
traverse les entreprises et le dit dans le journal. Avec `--entreprise <slug ou identifiant>`, elle
ne voit que celle-là.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

from django.core.management.base import CommandError

from apps.core.contexte import contexte_entreprise, portee_plateforme


def trouver_entreprise(identifiant: str):
    """Une entreprise par son identifiant, ou par son slug (encore `schema_name` jusqu'au lot 8)."""
    from apps.tenants.models import Entreprise

    try:
        cle = uuid.UUID(str(identifiant))
    except ValueError:
        cle = None
    entreprise = (
        Entreprise.objects.filter(pk=cle).first()
        if cle
        else Entreprise.objects.filter(schema_name=str(identifiant).strip().lower()).first()
    )
    if entreprise is None:
        raise CommandError(f"Aucune entreprise « {identifiant} ».")
    return entreprise


class CommandeEntrepriseMixin:
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--entreprise",
            help="Slug ou identifiant de l'entreprise ; sans lui, portée plateforme.",
        )

    @contextmanager
    def contexte(self, options):
        identifiant = options.get("entreprise")
        if identifiant:
            with contexte_entreprise(trouver_entreprise(identifiant)):
                yield
        else:
            nom = self.__class__.__module__.rsplit(".", 1)[-1]
            with portee_plateforme(motif=f"commande {nom}"):
                yield
