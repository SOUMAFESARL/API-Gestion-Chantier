import pytest
from apps.catalogue.models import ModeleRole, ModeleRoleModule


@pytest.mark.django_db
def test_10_modeles_roles_presents():
    codes_attendus = {"DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI"}
    codes_reels = set(ModeleRole.objects.values_list("code", flat=True))
    assert codes_attendus.issubset(codes_reels)


@pytest.mark.django_db
def test_plafonds_dg_et_ad():
    dg = ModeleRole.objects.get(code="DG")
    plafonds_dg = {mrm.module_code: mrm.niveau_max for mrm in dg.modules_plafonds.all()}
    assert plafonds_dg.get("projets") == 3
    assert plafonds_dg.get("chantier") == 3
    assert plafonds_dg.get("administration") == 3

    ad = ModeleRole.objects.get(code="AD")
    plafonds_ad = {mrm.module_code: mrm.niveau_max for mrm in ad.modules_plafonds.all()}
    assert plafonds_ad.get("projets") == 3
    assert plafonds_ad.get("chantier") == 3
    assert plafonds_ad.get("tiers") == 2
    assert plafonds_ad.get("pilotage") == 2
    assert plafonds_ad.get("administration") == 2


@pytest.mark.django_db
def test_plafonds_ct_et_magasinier():
    ct = ModeleRole.objects.get(code="CT")
    plafonds_ct = {mrm.module_code: mrm.niveau_max for mrm in ct.modules_plafonds.all()}
    assert plafonds_ct.get("projets") == 2
    assert plafonds_ct.get("chantier") == 3
    assert plafonds_ct.get("administration") == 0

    mag = ModeleRole.objects.get(code="MAG")
    plafonds_mag = {mrm.module_code: mrm.niveau_max for mrm in mag.modules_plafonds.all()}
    assert plafonds_mag.get("projets") == 0
    assert plafonds_mag.get("chantier") == 1
    assert plafonds_mag.get("tiers") == 2
    assert plafonds_mag.get("administration") == 0


@pytest.mark.django_db
def test_str_modeles():
    ct = ModeleRole.objects.get(code="CT")
    assert "CT" in str(ct)
    mrm = ct.modules_plafonds.first()
    assert "CT" in str(mrm)
