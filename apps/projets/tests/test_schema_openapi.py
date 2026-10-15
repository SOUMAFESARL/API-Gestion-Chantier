"""Vérification de la conformité du schéma OpenAPI pour le module projets (B6)."""

import re

import pytest
from django.urls import get_resolver
from drf_spectacular.generators import SchemaGenerator


def _normaliser_chemin_openapi(pattern_str: str) -> str:
    """Convertit un motif Django URL en chemin OpenAPI (/api/v1/.../{id}/)."""
    p = "/" + pattern_str.lstrip("/")
    p = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", p)
    return p.replace("{pk}", "{id}")


def _extraire_routes_projets():
    """Parcourt le résolveur d'URL tenant pour extraire toutes les routes du module projets."""
    resolver = get_resolver("config.urls_tenant")
    prefixes = (
        "api/v1/projets/",
        "api/v1/lots/",
        "api/v1/activites/",
        "api/v1/arrets-chantier/",
        "api/v1/referentiels/motifs-report/",
    )

    routes = []

    def _explorer(patterns, prefix=""):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                _explorer(p.url_patterns, prefix + str(p.pattern))
            elif hasattr(p, "callback"):
                full = prefix + str(p.pattern)
                if any(full.startswith(pref) for pref in prefixes):
                    view_class = getattr(
                        p.callback, "cls", getattr(p.callback, "view_class", None)
                    )
                    methods = []
                    if view_class:
                        allowed = getattr(
                            view_class,
                            "http_method_names",
                            ["get", "post", "put", "patch", "delete", "options", "head"],
                        )
                        for m in ["get", "post", "put", "patch", "delete"]:
                            if hasattr(view_class, m) and m in allowed:
                                methods.append(m)
                    routes.append((full, _normaliser_chemin_openapi(full), methods, view_class))

    _explorer(resolver.url_patterns)
    return routes


def test_schema_sans_avertissement_pour_projets():
    """Chaque route projets du résolveur doit être dans OpenAPI avec ses méthodes."""
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(request=None, public=True)
    paths = schema["paths"]

    routes = _extraire_routes_projets()
    assert len(routes) >= 30, f"On attendait au moins 30 routes projets, trouvé {len(routes)}"

    routes_manquantes = []
    methodes_manquantes = []

    for _full_pattern, openapi_path, methods, view_class in routes:
        if openapi_path not in paths:
            routes_manquantes.append((
                openapi_path,
                getattr(view_class, "__name__", str(view_class)),
            ))
            continue

        schema_methods = paths[openapi_path]
        for m in methods:
            if m not in schema_methods:
                methodes_manquantes.append((
                    openapi_path,
                    m,
                    getattr(view_class, "__name__", ""),
                ))

    assert not routes_manquantes, f"Routes projets manquantes dans OpenAPI: {routes_manquantes}"
    assert not methodes_manquantes, f"Méthodes manquantes dans OpenAPI: {methodes_manquantes}"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/projets/{id}/reprogrammer/",
        "/api/v1/lots/{id}/reprogrammer/",
        "/api/v1/activites/{id}/reprogrammer/",
    ],
)
def test_reprogrammer_documente(path):
    """Les routes de reprogrammation exposent motif_id et justification."""
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(request=None, public=True)
    assert path in schema["paths"], f"Chemin {path} absent du schéma OpenAPI"

    operation = schema["paths"][path]["post"]
    assert "requestBody" in operation, f"requestBody manquant pour {path}"

    body_content = operation["requestBody"]["content"]["application/json"]
    schema_ref = body_content["schema"]["$ref"]
    component_name = schema_ref.rsplit("/", 1)[-1]

    proprietes = schema["components"]["schemas"][component_name]["properties"]
    assert "motif_id" in proprietes, f"motif_id absent du schéma de requête pour {path}"
    assert "justification" in proprietes, f"justification absent du schéma de requête pour {path}"
