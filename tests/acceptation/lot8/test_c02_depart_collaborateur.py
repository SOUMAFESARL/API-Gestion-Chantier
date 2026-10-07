"""Tests d'acceptation : Règle C-02 (Départ d'un collaborateur).

Matrice issue du cadrage Lot 8 :
- Désactivation, historisation, conservation des lignes
- Désactivation des affectations
- Blocage de connexion
- Libération de l'e-mail d'origine (renommage + conservation dans email_origine)
- Indicateur sans_chef_projet (stocké, mis à True, remis à False, exposé dans l'API)
- Alerte par e-mail unique au DG sur transaction.on_commit
- Libération de place dans le quota
"""

import pytest
from rest_framework import status
from django.db import transaction

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet

pytestmark = pytest.mark.django_db


# ==============================================================================
# Désactivation, affectations et connexion
# ==============================================================================

@pytest.mark.carac
def test_c02_dg_supprime_collaborateur_soft_delete(fabrique):
    """[C-02] DG supprime un collaborateur : compte DESACTIVE, is_active=False, supprime_le renseigné, toujours en base."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cc = fabrique.utilisateur("CC")

    res = client_dg.delete(fabrique.url_collaborateur(cc))
    assert res.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    cc_actualise = Utilisateur.tous_objets.filter(id=cc.id).first()
    assert cc_actualise is not None
    assert cc_actualise.statut == StatutUtilisateur.DESACTIVE
    assert cc_actualise.is_active is False
    assert cc_actualise.supprime_le is not None


@pytest.mark.carac
def test_c02_depart_desactive_affectations(fabrique):
    """[C-02] Lors du départ, toutes les affectations actives passent à est_actif=False."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    collab = fabrique.utilisateur("CT")
    p = fabrique.projet()
    fabrique.affecter(p, collab, role_projet="CT")

    assert AffectationProjet.objects.filter(utilisateur=collab, est_actif=True).exists()

    res = client_dg.delete(fabrique.url_collaborateur(collab))
    assert res.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    assert not AffectationProjet.objects.filter(utilisateur=collab, est_actif=True).exists()


@pytest.mark.carac
def test_c02_collaborateur_parti_ne_peut_plus_se_connecter(fabrique):
    """[C-02] Un collaborateur désactivé ne peut plus se connecter (401)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    collab = fabrique.utilisateur("VI")
    collab.set_password("MotDePasse123!")
    collab.save()

    res_depart = client_dg.delete(fabrique.url_collaborateur(collab))
    assert res_depart.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    res_auth = fabrique.se_connecter(collab.email, "MotDePasse123!")
    assert res_auth.status_code == status.HTTP_401_UNAUTHORIZED


# ==============================================================================
# Indicateur sans_chef_projet
# ==============================================================================

@pytest.mark.regle
def test_c02_depart_cp_et_conducteur_met_indicateur_sans_chef_projet(fabrique):
    """[C-02] CP chef de p1 et conducteur de p2 part : chef_projet et conducteur à None, sans_chef_projet=True sur p1 et p2."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cp = fabrique.utilisateur("CP")

    p1 = fabrique.projet_avec_chef(cp)
    p2 = fabrique.projet_avec_conducteur(cp)

    res = client_dg.delete(fabrique.url_collaborateur(cp))
    assert res.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    p1.refresh_from_db()
    p2.refresh_from_db()

    assert p1.chef_projet is None
    assert p2.conducteur_travaux is None
    assert getattr(p1, "sans_chef_projet", None) is True
    assert getattr(p2, "sans_chef_projet", None) is True


@pytest.mark.regle
def test_c02_autres_projets_sans_chef_projet_reste_false(fabrique):
    """[C-02] Les autres projets non touchés par le départ restent avec sans_chef_projet=False."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cp = fabrique.utilisateur("CP")
    autre_cp = fabrique.utilisateur("CP")

    p_autre = fabrique.projet_avec_chef(autre_cp)
    client_dg.delete(fabrique.url_collaborateur(cp))

    p_autre.refresh_from_db()
    assert getattr(p_autre, "sans_chef_projet", False) is False


@pytest.mark.regle
def test_c02_projet_neuf_sans_chef_projet_est_false(fabrique):
    """[C-02] Un projet nouvellement créé a sans_chef_projet=False."""
    p = fabrique.projet()
    assert getattr(p, "sans_chef_projet", False) is False


@pytest.mark.regle
def test_c02_affectation_nouveau_chef_reinitialise_sans_chef_projet(fabrique):
    """[C-02] Réaffecter un chef de projet sur un projet orphelin remet sans_chef_projet=False."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cp1 = fabrique.utilisateur("CP")
    cp2 = fabrique.utilisateur("CP")

    p = fabrique.projet_avec_chef(cp1)
    client_dg.delete(fabrique.url_collaborateur(cp1))
    p.refresh_from_db()
    assert getattr(p, "sans_chef_projet", None) is True

    # Réaffectation d'un chef de projet via PATCH ou affectation
    client_dg.patch(fabrique.url_projet(p), {"chef_projet": str(cp2.id)}, format="json")
    p.refresh_from_db()
    assert getattr(p, "sans_chef_projet", False) is False


@pytest.mark.regle
def test_c02_indicateur_sans_chef_projet_visible_dans_api(fabrique):
    """[C-02] L'indicateur sans_chef_projet est exposé en lecture dans /projets/ et /projets/{id}/ pour un VI affecté."""
    dg = fabrique.utilisateur("DG")
    cp = fabrique.utilisateur("CP")
    vi = fabrique.utilisateur("VI")

    p = fabrique.projet_avec_chef(cp)
    fabrique.affecter(p, vi, role_projet="VI")

    # Départ du CP
    client_dg = fabrique.client(dg)
    client_dg.delete(fabrique.url_collaborateur(cp))

    client_vi = fabrique.client(vi)
    res_detail = client_vi.get(fabrique.url_projet(p))
    assert res_detail.status_code == status.HTTP_200_OK
    assert "sans_chef_projet" in res_detail.data
    assert res_detail.data["sans_chef_projet"] is True

    res_liste = client_vi.get(fabrique.url_projets())
    assert res_liste.status_code == status.HTTP_200_OK
    resultats = res_liste.data.get("results") or res_liste.data
    projet_data = next((item for item in resultats if str(item["id"]) == str(p.id)), None)
    assert projet_data is not None
    assert "sans_chef_projet" in projet_data
    assert projet_data["sans_chef_projet"] is True


# ==============================================================================
# Libération de l'e-mail
# ==============================================================================

@pytest.mark.regle
def test_c02_liberation_email_et_email_origine(fabrique):
    """[C-02] Après départ : création d'un compte avec la même adresse acceptée ; ancien compte a email!=original et email_origine=original."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    email_test = "collab.reemploi@test.ci"

    # Création initiale
    res1 = fabrique.inviter(client_dg, email_test, "VI")
    assert res1.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    ancien_compte = Utilisateur.objects.filter(email__iexact=email_test).first()
    assert ancien_compte is not None

    # Départ
    res_del = client_dg.delete(fabrique.url_collaborateur(ancien_compte))
    assert res_del.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    ancien_compte.refresh_from_db()
    assert ancien_compte.email != email_test
    assert getattr(ancien_compte, "email_origine", None) == email_test

    # Réutilisation immédiate de la même adresse
    res2 = fabrique.inviter(client_dg, email_test, "VI")
    assert res2.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    nouveau_compte = Utilisateur.objects.filter(email__iexact=email_test, statut=StatutUtilisateur.INVITE).first()
    assert nouveau_compte is not None
    assert nouveau_compte.id != ancien_compte.id


@pytest.mark.regle
def test_c02_reutilisation_email_en_majuscules(fabrique):
    """[C-02] L'e-mail libéré peut être réutilisé avec une casse en majuscules."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    email_test = "casse.depart@test.ci"

    fabrique.inviter(client_dg, email_test, "VI")
    compte = Utilisateur.objects.filter(email__iexact=email_test).first()
    client_dg.delete(fabrique.url_collaborateur(compte))

    # Réutilisation avec majuscules
    res = fabrique.inviter(client_dg, email_test.upper(), "VI")
    assert res.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)


# ==============================================================================
# Alerte par e-mail au DG
# ==============================================================================

@pytest.mark.regle
def test_c02_email_alerte_dg_projets_orphelins(fabrique):
    """[C-02] Départ d'un CP/CT avec projets orphelins : un seul message au DG citant p1 et p2 après validation de transaction."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cp = fabrique.utilisateur("CP")

    p1 = fabrique.projet_avec_chef(cp)
    p2 = fabrique.projet_avec_conducteur(cp)

    with transaction.atomic():
        res = client_dg.delete(fabrique.url_collaborateur(cp))
        assert res.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)

    fabrique.valider_transaction()

    courriels = fabrique.courriels_envoyes()
    assert len(courriels) == 1
    msg = courriels[0]
    assert dg.email in msg.to
    assert p1.reference in msg.body or p1.nom in msg.body
    assert p2.reference in msg.body or p2.nom in msg.body


@pytest.mark.regle
def test_c02_depart_sans_projet_aucun_email(fabrique):
    """[C-02] Départ d'un collaborateur sans aucun projet associé : aucun e-mail envoyé."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cc = fabrique.utilisateur("CC")

    with transaction.atomic():
        client_dg.delete(fabrique.url_collaborateur(cc))

    fabrique.valider_transaction()
    assert len(fabrique.courriels_envoyes()) == 0


@pytest.mark.regle
def test_c02_depart_annule_aucun_email(fabrique):
    """[C-02] Si la transaction de départ est annulée (rollback), aucun e-mail n'est envoyé."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    cp = fabrique.utilisateur("CP")
    fabrique.projet_avec_chef(cp)

    try:
        with transaction.atomic():
            client_dg.delete(fabrique.url_collaborateur(cp))
            raise RuntimeError("Simulation échec transaction")
    except RuntimeError:
        pass

    fabrique.valider_transaction()
    assert len(fabrique.courriels_envoyes()) == 0


# ==============================================================================
# Quotas et non-régression
# ==============================================================================

@pytest.mark.carac
def test_c02_depart_libere_place_quota(fabrique):
    """[C-02] Un départ libère une place du quota de collaborateurs : invitation à nouveau possible."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    fabrique.fixer_limites_plan(utilisateurs=1)

    collab = fabrique.utilisateur("VI")
    # Limite atteinte
    res_bloque = fabrique.inviter(client_dg, "trop_de_monde@test.ci", "VI")
    assert res_bloque.status_code == status.HTTP_403_FORBIDDEN

    # Départ du collaborateur
    client_dg.delete(fabrique.url_collaborateur(collab))

    # Place libérée
    res_libre = fabrique.inviter(client_dg, "nouvel_invite_libre@test.ci", "VI")
    assert res_libre.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    fabrique.fixer_limites_plan(utilisateurs=None)


@pytest.mark.carac
def test_c02_non_regression_ad_ne_supprime_pas_ad_ni_dg(fabrique):
    """[C-02] AD ne peut supprimer ni un AD ni le DG (403, non-régression lots 2 et 4)."""
    ad1 = fabrique.utilisateur("AD")
    ad2 = fabrique.utilisateur("AD")
    dg = fabrique.utilisateur("DG")

    client_ad = fabrique.client(ad1)
    assert client_ad.delete(fabrique.url_collaborateur(ad2)).status_code == status.HTTP_403_FORBIDDEN
    assert client_ad.delete(fabrique.url_collaborateur(dg)).status_code == status.HTTP_403_FORBIDDEN
