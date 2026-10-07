"""Tests des modèles de rôles du catalogue (Règle A-12 : plus de plafond)."""

import pytest
from apps.catalogue.models import ModeleRole


@pytest.mark.django_db
def test_10_modeles_roles_presents():
    codes_attendus = {"DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"}
    codes_reels = set(ModeleRole.objects.values_list("code", flat=True))
    assert codes_attendus.issubset(codes_reels)


@pytest.mark.django_db
def test_modules_dg_et_ad():
    """[A-12] Vérifie les modules associés aux modèles de rôles DG et AD."""
    dg = ModeleRole.objects.get(code="DG")
    modules_dg = {mrm.module_code for mrm in dg.modules_plafonds.all()}
    assert "projets" in modules_dg
    assert "chantier" in modules_dg
    assert "administration" in modules_dg

    ad = ModeleRole.objects.get(code="AD")
    modules_ad = {mrm.module_code for mrm in ad.modules_plafonds.all()}
    assert "projets" in modules_ad
    assert "chantier" in modules_ad
    assert "tiers" in modules_ad
    assert "pilotage" in modules_ad
    assert "administration" in modules_ad


@pytest.mark.django_db
def test_modules_ct_et_magasinier():
    """[A-12] Vérifie les modules associés aux modèles de rôles CT et MAG."""
    ct = ModeleRole.objects.get(code="CT")
    modules_ct = {mrm.module_code for mrm in ct.modules_plafonds.all()}
    assert "projets" in modules_ct
    assert "chantier" in modules_ct

    mag = ModeleRole.objects.get(code="MAG")
    modules_mag = {mrm.module_code for mrm in mag.modules_plafonds.all()}
    assert "chantier" in modules_mag
    assert "tiers" in modules_mag


@pytest.mark.django_db
def test_str_modeles():
    ct = ModeleRole.objects.get(code="CT")
    assert "CT" in str(ct)
    mrm = ct.modules_plafonds.first()
    assert "CT" in str(mrm)
