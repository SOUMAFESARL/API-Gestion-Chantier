"""Project documentation exposes the CRUD while business routes still resolve."""

from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator


def test_schema_contains_only_project_crud():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    paths = {path: value for path, value in schema["paths"].items() if "/projets/" in path}
    assert set(paths) == {"/api/v1/projets/", "/api/v1/projets/{id}/"}
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
