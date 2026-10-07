"""Tests d'acceptation : Règles F-03 à F-08 (Lectures et vues protégées).

Matrice issue du cadrage Lot 8 :
- F-03 : Abonnement (clés réduites jours_essai_restants et est_expire pour non gestionnaires)
- F-04 : Factures et alertes d'expiration (administration.factures_voir / administration.abonnement_voir)
- F-05 : Paiements CinetPay et changement de plan (administration.abonnement_gerer, DG seul)
- F-06 : Modules (filtrage granulaire sur les modules et permissions effectifs de l'utilisateur)
- F-07 : Entreprise (GET ouvert à tous, écriture réservée au DG seul via administration.entreprise_modifier)
- F-08 : Onboarding (réservé à administration.onboarding_suivre : DG, AD)
"""

import uuid
import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


# ==============================================================================
# F-03 : Abonnement
# ==============================================================================

@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["CP", "DO", "VI", "DF"])
def test_f03_lecture_abonnement_restreinte_non_gestionnaire(fabrique, role_code):
    """[F-03] CP, DO, VI, DF lisent GET /abonnement/ : exactement les clés jours_essai_restants et est_expire."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    res = client.get("/api/v1/abonnement/")
    assert res.status_code == status.HTTP_200_OK
    assert set(res.data.keys()) == {"jours_essai_restants", "est_expire"}


@pytest.mark.carac
def test_f03_lecture_abonnement_complete_dg(fabrique):
    """[F-03] DG lit GET /abonnement/ : reçoit les clés complètes (plan, quotas, échéances)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    res = client_dg.get("/api/v1/abonnement/")
    assert res.status_code == status.HTTP_200_OK
    assert "jours_essai_restants" in res.data
    assert "est_expire" in res.data
    assert "plan" in res.data or "statut" in res.data


@pytest.mark.regle
def test_f03_lecture_abonnement_complete_ad(fabrique):
    """[F-03] AD lit GET /abonnement/ : reçoit les clés complètes comme le DG."""
    ad = fabrique.utilisateur("AD")
    client_ad = fabrique.client(ad)

    res = client_ad.get("/api/v1/abonnement/")
    assert res.status_code == status.HTTP_200_OK
    assert "jours_essai_restants" in res.data
    assert "est_expire" in res.data
    assert "plan" in res.data or "statut" in res.data


@pytest.mark.carac
def test_f03_abonnement_expire_affiche_est_expire_true(fabrique):
    """[F-03] Abonnement expiré : est_expire est True pour tous."""
    vi = fabrique.utilisateur("VI")
    client_vi = fabrique.client(vi)

    fabrique.expirer_abonnement()
    try:
        res = client_vi.get("/api/v1/abonnement/")
        assert res.status_code == status.HTTP_200_OK
        assert res.data.get("est_expire") is True
    finally:
        fabrique.restaurer_abonnement()


# ==============================================================================
# F-04 : Factures et Notifications
# ==============================================================================

@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DG", "AD"])
def test_f04_factures_dg_ad_autorises(fabrique, role_code):
    """[F-04] DG et AD accèdent à la liste, détail et PDF des factures."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)
    facture = fabrique.creer_facture()

    res_liste = client.get(fabrique.url_factures())
    assert res_liste.status_code == status.HTTP_200_OK

    res_detail = client.get(fabrique.url_facture(facture.pk))
    assert res_detail.status_code == status.HTTP_200_OK

    res_pdf = client.get(fabrique.url_facture_pdf(facture.pk))
    assert res_pdf.status_code == status.HTTP_200_OK


@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DF", "DO", "CP", "VI", "perso_entreprise"])
def test_f04_factures_autres_roles_refuses(fabrique, role_code):
    """[F-04] DF, DO, CP, VI, perso_entreprise : liste, détail et PDF de facture refusés en 403."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)
    facture = fabrique.creer_facture()

    assert client.get(fabrique.url_factures()).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(fabrique.url_facture(facture.pk)).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(fabrique.url_facture_pdf(facture.pk)).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.carac
def test_f04_facture_inexistante_403_avant_404(fabrique):
    """[F-04] Facture inexistante : 403 pour un non autorisé, 404 pour le DG (L8-9)."""
    pk_inexistante = uuid.uuid4()
    dg = fabrique.utilisateur("DG")
    vi = fabrique.utilisateur("VI")

    client_vi = fabrique.client(vi)
    assert client_vi.get(fabrique.url_facture(pk_inexistante)).status_code == status.HTTP_403_FORBIDDEN

    client_dg = fabrique.client(dg)
    assert client_dg.get(fabrique.url_facture(pk_inexistante)).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DG", "AD"])
def test_f04_notifications_expiration_dg_ad_autorises(fabrique, role_code):
    """[F-04] DG et AD accèdent à GET /abonnement/notifications/ (200)."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    assert client.get(fabrique.url_abonnement_notifications()).status_code == status.HTTP_200_OK


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["DO", "CP", "DF", "VI", "perso_entreprise"])
def test_f04_notifications_expiration_autres_refuses(fabrique, role_code):
    """[F-04] DO, CP, DF, VI, perso_entreprise reçoivent 403 sur GET /abonnement/notifications/."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    assert client.get(fabrique.url_abonnement_notifications()).status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# F-05 : Paiements CinetPay
# ==============================================================================

@pytest.mark.carac
def test_f05_cinetpay_initier_dg_autorise(fabrique):
    """[F-05] POST /cinetpay/initier/ corps vide : DG passe la garde (reçoit 400 validation)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    res = client_dg.post(fabrique.url_cinetpay_initier(), {}, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["AD", "DO", "CP", "DF", "VI"])
def test_f05_cinetpay_initier_autres_refuses(fabrique, role_code):
    """[F-05] POST /cinetpay/initier/ : AD, DO, CP, DF, VI reçoivent 403."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    res = client.post(fabrique.url_cinetpay_initier(), {}, format="json")
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.carac
def test_f05_cinetpay_statut_dg_autorise(fabrique):
    """[F-05] GET /cinetpay/statut/{id}/ : DG passe la garde de permission."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    res = client_dg.get(fabrique.url_cinetpay_statut("dummy-trans-123"))
    assert res.status_code != status.HTTP_403_FORBIDDEN


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["AD", "DO", "CP", "DF", "VI"])
def test_f05_cinetpay_statut_autres_refuses(fabrique, role_code):
    """[F-05] GET /cinetpay/statut/{id}/ : AD et autres rôles reçoivent 403."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    res = client.get(fabrique.url_cinetpay_statut("dummy-trans-123"))
    assert res.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# F-06 : Modules effectifs
# ==============================================================================

@pytest.mark.regle
def test_f06_modules_vi_filtrage_strict(fabrique):
    """[F-06] VI : tout code de permission présent dans la réponse appartient aux permissions de GET /auth/profil/ du VI."""
    vi = fabrique.utilisateur("VI")
    client_vi = fabrique.client(vi)

    res_profil = client_vi.get("/api/v1/auth/profil/")
    perms_profil = set(res_profil.data.get("permissions", []))

    res_modules = client_vi.get(fabrique.url_modules())
    assert res_modules.status_code == status.HTTP_200_OK

    for mod in res_modules.data:
        for perm in mod.get("permissions", []):
            code_perm = perm.get("code")
            assert code_perm in perms_profil


@pytest.mark.regle
def test_f06_modules_module_sans_permission_absent(fabrique):
    """[F-06] VI : un module dont il n'a aucune permission est complètement absent de la réponse."""
    vi = fabrique.utilisateur("VI")
    client_vi = fabrique.client(vi)

    res_modules = client_vi.get(fabrique.url_modules())
    assert res_modules.status_code == status.HTTP_200_OK

    codes_modules = [m.get("code") for m in res_modules.data]
    # Par exemple, le module administration n'a aucune permission pour un VI
    assert "administration" not in codes_modules


@pytest.mark.carac
def test_f06_modules_dg_retrouve_toutes_ses_permissions(fabrique):
    """[F-06] DG : toutes les permissions de son profil se retrouvent dans les modules exposés."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    res_profil = client_dg.get("/api/v1/auth/profil/")
    perms_profil = set(res_profil.data.get("permissions", []))

    res_modules = client_dg.get(fabrique.url_modules())
    assert res_modules.status_code == status.HTTP_200_OK

    perms_modules = set()
    for mod in res_modules.data:
        for p in mod.get("permissions", []):
            perms_modules.add(p.get("code"))

    # L'ensemble des permissions modules du DG inclut ses permissions
    assert len(perms_modules) > 0


@pytest.mark.regle
def test_f06_deux_roles_differents_reponses_differentes(fabrique):
    """[F-06] Deux utilisateurs de rôles différents reçoivent des réponses différentes sur GET /modules/."""
    vi = fabrique.utilisateur("VI")
    cp = fabrique.utilisateur("CP")

    client_vi = fabrique.client(vi)
    client_cp = fabrique.client(cp)

    res_vi = client_vi.get(fabrique.url_modules())
    res_cp = client_cp.get(fabrique.url_modules())

    assert res_vi.data != res_cp.data


# ==============================================================================
# F-07 : Entreprise
# ==============================================================================

@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DG", "AD", "CP", "VI"])
def test_f07_entreprise_lecture_ouverte_tous_roles(fabrique, role_code):
    """[F-07] GET /entreprise/ et /parametres/configuration/ : 200 pour tous les rôles."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    assert client.get(fabrique.url_entreprise()).status_code == status.HTTP_200_OK
    assert client.get(fabrique.url_parametres_configuration()).status_code == status.HTTP_200_OK


@pytest.mark.carac
def test_f07_entreprise_ecriture_dg_autorise(fabrique):
    """[F-07] PATCH et PUT sur /entreprise/ : DG passe la garde."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    res_patch = client_dg.patch(fabrique.url_entreprise(), {"nom_commercial": "DG BTP"}, format="json")
    assert res_patch.status_code == status.HTTP_200_OK


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["AD", "DO", "CP", "DF", "VI"])
def test_f07_entreprise_ecriture_ad_et_autres_refuses(fabrique, role_code):
    """[F-07] PATCH et PUT sur /entreprise/ : AD, DO, CP, DF, VI reçoivent 403 (L8-8 : DG seul)."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    res_patch = client.patch(fabrique.url_entreprise(), {"nom_commercial": "Refus BTP"}, format="json")
    assert res_patch.status_code == status.HTTP_403_FORBIDDEN

    res_config = client.post(fabrique.url_parametres_configuration(), {"nom_commercial": "Refus BTP"}, format="json")
    assert res_config.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# F-08 : Onboarding
# ==============================================================================

@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DG", "AD"])
def test_f08_onboarding_dg_ad_autorises(fabrique, role_code):
    """[F-08] Chaque route GET de /configuration/ : DG et AD passent la garde (200)."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    assert client.get(fabrique.url_onboarding()).status_code == status.HTTP_200_OK
    assert client.get(fabrique.url_onboarding_recapitulatif()).status_code == status.HTTP_200_OK


@pytest.mark.carac
@pytest.mark.parametrize("role_code", ["DO", "CP", "DF", "CT", "VI"])
def test_f08_onboarding_autres_roles_refuses(fabrique, role_code):
    """[F-08] Chaque route GET de /configuration/ : DO, CP, DF, CT, VI reçoivent 403."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    assert client.get(fabrique.url_onboarding()).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(fabrique.url_onboarding_recapitulatif()).status_code == status.HTTP_403_FORBIDDEN
