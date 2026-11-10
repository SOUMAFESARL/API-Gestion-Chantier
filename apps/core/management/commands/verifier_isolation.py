"""Controle le retrait de la RLS ; les tests ORM/API verifient l'isolation Django."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.rls import diagnostic_isolation


class Command(BaseCommand):
    help = "Controle l'absence de RLS residuelle apres migration."

    def handle(self, *args, **options):
        defauts = diagnostic_isolation(connection)
        if defauts:
            for defaut in defauts:
                self.stderr.write(self.style.ERROR(f"- {defaut}"))
            raise CommandError(f"{len(defauts)} defaut(s) de configuration.")
        self.stdout.write(
            self.style.SUCCESS(
                "RLS retiree. Isolation assuree par Django ; validation par les tests ORM et API."
            )
        )
