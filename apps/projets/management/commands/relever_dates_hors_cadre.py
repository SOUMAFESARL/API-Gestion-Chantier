"""Commande de gestion pour relever les dates hors cadre (règles D4 et D5).

Parcourt les schémas tenants et liste en lecture seule :
- Les lots dont les dates prévues dépassent celles de leur projet parent.
- Les activités dont les dates prévues dépassent celles de leur lot parent.

Code de sortie :
- 0 si aucune anomalie
- 1 si au moins une anomalie est détectée
"""

import sys

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.projets.models import Activite, Lot
from apps.tenants.models import Entreprise


class Command(BaseCommand):
    help = (
        "Relève les lots et activités dont les dates sortent du cadre de leur parent "
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
                    "\nAucune anomalie de date constatée sur les projets, lots et activités."
                )
            )

    def _verifier_schema(self) -> int:
        anomalies = 0

        # 1. Vérification des lots
        lots = (
            Lot.objects.select_related("projet")
            .filter(
                supprime_le__isnull=True,
                projet__supprime_le__isnull=True,
            )
            .order_by("projet__nom", "code")
        )

        for lot in lots:
            projet = lot.projet
            debut_hors_cadre = (
                lot.date_debut_prevue
                and projet.date_debut_prevue
                and lot.date_debut_prevue < projet.date_debut_prevue
            )
            fin_hors_cadre = (
                lot.date_fin_prevue
                and projet.date_fin_prevue
                and lot.date_fin_prevue > projet.date_fin_prevue
            )

            if debut_hors_cadre or fin_hors_cadre:
                anomalies += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  [LOT HORS CADRE] ID: {lot.id} | Code: {lot.code} | "
                        f"Libellé: {lot.libelle}\n"
                        f"    Dates lot    : {lot.date_debut_prevue} -> {lot.date_fin_prevue}\n"
                        f"    Dates projet : {projet.date_debut_prevue} -> "
                        f"{projet.date_fin_prevue} (Projet: {projet.nom})"
                    )
                )

        # 2. Vérification des activités
        activites = (
            Activite.objects.select_related("lot", "lot__projet")
            .filter(
                supprime_le__isnull=True,
                lot__supprime_le__isnull=True,
            )
            .order_by("lot__code", "ordre")
        )

        for act in activites:
            lot = act.lot
            debut_hors_cadre = (
                act.date_debut_prevue
                and lot.date_debut_prevue
                and act.date_debut_prevue < lot.date_debut_prevue
            )
            fin_hors_cadre = (
                act.date_fin_prevue
                and lot.date_fin_prevue
                and act.date_fin_prevue > lot.date_fin_prevue
            )

            if debut_hors_cadre or fin_hors_cadre:
                anomalies += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  [ACTIVITÉ HORS CADRE] ID: {act.id} | Libellé: {act.libelle}\n"
                        f"    Dates activité : {act.date_debut_prevue} -> {act.date_fin_prevue}\n"
                        f"    Dates lot      : {lot.date_debut_prevue} -> {lot.date_fin_prevue} "
                        f"(Lot: {lot.code})"
                    )
                )

        return anomalies
