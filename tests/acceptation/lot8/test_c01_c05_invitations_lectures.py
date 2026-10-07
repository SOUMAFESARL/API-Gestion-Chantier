"""Tests d'acceptation : Règles C-01 (Ajout en deux temps) et C-05 puce 1 (Lectures réservées).

Matrice issue du cadrage Lot 8.
"""

import pytest
from rest_framework import status
from apps.projets.models import AffectationProjet
from apps.accounts.models import Utilisateur

pytestmark = pytest.mark.django_db


# ==============================================================================
# C-01 : Ajout en deux temps
# ==============================================================================

@pytest.mark.carac
def test_c01_dg_invite_par_invitations_et_collaborateurs_sans_affectation(fabrique):
    """[C-01] DG invite par /invitations/ puis par /parametres/collaborateurs/ : 2xx, aucune AffectationProjet."""
    dg = fabrique.utilisateur("DG")
    client = fabrique.client(dg)

    # 1. Route /invitations/
    res1 = fabrique.inviter(client, "invite1_c01@test.ci", "VI", route=fabrique.url_invitations())
    assert res1.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    u1 = Utilisateur.objects.filter(email__iexact="invite1_c01@test.ci").first()
    assert u1 is not None
    assert AffectationProjet.objects.filter(utilisateur=u1).count() == 0

    # 2. Route /parametres/collaborateurs/
    res2 = fabrique.inviter(client, "invite2_c01@test.ci", "VI", route=fabrique.url_collaborateurs())
    assert res2.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    u2 = Utilisateur.objects.filter(email__iexact="invite2_c01@test.ci").first()
    assert u2 is not None
    assert AffectationProjet.objects.filter(utilisateur=u2).count() == 0


@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DO", "CP", "DF", "CT", "VI", "perso_entreprise"])
def test_c01_roles_non_autorises_inviter_refuses(fabrique, role_code):
    """[C-01] DO, CP, DF, CT, VI, perso_entreprise invitent : refus 403 sur les deux routes."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    for route in (fabrique.url_invitations(), fabrique.url_collaborateurs()):
        res = fabrique.inviter(client, f"test_non_auth_{role_code}@test.ci", "VI", route=route)
        assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.regle
@pytest.mark.parametrize("role_attribue", ["VI", "BAI"])
def test_c01_ad_invite_avec_role_autorise(fabrique, role_attribue):
    """[C-01] AD invite avec rôle VI et avec rôle BAI : 2xx sur les deux routes."""
    ad = fabrique.utilisateur("AD")
    client = fabrique.client(ad)

    for i, route in enumerate((fabrique.url_invitations(), fabrique.url_collaborateurs())):
        email = f"ad_invite_{role_attribue}_{i}@test.ci"
        res = fabrique.inviter(client, email, role_attribue, route=route)
        assert res.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
        assert Utilisateur.objects.filter(email__iexact=email).exists()


@pytest.mark.regle
@pytest.mark.parametrize("role_interdit", ["DF", "DO", "CP", "AD", "DG"])
def test_c01_ad_invite_avec_role_non_autorise_refuse(fabrique, role_interdit):
    """[C-01] AD invite avec DF, DO, CP, AD, DG (sous-ensemble non respecté) : 403, aucun compte créé."""
    ad = fabrique.utilisateur("AD")
    client = fabrique.client(ad)

    for route in (fabrique.url_invitations(), fabrique.url_collaborateurs()):
        email = f"ad_refus_{role_interdit}@test.ci"
        res = fabrique.inviter(client, email, role_interdit, route=route)
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert not Utilisateur.objects.filter(email__iexact=email).exists()


@pytest.mark.regle
def test_c01_dg_invite_avec_role_dg_refuse(fabrique):
    """[C-01] DG invite avec le rôle DG : 403 (B-03 : Directeur Général unique et immuable)."""
    dg = fabrique.utilisateur("DG")
    client = fabrique.client(dg)

    for route in (fabrique.url_invitations(), fabrique.url_collaborateurs()):
        email = f"dg_clone_{route.replace('/', '_')}@test.ci"
        res = fabrique.inviter(client, email, "DG", route=route)
        assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["DG", "AD", "CP", "VI"])
def test_c01_egalite_statuts_deux_routes_invitations(fabrique, role_code):
    """[C-01] Les deux routes d'invitation donnent exactement les mêmes statuts pour chaque acteur."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    res_inv = fabrique.inviter(client, f"egalite_inv_{role_code}@test.ci", "VI", route=fabrique.url_invitations())
    res_collab = fabrique.inviter(client, f"egalite_collab_{role_code}@test.ci", "VI", route=fabrique.url_collaborateurs())

    assert res_inv.status_code == res_collab.status_code


# ==============================================================================
# C-05 puce 1 : Lectures réservées
# ==============================================================================

@pytest.mark.carac
def test_c05_dg_liste_collaborateurs_et_invitations(fabrique):
    """[C-05 puce 1] DG liste collaborateurs et invitations : 200."""
    dg = fabrique.utilisateur("DG")
    client = fabrique.client(dg)

    assert client.get(fabrique.url_collaborateurs()).status_code == status.HTTP_200_OK
    assert client.get(fabrique.url_invitations()).status_code == status.HTTP_200_OK


@pytest.mark.regle
def test_c05_ad_liste_collaborateurs_et_invitations(fabrique):
    """[C-05 puce 1] AD liste collaborateurs et invitations : 200."""
    ad = fabrique.utilisateur("AD")
    client = fabrique.client(ad)

    assert client.get(fabrique.url_collaborateurs()).status_code == status.HTTP_200_OK
    assert client.get(fabrique.url_invitations()).status_code == status.HTTP_200_OK


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["DO", "CP", "DF", "CT", "VI", "perso_entreprise"])
def test_c05_autres_roles_liste_collaborateurs_refusee(fabrique, role_code):
    """[C-05 puce 1] DO, CP, DF, CT, VI, perso_entreprise lisent collaborateurs ou invitations : 403 sur les deux."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    assert client.get(fabrique.url_collaborateurs()).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(fabrique.url_invitations()).status_code == status.HTTP_403_FORBIDDEN
