"""Project documentation exposes the CRUD while business routes still resolve."""

from django.urls import resolve
from drf_spectacular.generators import SchemaGenerator

from apps.core.enums import StatutProjet


def test_evolution_status_is_writable_in_post_and_patch_requests():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    for path, method in (
        ("/api/v1/projets/{id}/lots/", "post"),
        ("/api/v1/lots/{lot_id}/activites/", "post"),
        ("/api/v1/lots/{id}/", "patch"),
        ("/api/v1/activites/{id}/", "patch"),
    ):
        body = schema["paths"][path][method]["requestBody"]["content"]["application/json"]
        component = body["schema"]["$ref"].rsplit("/", 1)[-1]
        definition = schema["components"]["schemas"][component]
        assert "statut" in definition["properties"]
        assert not definition["properties"]["statut"].get("readOnly", False)
        assert definition["properties"]["statut"]["type"] == "string"
        assert "enum" not in definition["properties"]["statut"]
        assert "maxLength" not in definition["properties"]["statut"]
        assert "statut" not in definition.get("required", [])
        assert definition["properties"]["motif"]["type"] == "string"
        assert not definition["properties"]["motif"].get("readOnly", False)
        assert "motif" not in definition.get("required", [])
    for component in ("LotResponse", "Activite"):
        fields = schema["components"]["schemas"][component]["properties"]
        assert fields["statut"]["type"] == "string"
        assert fields["motif"]["type"] == "string"


def test_lot_and_activity_mutations_are_visible_in_swagger():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    for resource in ("lots", "activites"):
        detail = schema["paths"][f"/api/v1/{resource}/{{id}}/"]
        assert set(detail) == {"get", "patch", "delete"}
        assert "204" in detail["delete"]["responses"]
        assert "requestBody" in detail["patch"]
        activation = schema["paths"][f"/api/v1/{resource}/{{id}}/activation/"]
        assert set(activation) == {"patch"}
        assert "400" in activation["patch"]["responses"]
    activation_fields = schema["components"]["schemas"]["PatchedActivation"]["properties"]
    assert activation_fields["est_actif"]["type"] == "boolean"


def test_schema_contains_project_crud_and_lot_workflow():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    paths = {path: value for path, value in schema["paths"].items() if "/projets/" in path}
    assert set(paths) == {
        "/api/v1/projets/",
        "/api/v1/projets/{id}/",
        "/api/v1/projets/{id}/lots/",
        "/api/v1/projets/{id}/lots/import/",
        "/api/v1/projets/{id}/lots/modele/",
        "/api/v1/projets/{id}/statistiques/",
        "/api/v1/projets/{id}/equipes/",
        "/api/v1/projets/{id}/equipes/statistiques/",
        "/api/v1/projets/{id}/equipes/affectations/",
        "/api/v1/projets/{id}/equipes/affectations/{affectation_id}/",
        "/api/v1/projets/{id}/equipes/{equipe_id}/",
    }
    assert set(paths["/api/v1/projets/"]) == {"get", "post"}
    assert set(paths["/api/v1/projets/{id}/"]) == {"get", "put", "patch", "delete"}


def test_hidden_business_routes_remain_available():
    for path in (
        "/api/v1/projets/meteo/",
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
    assert any(
        set(item.get("enum", [])) == set(StatutProjet.values) for item in components.values()
    )
    for name in ("ProjetPost", "ProjetPatch", "ProjetCreationResponse"):
        assert "statut" in components[name]["properties"]
    operation = schema["paths"]["/api/v1/projets/{id}/"]["patch"]
    examples = operation["requestBody"]["content"]["application/json"]["examples"]
    assert {item["value"]["statut"] for item in examples.values()} == {
        "EN_ATTENTE",
        "SUSPENDU",
        "BLOQUE",
        "DESACTIVE",
        "RESILIE",
        "EN_COURS",
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


def test_activity_form_and_statistics_documented():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    operation = schema["paths"]["/api/v1/lots/{lot_id}/activites/"]["post"]
    body = operation["requestBody"]["content"]["application/json"]
    component = body["schema"]["$ref"].rsplit("/", 1)[-1]
    definition = schema["components"]["schemas"][component]
    assert definition["required"] == ["libelle"]
    for field in ("date_debut_prevue", "date_fin_prevue", "dependance"):
        assert definition["properties"][field]["nullable"] is True
    assert "equipe_ids" in definition["properties"]
    assert len(body["examples"]) == 2
    assert set(operation["responses"]) == {"201", "400", "401", "403", "404"}
    stats = schema["paths"]["/api/v1/projets/{id}/statistiques/"]["get"]
    assert set(stats["responses"]) == {"200", "401", "403", "404"}


def test_team_errors_and_assignment_dates_documented():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    paths = schema["paths"]
    for path, methods in paths.items():
        if "/equipes/" in path:
            for operation in methods.values():
                assert {"401", "403", "404"} <= set(operation["responses"])
    teams = paths["/api/v1/projets/{id}/equipes/"]["post"]
    assert "400" in teams["responses"]
    assignments = paths["/api/v1/projets/{id}/equipes/affectations/"]
    assert "400" in assignments["get"]["responses"]
    assert "400" in assignments["post"]["responses"]
    fields = schema["components"]["schemas"]["AffectationEquipeResponse"]["properties"]
    for name in ("date_debut", "date_fin"):
        assert fields[name]["nullable"] is True
        assert fields[name]["readOnly"] is True


def test_lot_real_dates_and_project_id_documented():
    schema = SchemaGenerator(urlconf="config.urls_tenant").get_schema(public=True)
    components = schema["components"]["schemas"]
    response = components["LotResponse"]["properties"]
    assert "projet" not in response
    assert response["projet_id"]["format"] == "uuid"
    assert response["projet_id"]["readOnly"] is True
    creation = components["LotCreation"]
    for champ in ("date_debut_reelle", "date_fin_reelle"):
        assert creation["properties"][champ]["nullable"] is True
        assert champ not in creation.get("required", [])
        assert response[champ]["nullable"] is True
