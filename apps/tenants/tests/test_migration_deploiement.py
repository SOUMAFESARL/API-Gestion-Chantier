"""Les migrations passent au déploiement, jamais au démarrage d'un processus Passenger."""

import hashlib
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client, override_settings

JETON_TEST = "jeton-de-test-uniquement-pour-pytest"
EMPREINTE_TEST = hashlib.sha256(JETON_TEST.encode("utf-8")).hexdigest()


def test_passenger_ne_migre_pas_au_demarrage():
    """Chaque démarrage de processus payait migrate_schemas sur tous les tenants (7 à 10 s)."""
    source = (Path(settings.BASE_DIR) / "passenger_wsgi.py").read_text(encoding="utf-8")
    assert "call_command" not in source
    assert "migrate_schemas" not in source
    assert "application = get_wsgi_application()" in source


@pytest.mark.django_db
@override_settings(MAINTENANCE_TOKEN_SHA256=EMPREINTE_TEST)
def test_migrer_bd_reprend_tout_ce_que_faisait_le_demarrage(monkeypatch):
    """L'endpoint du déploiement doit enchaîner les cinq commandes, provisionnement compris."""
    appels = []
    monkeypatch.setattr(
        "config.urls_public.call_command",
        lambda nom, *args, **kwargs: appels.append(nom),
    )

    resp = Client().post(
        "/api/v1/maintenance/migrer-bd/",
        content_type="application/json",
        HTTP_X_MAINTENANCE_TOKEN=JETON_TEST,
    )

    assert resp.status_code == 200
    assert resp.json()["statut"] == "succes"
    assert appels == [
        "migrate_schemas",
        "provisionner_inscriptions",
        "remplir_registre_global",
        "synchroniser_catalogue_permissions",
        "propager_roles_systeme",
    ]


@pytest.mark.django_db
@override_settings(MAINTENANCE_TOKEN_SHA256=EMPREINTE_TEST)
def test_echec_du_provisionnement_ne_masque_pas_les_migrations(monkeypatch):
    """Une inscription en échec ne doit pas faire croire que la base n'a pas migré."""

    def faux_call_command(nom, *args, **kwargs):
        if nom == "provisionner_inscriptions":
            raise RuntimeError("schéma déjà existant")

    monkeypatch.setattr("config.urls_public.call_command", faux_call_command)

    resp = Client().post(
        "/api/v1/maintenance/migrer-bd/",
        content_type="application/json",
        HTTP_X_MAINTENANCE_TOKEN=JETON_TEST,
    )

    assert resp.status_code == 200
    assert "Échec du provisionnement des inscriptions" in resp.json()["output"]
