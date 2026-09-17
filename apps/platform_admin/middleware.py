"""Middleware de restriction en lecture seule pour l'assistance Super Admin.

Règles de sécurité :
- R-128 : L'impersonification est en lecture seule absolue. Aucune écriture n'est permise.
- Test 11 : Une écriture tentée pendant une impersonification est systématiquement refusée.
"""

from __future__ import annotations

import logging
import jwt
from django.http import JsonResponse
from django_tenants.utils import get_public_schema_name, schema_context

from apps.core.ip_restriction import extraire_ip_client
from apps.core.middleware import identifiant_requete_courant
from apps.platform_admin.models import JournalPlateforme

logger = logging.getLogger(__name__)

METHODES_MUTATION = frozenset({"POST", "PUT", "PATCH", "DELETE"})

CHEMINS_EXCLUS_DECONNEXION = (
    "/api/v1/super-admin/assistance/deconnexion/",
    "/api/v1/auth/deconnexion/",
)


class LectureSeuleAssistanceMiddleware:
    """Interdit toute écriture lorsqu'un jeton d'assistance Super Admin est utilisé."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token_payload = self._extraire_payload_jwt(request)
        if token_payload and (
            token_payload.get("is_impersonation") or token_payload.get("read_only")
        ):
            request.is_impersonation = True
            request.impersonation_payload = token_payload

            # Si c'est une méthode d'écriture et que ce n'est pas la déconnexion
            if request.method in METHODES_MUTATION:
                path = request.path
                if not any(path.startswith(exclu) for exclu in CHEMINS_EXCLUS_DECONNEXION):
                    self._journaliser_tentative_ecriture(request, token_payload)
                    trace_id = (
                        getattr(request, "identifiant_requete", None)
                        or identifiant_requete_courant()
                    )
                    return JsonResponse(
                        {
                            "erreur": {
                                "code": "ecriture_interdite_assistance",
                                "message": (
                                    "Les modifications sont strictement interdites en mode assistance "
                                    "Super Admin (lecture seule)."
                                ),
                                "trace_id": trace_id,
                            }
                        },
                        status=403,
                    )

        return self.get_response(request)

    @staticmethod
    def _extraire_payload_jwt(request) -> dict | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:].strip()
            if token_str:
                try:
                    return jwt.decode(token_str, options={"verify_signature": False})
                except Exception:
                    return None
        return None

    @staticmethod
    def _journaliser_tentative_ecriture(request, payload: dict) -> None:
        ip = extraire_ip_client(request)
        super_admin_id = payload.get("impersonateur_id")
        super_admin_email = payload.get("impersonateur_email")
        schema = payload.get("schema")

        logger.warning(
            "Tentative d'écriture bloquée en mode assistance : super_admin=%s methode=%s url=%s ip=%s",
            super_admin_email,
            request.method,
            request.path,
            ip,
        )

        try:
            with schema_context(get_public_schema_name()):
                JournalPlateforme.objects.create(
                    utilisateur_id=super_admin_id if super_admin_id else None,
                    action="TENTATIVE_ECRITURE_BLOQUEE",
                    detail={
                        "super_admin_id": super_admin_id,
                        "super_admin_email": super_admin_email,
                        "methode": request.method,
                        "chemin": request.path,
                        "schema_cible": schema,
                    },
                    adresse_ip=ip,
                    appareil=request.headers.get("User-Agent", "")[:255],
                )
        except Exception:
            logger.exception("Échec d'enregistrement de la tentative d'écriture bloquée dans l'audit.")
