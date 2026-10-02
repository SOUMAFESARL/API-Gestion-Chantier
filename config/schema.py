"""Visibility rules for project endpoints in the public OpenAPI document."""


def limiter_projets_au_crud(endpoints):
    """Expose project CRUD and the independent lot creation/import workflow."""
    from apps.projets.views import ProjetDetailView, ProjetListCreateView
    from apps.projets.views.equipe import (
        ProjetEquipeAffectationDetailView,
        ProjetEquipeAffectationView,
        ProjetEquipeDetailView,
        ProjetEquipeListCreateView,
        ProjetEquipeStatistiquesView,
    )
    from apps.projets.views.lot import (
        ProjetLotImportView,
        ProjetLotListCreateView,
        ProjetLotModeleView,
    )
    from apps.projets.views.statistiques import ProjetStatistiquesView

    crud = {
        ProjetListCreateView: {"GET", "POST"},
        ProjetDetailView: {"GET", "PUT", "PATCH", "DELETE"},
        ProjetEquipeListCreateView: {"GET", "POST"},
        ProjetEquipeDetailView: {"GET", "DELETE"},
        ProjetEquipeAffectationView: {"GET", "POST"},
        ProjetEquipeAffectationDetailView: {"DELETE"},
        ProjetEquipeStatistiquesView: {"GET"},
        ProjetStatistiquesView: {"GET"},
        ProjetLotListCreateView: {"GET", "POST"},
        ProjetLotImportView: {"POST"},
        ProjetLotModeleView: {"GET"},
    }
    return [
        endpoint
        for endpoint in endpoints
        if "/projets/" not in endpoint[0]
        or endpoint[2] in crud.get(getattr(endpoint[3], "cls", None), set())
    ]
