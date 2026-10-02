"""Visibility rules for project endpoints in the public OpenAPI document."""


def limiter_projets_au_crud(endpoints):
    """Keep only list/create and detail/update/delete under /projets/."""
    from apps.projets.views import ProjetDetailView, ProjetListCreateView

    crud = {
        ProjetListCreateView: {"GET", "POST"},
        ProjetDetailView: {"GET", "PUT", "PATCH", "DELETE"},
    }
    return [
        endpoint
        for endpoint in endpoints
        if "/projets/" not in endpoint[0]
        or endpoint[2] in crud.get(getattr(endpoint[3], "cls", None), set())
    ]
