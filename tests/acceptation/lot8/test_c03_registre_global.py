"""Tests d'acceptation : Règle C-03 (Registre Global Schéma Public & Connexion).

Matrice issue du cadrage Lot 8 :
- Table RegistreEmail dans le schéma public (email en minuscules, entreprise FK, cree_le)
- Alimentation automatique lors de la création d'un utilisateur
- Refus 400 code email_deja_utilise si l'e-mail existe déjà dans la même ou une autre entreprise (L8-1)
- Réponse strictement identique dans les deux cas pour ne pas divulguer l'existence d'autres locataires
- Purge de la ligne lors du départ du collaborateur
- Connexion directe O(1) via le registre (plus de boucle sur les schémas)
- Commande de gestion idempotente 'remplir_registre_global'
"""

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django_tenants.utils import schema_context
from rest_framework import status

from apps.accounts.models import Utilisateur

pytestmark = pytest.mark.django_db


# ==============================================================================
# Inscription et alimentation du Registre
# ==============================================================================

@pytest.mark.regle
def test_c03_creation_collaborateur_ajoute_ligne_registre(fabrique):
    """[C-03] La création d'un collaborateur ajoute une ligne dans RegistreEmail (e-mail en minuscules, entreprise=demo)."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    email = "Nouveau.Collab.C03@Test.CI"

    res = fabrique.inviter(client_dg, email, "VI")
    assert res.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

    ligne = fabrique.registre_ligne(email)
    assert ligne is not None
    assert ligne.email == email.lower()
    assert ligne.entreprise.schema_name == "demo"


@pytest.mark.regle
def test_c03_invitation_adresse_autre_entreprise_refusee(fabrique):
    """[C-03] Inviter une adresse déjà présente dans une autre entreprise renvoie 400 email_deja_utilise, aucun compte créé."""
    autre_ent = fabrique.entreprise_fantome("Entreprise Concurrent")
    email_pris = "concurrent.employe@autre.ci"
    fabrique.declarer_dans_registre(email_pris, autre_ent)

    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    for route in (fabrique.url_invitations(), fabrique.url_collaborateurs()):
        res = fabrique.inviter(client_dg, email_pris, "VI", route=route)
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        code_err = res.data.get("erreur", {}).get("code") or res.data.get("code")
        assert code_err == "email_deja_utilise"
        assert not Utilisateur.objects.filter(email__iexact=email_pris).exists()


@pytest.mark.regle
def test_c03_meme_adresse_autre_entreprise_casse_differente(fabrique):
    """[C-03] La détection d'e-mail pris dans une autre entreprise est insensible à la casse."""
    autre_ent = fabrique.entreprise_fantome("Autre BTP")
    email_pris = "maj.mixte@autre.ci"
    fabrique.declarer_dans_registre(email_pris, autre_ent)

    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)

    res = fabrique.inviter(client_dg, "MAJ.MIXTE@autre.ci", "VI")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    code_err = res.data.get("erreur", {}).get("code") or res.data.get("code")
    assert code_err == "email_deja_utilise"


@pytest.mark.regle
def test_c03_adresse_deja_dans_meme_entreprise(fabrique):
    """[C-03] Une adresse déjà présente dans la même entreprise renvoie 400 email_deja_utilise."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    email = "interne.existant@demo.ci"

    fabrique.inviter(client_dg, email, "VI")
    res_doublon = fabrique.inviter(client_dg, email, "VI")

    assert res_doublon.status_code == status.HTTP_400_BAD_REQUEST
    code_err = res_doublon.data.get("erreur", {}).get("code") or res_doublon.data.get("code")
    assert code_err == "email_deja_utilise"


@pytest.mark.regle
def test_c03_message_erreur_identique_meme_et_autre_entreprise(fabrique):
    """[C-03] Le message et l'enveloppe d'erreur sont strictement identiques pour la même entreprise ou une autre (L8-1)."""
    autre_ent = fabrique.entreprise_fantome("Externe Group")
    email_externe = "externe.identique@autre.ci"
    fabrique.declarer_dans_registre(email_externe, autre_ent)

    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    email_interne = "interne.identique@demo.ci"
    fabrique.inviter(client_dg, email_interne, "VI")

    rep_externe = fabrique.inviter(client_dg, email_externe, "VI")
    rep_interne = fabrique.inviter(client_dg, email_interne, "VI")

    assert rep_externe.status_code == rep_interne.status_code
    assert rep_externe.data == rep_interne.data


@pytest.mark.regle
def test_c03_depart_purge_registre_et_reinvitation(fabrique):
    """[C-03] Le départ purge la ligne du registre ; une réinvitation crée une nouvelle ligne."""
    dg = fabrique.utilisateur("DG")
    client_dg = fabrique.client(dg)
    email = "cycle.registre@test.ci"

    # Création
    fabrique.inviter(client_dg, email, "VI")
    assert fabrique.registre_ligne(email) is not None
    user = Utilisateur.objects.filter(email__iexact=email).first()

    # Départ
    client_dg.delete(fabrique.url_collaborateur(user))
    assert fabrique.registre_ligne(email) is None

    # Réinvitation
    res_reinv = fabrique.inviter(client_dg, email, "VI")
    assert res_reinv.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    assert fabrique.registre_ligne(email) is not None


# ==============================================================================
# Connexion sans boucle via Registre
# ==============================================================================

@pytest.mark.carac
def test_c03_connexion_utilisateur_avec_registre(fabrique):
    """[C-03] Connexion normale d'un utilisateur du tenant : 200 OK."""
    user = fabrique.utilisateur("VI")
    user.set_password("MotDePasse123!")
    user.save()

    # Si RegistreEmail existe, y enregistrer l'utilisateur pour le test
    from apps.tenants.models import Entreprise
    with schema_context("public"):
        ent = Entreprise.objects.get(schema_name="demo")
    fabrique.declarer_dans_registre(user.email, ent)

    res = fabrique.se_connecter(user.email, "MotDePasse123!")
    assert res.status_code == status.HTTP_200_OK
    assert "access" in res.data


@pytest.mark.regle
def test_c03_connexion_sans_ligne_registre_refusee(fabrique):
    """[C-03] Supprimer la ligne du registre refuse la connexion comme un mauvais mot de passe (401)."""
    user = fabrique.utilisateur("VI")
    user.set_password("MotDePasse123!")
    user.save()

    fabrique.supprimer_du_registre(user.email)

    res = fabrique.se_connecter(user.email, "MotDePasse123!")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.regle
def test_c03_connexion_retablie_apres_restauration(fabrique):
    """[C-03] Rétablir la ligne du registre rétablit l'accès à la connexion (200)."""
    user = fabrique.utilisateur("VI")
    user.set_password("MotDePasse123!")
    user.save()

    from apps.tenants.models import Entreprise
    with schema_context("public"):
        ent = Entreprise.objects.get(schema_name="demo")

    fabrique.supprimer_du_registre(user.email)
    assert fabrique.se_connecter(user.email, "MotDePasse123!").status_code == status.HTTP_401_UNAUTHORIZED

    fabrique.declarer_dans_registre(user.email, ent)
    assert fabrique.se_connecter(user.email, "MotDePasse123!").status_code == status.HTTP_200_OK


@pytest.mark.carac
def test_c03_email_inconnu_et_mot_de_passe_faux_identique(fabrique):
    """[C-03] E-mail inconnu et mauvais mot de passe renvoient un statut et corps identiques."""
    user = fabrique.utilisateur("VI")
    user.set_password("BonMotDePasse1!")
    user.save()

    res_faux_mdp = fabrique.se_connecter(user.email, "FauxMotDePasse1!")
    res_inconnu = fabrique.se_connecter("inconnu_complet@introuvable.ci", "FauxMotDePasse1!")

    assert res_faux_mdp.status_code == status.HTTP_401_UNAUTHORIZED
    def _purger_trace_id(obj):
        if isinstance(obj, dict):
            return {k: _purger_trace_id(v) for k, v in obj.items() if k != "trace_id"}
        if isinstance(obj, list):
            return [_purger_trace_id(v) for v in obj]
        return obj

    assert _purger_trace_id(res_faux_mdp.data) == _purger_trace_id(res_inconnu.data)


@pytest.mark.regle
def test_c03_doublon_registre_integrity_error(fabrique):
    """[C-03] Insérer un doublon dans RegistreEmail (y compris avec casse différente) lève IntegrityError."""
    from apps.tenants.models import Entreprise
    with schema_context("public"):
        ent = Entreprise.objects.get(schema_name="demo")

    email = "doublon.force@registre.ci"
    fabrique.declarer_dans_registre(email, ent)

    with pytest.raises(IntegrityError):
        fabrique.declarer_dans_registre(email.upper(), ent)


@pytest.mark.regle
def test_c03_remplir_registre_global_idempotent(fabrique):
    """[C-03] La commande remplir_registre_global est idempotente."""
    total_avant = fabrique.nombre_dans_registre()
    call_command("remplir_registre_global")
    total_premier = fabrique.nombre_dans_registre()
    call_command("remplir_registre_global")
    total_second = fabrique.nombre_dans_registre()

    assert total_second == total_premier
