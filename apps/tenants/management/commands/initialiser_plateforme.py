"""Rend le schéma `public` adressable.

    python manage.py initialiser_plateforme

django-tenants résout le schéma à partir du nom d'hôte. Sans une ligne
d'`Entreprise` portant `schema_name = "public"` et son domaine, aucune
requête vers `localhost` ne trouve de tenant : le middleware répond 404
avant même d'atteindre une vue. C'est vrai aussi en production pour le
domaine principal.

Cette entreprise-là ne représente pas un client : elle représente
**CCD Digital, exploitant de la plateforme**. Aucun schéma n'est créé,
`public` existe déjà.

Idempotent.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.enums import StatutEntreprise
from apps.tenants.models import Domaine, Entreprise


class Command(BaseCommand):
    help = "Crée l'entreprise et le domaine représentant le schéma public."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domaine",
            default="localhost",
            help="Nom d'hôte du schéma public (en production : le domaine principal).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        code_public = settings.PUBLIC_SCHEMA_NAME

        entreprise = Entreprise.objects.filter(schema_name=code_public).first()
        if entreprise is None:
            entreprise = Entreprise(
                schema_name=code_public,
                raison_sociale="CCD Digital",
                nom_commercial="CCD Digital",
                pays="CI",
                ville="Abidjan",
                email_contact="contact@ccd-digital.ci",
                statut=StatutEntreprise.ACTIF,
            )
            # Le schéma `public` existe déjà : ne rien tenter de créer.
            entreprise.auto_create_schema = False
            entreprise.save()
            self.stdout.write(self.style.SUCCESS(f"Entreprise plateforme créée : {entreprise}"))
        else:
            self.stdout.write(f"Entreprise plateforme déjà présente : {entreprise}")

        domaine, cree = Domaine.objects.get_or_create(
            domain=options["domaine"],
            defaults={"tenant": entreprise, "is_primary": True},
        )
        if cree:
            self.stdout.write(self.style.SUCCESS(f"Domaine public créé : {domaine.domain}"))
        else:
            self.stdout.write(f"Domaine public déjà présent : {domaine.domain}")

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("  Ouvrir  http://localhost:8000/api/health/"))
