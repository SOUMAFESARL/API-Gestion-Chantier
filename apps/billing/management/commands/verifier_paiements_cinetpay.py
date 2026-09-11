"""Commande CLI pour déclencher la réconciliation automatique des paiements CinetPay."""

from django.core.management.base import BaseCommand
from django_tenants.utils import get_public_schema_name, schema_context

from apps.billing.services.paiement import PaiementAbonnementService


class Command(BaseCommand):
    help = (
        "Vérifie l'état des paiements CinetPay en attente auprès de la passerelle "
        "et réconcilie les abonnements."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--transaction-id",
            type=str,
            help="Identifiant d'une transaction spécifique à vérifier et valider immédiatement.",
        )
        parser.add_argument(
            "--delai-minutes",
            type=int,
            default=0,
            help="Délai minimum en minutes pour les transactions initiées (par défaut: 0 en CLI).",
        )
        parser.add_argument(
            "--timeout-heures",
            type=int,
            default=48,
            help="Nombre d'heures après lesquelles une transaction non confirmée expire.",
        )

    def handle(self, *args, **options):
        with schema_context(get_public_schema_name()):
            tx_id = options.get("transaction_id")
            delai = options.get("delai_minutes", 0)
            timeout = options.get("timeout_heures", 48)

            if tx_id:
                self.stdout.write(f"Vérification de la transaction unique : {tx_id}...")
                res = PaiementAbonnementService.traiter_notification_webhook(transaction_id=tx_id)
                statut = res.get("statut")

                if statut in ["CONFIRME", "DEJA_CONFIRME"]:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Succès ! Transaction {tx_id} confirmée. "
                            f"Facture : {res.get('facture')}, "
                            f"Expiration : {res.get('abonnement_expire_le')}"
                        )
                    )
                elif statut == "EN_ATTENTE":
                    self.stdout.write(
                        self.style.NOTICE(f"Paiement {tx_id} toujours en attente chez l'opérateur.")
                    )
                else:
                    self.stdout.write(self.style.WARNING(f"Résultat : {res}"))
                return

            self.stdout.write(
                f"Lancement de la réconciliation globale (délai min: {delai} min, "
                f"expiration: {timeout} h)..."
            )
            stats = PaiementAbonnementService.verifier_paiements_en_attente(
                delai_min_minutes=delai,
                timeout_heures=timeout,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Réconciliation terminée :\n"
                    f"  - Candidats examinés : {stats['total_candidats']}\n"
                    f"  - Confirmés : {stats['confirmes']}\n"
                    f"  - Toujours en attente : {stats['en_attente']}\n"
                    f"  - Échoués : {stats['echoues']}\n"
                    f"  - Expirés : {stats['expires']}"
                )
            )
