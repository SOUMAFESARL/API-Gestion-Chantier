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
    """Ancien middleware de restriction IP — complètement désactivé.

    Toutes les requêtes passent directement sans aucune restriction d'adresse IP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

