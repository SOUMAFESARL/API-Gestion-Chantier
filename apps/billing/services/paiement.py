"""Service d'orchestration des paiements d'abonnement et facturation — MLD §4.5."""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.billing.models import Abonnement, Facture, PaiementAbonnement, Plan
from apps.billing.services.cinetpay import CinetPayClient, CinetPayError
from apps.core.enums import StatutEntreprise

logger = logging.getLogger(__name__)

__all__ = ["PaiementAbonnementService"]


class PaiementAbonnementService:
    """Service gérant le cycle de vie des paiements et des factures d'abonnements."""

    @classmethod
    def mapper_mode_paiement(cls, code_prestataire: str) -> str:
        """Mappe le code retourné par CinetPay vers notre énumération interne."""
        code = (code_prestataire or "").upper()
        if "WAVE" in code:
            return PaiementAbonnement.Mode.WAVE
        if "OM" in code or "ORANGE" in code:
            return PaiementAbonnement.Mode.ORANGE_MONEY
        if "MTN" in code or "MOMO" in code:
            return PaiementAbonnement.Mode.MTN_MOMO
        if "MOOV" in code or "FLOOZ" in code:
            return PaiementAbonnement.Mode.MOOV_MONEY
        if any(c in code for c in ["CARD", "VISA", "MASTERCARD", "CB"]):
            return PaiementAbonnement.Mode.CARTE
        if "VIREMENT" in code:
            return PaiementAbonnement.Mode.VIREMENT
        return PaiementAbonnement.Mode.AUTRE

    @classmethod
    def initier_paiement(
        cls,
        entreprise,
        plan: Plan,
        cycle: str = "MENSUEL",
        user_email: str | None = None,
        user_name: str | None = None,
        return_url: str | None = None,
        notify_url: str | None = None,
    ) -> dict[str, Any]:
        """Prépare la facture et la transaction, puis contacte CinetPay pour obtenir le payment_url.

        Exécuté dans le schéma `public` (tables billing).
        """
        with schema_context(get_public_schema_name()):
            # 1. Validation du tarif
            if cycle == "ANNUEL":
                prix_montant = plan.prix_annuel_montant
                duree_jours = 365
            else:
                cycle = "MENSUEL"
                prix_montant = plan.prix_mensuel_montant
                duree_jours = 30

            if not prix_montant or prix_montant <= 0:
                msg = (
                    f"Le forfait « {plan.libelle} » ne possède pas de tarif "
                    f"configuré pour le cycle {cycle}."
                )
                raise ValueError(msg)

            # 2. Récupération ou initialisation de l'abonnement
            abonnement = Abonnement.objects.filter(entreprise=entreprise).first()
            aujourdhui = timezone.localdate()

            if abonnement is None:
                abonnement = Abonnement.objects.create(
                    entreprise=entreprise,
                    plan=plan,
                    date_debut=aujourdhui,
                    date_fin=aujourdhui,
                    statut=Abonnement.Statut.ESSAI,
                )

            # 3. Calculs financiers (montants en centimes FCFA)
            # Montant TTC = prix_montant
            taux_tva = Decimal("18.00")
            montant_ttc = prix_montant
            # HT = TTC / (1 + TVA)
            montant_ht = int(Decimal(montant_ttc) / (Decimal("1") + (taux_tva / Decimal("100"))))
            montant_tva = montant_ttc - montant_ht

            periode_debut = max(aujourdhui, abonnement.date_fin)
            periode_fin = periode_debut + timedelta(days=duree_jours)

            with transaction.atomic():
                # 4. Création de la facture OHADA
                numero_facture = Facture.generer_prochain_numero()
                facture = Facture.objects.create(
                    numero=numero_facture,
                    abonnement=abonnement,
                    entreprise=entreprise,
                    periode_debut=periode_debut,
                    periode_fin=periode_fin,
                    montant_ht=montant_ht,
                    taux_tva=taux_tva,
                    montant_tva=montant_tva,
                    montant_ttc=montant_ttc,
                    statut=Facture.Statut.EMISE,
                    date_emission=aujourdhui,
                    date_echeance=periode_debut + timedelta(days=7),
                )

                # 5. Création de la transaction de paiement initiée
                # Référence unique CinetPay (<= 100 caractères, alphanumérique)
                ref_unique = (
                    f"TX{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
                )
                paiement = PaiementAbonnement.objects.create(
                    facture=facture,
                    mode=PaiementAbonnement.Mode.AUTRE,
                    reference_commande=ref_unique,
                    reference_transaction=ref_unique,
                    montant=montant_ttc,
                    statut=PaiementAbonnement.Statut.INITIE,
                )

            # 6. Appel au client CinetPay
            client = CinetPayClient()
            c_return_url = (
                return_url
                or getattr(settings, "CINETPAY_RETURN_URL", None)
                or f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/abonnements/statut"
            )
            c_notify_url = (
                notify_url
                or getattr(settings, "CINETPAY_NOTIFY_URL", None)
                or f"{getattr(settings, 'BACKEND_URL', 'http://localhost:8000')}/api/v1/billing/cinetpay/webhook/"
            )

            email_client = user_email or entreprise.email_contact or "client@ccd-digital.ci"
            nom_client = user_name or entreprise.raison_sociale or "Client BTP"
            description = f"Abonnement {plan.libelle} ({cycle}) - {entreprise.raison_sociale}"[:250]

            try:
                res_cinetpay = client.initier_paiement(
                    transaction_id=ref_unique,
                    montant_fcfa=paiement.montant_fcfa,
                    description=description,
                    notify_url=c_notify_url,
                    return_url=c_return_url,
                    customer_email=email_client,
                    customer_name=nom_client,
                    customer_phone=entreprise.telephone_contact,
                    customer_city=entreprise.ville or "Abidjan",
                    customer_country=entreprise.pays or "CI",
                )
            except CinetPayError as e:
                # Marquer le paiement comme échoué en cas d'erreur de contact prestataire
                paiement.statut = PaiementAbonnement.Statut.ECHOUE
                paiement.charge_utile = {"erreur": str(e)}
                paiement.save(update_fields=["statut", "charge_utile"])
                raise

            payment_url = res_cinetpay.get("data", {}).get("payment_url")
            payment_token = res_cinetpay.get("data", {}).get("payment_token")

            # Sauvegarde du jeton prestataire
            paiement.charge_utile = res_cinetpay
            paiement.save(update_fields=["charge_utile"])

            return {
                "transaction_id": ref_unique,
                "payment_url": payment_url,
                "payment_token": payment_token,
                "numero_facture": facture.numero,
                "montant_fcfa": paiement.montant_fcfa,
                "forfait": plan.libelle,
                "cycle": cycle,
                "mode_simulation": client.est_en_mode_simulation,
            }

    @classmethod
    def traiter_notification_webhook(
        cls,
        transaction_id: str,
        donnees_webhook: dict | None = None,
    ) -> dict[str, Any]:
        """Traite une notification de paiement de manière sécurisée et IDEMPOTENTE.

        1. Vérifie l'existence de la transaction.
        2. Si déjà CONFIRMEE : acquitte immédiatement sans rejeu.
        3. Appelle CinetPay check_payment pour certifier le statut et le montant.
        4. Si validé :
           - Paiement -> CONFIRME
           - Facture -> PAYEE
           - Abonnement -> ACTIF (date_fin prolongée)
           - Entreprise -> ACTIF
        """
        with schema_context(get_public_schema_name()):
            paiement = (
                PaiementAbonnement.objects.filter(reference_transaction=transaction_id)
                .select_related("facture__abonnement__plan", "facture__entreprise")
                .first()
            )

            if not paiement:
                paiement = (
                    PaiementAbonnement.objects.filter(reference_commande=transaction_id)
                    .select_related("facture__abonnement__plan", "facture__entreprise")
                    .first()
                )

            if not paiement:
                logger.warning(
                    f"Webhook CinetPay reçu pour une transaction inconnue : {transaction_id}"
                )
                return {
                    "statut": "INCONNU",
                    "message": f"Transaction {transaction_id} introuvable.",
                }

            # Protection contre le rejeu (Idempotence)
            if paiement.statut == PaiementAbonnement.Statut.CONFIRME:
                logger.info(
                    f"Transaction {transaction_id} déjà confirmée. Acquittement sans doublon."
                )
                return {
                    "statut": "DEJA_CONFIRME",
                    "transaction_id": transaction_id,
                    "facture": paiement.facture.numero,
                }

            # Contre-vérification sécurisée auprès de CinetPay
            client = CinetPayClient()
            verification = client.verifier_transaction(transaction_id)

            statut_cinet = verification.get("statut")
            montant_paye_fcfa = verification.get("montant", 0)
            moyen = verification.get("moyen_paiement", "")

            with transaction.atomic():
                # Enregistrement de la charge utile brute
                charge_totale = {
                    "webhook": donnees_webhook or {},
                    "verification": verification.get("donnees_brutes", {}),
                    "verifie_le": timezone.now().isoformat(),
                }
                paiement.charge_utile = charge_totale

                if statut_cinet == "ACCEPTED":
                    # Contrôle de cohérence du montant (tolérance d'arrondi 100 FCFA)
                    if (
                        montant_paye_fcfa > 0
                        and abs(montant_paye_fcfa - paiement.montant_fcfa) > 100
                    ):
                        logger.error(
                            f"Discordance de montant sur {transaction_id} : "
                            f"attendu {paiement.montant_fcfa} FCFA, reçu {montant_paye_fcfa} FCFA."
                        )
                        paiement.statut = PaiementAbonnement.Statut.ECHOUE
                        paiement.save(update_fields=["statut", "charge_utile"])
                        return {
                            "statut": "ERREUR_MONTANT",
                            "message": (
                                "Le montant payé ne correspond pas au montant de la facture."
                            ),
                        }

                    # Confirmation du paiement
                    paiement.statut = PaiementAbonnement.Statut.CONFIRME
                    paiement.mode = cls.mapper_mode_paiement(moyen)
                    paiement.paye_le = timezone.now()
                    paiement.save(
                        update_fields=["statut", "mode", "paye_le", "charge_utile", "modifie_le"]
                    )

                    # Validation de la facture
                    facture = paiement.facture
                    facture.statut = Facture.Statut.PAYEE
                    facture.save(update_fields=["statut", "modifie_le"])

                    # Mise à jour de l'abonnement
                    abonnement = facture.abonnement
                    aujourdhui = timezone.localdate()

                    duree = facture.periode_fin - facture.periode_debut
                    base_date = max(aujourdhui, abonnement.date_fin)
                    abonnement.date_fin = base_date + duree
                    abonnement.statut = Abonnement.Statut.ACTIF
                    # Basculer le plan si l'utilisateur a changé de formule
                    nouveau_plan = (
                        Plan.objects.filter(prix_mensuel_montant=facture.montant_ttc).first()
                        or Plan.objects.filter(prix_annuel_montant=facture.montant_ttc).first()
                    )
                    if nouveau_plan:
                        abonnement.plan = nouveau_plan
                    abonnement.save(update_fields=["statut", "date_fin", "plan", "modifie_le"])

                    # Synchronisation du statut de l'entreprise (Règle R-113)
                    entreprise = facture.entreprise
                    entreprise.statut = StatutEntreprise.ACTIF
                    entreprise.save(update_fields=["statut"])

                    logger.info(
                        f"Paiement validé avec succès pour {entreprise.raison_sociale} "
                        f"(Transaction: {transaction_id}, Facture: {facture.numero})"
                    )

                    return {
                        "statut": "CONFIRME",
                        "transaction_id": transaction_id,
                        "facture": facture.numero,
                        "abonnement_expire_le": abonnement.date_fin.isoformat(),
                    }
                else:
                    # Échec ou annulation
                    paiement.statut = PaiementAbonnement.Statut.ECHOUE
                    paiement.save(update_fields=["statut", "charge_utile", "modifie_le"])
                    logger.warning(
                        f"Paiement refusé pour {transaction_id} : statut={statut_cinet}"
                    )
                    return {
                        "statut": "ECHOUE",
                        "motif": verification.get("message", "Paiement non accepté"),
                    }
