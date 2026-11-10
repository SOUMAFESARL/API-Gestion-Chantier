"""Vérifie la deuxième couche de l'isolation (RLS) sur la base configurée — D9, R-5.

    python manage.py verifier_isolation

Sort en erreur au moindre défaut : à lancer après un déploiement ou une migration. Équivaut à
`manage.py check --database default`, en plus lisible.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.rls import (
    diagnostic_isolation,
    plateforme_sans_role,
    role_plateforme,
    tables_attendues,
)


class Command(BaseCommand):
    help = "Vérifie la sécurité au niveau des lignes (RLS) et les rôles PostgreSQL."

    def handle(self, *args, **options):
        defauts = diagnostic_isolation(connection)
        if defauts:
            for defaut in defauts:
                self.stderr.write(self.style.ERROR(f"- {defaut}"))
            raise CommandError(f"{len(defauts)} défaut(s) d'isolation.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Isolation en place : {len(tables_attendues())} tables sous RLS forcée, "
                + (
                    "portée plateforme par session."
                    if plateforme_sans_role()
                    else f"portée plateforme par le rôle « {role_plateforme()} »."
                )
            )
        )
