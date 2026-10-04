import pytest
from apps.core.registre_permissions import REGISTRE, DefPermission, permissions_du_module


def test_registre_unicite_codes():
    assert len(REGISTRE) > 0
    # Every code matches its key
    for code, definition in REGISTRE.items():
        assert code == definition.code
        assert isinstance(definition, DefPermission)
        assert definition.rang in (1, 2, 3)
        assert bool(definition.module)
        assert bool(definition.libelle)


def test_permissions_du_module_niveaux():
    # Niveau 0 : aucune permission
    assert permissions_du_module("projets", 0) == set()

    # Niveau 1 : lecture seule (rang 1)
    p1 = permissions_du_module("projets", 1)
    assert p1 == {"projets.lire"}

    # Niveau 2 : lecture + ecriture (rang <= 2)
    p2 = permissions_du_module("projets", 2)
    assert "projets.lire" in p2
    assert "projets.creer" in p2
    assert "projets.ecrire" in p2
    assert "projets.changer_statut" not in p2

    # Niveau 3 : complet (rang <= 3)
    p3 = permissions_du_module("projets", 3)
    assert "projets.changer_statut" in p3
    assert "projets.voir_tous" in p3
    assert p2.issubset(p3)


def test_permissions_du_module_inconnu():
    assert permissions_du_module("inconnu_xyz", 3) == set()
