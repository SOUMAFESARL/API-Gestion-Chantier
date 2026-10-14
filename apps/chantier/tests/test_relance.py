"""La relance d'une ligne du journal : manuelle depuis l'écran, automatique à 17 h 30."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command

from apps.chantier.models import RelanceJournal
from apps.chantier.services.journal import aujourdhui
from apps.chantier.services.relance import relancer_rapports_manquants
from apps.chantier.tests.test_journal_api import API, creer, soumettre, terrain  # noqa: F401

pytestmark = pytest.mark.django_db


def _jour_ouvre():
    """Le dernier jour ouvré, aujourd'hui compris : un rapport y est attendu."""
    jour = aujourdhui()
    while jour.weekday() >= 5:
        jour -= timedelta(days=1)
    return jour


def _ligne_manquante(terrain, jour):  # noqa: F811
    return f"{terrain['projet'].id}_{jour.isoformat()}"


def test_relancer_un_rapport_manquant_ecrit_au_chef_de_chantier(terrain):  # noqa: F811
    mail.outbox = []
    jour = _jour_ouvre()
    rep = terrain["clients"]["CT"].post(
        f"{API}/journal/{_ligne_manquante(terrain, jour)}/relancer/", {}, format="json"
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["etape"] == "CC"
    assert [m.to for m in mail.outbox] == [[terrain["CC"].email]]
    assert "Rapport journalier attendu" in mail.outbox[0].subject
    assert f"/rapports/saisie/{terrain['projet'].id}?date={jour.isoformat()}" in mail.outbox[0].body

    # La ligne du journal porte la relance du jour : l'écran affiche « envoyée ».
    journal = terrain["clients"]["CT"].get(
        f"{API}/journal/",
        {
            "projet": str(terrain["projet"].id),
            "date_debut": jour.isoformat(),
            "date_fin": jour.isoformat(),
        },
    )
    ligne = next(e for e in journal.data["resultats"] if e["date"] == jour.isoformat())
    assert ligne["relance_le"] == rep.data["relance_le"]


def test_une_relance_par_ligne_et_par_jour(terrain):  # noqa: F811
    mail.outbox = []
    chemin = f"{API}/journal/{_ligne_manquante(terrain, _jour_ouvre())}/relancer/"
    premiere = terrain["clients"]["CT"].post(chemin, {}, format="json")
    seconde = terrain["clients"]["CT"].post(chemin, {}, format="json")
    assert premiere.status_code == seconde.status_code == 200
    assert seconde.data["relance_le"] == premiere.data["relance_le"]
    assert len(mail.outbox) == 1
    assert RelanceJournal.objects.count() == 1


def test_un_rapport_soumis_relance_le_conducteur_puis_le_chef_de_projet(terrain):  # noqa: F811
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    mail.outbox = []
    rep = terrain["clients"]["CT"].post(f"{API}/journal/{identifiant}/relancer/", {}, format="json")
    assert rep.status_code == 200, rep.data
    assert rep.data["etape"] == "CT"
    assert mail.outbox[0].to == [terrain["CT"].email]
    assert f"/rapports/{identifiant}" in mail.outbox[0].body


def test_un_rapport_approuve_ne_se_relance_pas(terrain):  # noqa: F811
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    terrain["clients"]["CT"].post(f"{API}/rapports/{identifiant}/valider/", {}, format="json")
    terrain["clients"]["CP"].post(f"{API}/rapports/{identifiant}/approuver/", {}, format="json")
    rep = terrain["clients"]["CT"].post(f"{API}/journal/{identifiant}/relancer/", {}, format="json")
    assert rep.status_code == 422


def test_relancer_exige_le_droit_de_validation(terrain):  # noqa: F811
    chemin = f"{API}/journal/{_ligne_manquante(terrain, _jour_ouvre())}/relancer/"
    assert terrain["clients"]["CC"].post(chemin, {}, format="json").status_code == 403
    assert (
        terrain["clients"]["CT"]
        .post(f"{API}/journal/pas-une-ligne/relancer/", {}, format="json")
        .status_code
        == 400
    )


def test_un_echec_d_envoi_ne_laisse_pas_croire_a_une_relance(terrain):  # noqa: F811
    chemin = f"{API}/journal/{_ligne_manquante(terrain, _jour_ouvre())}/relancer/"
    with mock.patch("apps.chantier.services.relance.envoyer", return_value=False):
        rep = terrain["clients"]["CT"].post(chemin, {}, format="json")
    assert rep.status_code == 503
    assert RelanceJournal.objects.count() == 0


def test_la_relance_automatique_vise_les_seuls_rapports_non_remis(terrain):  # noqa: F811
    jour = _jour_ouvre()
    mail.outbox = []
    bilan = relancer_rapports_manquants(jour)
    assert bilan["relances"] == 1
    assert RelanceJournal.objects.get().automatique is True
    assert [m.to for m in mail.outbox] == [[terrain["CC"].email]]
    # Repassée le même jour : rien de plus.
    assert relancer_rapports_manquants(jour)["deja_relances"] == 1
    assert len(mail.outbox) == 1


def test_la_relance_automatique_ignore_un_rapport_soumis_et_le_week_end(terrain):  # noqa: F811
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    assert relancer_rapports_manquants(aujourdhui())["relances"] == 0
    samedi = aujourdhui() + timedelta(days=(5 - aujourdhui().weekday()) % 7)
    assert relancer_rapports_manquants(samedi)["relances"] == 0


def test_la_commande_de_17h30_tourne_dans_le_schema_de_l_entreprise(terrain):  # noqa: F811
    """Sans `schema_context`, la tâche tournerait sur `public` et ne trouverait rien."""
    mail.outbox = []
    with mock.patch("apps.chantier.services.relance.aujourdhui", return_value=_jour_ouvre()):
        call_command("relancer_rapports_manquants", schema="demo")
    assert RelanceJournal.objects.filter(projet=terrain["projet"], automatique=True).exists()
