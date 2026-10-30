"""Commande de gestion pour relever les dates hors cadre (règles D4 et D5).

Parcourt les schémas tenants et liste en lecture seule :
- Les cases de l'arbre dont les dates prévues dépassent celles de leur parent (case ou projet).

Code de sortie :
- 0 si aucune anomalie
- 1 si au moins une anomalie est détectée
"""

import sys

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.projets.models import Element
from apps.tenants.models import Entreprise


class Command(BaseCommand):
    help = (
        "Relève les cases de l'arbre dont les dates sortent du cadre de leur parent "
        "(lecture seule)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            help="Nom de schéma tenant spécifique à inspecter (optionnel).",
        )

    def handle(self, *args, **options):
        schema_cible = options.get("schema")

        if schema_cible:
            schemas = [schema_cible]
        else:
            schemas = list(
                Entreprise.objects.exclude(schema_name="public").values_list(
                    "schema_name", flat=True
                )
            )

        total_anomalies = 0

        for schema_nom in schemas:
            self.stdout.write(self.style.NOTICE(f"=== Vérification du schéma : {schema_nom} ==="))
            with schema_context(schema_nom):
                anomalies_schema = self._verifier_schema()
                total_anomalies += anomalies_schema

        if total_anomalies > 0:
            self.stdout.write(
                self.style.ERROR(f"\n{total_anomalies} anomalie(s) calendaire(s) détectée(s).")
            )
            sys.exit(1)
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nAucune anomalie de date constatée dans les arbres des projets."
                )
            )

    def _verifier_schema(self) -> int:
        """Les cases dont les dates sortent de celles de leur parent (case ou projet)."""
        anomalies = 0
        cases = Element.objects.select_related("projet", "parent").filter(
            est_actif=True, projet__supprime_le__isnull=True
        )
        for case in cases.iterator():
            parent = case.parent or case.projet
            debut_p, fin_p = parent.date_debut_prevue, parent.date_fin_prevue
            avant = case.date_debut_prevue and debut_p and case.date_debut_prevue < debut_p
            apres = case.date_fin_prevue and fin_p and case.date_fin_prevue > fin_p
            if not (avant or apres):
                continue
            anomalies += 1
            nom_parent = parent.libelle if case.parent_id else f"projet {case.projet.reference}"
            self.stdout.write(
                self.style.WARNING(
                    f"  [CASE HORS CADRE] ID: {case.id} | {case.libelle}\n"
                    f"    Dates case   : {case.date_debut_prevue} -> {case.date_fin_prevue}\n"
                    f"    Dates parent : {debut_p} -> {fin_p} ({nom_parent})"
                )
            )
        return anomalies
