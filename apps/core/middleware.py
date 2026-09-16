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
    """Restreint l'accès aux routes d'authentification du schéma `public`.

    **Le Super Admin n'est pas un rôle, c'est un territoire.** Il vit dans
    `public.utilisateur` — la même table que les collaborateurs d'un client,
    mais dans un autre schéma (écart E1). Ce qui le distingue n'est donc pas
    une colonne qu'on peut se donner : c'est l'endroit d'où il se connecte.

    La matrice des rôles §1.1 exige que cette porte soit **restreinte par
    adresse IP**. C'est une restriction d'infrastructure — un `allow` Nginx la
    poserait aussi bien — mais la poser ici la rend vraie même quand le
    reverse-proxy est mal configuré, et une porte d'administration qui dépend
    d'un fichier de configuration qu'on ne relit jamais n'est pas restreinte.

    **En production, une liste vide interdit tout.** C'est délibéré : la
    valeur par défaut d'une porte d'administration doit être fermée. Un
    déploiement qui oublie `SUPER_ADMIN_IPS` s'en aperçoit à la première
    connexion, ce qui est infiniment préférable à ne jamais s'en apercevoir.
    En développement, une liste vide laisse passer.
    """

    PREFIXE_PROTEGE = "/api/v1/auth/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from django.http import JsonResponse
        from django_tenants.utils import get_public_schema_name

        # Prévol CORS (OPTIONS) : les requêtes preflight du navigateur ne transportent
        # ni corps ni authentification et ne doivent jamais être bloquées par restriction IP.
        if request.method == "OPTIONS":
            return self.get_response(request)

        if (
            request.path.startswith(self.PREFIXE_PROTEGE)
            and not request.path.startswith("/api/v1/auth/mot-de-passe/")
            and self._sur_la_plateforme(request, get_public_schema_name())
        ):
            est_compte_plateforme = True
            if request.path == "/api/v1/auth/token/" and request.method == "POST":
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
                request.path
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
                        if schema and schema != get_public_schema_name():
                            est_compte_plateforme = False
                except Exception:
                    pass

            if est_compte_plateforme:
                autorisees = getattr(settings, "SUPER_ADMIN_IPS", [])
                ouverte = bool(autorisees) is False and settings.DEBUG

                if not ouverte and request.META.get("REMOTE_ADDR") not in autorisees:
                    return JsonResponse(
                        {
                            "erreur": {
                                "code": "acces_refuse",
                                "message": "Cet accès est restreint.",
                                "details": {},
                            }
                        },
                        status=403,
                    )

        return self.get_response(request)

    @staticmethod
    def _sur_la_plateforme(request, schema_public: str) -> bool:
        """Vrai quand la requête est résolue sur le schéma `public`.

        `request.tenant` est posé par `TenantMainMiddleware`, qui s'exécute
        avant celui-ci — d'où sa place en deuxième dans la chaîne.
        """
        tenant = getattr(request, "tenant", None)
        return tenant is not None and tenant.schema_name == schema_public
