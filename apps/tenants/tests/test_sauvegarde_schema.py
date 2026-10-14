"""Tests unitaires pour la sauvegarde des schémas avant suppression définitive et la purge."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.tenants.services.sauvegarde_schema import (
    SauvegardeImpossible,
    sauvegarder_schema,
)


class FauxAbonnements:
    def values(self):
        return [{"plan_code": "BATISSEUR", "statut": "ACTIF"}]


class FausseEntreprise:
    def __init__(self, schema_name="tenant_test"):
        self.id = "11111111-1111-1111-1111-111111111111"
        self.schema_name = schema_name
        self.nom = "Entreprise Test"
        self.raison_sociale = "Entreprise Test SARL"
        self.slug = schema_name
        self.statut = "SUSPENDU"
        self.cree_le = "2026-01-01T00:00:00Z"
        self.abonnements = FauxAbonnements()


def test_nom_de_schema_dangereux_refuse(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: pytest.fail("subprocess.run ne doit pas être appelé"),
    )
    dangereux = FausseEntreprise(schema_name="a; DROP SCHEMA public")
    with pytest.raises(SauvegardeImpossible):
        sauvegarder_schema(dangereux, complement={"test": True})


def test_pg_dump_introuvable(settings, tmp_path):
    settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)
    settings.PG_DUMP_CHEMIN = "pg_dump_inexistant_xyz"
    ent = FausseEntreprise(schema_name="tenant_b")

    with pytest.raises(SauvegardeImpossible):
        sauvegarder_schema(ent, complement={"test": True})

    assert list(tmp_path.glob("*")) == []


def test_fichier_vide_refuse(settings, tmp_path, monkeypatch):
    settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)
    settings.PG_DUMP_CHEMIN = "pg_dump"
    ent = FausseEntreprise(schema_name="tenant_b")

    def faux_run(cmd, **kw):
        for arg in cmd:
            if str(arg).startswith("--file="):
                chemin = Path(str(arg).split("=", 1)[1])
                chemin.touch()  # taille 0

    monkeypatch.setattr(subprocess, "run", faux_run)

    with pytest.raises(SauvegardeImpossible):
        sauvegarder_schema(ent, complement={"test": True})

    assert list(tmp_path.glob("*")) == []


def test_commande_sans_shell_et_sans_mot_de_passe_en_argument(settings, tmp_path, monkeypatch):
    settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)
    settings.PG_DUMP_CHEMIN = "pg_dump"
    ent = FausseEntreprise(schema_name="tenant_b")

    appels = []

    def faux_run(cmd, env=None, **kw):
        appels.append({"cmd": cmd, "env": env, "kw": kw})
        for arg in cmd:
            if str(arg).startswith("--file="):
                chemin = Path(str(arg).split("=", 1)[1])
                chemin.write_text("dump content")

    monkeypatch.setattr(subprocess, "run", faux_run)

    res = sauvegarder_schema(ent, complement={"test": True})
    assert res.exists()

    assert len(appels) == 1
    appel = appels[0]
    # Pas de shell=True
    assert not appel["kw"].get("shell")
    # Mot de passe jamais en argument de ligne de commande
    password = settings.DATABASES["default"].get("PASSWORD")
    if password:
        assert all(password not in str(arg) for arg in appel["cmd"])
        assert appel["env"]["PGPASSWORD"] == password


def test_json_compagnon_ecrit(settings, tmp_path, monkeypatch):
    settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)
    settings.PG_DUMP_CHEMIN = "pg_dump"
    ent = FausseEntreprise(schema_name="tenant_b")

    def faux_run(cmd, **kw):
        for arg in cmd:
            if str(arg).startswith("--file="):
                chemin = Path(str(arg).split("=", 1)[1])
                chemin.write_text("dump content")

    monkeypatch.setattr(subprocess, "run", faux_run)

    res = sauvegarder_schema(ent, complement={"apercu_nb": 42})
    assert res.exists()

    json_compagnon = res.with_suffix(".json")
    assert json_compagnon.exists()

    donnees = json.loads(json_compagnon.read_text(encoding="utf-8"))
    assert donnees["entreprise"]["schema_name"] == "tenant_b"
    assert donnees["complement"]["apercu_nb"] == 42
    assert "sauvegarde_le" in donnees


def test_purge_decrit_sans_appliquer(settings, tmp_path):
    settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)

    vieux_dump = tmp_path / "vieux_schema_20260101_000000.dump"
    vieux_json = tmp_path / "vieux_schema_20260101_000000.json"
    recent_dump = tmp_path / "recent_schema_20261014_000000.dump"

    vieux_dump.write_text("vieux dump")
    vieux_json.write_text("vieux json")
    recent_dump.write_text("recent dump")

    temps_vieux = time.time() - (35 * 86400)
    os.utime(vieux_dump, (temps_vieux, temps_vieux))
    os.utime(vieux_json, (temps_vieux, temps_vieux))

    temps_recent = time.time() - (2 * 86400)
    os.utime(recent_dump, (temps_recent, temps_recent))

    # 1. Simulation sans --appliquer
    call_command("purger_sauvegardes_suppression", "--jours=30")
    assert vieux_dump.exists()
    assert vieux_json.exists()
    assert recent_dump.exists()

    # 2. Avec --appliquer
    call_command("purger_sauvegardes_suppression", "--jours=30", "--appliquer")
    assert not vieux_dump.exists()
    assert not vieux_json.exists()
    assert recent_dump.exists()
