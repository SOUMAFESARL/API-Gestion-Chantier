"""Identifiant de corrélation — conventions d'API §10.

Chaque requête reçoit un identifiant, renvoyé dans l'en-tête `X-Request-Id`
et repris comme `trace_id` dans toute erreur. C'est ce que l'utilisateur
communique au support, et ce qui permet de retrouver la requête exacte
dans les journaux — y compris à travers une tâche Celery.

Le client peut fournir le sien : on le reprend tel quel plutôt que d'en
générer un autre, pour que la trace couvre l'aller-retour complet.
"""

import uuid
from contextvars import ContextVar

_identifiant: ContextVar[str | None] = ContextVar("identifiant_requete", default=None)

EN_TETE = "X-Request-Id"
LONGUEUR_MAX = 64


def identifiant_requete_courant() -> str | None:
    """Identifiant de la requête en cours de traitement, s'il y en a une."""
    return _identifiant.get()


class IdentifiantRequeteMiddleware:
    """Attribue un identifiant à chaque requête et le renvoie au client."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        fourni = request.headers.get(EN_TETE, "").strip()
        # Un identifiant fourni par le client est repris s'il est plausible ;
        # sinon on en génère un, sans jamais refuser la requête pour si peu.
        identifiant = fourni[:LONGUEUR_MAX] if fourni.isascii() and fourni else uuid.uuid4().hex

        jeton = _identifiant.set(identifiant)
        try:
            request.identifiant_requete = identifiant
            reponse = self.get_response(request)
            reponse[EN_TETE] = identifiant
            return reponse
        finally:
            _identifiant.reset(jeton)


class RestrictionIPPlateformeMiddleware:
    """Restreint l'accès aux routes d'administration et d'authentification du schéma `public`.

    **Le Super Admin n'est pas un rôle, c'est un territoire.** Il vit dans
    `public.utilisateur` — la même table que les collaborateurs d'un client,
    mais dans un autre schéma (écart E1). Ce qui le distingue n'est donc pas
    une colonne qu'on peut se donner : c'est l'endroit d'où il se connecte.

    La matrice des rôles §1.1 et US-023 exigent que les portes d'administration
    (`/admin/`, `/admin/dashboard/`, endpoints Super Admin) et d'authentification
    plateforme soient **strictement restreintes par adresse IP**.

    **En production, une liste vide interdit tout.** C'est délibéré : la
    valeur par défaut d'une porte d'administration doit être fermée. Un
    déploiement qui oublie `SUPER_ADMIN_IPS` s'en aperçoit à la première
    connexion, ce qui est infiniment préférable à ne jamais s'en apercevoir.
    En développement, une liste vide laisse passer.
    """

    PREFIXES_API_AUTH = "/api/v1/auth/"
    PREFIXES_ADMIN = ("/admin/", "/admin")
    PREFIXES_SUPER_ADMIN = "/api/v1/super-admin/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import logging
        from django.conf import settings
        from django.http import HttpResponseForbidden, JsonResponse
        from django_tenants.utils import get_public_schema_name

        from apps.core.ip_restriction import est_ip_autorisee, extraire_ip_client

        logger = logging.getLogger("securite.super_admin")

        # Prévol CORS (OPTIONS) : les requêtes preflight du navigateur ne transportent
        # ni corps ni authentification et ne doivent jamais être bloquées par restriction IP.
        if request.method == "OPTIONS":
            return self.get_response(request)

        path = request.path
        schema_public = get_public_schema_name()
        sur_plateforme = self._sur_la_plateforme(request, schema_public)
        ip_cliente = extraire_ip_client(request)

        # 1. Protection de l'administration Django (/admin/ et /admin/dashboard/)
        est_route_admin = path == "/admin" or path.startswith("/admin/")
        if est_route_admin:
            # L'administration Django est strictement interdite sur les sous-domaines clients (tenants)
            if not sur_plateforme:
                self._journaliser_rejet(logger, ip_cliente, request, motif="acces_admin_sur_tenant")
                return self._reponse_interdite(request, "Accès au panneau d'administration non autorisé.")

            # Sur la plateforme (public), l'accès est restreint par adresse IP
            autorisees = getattr(settings, "SUPER_ADMIN_IPS", [])
            ouverte = bool(autorisees) is False and settings.DEBUG

            if not ouverte and not est_ip_autorisee(ip_cliente, autorisees):
                self._journaliser_rejet(logger, ip_cliente, request, motif="ip_non_autorisee_admin")
                return self._reponse_interdite(request, "Cet accès est restreint.")

        # 2. Protection des endpoints API Super Admin (/api/v1/super-admin/)
        elif path.startswith(self.PREFIXES_SUPER_ADMIN):
            if not sur_plateforme:
                self._journaliser_rejet(logger, ip_cliente, request, motif="super_admin_api_sur_tenant")
                return self._reponse_interdite(request, "Cet accès est restreint.")

            autorisees = getattr(settings, "SUPER_ADMIN_IPS", [])
            ouverte = bool(autorisees) is False and settings.DEBUG

            if not ouverte and not est_ip_autorisee(ip_cliente, autorisees):
                self._journaliser_rejet(logger, ip_cliente, request, motif="ip_non_autorisee_super_admin")
                return self._reponse_interdite(request, "Cet accès est restreint.")

        # 3. Protection de l'authentification plateforme (/api/v1/auth/)
        elif (
            path.startswith(self.PREFIXES_API_AUTH)
            and not path.startswith("/api/v1/auth/mot-de-passe/")
            and sur_plateforme
        ):
            est_compte_plateforme = True
            if path == "/api/v1/auth/token/" and request.method == "POST":
                try:
                    import json

                    body = json.loads(request.body.decode("utf-8"))
                    email = (body.get("email") or "").strip().lower()
                    if email:
                        from apps.accounts.models import Utilisateur

                        est_compte_plateforme = Utilisateur.objects.filter(
                            email__iexact=email
                        ).exists()
                except Exception:
                    pass
            elif (
                path
                in (
                    "/api/v1/auth/token/refresh/",
                    "/api/v1/auth/token/verifier/",
                    "/api/v1/auth/deconnexion/",
                )
                and request.method == "POST"
            ):
                try:
                    import json
                    import jwt

                    body = json.loads(request.body.decode("utf-8"))
                    token_str = (body.get("refresh") or body.get("token") or "").strip()
                    if token_str:
                        payload = jwt.decode(token_str, options={"verify_signature": False})
                        schema = payload.get("schema")
                        if schema and schema != schema_public:
                            est_compte_plateforme = False
                except Exception:
                    pass

            if est_compte_plateforme:
                autorisees = getattr(settings, "SUPER_ADMIN_IPS", [])
                ouverte = bool(autorisees) is False and settings.DEBUG

                if not ouverte and not est_ip_autorisee(ip_cliente, autorisees):
                    self._journaliser_rejet(logger, ip_cliente, request, motif="ip_non_autorisee_auth")
                    return self._reponse_interdite(request, "Cet accès est restreint.")

        return self.get_response(request)

    @staticmethod
    def _journaliser_rejet(logger, ip_cliente: str, request, motif: str):
        trace_id = getattr(request, "identifiant_requete", None) or identifiant_requete_courant()
        user_agent = request.headers.get("User-Agent", "inconnu")[:200]
        logger.warning(
            "Tentative d'accès non autorisée au panneau d'administration [motif=%s] : "
            "IP=%s, chemin=%s, methode=%s, trace_id=%s, user_agent=%s",
            motif,
            ip_cliente,
            request.path,
            request.method,
            trace_id,
            user_agent,
        )

    @staticmethod
    def _reponse_interdite(request, message: str):
        from django.http import HttpResponseForbidden, JsonResponse

        veut_json = (
            request.path.startswith("/api/")
            or request.content_type == "application/json"
            or "application/json" in request.headers.get("Accept", "")
        )

        if veut_json:
            return JsonResponse(
                {
                    "erreur": {
                        "code": "acces_refuse",
                        "message": message,
                        "details": {},
                    }
                },
                status=403,
            )

        html = (
            "<!DOCTYPE html>\n"
            "<html lang=\"fr\"><head><meta charset=\"utf-8\"><title>403 Accès Refusé</title>\n"
            "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;"
            "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}\n"
            ".card{text-align:center;padding:2.5rem;background:#1e293b;border-radius:12px;"
            "box-shadow:0 10px 25px rgba(0,0,0,0.5);max-width:480px;border:1px solid #334155;}\n"
            "h1{font-size:1.75rem;margin-bottom:0.75rem;color:#f43f5e;}\n"
            "p{color:#94a3b8;line-height:1.6;font-size:0.95rem;margin:0;}\n"
            "</style></head><body>\n"
            "<div class=\"card\"><h1>Accès Restreint (403)</h1>\n"
            "<p>Cette zone d'administration est strictement réservée aux adresses IP autorisées.</p>\n"
            "</div></body></html>"
        )
        return HttpResponseForbidden(html, content_type="text/html; charset=utf-8")

    @staticmethod
    def _sur_la_plateforme(request, schema_public: str) -> bool:
        """Vrai quand la requête est résolue sur le schéma `public`.

        `request.tenant` est posé par `TenantMainMiddleware`, qui s'exécute
        avant celui-ci — d'où sa place en deuxième dans la chaîne.
        """
        tenant = getattr(request, "tenant", None)
        return tenant is not None and tenant.schema_name == schema_public
