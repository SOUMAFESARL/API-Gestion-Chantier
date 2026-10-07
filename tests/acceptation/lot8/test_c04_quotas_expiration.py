"""Tests d'acceptation : Règle C-04 (Limites du plan et expiration d'abonnement).

Matrice issue du cadrage Lot 8 :
- Quota de collaborateurs (inchangé, enveloppe Q relevée à l'exécution)
- Quota de projets à la création (POST /projets/) : même statut et code d'erreur que Q, details.ressource="projets"
- Projets en fin de vie (RESILIE, ARCHIVE, DESACTIVE) ignorés du quota
- Contrôle de permission prioritaire sur le contrôle de quota
- Abonnement expiré : toutes les écritures bloquées en 403 abonnement_suspendu
- Lectures et authentification conservées
- Exceptions ouvertes : /cinetpay/, /billing/, /auth/
- Les routes ouvertes de facturation restent protégées par administration.abonnement_gerer (DG seul)
"""

import pytest
from rest_framework import status
from apps.core.enums import StatutProjet
from apps.projets.models import Projet

pytestmark = pytest.mark.django_db


# ==============================================================================
# Quotas (Collaborateurs et Projets)
# ==============================================================================

@pytest.mark.carac
def test_c04_quota_collaborateurs_atteint_refus(fabrique):
    """[C-04] Quota collaborateurs atteint : invitation par le DG refusée en 403 avec enveloppe Q."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    fabrique.fixer_limites_plan(utilisateurs=1)

    try:
        # 1er compte existant
        fabrique.utilisateur("VI")
        res = fabrique.inviter(client_dg, "depassement_collab@test.ci", "VI")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        code_err = res.data.get("erreur", {}).get("code") or res.data.get("code")
        assert code_err in ("quota_plan_atteint", "QUOTA_PLAN_ATTEINT", "quota_atteint")
    finally:
        fabrique.fixer_limites_plan(utilisateurs=None)


@pytest.mark.regle
def test_c04_quota_projets_atteint_refus(fabrique):
    """[C-04] Quota projets atteint (limite 2, deux projets vivants) : POST /projets/ renvoie même statut et code que Q, ressource='projets'."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    # Relever l'enveloppe Q
    q_env = fabrique.enveloppe_quota_utilisateurs()

    fabrique.fixer_limites_plan(projets=2)
    try:
        # Créer 2 projets vivants
        p1 = fabrique.projet(statut="EN_COURS")
        p2 = fabrique.projet(statut="EN_ATTENTE")

        # Tenter la création d'un 3e projet
        res = client_dg.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
        assert res.status_code == q_env["status_code"]

        data = res.data
        code_err = data.get("erreur", {}).get("code") or data.get("code")
        assert code_err == q_env["code"]

        details = data.get("erreur", {}).get("details") or data.get("details", {})
        assert details.get("ressource") == "projets"
    finally:
        fabrique.fixer_limites_plan(projets=None)


@pytest.mark.regle
def test_c04_limite_2_un_projet_vivant_et_un_archive(fabrique):
    """[C-04] Limite 2 projets, un projet vivant et un ARCHIVE : création acceptée (201)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    fabrique.fixer_limites_plan(projets=2)
    try:
        p_vivant = fabrique.projet(statut="EN_COURS")
        p_archive = fabrique.projet(statut=StatutProjet.ARCHIVE)

        res = client_dg.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
        assert res.status_code == status.HTTP_201_CREATED
    finally:
        fabrique.fixer_limites_plan(projets=None)


@pytest.mark.regle
def test_c04_limite_projets_nulle_creation_acceptee(fabrique):
    """[C-04] limite_projets nulle (illimitée) : création acceptée sans blocage de quota."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    fabrique.fixer_limites_plan(projets=None)
    for _ in range(3):
        fabrique.projet()

    res = client_dg.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
    assert res.status_code == status.HTTP_201_CREATED


@pytest.mark.regle
def test_c04_ordre_permission_avant_quota_projet(fabrique):
    """[C-04] CP sans projets.creer tente de créer un projet alors que le quota est atteint : 403 permission, pas de quota."""
    cp = fabrique.utilisateur("CP")
    client_cp = fabrique.client(cp)

    fabrique.fixer_limites_plan(projets=1)
    try:
        fabrique.projet()
        res = client_cp.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        code_err = res.data.get("erreur", {}).get("code") or res.data.get("code")
        assert code_err != "quota_plan_atteint"
    finally:
        fabrique.fixer_limites_plan(projets=None)


# ==============================================================================
# Expiration d'Abonnement
# ==============================================================================

@pytest.mark.carac
def test_c04_abonnement_expire_bloque_ecritures_dg_et_cp(fabrique):
    """[C-04] Abonnement expiré : toute écriture métier (lot, projet, collaborateur) reçoit 403 abonnement_suspendu."""
    dg = fabrique.utilisateur("DG")
    cp = fabrique.utilisateur("CP")
    p = fabrique.projet()
    fabrique.affecter(p, cp, role_projet="CP")

    client_dg = fabrique.client(dg)
    client_cp = fabrique.client(cp)

    fabrique.expirer_abonnement()
    try:
        # Écriture par DG
        res_dg = client_dg.post(fabrique.url_projets(), fabrique.payload_projet(), format="json")
        assert res_dg.status_code == status.HTTP_403_FORBIDDEN
        assert res_dg.data.get("erreur", {}).get("code") == "abonnement_suspendu"

        # Écriture par CP (lot)
        res_cp = client_cp.post(fabrique.url_lots(p), fabrique.payload_lot(), format="json")
        assert res_cp.status_code == status.HTTP_403_FORBIDDEN
        assert res_cp.data.get("erreur", {}).get("code") == "abonnement_suspendu"
    finally:
        fabrique.restaurer_abonnement()


@pytest.mark.carac
def test_c04_abonnement_expire_lectures_autorisees(fabrique):
    """[C-04] Abonnement expiré : les requêtes GET (projets, tableau de bord) restent permises (200)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    fabrique.expirer_abonnement()
    try:
        res = client_dg.get(fabrique.url_projets())
        assert res.status_code == status.HTTP_200_OK
    finally:
        fabrique.restaurer_abonnement()


@pytest.mark.carac
def test_c04_abonnement_expire_connexion_et_refresh_autorises(fabrique):
    """[C-04] Abonnement expiré : l'authentification et le renouvellement de jeton ne sont pas bloqués."""
    user = fabrique.utilisateur("VI")
    user.set_password("MotDePasse123!")
    user.save()

    fabrique.expirer_abonnement()
    try:
        res_auth = fabrique.se_connecter(user.email, "MotDePasse123!")
        assert res_auth.status_code == status.HTTP_200_OK
        refresh_token = res_auth.data.get("refresh")

        client = fabrique.client()
        res_refresh = client.post("/api/v1/auth/token/refresh/", {"refresh": refresh_token}, format="json")
        assert res_refresh.status_code == status.HTTP_200_OK
    finally:
        fabrique.restaurer_abonnement()


@pytest.mark.regle
def test_c04_abonnement_expire_dg_peut_initier_cinetpay(fabrique):
    """[C-04] Abonnement expiré : DG appelle cinetpay/initier avec un corps vide -> 400 (garde et middleware passés)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    fabrique.expirer_abonnement()
    try:
        res = client_dg.post(fabrique.url_cinetpay_initier(), {}, format="json")
        # 400 validation prouve que le middleware abonnement et la garde de permission l'ont laissé passer
        assert res.status_code == status.HTTP_400_BAD_REQUEST
    finally:
        fabrique.restaurer_abonnement()


@pytest.mark.regle
@pytest.mark.parametrize("role_code", ["AD", "CP", "DO"])
def test_c04_abonnement_expire_non_dg_cinetpay_refuse_permission(fabrique, role_code):
    """[C-04] Abonnement expiré : AD, CP, DO appellent cinetpay/initier -> 403 avec erreur.code != abonnement_suspendu."""
    user = fabrique.utilisateur(role_code)
    client = fabrique.client(user)

    fabrique.expirer_abonnement()
    try:
        res = client.post(fabrique.url_cinetpay_initier(), {}, format="json")
        assert res.status_code == status.HTTP_403_FORBIDDEN
        code_err = res.data.get("erreur", {}).get("code") or res.data.get("code")
        assert code_err != "abonnement_suspendu"
    finally:
        fabrique.restaurer_abonnement()


@pytest.mark.regle
def test_c04_routes_ouvertes_billing_exigent_dg(fabrique):
    """[C-04] Les routes d'écriture sous /billing/ et /cinetpay/ exigent le DG seul même en abonnement expiré."""
    ad = fabrique.utilisateur("AD")
    client_ad = fabrique.client(ad)

    fabrique.expirer_abonnement()
    try:
        assert client_ad.post(fabrique.url_cinetpay_initier(), {}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert client_ad.post("/api/v1/cinetpay/annuler/", {}, format="json").status_code == status.HTTP_403_FORBIDDEN
    finally:
        fabrique.restaurer_abonnement()
