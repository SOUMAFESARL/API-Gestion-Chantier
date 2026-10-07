"""
[E-10] Tests d'acceptation du Lot 6 : Effets des statuts sur les écritures (Refus 409 projet_clos).
Règles : E-10 (cahier-regles.md).
"""
import pytest
from apps.core.enums import StatutProjet

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


@NOUVEAU
def test_e10_projet_resilie_rapport_refuse_409_projet_clos(fab):
    """[E-10 CA] POST d'un rapport sur un projet RESILIE renvoie 409 projet_clos."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_rapports(),
        fab.corps_rapport(projet),
        format="json",
    )
    assert r.status_code == 409, f"Écriture sur projet résilié doit renvoyer 409, reçu {r.status_code}"
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)


@CARAC
def test_e10_projet_suspendu_rapport_autorise_201(fab):
    """[E-10 CA] Même requête POST de rapport sur un projet SUSPENDU renvoie 201 (tout reste permis)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.SUSPENDU)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_rapports(),
        fab.corps_rapport(projet),
        format="json",
    )
    assert r.status_code == 201, f"Écriture de rapport sur projet suspendu doit être acceptée, reçu {r.status_code}"


@NOUVEAU
def test_e10_projet_resilie_ecritures_lots_refusees_409(fab):
    """[E-10] Fin de vie : POST lot sur un projet RESILIE renvoie 409 projet_clos."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_lots(projet),
        fab.corps_lot("Nouveau Lot Test"),
        format="json",
    )
    assert r.status_code == 409, f"Création de lot sur projet clos doit renvoyer 409, reçu {r.status_code}"
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)


@NOUVEAU
def test_e10_projet_resilie_equipes_refusees_409(fab):
    """[E-10] Fin de vie : POST équipe sur un projet RESILIE renvoie 409 projet_clos."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_equipes(projet),
        fab.corps_equipe("Équipe Clos"),
        format="json",
    )
    assert r.status_code == 409
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)


@NOUVEAU
def test_e10_projet_resilie_affectations_refusees_409(fab):
    """[E-10] Fin de vie : POST affectation sur un projet RESILIE renvoie 409 projet_clos."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")
    cible = fab.acteur("CC")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_affectations(projet),
        fab.corps_affectation(cible, role_projet="CC"),
        format="json",
    )
    assert r.status_code == 409
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)


@NOUVEAU
def test_e10_projet_resilie_reprogrammation_refusee_409(fab):
    """[E-10] Fin de vie : POST reprogrammation sur un projet RESILIE renvoie 409 projet_clos."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_reprogrammer_projet(projet),
        fab.corps_reprogrammation(),
        format="json",
    )
    assert r.status_code == 409
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)


@NOUVEAU
def test_e10_priorite_garde_rbac_sur_projet_clos(fab):
    """[E-10 Ordre des gardes] Un acteur sans droit (VI) reçoit 403 (et non 409) même si le projet est clos."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")

    client_vi = fab.client_pour(vi)
    r = client_vi.post(
        fab.url_lots(projet),
        fab.corps_lot("Lot VI Refusé"),
        format="json",
    )
    assert r.status_code == 403, f"Sans permission d'écriture, l'acteur doit recevoir 403, reçu {r.status_code}"


@CARAC
def test_e10_lecture_projet_clos_reste_autorisee_200(fab):
    """[E-10] Fin de vie : la lecture (GET) d'un projet résilié reste permise (lecture seule)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.RESILIE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.get(fab.url_projet_detail(projet))
    assert r.status_code == 200


@NOUVEAU
def test_e10_projet_termine_nouveau_rapport_refuse_409(fab):
    """[E-10 Achèvement] Projet TERMINE : nouveaux rapports journaliers interdits (409 projet_clos)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.TERMINE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_rapports(),
        fab.corps_rapport(projet),
        format="json",
    )
    assert r.status_code == 409
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)


@NOUVEAU
def test_e10_projet_termine_reprogrammation_refusee_409(fab):
    """[E-10 Achèvement] Projet TERMINE : reprogrammation interdite (409 projet_clos)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.TERMINE)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.post(
        fab.url_reprogrammer_projet(projet),
        fab.corps_reprogrammation(),
        format="json",
    )
    assert r.status_code == 409
    assert r.data.get("code") == "projet_clos" or "projet_clos" in str(r.data)
