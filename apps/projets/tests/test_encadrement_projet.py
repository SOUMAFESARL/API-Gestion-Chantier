"""L'encadrement du projet dans la réponse de `/projets/` (alignement du frontend, tâche 1.2 bis).

Le frontend décide qui voit quel chantier d'après `chef_projet`,
`conducteurs_travaux` et `chefs_chantier`. Sans eux, un chef de chantier ne
voyait jamais son chantier à l'écran, alors que le serveur le lui renvoyait.
"""

from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet
from apps.projets.selectors.encadrement import aujourdhui

SCHEMA = "demo"
HOTE = "demo.localhost"

pytestmark = pytest.mark.django_db

#: La forme d'un intervenant que lit `versIntervenant()` côté frontend.
CHAMPS_INTERVENANT = {
    "id",
    "nom",
    "prenom",
    "nom_complet",
    "email",
    "telephone",
    "statut",
    "lien_whatsapp",
    "affectation_id",
}


def _utilisateur(email, nom, role):
    u, _ = Utilisateur.tous_objets.get_or_create(
        email=email,
        defaults={
            "nom": nom,
            "prenom": "Test",
            "role_global": role,
            "statut": StatutUtilisateur.ACTIF,
        },
    )
    return u


def _projet(reference, **champs):
    return Projet.objects.create(
        reference=reference,
        nom=f"Chantier {reference}",
        ville="Abidjan",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2027, 12, 31),
        statut=StatutProjet.EN_COURS,
        **champs,
    )


def _affecter(projet, utilisateur, role, **champs):
    return AffectationProjet.objects.create(
        projet=projet, utilisateur=utilisateur, role_projet=role, est_actif=True, **champs
    )


@pytest.fixture
def chantier(db):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        dg = _utilisateur("dg.encadrement@demo.ci", "Direction", RoleGlobal.DIRECTEUR_GENERAL)
        dg.is_owner = True
        dg.save(update_fields=["is_owner"])
        cp = _utilisateur("cp.encadrement@demo.ci", "Chef", RoleGlobal.CHEF_PROJET)
        ct = _utilisateur("ct.encadrement@demo.ci", "Conducteur", RoleGlobal.CONDUCTEUR_TRAVAUX)
        ct2 = _utilisateur("ct2.encadrement@demo.ci", "Second", RoleGlobal.CONDUCTEUR_TRAVAUX)
        cc = _utilisateur("cc.encadrement@demo.ci", "Chantier", RoleGlobal.CHEF_CHANTIER)
        projet = _projet("PRJ-ENC-01", chef_projet=cp, conducteur_travaux=ct)
        # Le conducteur principal est aussi affecté : il ne doit figurer qu'une fois.
        _affecter(projet, ct, RoleProjet.CONDUCTEUR_TRAVAUX)
        _affecter(projet, ct2, RoleProjet.CONDUCTEUR_TRAVAUX)
        _affecter(projet, cc, RoleProjet.CHEF_CHANTIER)
        return {"dg": dg, "cp": cp, "ct": ct, "ct2": ct2, "cc": cc, "projet": projet}


def _lire(utilisateur, chemin):
    client = APIClient()
    client.force_authenticate(user=utilisateur)
    reponse = client.get(chemin, HTTP_HOST=HOTE)
    assert reponse.status_code == 200, reponse.content
    return reponse.json()


def test_le_chef_de_chantier_se_trouve_dans_son_chantier(chantier):
    with schema_context(SCHEMA):
        liste = _lire(chantier["cc"], "/api/v1/projets/")
    projet = next(p for p in liste if p["reference"] == "PRJ-ENC-01")
    chefs = projet["chefs_chantier"]
    assert [c["utilisateur"]["id"] for c in chefs] == [str(chantier["cc"].id)]
    assert set(chefs[0]["utilisateur"]) == CHAMPS_INTERVENANT
    assert chefs[0]["zone"] is None


def test_le_detail_porte_chef_de_projet_et_conducteurs_sans_doublon(chantier):
    with schema_context(SCHEMA):
        projet = _lire(chantier["dg"], f"/api/v1/projets/{chantier['projet'].id}/")
    assert projet["chef_projet"]["id"] == str(chantier["cp"].id)
    assert set(projet["chef_projet"]) == CHAMPS_INTERVENANT
    # Le conducteur principal d'abord, puis l'affecté ; le principal, affecté aussi, une seule fois.
    assert [c["id"] for c in projet["conducteurs_travaux"]] == [
        str(chantier["ct"].id),
        str(chantier["ct2"].id),
    ]


def test_une_affectation_inactive_ou_hors_periode_ne_compte_pas(chantier):
    with schema_context(SCHEMA):
        projet = chantier["projet"]
        jour = aujourdhui()
        partis = _utilisateur("cc.parti@demo.ci", "Parti", RoleGlobal.CHEF_CHANTIER)
        futur = _utilisateur("cc.futur@demo.ci", "Futur", RoleGlobal.CHEF_CHANTIER)
        inactif = _utilisateur("cc.inactif@demo.ci", "Inactif", RoleGlobal.CHEF_CHANTIER)
        _affecter(projet, partis, RoleProjet.CHEF_CHANTIER, date_fin=jour - timedelta(days=1))
        _affecter(projet, futur, RoleProjet.CHEF_CHANTIER, date_debut=jour + timedelta(days=3))
        affectation = _affecter(projet, inactif, RoleProjet.CHEF_CHANTIER)
        affectation.est_actif = False
        affectation.save(update_fields=["est_actif"])
        detail = _lire(chantier["dg"], f"/api/v1/projets/{projet.id}/")
    assert [c["utilisateur"]["id"] for c in detail["chefs_chantier"]] == [str(chantier["cc"].id)]


def test_un_projet_sans_encadrement_renvoie_des_listes_vides(chantier):
    with schema_context(SCHEMA):
        nu = _projet("PRJ-ENC-NU")
        detail = _lire(chantier["dg"], f"/api/v1/projets/{nu.id}/")
    assert detail["chef_projet"] is None
    assert detail["conducteurs_travaux"] == []
    assert detail["chefs_chantier"] == []


def test_la_liste_ne_fait_pas_une_requete_par_projet(chantier):
    """L'encadrement est préchargé : ajouter des chantiers n'ajoute pas de requêtes."""
    client = APIClient()
    client.force_authenticate(user=chantier["dg"])
    with schema_context(SCHEMA):
        with CaptureQueriesContext(connection) as avant:
            assert client.get("/api/v1/projets/", HTTP_HOST=HOTE).status_code == 200
        for rang in range(3):
            autre = _projet(f"PRJ-ENC-X{rang}", chef_projet=chantier["cp"])
            _affecter(autre, chantier["cc"], RoleProjet.CHEF_CHANTIER)
            _affecter(autre, chantier["ct2"], RoleProjet.CONDUCTEUR_TRAVAUX)
        with CaptureQueriesContext(connection) as apres:
            assert client.get("/api/v1/projets/", HTTP_HOST=HOTE).status_code == 200
    assert len(apres.captured_queries) == len(avant.captured_queries)
