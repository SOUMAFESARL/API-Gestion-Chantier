"""Commande de gestion Django pour l'évaluation quotidienne automatique des statuts chantiers.

Parcourt les schémas tenants d'entreprises clientes et applique les transitions calendaires
strictes sur les Activités, les Lots et les Projets :
- PLANIFIE (EN_ATTENTE) -> EN_COURS si date_du_jour >= date_debut_prevue
- EN_COURS -> EN_RETARD si date_du_jour > date_fin_prevue (si non clôturé)
- Préservation absolue des statuts stables/manuels (SUSPENDU, BLOQUE, RECEPTIONNE, TERMINE, etc.)
"""

from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.projets.services.machine_etats import executer_evaluation_quotidienne_schema
from apps.tenants.models import Entreprise


class Command(BaseCommand):
    help = "Évalue et met à jour les statuts calendaires des activités, lots et projets de tous les tenants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            help="Nom de schéma tenant spécifique à évaluer (optionnel).",
        )
        parser.add_argument(
            "--date",
            type=str,
            help="Date de référence au format YYYY-MM-DD (par défaut: date du jour).",
        )

    def handle(self, *args, **options):
        schema_cible = options.get("schema")
        date_str = options.get("date")

        if date_str:
            try:
                date_ref = date.fromisoformat(date_str)
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Format de date invalide : {date_str}. Utilisez YYYY-MM-DD."))
                return
        else:
            date_ref = timezone.now().date()

        self.stdout.write(
            self.style.NOTICE(f"--- Démarrage de l'évaluation quotidienne des statuts ({date_ref}) ---")
        )

        if schema_cible:
            schemas = [schema_cible]
        else:
            from apps.core.enums import StatutEntreprise

            schemas = list(
                Entreprise.objects.exclude(schema_name="public")
                .filter(statut__in=[StatutEntreprise.ACTIF, StatutEntreprise.ESSAI])
                .values_list("schema_name", flat=True)
            )

        total_activites = 0
        total_lots = 0
        total_projets = 0

        for schema_name in schemas:
            try:
                with schema_context(schema_name):
                    rapport = executer_evaluation_quotidienne_schema(date_reference=date_ref)
                    total_activites += rapport["activites_modifiees"]
                    total_lots += rapport["lots_modifies"]
                    total_projets += rapport["projets_modifies"]
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{schema_name}] Succès : "
                            f"{rapport['projets_modifies']} projets, "
                            f"{rapport['lots_modifies']} lots, "
                            f"{rapport['activites_modifiees']} activités mis à jour."
                        )
                    )
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"[{schema_name}] Erreur lors de l'évaluation : {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"--- Évaluation terminée avec succès : {total_projets} projets, "
                f"{total_lots} lots, {total_activites} activités modifiés au total. ---"
            )
        )
