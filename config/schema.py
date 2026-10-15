"""Visibility rules for project endpoints in the public OpenAPI document."""


def limiter_projets_au_crud(endpoints):
    """Expose all project endpoints in the public OpenAPI document."""
    return endpoints
