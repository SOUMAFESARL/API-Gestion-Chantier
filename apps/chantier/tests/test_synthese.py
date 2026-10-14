"""La synthèse périodique : agrégée des rapports, rédigée et signée par le CT, décidée par le CP."""

from datetime import timedelta

import pytest

from apps.chantier.models import RapportJournalier, SynthesePeriodique
from apps.chantier.services.journal import aujourdhui
from apps.chantier.tests.test_journal_api import (  # noqa: F401
    API,
    _client,
    _personne,
    creer,
    soumettre,
    terrain,
)
from apps.projets.models import AffectationProjet

pytestmark = pytest.mark.django_db

APPRECIATION = "Semaine correcte sur le gros œuvre, un rapport manque le mardi."
OBJECTIFS = [
    {
        "lot_code": "L-01",
        "activite": "Béton",
        "objectif": "+20 m3",
        "cible": 45,
        "prerequis": "Livraison de ciment confirmée",
    }
]


@pytest.fixture
def chantier(terrain):  # noqa: F811
    """Le chantier a commencé bien avant la semaine dernière : elle est entière."""
    projet = terrain["projet"]
    projet.date_debut_prevue = aujourdhui() - timedelta(days=60)
    projet.save(update_fields=["date_debut_prevue"])
    return terrain


def semaine_close():
    lundi = aujourdhui() - timedelta(days=aujourdhui().weekday() + 7)
    return lundi, lundi + timedelta(days=4)


def rapport_le(terrain, jour, *, valider=False):  # noqa: F811
    """Un rapport soumis aujourd'hui, puis reporté au jour voulu de la période."""
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    if valider:
        rep = terrain["clients"]["CT"].post(
            f"{API}/rapports/{identifiant}/valider/", {}, format="json"
        )
        assert rep.status_code == 200, rep.data
    RapportJournalier.objects.filter(pk=identifiant).update(date_rapport=jour)
    return identifiant


def periode(terrain, debut, fin, type_="HEBDOMADAIRE"):  # noqa: F811
    return {
        "projet": str(terrain["projet"].id),
        "type": type_,
        "date_debut": debut.isoformat(),
        "date_fin": fin.isoformat(),
    }


def lire(client, terrain, debut, fin, type_="HEBDOMADAIRE"):  # noqa: F811
    rep = client.get(f"{API}/syntheses/", periode(terrain, debut, fin, type_))
    assert rep.status_code == 200, rep.data
    return rep.data


def rediger(client, terrain, debut, fin, *, signer=False, appreciation=APPRECIATION):  # noqa: F811
    corps = {**periode(terrain, debut, fin), "appreciation": appreciation, "objectifs": OBJECTIFS}
    if signer:
        return client.post(f"{API}/syntheses/soumettre/", corps, format="json")
    return client.post(f"{API}/syntheses/redaction/", corps, format="json")


def test_une_semaine_close_s_agrege_de_ses_rapports_absences_comprises(chantier):
    lundi, vendredi = semaine_close()
    rapport_le(chantier, lundi, valider=True)
    rapport_le(chantier, lundi + timedelta(days=2))

    synthese = lire(chantier["clients"]["CT"], chantier, lundi, vendredi)

    assert synthese["statut"] == "A_REDIGER"
    assert synthese["id"] is None
    assert synthese["reference"].startswith(f"SYNT-{lundi.year}-")
    chiffres = synthese["chiffres"]
    assert chiffres["rapports_attendus"] == 5
    assert chiffres["rapports_recus"] == 2
    assert chiffres["rapports_valides"] == 1
    assert chiffres["incidents"] == 2
    assert chiffres["effectifs_presents"] == chiffres["effectifs_prevus"] == 8
    assert [ligne["statut"] for ligne in synthese["recapitulatif"]].count("NON_SOUMIS") == 3
    # La même activité, de la première à la dernière fois qu'elle a été travaillée.
    [bloc] = synthese["avancement"]
    [beton] = bloc["activites"]
    assert (beton["avancement_debut"], beton["avancement_fin"]) == (0, 25)
    assert synthese["effectifs"][0]["heures"] == 16
    assert synthese["materiaux"][0]["consomme"] == 30
    assert synthese["materiaux"][0]["stock_fin"] is None
    ct, cp = synthese["circuit"]
    assert (ct["etat"], cp["etat"]) == ("EN_ATTENTE", "A_VENIR")
    assert synthese["appreciation"] is None and synthese["objectifs"] == []


def test_un_brouillon_compte_pour_un_rapport_manquant_quel_que_soit_le_lecteur(chantier):
    lundi, vendredi = semaine_close()
    identifiant = creer(chantier)
    RapportJournalier.objects.filter(pk=identifiant).update(date_rapport=lundi)

    synthese = lire(chantier["clients"]["CC"], chantier, lundi, vendredi)

    assert synthese["chiffres"]["rapports_recus"] == 0
    assert all(ligne["statut"] == "NON_SOUMIS" for ligne in synthese["recapitulatif"])


def test_le_ct_redige_signe_puis_le_cp_approuve(chantier):
    lundi, vendredi = semaine_close()
    rapport_le(chantier, lundi)
    ct, cp = chantier["clients"]["CT"], chantier["clients"]["CP"]

    rep = rediger(ct, chantier, lundi, vendredi, appreciation="Brouillon")
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "BROUILLON"
    assert rep.data["redaction"]["appreciation"] == "Brouillon"
    # Un brouillon reste au CT : le CP n'en voit rien.
    vu_du_cp = lire(cp, chantier, lundi, vendredi)
    assert vu_du_cp["appreciation"] is None and vu_du_cp["redaction"] is None

    # Trop courte pour être signée : rien n'est figé.
    assert (
        rediger(ct, chantier, lundi, vendredi, signer=True, appreciation="Court").status_code == 422
    )
    assert SynthesePeriodique.objects.get().statut == "BROUILLON"

    rep = rediger(ct, chantier, lundi, vendredi, signer=True)
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "SOUMISE"
    assert rep.data["appreciation"]["texte"] == APPRECIATION
    assert rep.data["objectifs"][0]["activite"] == "Béton"
    etapes = {etape["role"]: etape for etape in rep.data["circuit"]}
    assert etapes["CT"]["etat"] == "SIGNE" and etapes["CP"]["etat"] == "EN_ATTENTE"

    identifiant = rep.data["id"]
    rep = cp.post(f"{API}/syntheses/{identifiant}/approuver/", {"commentaire": "Vu"}, format="json")
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "APPROUVEE"
    assert all(etape["etat"] == "SIGNE" for etape in rep.data["circuit"])

    # Approuvée, elle ne se réécrit plus.
    assert rediger(ct, chantier, lundi, vendredi).status_code == 422


def test_la_synthese_signee_est_figee(chantier):
    lundi, vendredi = semaine_close()
    rapport_le(chantier, lundi)
    rep = rediger(chantier["clients"]["CT"], chantier, lundi, vendredi, signer=True)
    assert rep.status_code == 200, rep.data
    signee_le = rep.data["genere_le"]

    # Un rapport arrive après la signature : la synthèse signée ne bouge pas.
    rapport_le(chantier, lundi + timedelta(days=1))
    synthese = lire(chantier["clients"]["CP"], chantier, lundi, vendredi)

    assert synthese["chiffres"]["rapports_recus"] == 1
    assert synthese["genere_le"] == signee_le


def test_le_cp_rejette_avec_motif_et_le_ct_reprend(chantier):
    lundi, vendredi = semaine_close()
    rapport_le(chantier, lundi)
    ct, cp = chantier["clients"]["CT"], chantier["clients"]["CP"]
    identifiant = rediger(ct, chantier, lundi, vendredi, signer=True).data["id"]

    chemin = f"{API}/syntheses/{identifiant}/rejeter/"
    assert cp.post(chemin, {"motif": "Trop court"}, format="json").status_code == 400
    rep = cp.post(chemin, {"motif": "Le rapport du mardi doit être expliqué."}, format="json")
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "REJETEE"
    etapes = {etape["role"]: etape for etape in rep.data["circuit"]}
    assert etapes["CP"]["etat"] == "REJETE"
    assert etapes["CP"]["commentaire"] == "Le rapport du mardi doit être expliqué."
    assert etapes["CT"]["etat"] == "EN_ATTENTE"

    # Rendue au CT : il la reprend, et la signature suivante la fige de nouveau.
    rapport_le(chantier, lundi + timedelta(days=1))
    rep = rediger(ct, chantier, lundi, vendredi, signer=True)
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "SOUMISE"
    assert rep.data["chiffres"]["rapports_recus"] == 2


def test_seul_celui_qui_tient_la_fonction_signe(chantier):
    lundi, vendredi = semaine_close()
    rapport_le(chantier, lundi)
    # Le chef de chantier n'a pas l'accès « validation » du journal.
    assert rediger(chantier["clients"]["CC"], chantier, lundi, vendredi).status_code == 403
    # Le DG l'a, mais ne tient pas la fonction de CT sur ce chantier (option 3).
    dg = _personne("DG", is_owner=True)
    rep = rediger(_client(dg), chantier, lundi, vendredi)
    assert rep.status_code == 403
    assert (
        rep.data["erreur"]["message"] == "Cette signature exige l'affectation CT sur le chantier."
    )

    identifiant = rediger(chantier["clients"]["CT"], chantier, lundi, vendredi, signer=True).data[
        "id"
    ]
    # Le CT n'approuve pas : il n'est pas chef de projet du chantier.
    rep = chantier["clients"]["CT"].post(
        f"{API}/syntheses/{identifiant}/approuver/", {}, format="json"
    )
    assert rep.status_code == 403


def test_qui_tient_les_deux_fonctions_ne_s_approuve_pas(chantier):
    lundi, vendredi = semaine_close()
    rapport_le(chantier, lundi)
    # Petite structure : le conducteur de travaux est aussi chef de projet désigné.
    projet = chantier["projet"]
    projet.chef_projet = chantier["CT"]
    projet.save(update_fields=["chef_projet"])
    ct = chantier["clients"]["CT"]
    rep = rediger(ct, chantier, lundi, vendredi, signer=True)
    assert rep.status_code == 200, rep.data
    rep = ct.post(f"{API}/syntheses/{rep.data['id']}/approuver/", {}, format="json")
    assert rep.status_code == 403
    assert rep.data["erreur"]["message"] == (
        "Le signataire CT ne peut pas approuver sa propre synthèse."
    )
    assert SynthesePeriodique.objects.get().statut == "SOUMISE"


def test_periode_libre_ou_en_cours_ne_se_signe_pas(chantier):
    lundi, _ = semaine_close()
    ct = chantier["clients"]["CT"]

    libre = lire(ct, chantier, lundi, lundi + timedelta(days=2), "PERSONNALISEE")
    assert libre["statut"] == "LIBRE" and libre["circuit"] == []
    corps = {
        **periode(chantier, lundi, lundi + timedelta(days=2), "PERSONNALISEE"),
        "appreciation": APPRECIATION,
    }
    assert ct.post(f"{API}/syntheses/redaction/", corps, format="json").status_code == 422

    cette_semaine = aujourdhui() - timedelta(days=aujourdhui().weekday())
    en_cours = lire(ct, chantier, cette_semaine, cette_semaine + timedelta(days=4))
    assert en_cours["statut"] == "EN_COURS"
    assert [etape["etat"] for etape in en_cours["circuit"]] == ["A_VENIR", "A_VENIR"]
    rep = rediger(ct, chantier, cette_semaine, cette_semaine + timedelta(days=4))
    assert rep.status_code == 422


@pytest.mark.parametrize(
    "decalage, type_, duree",
    [
        (1, "HEBDOMADAIRE", 4),  # une semaine commence le lundi
        (0, "HEBDOMADAIRE", 6),  # et finit le vendredi
        (0, "MENSUELLE", 10),  # un mois va du premier au dernier jour
    ],
)
def test_les_bornes_de_la_periode_sont_controlees(chantier, decalage, type_, duree):
    lundi, _ = semaine_close()
    debut = lundi + timedelta(days=decalage)
    rep = chantier["clients"]["CT"].get(
        f"{API}/syntheses/", periode(chantier, debut, debut + timedelta(days=duree), type_)
    )
    assert rep.status_code == 400


def test_une_periode_future_ne_se_synthetise_pas(chantier):
    lundi = aujourdhui() + timedelta(days=7 - aujourdhui().weekday())
    rep = chantier["clients"]["CT"].get(
        f"{API}/syntheses/", periode(chantier, lundi, lundi + timedelta(days=4))
    )
    assert rep.status_code == 400


def test_le_suivi_dit_ou_en_est_chaque_synthese(chantier):
    lundi, vendredi = semaine_close()
    rediger(chantier["clients"]["CT"], chantier, lundi, vendredi)
    rep = chantier["clients"]["CP"].get(
        f"{API}/syntheses/suivi/", {"projet": str(chantier["projet"].id)}
    )
    assert rep.status_code == 200, rep.data
    [ligne] = rep.data["resultats"]
    assert ligne["statut"] == "BROUILLON"
    assert ligne["date_debut"] == lundi.isoformat()


def test_un_visiteur_hors_chantier_ne_lit_pas_la_synthese(chantier):
    lundi, vendredi = semaine_close()
    AffectationProjet.objects.filter(projet=chantier["projet"], utilisateur=chantier["VI"]).update(
        est_actif=False
    )
    rep = chantier["clients"]["VI"].get(f"{API}/syntheses/", periode(chantier, lundi, vendredi))
    assert rep.status_code in (403, 404)
