"""Commande de gestion pour propager les modèles de rôles système aux entreprises clientes (A-07, A-08, A-09).

Exécutable via : python manage.py propager_roles_systeme
"""

from django.core.management.base import BaseCommand
from apps.platform_admin.services.catalogue import propager_roles_systeme


class Command(BaseCommand):
    help = "Propage les rôles système manquants à l'ensemble des entreprises clientes existantes."

    def handle(self, *args, **options):
        resultat = propager_roles_systeme(acteur=None)
        self.stdout.write(
            self.style.SUCCESS(
                f"Propagation terminée : {resultat.get('entreprises_modifiees', 0)} entreprise(s) modifiée(s) "
                f"sur {resultat.get('total_entreprises', 0)}."
            )
        )
