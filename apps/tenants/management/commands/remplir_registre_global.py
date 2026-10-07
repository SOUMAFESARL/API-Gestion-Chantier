"""Commande de gestion remplir_registre_global (C-03).

Remplit la table RegistreEmail (schéma public) à partir de tous les utilisateurs
actifs et existants dans chaque schéma tenant. Idempotente.
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.tenants.models import Entreprise, RegistreEmail


class Command(BaseCommand):
    help = "Remplit ou met à jour le registre global des adresses e-mail (schéma public) de façon idempotente."

    def handle(self, *args, **options):
        entreprises = Entreprise.objects.exclude(schema_name="public")
        total_ajoutes = 0
        total_existants = 0

        for entreprise in entreprises:
            with schema_context(entreprise.schema_name):
                from apps.accounts.models import Utilisateur

                utilisateurs = (
                    Utilisateur.objects.filter(supprime_le__isnull=True)
                    .exclude(statut="DESACTIVE")
                    .values_list("email", flat=True)
                )

                for email_brut in utilisateurs:
                    if not email_brut:
                        continue
                    email_norm = email_brut.strip().lower()
                    with schema_context("public"):
                        obj, cree = RegistreEmail.objects.get_or_create(
                            email=email_norm,
                            defaults={"entreprise": entreprise},
                        )
                        if cree:
                            total_ajoutes += 1
                        else:
                            total_existants += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Registre global synchronisé : {total_ajoutes} ajoutés, {total_existants} déjà présents."
            )
        )
