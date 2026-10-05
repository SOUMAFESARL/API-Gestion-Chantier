"""Commande de chargement des jours fériés légaux de Côte d'Ivoire (CI).

Usage :
    python manage.py charger_jours_feries --annee 2026 --annee 2027

Alimente la table `jour_ferie` dans le schéma public (SHARED_APPS).
Idempotente via `update_or_create(pays='CI', date_ferie=...)`.
"""

from datetime import date, timedelta
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django_tenants.utils import get_public_schema_name, schema_context

from apps.referentiels.models import JourFerie


def calculer_date_paques(annee: int) -> date:
    """Calcule la date du dimanche de Pâques grégorien (algorithme de Meeus/Jones/Butcher)."""
    a = annee % 19
    b = annee // 100
    c = annee % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = ((h + l - 7 * m + 114) % 31) + 1
    return date(annee, mois, jour)


class Command(BaseCommand):
    help = "Charge les jours fériés de Côte d'Ivoire pour les années spécifiées (schéma public)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--annee",
            action="append",
            type=int,
            dest="annees",
            help="Année à charger (répétable, ex: --annee 2026 --annee 2027). Défaut : 2026 et 2027.",
        )

    def handle(self, *args, **options):
        annees = options.get("annees") or [2026, 2027]
        annees = sorted(set(annees))

        # Chargement des éventuelles fêtes islamiques mobiles depuis le fichier JSON
        fichier_mobiles = Path(__file__).resolve().parent.parent.parent / "data" / "jours_feries_mobiles_ci.json"
        fetes_mobiles_externes = []
        if fichier_mobiles.exists():
            try:
                with open(fichier_mobiles, encoding="utf-8") as f:
                    donnees = json.load(f)
                    if isinstance(donnees, list):
                        fetes_mobiles_externes = donnees
            except Exception as e:
                self.stderr.write(f"Avertissement : lecture impossible de {fichier_mobiles} : {e}")

        total_charges = 0
        with schema_context(get_public_schema_name()):
            for annee in annees:
                jours_ci: list[tuple[date, str]] = []

                # 1. Jours fériés fixes en Côte d'Ivoire
                jours_ci.extend([
                    (date(annee, 1, 1), "Jour de l'An"),
                    (date(annee, 5, 1), "Fête du Travail"),
                    (date(annee, 8, 7), "Fête Nationale"),
                    (date(annee, 8, 15), "Assomption"),
                    (date(annee, 11, 1), "Toussaint"),
                    (date(annee, 11, 15), "Journée Nationale de la Paix"),
                    (date(annee, 12, 25), "Noël"),
                ])

                # 2. Fêtes mobiles chrétiennes liées à Pâques (calcul algorithmique)
                paques = calculer_date_paques(annee)
                jours_ci.extend([
                    (paques + timedelta(days=1), "Lundi de Pâques"),
                    (paques + timedelta(days=39), "Ascension"),
                    (paques + timedelta(days=50), "Lundi de Pentecôte"),
                ])

                # 3. Fêtes mobiles islamiques depuis le fichier externe dédié
                for entree in fetes_mobiles_externes:
                    if not isinstance(entree, dict):
                        continue
                    date_str = entree.get("date")
                    libelle = entree.get("libelle", "Fête mobile")
                    pays = entree.get("pays", "CI")
                    if pays == "CI" and date_str:
                        try:
                            d = date.fromisoformat(date_str)
                            if d.year == annee:
                                jours_ci.append((d, libelle))
                        except ValueError:
                            pass

                # Persistance idempotente
                nb_annee = 0
                for d_ferie, libelle in jours_ci:
                    obj, created = JourFerie.objects.update_or_create(
                        pays="CI",
                        date_ferie=d_ferie,
                        defaults={"libelle": libelle},
                    )
                    nb_annee += 1

                total_charges += nb_annee
                self.stdout.write(
                    self.style.SUCCESS(f"Année {annee} : {nb_annee} jours fériés enregistrés pour 'CI'.")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Chargement terminé : {total_charges} enregistrements au total (schéma public).")
        )
