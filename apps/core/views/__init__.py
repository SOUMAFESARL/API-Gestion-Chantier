"""Gestionnaires d'erreurs hors DRF.

Une URL qui ne correspond à aucune route n'atteint jamais une vue DRF :
c'est Django qui répond, et il répond en HTML. Sans ces gestionnaires, un
client qui se trompe d'URL reçoit une page web là où il attend du JSON, et
son analyseur échoue sur une erreur incompréhensible.

Les conventions d'API §5 disent « un seul format, pour toutes les erreurs,
sans exception ». Ces deux fonctions font que c'est vrai.
"""

from django.http import HttpResponse, JsonResponse

from apps.core.middleware import identifiant_requete_courant

PREFIXE_API = "/api/"


def _est_appel_api(request) -> bool:
    return request.path.startswith(PREFIXE_API) or "application/json" in request.headers.get(
        "Accept", ""
    )


def _json(code: str, message: str, statut: int) -> JsonResponse:
    return JsonResponse(
        {
            "erreur": {
                "code": code,
                "message": message,
                "details": {},
                "trace_id": identifiant_requete_courant(),
            }
        },
        status=statut,
    )


def page_introuvable(request, exception=None) -> HttpResponse:
    """handler404 — JSON pour l'API, comportement par défaut ailleurs."""
    if _est_appel_api(request):
        return _json("introuvable", "La ressource demandée est introuvable.", 404)
    return HttpResponse("Page introuvable", status=404, content_type="text/plain; charset=utf-8")


def erreur_serveur(request) -> HttpResponse:
    """handler500 — ne divulgue jamais de détail technique au client."""
    if _est_appel_api(request):
        return _json(
            "erreur_interne",
            "Une erreur interne est survenue. L'équipe technique a été informée.",
            500,
        )
    return HttpResponse("Erreur interne", status=500, content_type="text/plain; charset=utf-8")
