"""Commande pour simuler la réception d'un webhook CinetPay en local."""

from django.core.management.base import BaseCommand
from django_tenants.utils import get_public_schema_name, schema_context

from apps.billing.models import PaiementAbonnement
from apps.billing.services.paiement import PaiementAbonnementService


class Command(BaseCommand):
    help = "Simule la notification IPN de CinetPay pour valider une transaction en local."


    def add_arguments(self, parser):
        parser.add_argument(
            "--transaction-id",
            type=str,
            help="Identifiant de transaction à simuler (par défaut : dernière initiée).",
        )
        parser.add_argument(
            "--moyen",
            type=str,
            default="WAVE",
            help="Moyen de paiement simulé (WAVE, ORANGE_MONEY, MTN_MOMO, CARTE).",
        )

    def handle(self, *args, **options):
        with schema_context(get_public_schema_name()):
            tx_id = options.get("transaction_id")
            moyen = options.get("moyen", "WAVE")

            if not tx_id:
                dernier = (
                    PaiementAbonnement.objects.filter(statut=PaiementAbonnement.Statut.INITIE)
                    .order_by("-cree_le")
                    .first()
                )
                if not dernier:
                    from apps.billing.models import Plan
                    from apps.tenants.models import Entreprise

                    entreprise = Entreprise.objects.exclude(schema_name="public").first()
                    plan = (
                        Plan.objects.filter(code=Plan.Code.MAITRE_OEUVRE).first()
                        or Plan.objects.first()
                    )

                    if entreprise and plan:
                        nom_ent = entreprise.raison_sociale or str(entreprise)
                        self.stdout.write(
                            self.style.NOTICE(
                                "Aucune transaction en attente. "
                                f"Initialisation automatique pour '{nom_ent}'..."
                            )
                        )
                        init_res = PaiementAbonnementService.initier_paiement(
                            entreprise=entreprise,
                            plan=plan,
                            cycle="MENSUEL",
                        )
                        tx_id = init_res["transaction_id"]
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Transaction générée : {tx_id} ({init_res['montant_fcfa']} FCFA)"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                "Aucune transaction en attente trouvée et aucune "
                                "entreprise disponible.\n"
                                "Spécifiez un --transaction-id ou initiez un paiement via l'API."
                            )
                        )
                        return
                else:
                    tx_id = dernier.reference_transaction or dernier.reference_commande

            self.stdout.write(f"Simulation du webhook CinetPay pour la transaction {tx_id}...")

            donnees_simulees = {
                "cpm_trans_id": tx_id,
                "cpm_site_id": "SIM_SITE_ID",
                "cpm_amount": "49000",
                "cpm_currency": "XOF",
                "payment_method": moyen,
                "cpm_trans_status": "ACCEPTED",
            }

            resultat = PaiementAbonnementService.traiter_notification_webhook(
                transaction_id=tx_id,
                donnees_webhook=donnees_simulees,
            )

            if resultat.get("statut") in ["CONFIRME", "DEJA_CONFIRME"]:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Succès ! Transaction {tx_id} validée. "
                        f"Facture : {resultat.get('facture')}, "
                        f"Date d'expiration : {resultat.get('abonnement_expire_le')}"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING(f"Résultat du webhook : {resultat}"))
