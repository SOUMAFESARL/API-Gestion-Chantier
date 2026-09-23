"""Point d'entree cron pour les rappels sans worker Celery."""

from django.core.management.base import BaseCommand

from apps.billing.services.expiration import envoyer_rappels_expiration


class Command(BaseCommand):
    help = "Envoyer les rappels d'expiration des abonnements payants (J-7, J-3, J-1, J0)."

    def handle(self, *args, **options):
        total = envoyer_rappels_expiration()
        self.stdout.write(self.style.SUCCESS(f"{total} rappel(s) envoye(s)."))
