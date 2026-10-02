"""Project documentation exposes the CRUD while business routes still resolve."""

from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator

from apps.core.enums import StatutProjet


def test_schema_contains_project_crud_and_lot_workflow():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    paths = {path: value for path, value in schema["paths"].items() if "/projets/" in path}
    assert set(paths) == {
        "/api/v1/projets/", "/api/v1/projets/{id}/",
        "/api/v1/projets/{id}/lots/", "/api/v1/projets/{id}/lots/import/",
        "/api/v1/projets/{id}/lots/modele/",
    }
    assert set(paths["/api/v1/projets/"]) == {"get", "post"}
    assert set(paths["/api/v1/projets/{id}/"]) == {"get", "put", "patch", "delete"}


def test_hidden_business_routes_remain_available():
    for path in (
        "/api/v1/projets/contexte-creation/",
        "/api/v1/projets/meteo/",
        "/api/v1/projets/00000000-0000-0000-0000-000000000001/permissions-roles/",
        "/api/v1/projets/00000000-0000-0000-0000-000000000001/affectations/",
    ):
        assert resolve(path, urlconf="config.urls_tenant")


def test_project_id_is_documented_only_in_responses():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    schemas = schema["components"]["schemas"]
    response = schemas["ProjetCreationResponse"]["properties"]["id"]
    assert response["type"] == "string"
    assert response["format"] == "uuid"
    assert response["readOnly"] is True
    assert "id" not in schemas["ProjetPost"]["properties"]
    assert "id" not in schemas["ProjetPatch"]["properties"]


def test_status_patch_examples_and_choices():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    components = schema["components"]["schemas"]
    assert any(set(item.get("enum", [])) == set(StatutProjet.values)
               for item in components.values())
    for name in ("ProjetPost", "ProjetPatch", "ProjetCreationResponse"):
        assert "statut" in components[name]["properties"]
    operation = schema["paths"]["/api/v1/projets/{id}/"]["patch"]
    examples = operation["requestBody"]["content"]["application/json"]["examples"]
    assert {item["value"]["statut"] for item in examples.values()} == {
        "EN_ATTENTE", "SUSPENDU", "BLOQUE", "DESACTIVE", "RESILIE", "EN_COURS",
    }
    assert set(operation["responses"]) == {"200", "400", "401", "403", "404"}


def test_optional_real_dates_and_read_only_metrics():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    components = schema["components"]["schemas"]
    for name in ("ProjetPost", "ProjetPatch"):
        for field in ("date_debut_reelle", "date_fin_reelle"):
            prop = components[name]["properties"][field]
            assert prop["format"] == "date"
            assert prop["nullable"] is True
            assert field not in components[name].get("required", [])
        for field in ("avancement_reel", "indice_sante"):
            assert field not in components[name]["properties"]
    for field in ("avancement_reel", "indice_sante"):
        assert components["ProjetCreationResponse"]["properties"][field]["readOnly"] is True
    assert components["ProjetCreationResponse"]["properties"]["indice_sante"]["nullable"] is True
