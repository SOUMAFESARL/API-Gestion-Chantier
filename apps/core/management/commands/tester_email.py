"""Commande de test d'envoi d'email via la configuration SMTP active.

Usage:
    python manage.py tester_email
    python manage.py tester_email dzanfack@gmail.com
    python manage.py tester_email autre@domaine.com --gabarit=activation
"""

from django.conf import settings
from django.core.mail import get_connection
from django.core.management.base import BaseCommand

from apps.core.emails import envoyer


class Command(BaseCommand):
    help = "Vérifie la configuration SMTP et envoie un email de test."

    def add_arguments(self, parser):
        parser.add_argument(
            "destinataire",
            nargs="?",
            default=getattr(settings, "EMAIL_HOST_USER", "") or "test@example.com",
            help="Adresse email de destination (défaut: EMAIL_HOST_USER)",
        )
        parser.add_argument(
            "--gabarit",
            default="activation",
            help="Nom du gabarit dans templates/emails/ (défaut: activation)",
        )

    def handle(self, *args, **options):
        destinataire = options["destinataire"]
        gabarit = options["gabarit"]

        self.stdout.write(self.style.NOTICE("=== Diagnostic Configuration Email ==="))
        self.stdout.write(f"EMAIL_BACKEND       : {getattr(settings, 'EMAIL_BACKEND', 'Non défini')}")
        self.stdout.write(f"EMAIL_HOST          : {getattr(settings, 'EMAIL_HOST', 'Non défini')}")
        self.stdout.write(f"EMAIL_PORT          : {getattr(settings, 'EMAIL_PORT', 'Non défini')}")
        self.stdout.write(f"EMAIL_USE_TLS       : {getattr(settings, 'EMAIL_USE_TLS', 'Non défini')}")
        self.stdout.write(f"EMAIL_USE_SSL       : {getattr(settings, 'EMAIL_USE_SSL', 'Non défini')}")
        self.stdout.write(f"EMAIL_HOST_USER     : {getattr(settings, 'EMAIL_HOST_USER', 'Non défini')}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL  : {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Non défini')}")
        self.stdout.write(f"EMAIL_COMMERCIAL    : {getattr(settings, 'EMAIL_COMMERCIAL', 'Non défini')}")
        self.stdout.write("========================================")

        # 1. Test de connectivité SMTP brute
        self.stdout.write(f"Vérification de la connexion au serveur {settings.EMAIL_HOST}:{settings.EMAIL_PORT}...")
        try:
            connection = get_connection(fail_silently=False)
            connection.open()
            self.stdout.write(self.style.SUCCESS("Connexion SMTP établie avec succès !"))
            connection.close()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Échec de connexion SMTP : {exc}"))
            return

        # 2. Envoi via le service officiel de la plateforme (apps.core.emails.envoyer)
        self.stdout.write(f"Envoi d'un email de test ({gabarit}) à {destinataire}...")
        contexte_test = {
            "prenom": "Utilisateur",
            "nom": "Test",
            "raison_sociale": "CCD Digital Test",
            "lien_activation": "http://localhost:3000/activation#jeton=test_token_verification",
            "adresse_espace": "http://localhost:3000",
            "lien_connexion": "http://localhost:3000/connexion",
            "lien_reinitialisation": "http://localhost:3000/mot-de-passe/oublie",
        }

        succes = envoyer(
            gabarit=gabarit,
            sujet="[Test SMTP CCD Digital] Vérification d'envoi d'email Gmail",
            destinataires=destinataire,
            contexte=contexte_test,
        )

        if succes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Email envoyé avec succès à {destinataire} via {settings.EMAIL_HOST_USER} !"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR("L'envoi a échoué. Consultez les logs pour plus de détails.")
            )
