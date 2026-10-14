"""Le Directeur Général ne tient aucune fonction sur un chantier (décision du 14/10/2026).

Il garde ses attributions — il voit tous les chantiers, consulte, relance — et
ne se substitue à aucune fonction de chantier : ni chef de projet, ni
conducteur de travaux, ni chef de chantier. Trois chemins mènent à une
fonction : la création du projet, sa modification et les affectations. Tous
sont fermés au DG.
"""

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.core.enums import RoleGlobal, RoleProjet, StatutProjet, StatutUtilisateur
from apps.core.exceptions import DgNonAssignableCommeCp
from apps.projets.models import AffectationProjet, Projet
from apps.projets.services.affectations import affecter_collaborateur_projet

SCHEMA = "demo"
HOTE = "demo.localhost"
CODE = "dg_non_assignable_comme_cp"

pytestmark = pytest.mark.django_db


def _utilisateur(email, role, **champs):
    return Utilisateur.objects.create_user(
        email=email,
        nom=role,
        prenom="Fonction",
        role_global=role,
        statut=StatutUtilisateur.ACTIF,
        **champs,
    )


@pytest.fixture
def entreprise(db):
    with schema_context(SCHEMA):
        initialiser_roles_par_defaut()
        dg = _utilisateur("dg.fonction@demo.ci", RoleGlobal.DIRECTEUR_GENERAL, is_owner=True)
        cp = _utilisateur("cp.fonction@demo.ci", RoleGlobal.CHEF_PROJET)
        projet = Projet.objects.create(
            reference="PRJ-DG-FONCTION",
            nom="Chantier sans DG",
            ville="Abidjan",
            statut=StatutProjet.EN_COURS,
            chef_projet=cp,
            date_debut_prevue=date.today() - timedelta(days=5),
            date_fin_prevue=date.today() + timedelta(days=60),
        )
        AffectationProjet.objects.create(
            projet=projet, utilisateur=cp, role_projet=RoleProjet.CHEF_PROJET
        )
        client = APIClient()
        client.force_authenticate(user=dg)
        return {"dg": dg, "cp": cp, "projet": projet, "client": client}


@pytest.mark.parametrize(
    "role",
    [RoleProjet.CHEF_PROJET, RoleProjet.CONDUCTEUR_TRAVAUX, RoleProjet.CHEF_CHANTIER],
)
def test_une_affectation_ne_donne_pas_de_fonction_au_dg(entreprise, role):
    """La route refuse déjà tout rôle à portée entreprise ; le service le refuse aussi."""
    with schema_context(SCHEMA):
        rep = entreprise["client"].post(
            f"/api/v1/projets/{entreprise['projet'].id}/affectations/",
            {"utilisateur_id": str(entreprise["dg"].id), "role_projet": role},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == 400, rep.content
        assert "portée ENTREPRISE" in rep.content.decode()
        assert not AffectationProjet.objects.filter(utilisateur=entreprise["dg"]).exists()

        with pytest.raises(DgNonAssignableCommeCp):
            affecter_collaborateur_projet(
                projet=entreprise["projet"], utilisateur=entreprise["dg"], role_projet=role
            )
        entreprise["projet"].refresh_from_db()
        assert entreprise["projet"].chef_projet_id == entreprise["cp"].id


def test_la_modification_du_projet_ne_designe_pas_le_dg(entreprise):
    with schema_context(SCHEMA):
        rep = entreprise["client"].patch(
            f"/api/v1/projets/{entreprise['projet'].id}/",
            {"conducteur_travaux_id": str(entreprise["dg"].id)},
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == 422, rep.content
        assert rep.json()["erreur"]["code"] == CODE


def test_le_dg_cree_un_projet_sans_y_prendre_de_fonction(entreprise):
    """Créer un projet est un acte de direction : le DG le fait, et n'y est affecté à rien."""
    with schema_context(SCHEMA):
        rep = entreprise["client"].post(
            "/api/v1/projets/",
            {
                "nom": "Chantier créé par le DG",
                "type_projet": "BATIMENT_RESIDENTIEL",
                "maitre_ouvrage": "Client",
                "ville": "Abidjan",
                "chef_projet_id": str(entreprise["cp"].id),
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == 201, rep.content
        projet = Projet.objects.get(pk=rep.json()["id"])
        assert projet.chef_projet_id == entreprise["cp"].id
        assert not AffectationProjet.objects.filter(
            projet=projet, utilisateur=entreprise["dg"]
        ).exists()


def test_la_creation_ne_fait_pas_du_dg_un_conducteur_de_travaux(entreprise):
    with schema_context(SCHEMA):
        rep = entreprise["client"].post(
            "/api/v1/projets/",
            {
                "nom": "Chantier avec DG conducteur",
                "type_projet": "BATIMENT_RESIDENTIEL",
                "maitre_ouvrage": "Client",
                "ville": "Abidjan",
                "conducteur_travaux_id": str(entreprise["dg"].id),
            },
            format="json",
            HTTP_HOST=HOTE,
        )
        assert rep.status_code == 422, rep.content
        assert rep.json()["erreur"]["code"] == CODE


def test_la_commande_retire_le_dg_des_fonctions_qu_il_tient_encore(entreprise):
    with schema_context(SCHEMA):
        # Une donnée antérieure à la règle : le DG chef de projet désigné et affecté.
        projet = entreprise["projet"]
        AffectationProjet.objects.filter(utilisateur=entreprise["cp"]).update(est_actif=False)
        Projet.objects.filter(pk=projet.pk).update(
            chef_projet=entreprise["dg"], conducteur_travaux=entreprise["dg"]
        )
        AffectationProjet.objects.create(
            projet=projet, utilisateur=entreprise["dg"], role_projet=RoleProjet.CHEF_PROJET
        )

    sortie = StringIO()
    call_command("retirer_dg_des_chantiers", schema=SCHEMA, stdout=sortie)
    assert "PRJ-DG-FONCTION" in sortie.getvalue()
    with schema_context(SCHEMA):
        projet.refresh_from_db()
        assert projet.chef_projet_id == entreprise["dg"].id  # sans --appliquer, rien ne bouge

    call_command("retirer_dg_des_chantiers", schema=SCHEMA, appliquer=True, stdout=StringIO())
    with schema_context(SCHEMA):
        projet.refresh_from_db()
        assert projet.chef_projet_id is None
        assert projet.conducteur_travaux_id is None
        assert projet.sans_chef_projet is True
        assert not AffectationProjet.objects.filter(
            utilisateur=entreprise["dg"], est_actif=True
        ).exists()
