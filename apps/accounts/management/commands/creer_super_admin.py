"""Crée ou met à jour un compte Super Admin dans le schéma `public`.

    python manage.py creer_super_admin --email support@ccd-digital.ci --motdepasse MonMotDePasseFort123!

Configure le compte avec `is_superuser=True`, `is_staff=True`, `is_active=True`
dans le schéma `public` de la plateforme.
Idempotente : si le compte existe déjà, son mot de passe est mis à jour
et ses privilèges superuser sont activés.
"""

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur


class Command(BaseCommand):
    help = "Crée ou met à jour un compte Super Admin de la plateforme dans le schéma public."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Adresse email du Super Admin.")
        parser.add_argument("--motdepasse", required=True, help="Mot de passe du Super Admin.")
        parser.add_argument("--nom", default="Support", help="Nom de famille.")
        parser.add_argument("--prenom", default="CCD", help="Prénom.")

    def handle(self, *args, **options):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        email = options["email"].strip().lower()
        motdepasse = options["motdepasse"]

        try:
            validate_password(motdepasse)
        except ValidationError as erreur:
            raise CommandError(" ".join(erreur.messages)) from erreur

        with schema_context(get_public_schema_name()):
            existant = Utilisateur.objects.filter(email__iexact=email).first()
            if existant is not None:
                existant.is_superuser = True
                existant.is_staff = True
                existant.is_active = True
                existant.statut = StatutUtilisateur.ACTIF
                existant.role_global = RoleGlobal.ADMIN
                if options.get("nom"):
                    existant.nom = options["nom"]
                if options.get("prenom"):
                    existant.prenom = options["prenom"]
                existant.set_password(motdepasse)
                existant.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Compte Super Admin existant mis à niveau avec succès : {existant.email} (is_superuser=True)"
                    )
                )
                return

            utilisateur = Utilisateur.objects.create_superuser(
                email=email,
                password=motdepasse,
                nom=options["nom"],
                prenom=options["prenom"],
                role_global=RoleGlobal.ADMIN,
                statut=StatutUtilisateur.ACTIF,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Nouveau compte Super Admin créé avec succès : {utilisateur.email} (is_superuser=True)"
            )
        )
