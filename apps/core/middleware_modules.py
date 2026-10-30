"""Un module fermé à l'entreprise n'a plus de route — refus avant la vue.

**Pourquoi un middleware et non une permission DRF** (même raison que
`apps.billing.middleware`) : la plupart des vues écrivent
`permission_classes = [IsAuthenticated]`, ce qui remplace un réglage global au lieu de s'y
ajouter. `APermission` filtre déjà les permissions d'un module fermé ; ce verrou couvre en plus
les vues qui ne demandent aucune permission de module.

Le module d'une vue se lit dans son chemin Python (`apps.projets.views…`) : une application
Django = un module du catalogue. Le tableau de bord, rangé dans `apps.projets` mais gardé par
`pilotage.lire`, appartient au module « pilotage ».
"""

from __future__ import annotations

from django.http import JsonResponse

from apps.core.modules_actifs import codes_modules_actifs

__all__ = ["ModuleFermeMiddleware", "module_de_la_vue"]

# Du plus précis au plus général : le premier préfixe qui correspond l'emporte.
MODULES_PAR_CHEMIN: tuple[tuple[str, str], ...] = (
    ("apps.projets.views.tableau_de_bord", "pilotage"),
    ("apps.pilotage.", "pilotage"),
    ("apps.projets.", "projets"),
    ("apps.chantier.", "chantier"),
    ("apps.tiers.", "tiers"),
    ("apps.ged.", "ged"),
)


def module_de_la_vue(view_func) -> str | None:
    chemin = getattr(view_func, "__module__", "") or ""
    for prefixe, module in MODULES_PAR_CHEMIN:
        if chemin.startswith(prefixe):
            return module
    return None


class ModuleFermeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        tenant = getattr(request, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            return None
        module = module_de_la_vue(view_func)
        if module is None or module in codes_modules_actifs(tenant):
            return None
        return JsonResponse(
            {
                "erreur": {
                    "code": "module_desactive",
                    "message": "Ce module n'est pas ouvert à votre entreprise.",
                    "details": {"module": module},
                    "trace_id": getattr(request, "identifiant_requete", None),
                }
            },
            status=403,
        )
