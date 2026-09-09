"""Crée un compte du personnel CCD Digital, dans le schéma `public`.

    python manage.py creer_super_admin --email support@ccd-digital.ci

**Le Super Admin n'est pas un rôle, c'est un territoire.** Il vit dans
`public.utilisateur` — la même table que les collaborateurs d'un client, mais
dans un autre schéma (écart E1). Il n'apparaît dans aucune liste de
collaborateurs, ne consomme aucun siège de quota, et n'a aucune affectation de
projet — matrice des rôles §1.1.

**`create_user`, jamais `create_superuser`** — règle R-64. `is_superuser=True`
court-circuite *toute* vérification de permission Django : la matrice RBAC
deviendrait décorative, et un compte de support aurait accès aux tables de tous
les clients par l'admin Django. L'accès à l'admin Django en développement passe
par un compte technique séparé.

Idempotente.
"""

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur


class Command(BaseCommand):
    help = "Crée un compte du personnel de l'éditeur dans le schéma public."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--motdepasse", required=True)
        parser.add_argument("--nom", default="Support")
        parser.add_argument("--prenom", default="CCD")

    def handle(self, *args, **options):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            validate_password(options["motdepasse"])
        except ValidationError as erreur:
            # Le personnel de l'éditeur n'échappe pas à la politique du
            # Socle §2.1 : c'est lui qui a le plus à protéger.
            raise CommandError(" ".join(erreur.messages)) from erreur

        with schema_context(get_public_schema_name()):
            existant = Utilisateur.objects.filter(email__iexact=options["email"]).first()
            if existant is not None:
                self.stdout.write(f"Compte déjà présent : {existant.email}")
                return

            utilisateur = Utilisateur.objects.create_user(
                email=options["email"],
                password=options["motdepasse"],
                nom=options["nom"],
                prenom=options["prenom"],
                role_global=RoleGlobal.ADMIN,
                statut=StatutUtilisateur.ACTIF,
            )

        self.stdout.write(self.style.SUCCESS(f"Compte plateforme créé : {utilisateur.email}"))
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Cette porte est restreinte par adresse IP. Hors développement, "
                "`SUPER_ADMIN_IPS` doit être renseigné — vide, elle interdit tout."
            )
        )
