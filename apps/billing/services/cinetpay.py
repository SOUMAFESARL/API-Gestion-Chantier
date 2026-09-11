"""Client d'API CinetPay (Guichet Hébergé v2).

Gère l'initialisation de paiement et la vérification des transactions CinetPay
(Orange Money, Wave, MTN MoMo, Carte bancaire).
Intègre un mode simulation automatique lorsque les clés d'API ne sont pas encore configurées.
"""

import hashlib
import hmac
import logging
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

__all__ = ["CinetPayClient", "CinetPayError"]


class CinetPayError(Exception):
    """Erreur levée lors des interactions avec l'API CinetPay."""

    def __init__(self, message: str, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class CinetPayClient:
    """Client pour l'API CinetPay v2 (Checkout / Guichet Hébergé)."""

    def __init__(
        self,
        api_key: str | None = None,
        site_id: str | None = None,
        secret_key: str | None = None,
        checkout_url: str | None = None,
        check_url: str | None = None,
    ):
        self.api_key = api_key or getattr(settings, "CINETPAY_API_KEY", "")
        self.site_id = site_id or getattr(settings, "CINETPAY_SITE_ID", "")
        self.secret_key = secret_key or getattr(settings, "CINETPAY_SECRET_KEY", "")
        self.checkout_url = checkout_url or getattr(
            settings, "CINETPAY_CHECKOUT_URL", "https://api-checkout.cinetpay.com/v2/payment"
        )
        self.check_url = check_url or getattr(
            settings, "CINETPAY_CHECK_URL", "https://api-checkout.cinetpay.com/v2/payment/check"
        )

    @property
    def est_en_mode_simulation(self) -> bool:
        """Indique si le client opère en mode simulation locale (sans clés CinetPay réelles)."""
        return not (self.api_key and self.site_id)

    def verifier_signature(self, corps_brut: bytes | str, token_recu: str | None) -> bool:
        """Vérifie l'empreinte HMAC-SHA256 (en-tête X-Token) d'une notification webhook.

        - Si `secret_key` est renseigné et `token_recu` fourni, calcule le HMAC-SHA256
          du corps de requête et le compare à temps constant avec `token_recu`.
        - Si `secret_key` est renseigné mais `token_recu` absent, la notification est rejetée.
        - Si aucune `secret_key` n'est configurée (mode simulation locale ou test),
          la validation est acceptée et la sécurité repose sur la contre-interrogation directe.
        """
        if not self.secret_key:
            return True

        if not token_recu:
            logger.warning(
                "Notification CinetPay reçue sans X-Token alors que secret_key est configurée."
            )
            return False

        try:
            if isinstance(corps_brut, str):
                corps_brut = corps_brut.encode("utf-8")
            signature_calculee = hmac.new(
                self.secret_key.encode("utf-8"),
                corps_brut or b"",
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(signature_calculee.lower(), token_recu.strip().lower())
        except Exception as e:
            logger.error(f"Erreur lors du calcul HMAC CinetPay : {e}")
            return False

    def initier_paiement(
        self,
        transaction_id: str,
        montant_fcfa: int,
        description: str,
        notify_url: str,
        return_url: str,
        customer_email: str,
        customer_name: str,
        customer_surname: str = "Client",
        customer_phone: str = "",
        customer_city: str = "Abidjan",
        customer_country: str = "CI",
        channels: str = "ALL",
        metadata: str = "",
    ) -> dict[str, Any]:
        """Initie une session de paiement sur le guichet hébergé CinetPay.

        Retourne un dictionnaire contenant au minimum :
        - `payment_url`: URL vers laquelle rediriger l'utilisateur
        - `payment_token`: jeton unique de session
        """
        if self.est_en_mode_simulation:
            logger.warning(
                "CinetPay opérant en mode SIMULATION locale (clés API non fournies). "
                f"Transaction simulée : {transaction_id} ({montant_fcfa} FCFA)"
            )
            # URL de retour avec paramètre de succès simulé
            params = {
                "transaction_id": transaction_id,
                "token": f"sim_token_{transaction_id}",
                "simulated": "1",
            }
            simulated_url = f"{return_url}?{urlencode(params)}"
            return {
                "code": "201",
                "message": "CREATED (SIMULATION)",
                "data": {
                    "payment_token": f"sim_token_{transaction_id}",
                    "payment_url": simulated_url,
                },
                "api_response_id": f"sim_resp_{transaction_id}",
            }

        payload = {
            "apikey": self.api_key,
            "site_id": self.site_id,
            "transaction_id": transaction_id,
            "amount": int(montant_fcfa),
            "currency": "XOF",
            "description": description[:250],
            "notify_url": notify_url,
            "return_url": return_url,
            "channels": channels,
            "customer_id": customer_email,
            "customer_name": customer_name[:50],
            "customer_surname": customer_surname[:50] or "Client",
            "customer_email": customer_email,
            "customer_phone_number": customer_phone or "0000000000",
            "customer_address": "Abidjan",
            "customer_city": customer_city or "Abidjan",
            "customer_country": customer_country or "CI",
            "customer_state": customer_country or "CI",
            "customer_zip_code": "00225",
        }
        if metadata:
            payload["metadata"] = metadata

        try:
            response = requests.post(
                self.checkout_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Erreur de connexion CinetPay checkout : {e}")
            if getattr(settings, "DEBUG", False):
                logger.warning(
                    "Mode DEBUG actif : bascule automatique en simulation locale "
                    "car le serveur CinetPay n'est pas joignable."
                )
                params = {
                    "transaction_id": transaction_id,
                    "token": f"sim_token_{transaction_id}",
                    "simulated": "1",
                }
                return {
                    "code": "201",
                    "message": "CREATED (SIMULATION)",
                    "data": {
                        "payment_token": f"sim_token_{transaction_id}",
                        "payment_url": f"{return_url}?{urlencode(params)}",
                    },
                    "api_response_id": f"sim_resp_{transaction_id}",
                }
            raise CinetPayError(f"Impossible de joindre CinetPay : {e}") from e
        except ValueError as e:
            logger.error(f"Réponse CinetPay non JSON : {response.text}")
            raise CinetPayError("Réponse invalide du serveur de paiement") from e

        code = str(data.get("code"))
        if code != "201":
            msg = data.get("message") or data.get("description") or "Erreur d'initialisation"
            logger.error(f"Erreur CinetPay [{code}]: {msg}")
            raise CinetPayError(msg, code=code, details=data)

        return data

    def verifier_transaction(self, transaction_id: str) -> dict[str, Any]:
        """Vérifie l'état réel d'une transaction directement auprès de CinetPay (check_payment).

        Retourne les détails vérifiés de la transaction :
        - `statut`: 'ACCEPTED', 'REFUSED', 'CANCELLED', 'PENDING'
        - `montant`: montant en XOF
        - `moyen_paiement`: ex 'OM', 'WAVE', 'MOMO', 'VISA'
        - `donnees_brutes`: dictionnaire complet
        """
        if self.est_en_mode_simulation:
            logger.info(f"Vérification SIMULÉE pour transaction : {transaction_id}")
            return {
                "statut": "ACCEPTED",
                "code": "00",
                "message": "SUCCES (SIMULE)",
                "montant": 49000,
                "devise": "XOF",
                "moyen_paiement": "WAVE",
                "donnees_brutes": {
                    "code": "00",
                    "message": "SUCCES",
                    "data": {
                        "amount": "49000",
                        "currency": "XOF",
                        "status": "ACCEPTED",
                        "payment_method": "WAVE",
                        "operator_id": f"WAVE_SIM_{transaction_id}",
                        "payment_date": "2026-09-11 12:00:00",
                    },
                },
            }

        payload = {
            "apikey": self.api_key,
            "site_id": self.site_id,
            "transaction_id": transaction_id,
        }

        try:
            response = requests.post(
                self.check_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Erreur de connexion CinetPay check : {e}")
            if getattr(settings, "DEBUG", False):
                logger.warning(
                    "Mode DEBUG actif : vérification simulée ACCEPTED "
                    "car le serveur CinetPay n'est pas joignable."
                )
                return {
                    "statut": "ACCEPTED",
                    "code": "00",
                    "message": "SUCCES (SIMULATION LOCALE)",
                    "montant": 49000,
                    "devise": "XOF",
                    "moyen_paiement": "WAVE",
                    "donnees_brutes": {
                        "code": "00",
                        "message": "SUCCES",
                        "data": {
                            "amount": "49000",
                            "currency": "XOF",
                            "status": "ACCEPTED",
                            "payment_method": "WAVE",
                            "operator_id": f"OP_SIM_{transaction_id}",
                        },
                    },
                }
            msg = f"Impossible de vérifier la transaction auprès de CinetPay : {e}"
            raise CinetPayError(msg) from e
        except ValueError as e:
            logger.error(f"Réponse CinetPay non JSON : {response.text}")
            raise CinetPayError("Réponse invalide du serveur de paiement") from e

        code = str(data.get("code"))
        res_data = data.get("data", {})
        statut = res_data.get("status", "").upper()

        return {
            "statut": statut,
            "code": code,
            "message": data.get("message", ""),
            "montant": int(float(res_data.get("amount", 0))) if res_data.get("amount") else 0,
            "devise": res_data.get("currency", "XOF"),
            "moyen_paiement": res_data.get("payment_method", "AUTRE"),
            "donnees_brutes": data,
        }
