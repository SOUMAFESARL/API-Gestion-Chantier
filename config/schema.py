"""Visibility rules for project endpoints in the public OpenAPI document."""


def limiter_projets_au_crud(endpoints):
    """Expose project CRUD and the independent lot creation/import workflow."""
    from apps.projets.views import ProjetDetailView, ProjetListCreateView
    from apps.projets.views.lot import (
        ProjetLotImportView,
        ProjetLotListCreateView,
        ProjetLotModeleView,
    )

    crud = {
        ProjetListCreateView: {"GET", "POST"},
        ProjetDetailView: {"GET", "PUT", "PATCH", "DELETE"},
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
