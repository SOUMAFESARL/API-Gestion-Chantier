"""Service d'orchestration des paiements d'abonnement et facturation — MLD §4.5."""

import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.audit.services import journaliser
from apps.billing.models import Abonnement, Facture, PaiementAbonnement, Plan
from apps.billing.services.cinetpay import CinetPayClient, CinetPayError
from apps.core.emails import envoyer
from apps.core.enums import ActionAudit, StatutEntreprise

logger = logging.getLogger(__name__)

__all__ = ["PaiementAbonnementService", "PaiementEnCoursError"]


class PaiementEnCoursError(Exception):
    """Levée lorsqu'une session de paiement est déjà active pour l'entreprise (Option A2)."""

    def __init__(self, message: str, transaction_en_cours: dict[str, Any]):
        super().__init__(message)
        self.transaction_en_cours = transaction_en_cours


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
            # 0. Vérification du verrou d'initiation (Protection anti-double débit - Option A2)
            limite_active = timezone.now() - timedelta(minutes=PaiementAbonnement.DELAI_VERROU_MINUTES)
            paiement_actif = (
                PaiementAbonnement.objects.filter(
                    facture__entreprise=entreprise,
                    statut__in=[
                        PaiementAbonnement.Statut.INITIE,
                        PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR,
                    ],
                    cree_le__gte=limite_active,
                )
                .select_related("facture__abonnement__plan")
                .order_by("-cree_le")
                .first()
            )
            if paiement_actif:
                tx_ref = paiement_actif.reference_transaction or paiement_actif.reference_commande
                raise PaiementEnCoursError(
                    f"Un paiement de {paiement_actif.montant_fcfa:,} FCFA est déjà en cours pour cette entreprise. "
                    f"Veuillez attendre sa confirmation ou annuler la tentative avant d'en relancer une.",
                    transaction_en_cours={
                        "transaction_id": tx_ref,
                        "reference_facture": paiement_actif.facture.numero,
                        "montant_fcfa": paiement_actif.montant_fcfa,
                        "forfait": paiement_actif.facture.abonnement.plan.libelle,
                        "statut": paiement_actif.statut,
                        "secondes_restantes": paiement_actif.secondes_restantes_verrou,
                        "cree_le": (
                            paiement_actif.cree_le.isoformat()
                            if paiement_actif.cree_le
                            else None
                        ),
                    },
                )

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
                # 4. Gestion de la facture OHADA (Option A)
                facture_existante = (
                    Facture.objects.filter(
                        entreprise=entreprise,
                        statut=Facture.Statut.EMISE,
                    )
                    .order_by("-cree_le")
                    .first()
                )
                if facture_existante:
                    if (
                        facture_existante.montant_ttc == montant_ttc
                        and facture_existante.abonnement == abonnement
                    ):
                        # Réutilisation de la facture existante (même forfait et cycle)
                        facture = facture_existante
                        facture.periode_debut = periode_debut
                        facture.periode_fin = periode_fin
                        facture.date_echeance = periode_debut + timedelta(days=7)
                        facture.save(
                            update_fields=["periode_debut", "periode_fin", "date_echeance", "modifie_le"]
                        )
                    else:
                        # Changement de forfait ou cycle : on annule l'ancienne facture
                        facture_existante.statut = Facture.Statut.ANNULEE
                        facture_existante.save(update_fields=["statut", "modifie_le"])
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
                else:
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
                or "http://localhost:3000/abonnements/statut"
            )
            c_notify_url = (
                notify_url
                or getattr(settings, "CINETPAY_NOTIFY_URL", None)
                or f"{getattr(settings, 'BACKEND_URL', 'http://localhost:8000')}/api/v1/cinetpay/webhook/"
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
    def annuler_paiement_en_cours(
        cls,
        entreprise,
        transaction_id: str,
        motif: str = "Annulation demandée par l'utilisateur",
    ) -> dict[str, Any]:
        """Permet à l'utilisateur d'abandonner explicitement une transaction en attente (Option A2)."""
        with schema_context(get_public_schema_name()):
            with transaction.atomic():
                paiement = (
                    PaiementAbonnement.objects.select_for_update()
                    .filter(facture__entreprise=entreprise)
                    .filter(
                        models.Q(reference_transaction=transaction_id)
                        | models.Q(reference_commande=transaction_id)
                    )
                    .select_related("facture")
                    .first()
                )
                if not paiement:
                    raise ValueError(f"Transaction « {transaction_id} » introuvable pour cette entreprise.")

                if paiement.statut == PaiementAbonnement.Statut.CONFIRME:
                    raise ValueError("Cette transaction a déjà été confirmée et ne peut plus être annulée.")

                if paiement.statut in [
                    PaiementAbonnement.Statut.INITIE,
                    PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR,
                ]:
                    ancien_statut = paiement.statut
                    paiement.statut = PaiementAbonnement.Statut.ANNULE
                    charge = dict(paiement.charge_utile or {})
                    charge["annulation"] = {
                        "motif": motif,
                        "annule_le": timezone.now().isoformat(),
                    }
                    paiement.charge_utile = charge
                    paiement.save(update_fields=["statut", "charge_utile", "modifie_le"])

                    journaliser(
                        action=ActionAudit.MODIFICATION,
                        type_entite="PaiementAbonnement",
                        entite_id=paiement.id,
                        valeur_avant={"statut": ancien_statut},
                        valeur_apres={"statut": PaiementAbonnement.Statut.ANNULE, "motif": motif},
                    )

                    return {
                        "statut": "ANNULE",
                        "transaction_id": transaction_id,
                        "message": "La tentative de paiement a été annulée avec succès.",
                    }

                return {
                    "statut": paiement.statut,
                    "transaction_id": transaction_id,
                    "message": f"La transaction est déjà à l'état {paiement.get_statut_display()}.",
                }

    @classmethod
    def recuperer_paiement_en_cours(cls, entreprise) -> dict[str, Any] | None:
        """Retourne les informations du paiement actuellement en cours s'il existe."""
        with schema_context(get_public_schema_name()):
            limite_active = timezone.now() - timedelta(minutes=PaiementAbonnement.DELAI_VERROU_MINUTES)
            paiement = (
                PaiementAbonnement.objects.filter(
                    facture__entreprise=entreprise,
                    statut__in=[
                        PaiementAbonnement.Statut.INITIE,
                        PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR,
                    ],
                    cree_le__gte=limite_active,
                )
                .select_related("facture__abonnement__plan")
                .order_by("-cree_le")
                .first()
            )
            if not paiement:
                return None

            return {
                "transaction_id": paiement.reference_transaction or paiement.reference_commande,
                "reference_facture": paiement.facture.numero,
                "montant_fcfa": paiement.montant_fcfa,
                "forfait": paiement.facture.abonnement.plan.libelle,
                "statut": paiement.statut,
                "secondes_restantes": paiement.secondes_restantes_verrou,
                "cree_le": paiement.cree_le.isoformat() if paiement.cree_le else None,
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
        3. Contrôle le site_id si fourni.
        4. Appelle CinetPay check_payment pour certifier le statut et le montant.
        5. Verrouille la ligne en base de données (select_for_update).
        6. Si validé :
           - Résurrection (Règle C1) si la transaction avait été annulée/expirée mais a été débitée.
           - Paiement -> CONFIRME
           - Facture -> PAYEE
           - Abonnement -> ACTIF (prolongé à partir de max(aujourd'hui, abonnement.date_fin))
           - Entreprise -> ACTIF (Règle R-113)
           - Envoi email confirmation & journalisation audit
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

            # Protection contre le rejeu (Idempotence rapide avant appel distant)
            if paiement.statut == PaiementAbonnement.Statut.CONFIRME:
                logger.info(
                    f"Transaction {transaction_id} déjà confirmée. Acquittement sans doublon."
                )
                return {
                    "statut": "DEJA_CONFIRME",
                    "transaction_id": transaction_id,
                    "facture": paiement.facture.numero,
                    "reference_facture": paiement.facture.numero,
                }

            # Vérification du site_id si présent
            site_id_attendu = getattr(settings, "CINETPAY_SITE_ID", "")
            site_id_recu = (donnees_webhook or {}).get("cpm_site_id") or (
                donnees_webhook or {}
            ).get("site_id")
            if (
                site_id_attendu
                and site_id_recu
                and str(site_id_recu).strip() != str(site_id_attendu).strip()
            ):
                logger.warning(
                    f"Notification CinetPay rejetée : site_id mismatch "
                    f"(reçu: {site_id_recu}, attendu: {site_id_attendu})"
                )
                return {
                    "statut": "SITE_INVALIDE",
                    "message": "Identifiant de site CinetPay non conforme.",
                }

            # Contre-vérification sécurisée auprès de CinetPay
            client = CinetPayClient()
            verification = client.verifier_transaction(transaction_id)

            statut_cinet = verification.get("statut")
            montant_paye_fcfa = verification.get("montant", 0)
            moyen = verification.get("moyen_paiement", "")

            with transaction.atomic():
                # Verrouillage pessimiste pour éliminer toute condition de concurrence (Race Condition)
                paiement = (
                    PaiementAbonnement.objects.select_for_update()
                    .filter(id=paiement.id)
                    .select_related("facture__abonnement__plan", "facture__entreprise")
                    .first()
                )
                if not paiement:
                    return {"statut": "INCONNU", "message": f"Transaction {transaction_id} introuvable."}

                if paiement.statut == PaiementAbonnement.Statut.CONFIRME:
                    return {
                        "statut": "DEJA_CONFIRME",
                        "transaction_id": transaction_id,
                        "facture": paiement.facture.numero,
                        "reference_facture": paiement.facture.numero,
                    }

                # Enregistrement de la charge utile brute pour audit et conformité
                charge_totale = dict(paiement.charge_utile or {})
                charge_totale.update(
                    {
                        "webhook": donnees_webhook or {},
                        "verification": verification.get("donnees_brutes", {}),
                        "verifie_le": timezone.now().isoformat(),
                    }
                )

                if statut_cinet == "ACCEPTED":
                    # Option C1 : Résurrection si la transaction était annulée ou expirée
                    etait_annule_ou_expire = paiement.statut in [
                        PaiementAbonnement.Statut.ANNULE,
                        PaiementAbonnement.Statut.EXPIRE,
                        PaiementAbonnement.Statut.ECHOUE,
                    ]
                    if etait_annule_ou_expire:
                        logger.warning(
                            f"RÉSURRECTION (Option C1) : Transaction {transaction_id} "
                            f"initialement {paiement.statut} confirmée par l'opérateur. Prolongation d'abonnement appliquée."
                        )
                        charge_totale["resurrection"] = {
                            "statut_precedent": paiement.statut,
                            "resuscite_le": timezone.now().isoformat(),
                            "motif": "Confirmation opérateur reçue a posteriori",
                        }

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
                        paiement.charge_utile = charge_totale
                        paiement.save(update_fields=["statut", "charge_utile", "modifie_le"])
                        return {
                            "statut": "ERREUR_MONTANT",
                            "message": (
                                "Le montant payé ne correspond pas au montant de la facture."
                            ),
                        }

                    # Confirmation du paiement
                    ancien_statut = paiement.statut
                    paiement.statut = PaiementAbonnement.Statut.CONFIRME
                    paiement.mode = cls.mapper_mode_paiement(moyen)
                    paiement.paye_le = timezone.now()
                    paiement.charge_utile = charge_totale
                    paiement.save(
                        update_fields=["statut", "mode", "paye_le", "charge_utile", "modifie_le"]
                    )

                    # Validation de la facture
                    facture = paiement.facture
                    facture.statut = Facture.Statut.PAYEE
                    facture.save(update_fields=["statut", "modifie_le"])

                    # Mise à jour de l'abonnement (Option C1 : prolongation sans écrasement)
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

                    # Envoi de l'email de confirmation (Socle Commun §1.1, non bloquant)
                    email_destinataire = entreprise.email_contact
                    if email_destinataire:
                        envoyer(
                            "confirmation_paiement",
                            f"Confirmation de paiement — Facture {facture.numero}",
                            email_destinataire,
                            {
                                "raison_sociale": entreprise.raison_sociale,
                                "numero_facture": facture.numero,
                                "forfait": abonnement.plan.libelle,
                                "montant_fcfa": paiement.montant_fcfa,
                                "mode_paiement": paiement.get_mode_display(),
                                "date_fin": abonnement.date_fin.strftime("%d/%m/%Y"),
                                "transaction_id": transaction_id,
                            },
                        )

                    # Journalisation d'audit immuable (Socle Commun §2.4)
                    journaliser(
                        action=ActionAudit.VALIDATION,
                        type_entite="PaiementAbonnement",
                        entite_id=paiement.id,
                        valeur_avant={"statut": ancien_statut},
                        valeur_apres={
                            "statut": PaiementAbonnement.Statut.CONFIRME,
                            "facture": facture.numero,
                            "montant_fcfa": paiement.montant_fcfa,
                            "mode": paiement.mode,
                        },
                    )

                    logger.info(
                        f"Paiement validé avec succès pour {entreprise.raison_sociale} "
                        f"(Transaction: {transaction_id}, Facture: {facture.numero})"
                    )

                    return {
                        "statut": "CONFIRME",
                        "transaction_id": transaction_id,
                        "facture": facture.numero,
                        "reference_facture": facture.numero,
                        "abonnement_expire_le": abonnement.date_fin.isoformat(),
                        "date_fin": abonnement.date_fin.isoformat(),
                        "mode_paiement": paiement.get_mode_display(),
                        "montant_fcfa": paiement.montant_fcfa,
                    }
                elif statut_cinet in ["PENDING", "WAITING", "PROCESSING"]:
                    # Mise à jour vers EN_ATTENTE_OPERATEUR si la transaction n'est pas explicitement annulée
                    if paiement.statut != PaiementAbonnement.Statut.ANNULE:
                        paiement.statut = PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR
                    paiement.charge_utile = charge_totale
                    paiement.save(update_fields=["statut", "charge_utile", "modifie_le"])
                    logger.info(
                        f"Transaction {transaction_id} en attente opérateur ({statut_cinet})."
                    )
                    return {
                        "statut": "EN_ATTENTE_OPERATEUR",
                        "transaction_id": transaction_id,
                        "message": "Paiement en cours de traitement par l'opérateur.",
                    }
                else:
                    # Échec ou annulation confirmée par l'opérateur
                    paiement.statut = PaiementAbonnement.Statut.ECHOUE
                    paiement.charge_utile = charge_totale
                    paiement.save(update_fields=["statut", "charge_utile", "modifie_le"])
                    logger.warning(f"Paiement refusé pour {transaction_id} : statut={statut_cinet}")
                    return {
                        "statut": "ECHOUE",
                        "motif": verification.get("message", "Paiement non accepté"),
                    }

    @classmethod
    def verifier_paiements_en_attente(
        cls,
        delai_min_minutes: int = 2,
        delai_max_minutes: int | None = None,
        timeout_heures: int | None = 24,
    ) -> dict[str, Any]:
        """Vérifie automatiquement les transactions en attente auprès de CinetPay.

        - Analyse les paiements `INITIE` et `EN_ATTENTE_OPERATEUR` créés il y a au moins `delai_min_minutes`.
        - Si une transaction a plus de `timeout_heures` (si configuré), elle est marquée comme `EXPIRE`.
        - Pour les autres, interroge l'API CinetPay (check_payment) et applique les transitions.
        """
        with schema_context(get_public_schema_name()):
            maintenant = timezone.now()
            seuil_reconciliation = maintenant - timedelta(minutes=delai_min_minutes)

            # 1. Marquer les transactions dépassées comme expirées (si timeout_heures est défini)
            nb_expires = 0
            seuil_expiration = None
            if timeout_heures is not None:
                seuil_expiration = maintenant - timedelta(hours=timeout_heures)
                anciennes = PaiementAbonnement.objects.filter(
                    statut__in=[
                        PaiementAbonnement.Statut.INITIE,
                        PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR,
                    ],
                    cree_le__lt=seuil_expiration,
                )
                for p in anciennes:
                    p.statut = PaiementAbonnement.Statut.EXPIRE
                    motif = f"Délai d'attente dépassé ({timeout_heures}h sans confirmation opérateur)."
                    charge = dict(p.charge_utile or {})
                    charge.update(
                        {
                            "motif_expiration": motif,
                            "expire_le": maintenant.isoformat(),
                        }
                    )
                    p.charge_utile = charge
                    p.save(update_fields=["statut", "charge_utile", "modifie_le"])
                    nb_expires += 1

            # 2. Vérifier les transactions éligibles à la réconciliation
            query = PaiementAbonnement.objects.filter(
                statut__in=[
                    PaiementAbonnement.Statut.INITIE,
                    PaiementAbonnement.Statut.EN_ATTENTE_OPERATEUR,
                ],
                cree_le__lte=seuil_reconciliation,
            )
            if seuil_expiration is not None:
                query = query.filter(cree_le__gte=seuil_expiration)
            if delai_max_minutes is not None:
                seuil_max = maintenant - timedelta(minutes=delai_max_minutes)
                query = query.filter(cree_le__gte=seuil_max)

            candidats = list(query.order_by("cree_le"))

            nb_confirmes = 0
            nb_echoues = 0
            nb_en_attente = 0

            for paiement in candidats:
                tx_id = paiement.reference_transaction or paiement.reference_commande
                try:
                    res = cls.traiter_notification_webhook(tx_id)
                    st = res.get("statut")
                    if st in ["CONFIRME", "DEJA_CONFIRME"]:
                        nb_confirmes += 1
                    elif st in ["ECHOUE", "EXPIRE"]:
                        nb_echoues += 1
                    elif st in ["EN_ATTENTE", "EN_ATTENTE_OPERATEUR"]:
                        nb_en_attente += 1
                except Exception as e:
                    logger.error(f"Erreur lors de la vérification automatique de {tx_id} : {e}")

            logger.info(
                f"Réconciliation CinetPay terminée : {len(candidats)} examinés, "
                f"{nb_confirmes} confirmés, {nb_echoues} échoués/expirés, "
                f"{nb_en_attente} en attente, {nb_expires} expirés."
            )

            return {
                "total_candidats": len(candidats),
                "confirmes": nb_confirmes,
                "echoues": nb_echoues,
                "en_attente": nb_en_attente,
                "expires": nb_expires,
            }
