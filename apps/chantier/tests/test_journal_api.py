"""Parcours métier et refus d'accès du journal complet, dans un vrai tenant."""

import base64
import io
from datetime import timedelta
from uuid import uuid4

import pytest
from django_tenants.utils import schema_context
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.chantier.models import AlerteJournal, JournalChantier, RapportJournalier
from apps.chantier.services.journal import aujourdhui
from apps.projets.models import Activite, AffectationProjet, Lot, Projet

API = "/api/v1/chantier"
pytestmark = pytest.mark.django_db


@pytest.fixture
def terrain(db, schema_demo):
    initialiser_roles_par_defaut()
    personnes = {}
    for code in ("CC", "CT", "CP", "VI"):
        personnes[code] = Utilisateur.objects.create_user(
            email=f"journal-{code}-{uuid4().hex[:8]}@demo.ci",
            password="TestJournal!123",
            nom=code,
            prenom="Journal",
            role=Role.objects.get(code=code),
            role_global=code,
            statut="ACTIF",
        )
    projet = Projet.objects.create(
        reference=f"PRJ-J-{uuid4().hex[:6]}",
        nom="Journal chantier",
        ville="Abidjan",
        statut="EN_COURS",
        chef_projet=personnes["CP"],
        date_debut_prevue=aujourdhui() - timedelta(days=10),
        date_fin_prevue=aujourdhui() + timedelta(days=30),
    )
    for code, utilisateur in personnes.items():
        AffectationProjet.objects.create(projet=projet, utilisateur=utilisateur, role_projet=code)
    lot = Lot.objects.create(
        projet=projet, code="L-01", libelle="Gros œuvre", mode_execution="REGIE"
    )
    activite = Activite.objects.create(lot=lot, libelle="Béton", quantite_prevue=100, unite="M3")
    clients = {}
    for code, utilisateur in personnes.items():
        client = APIClient(HTTP_HOST="demo.localhost")
        client.force_authenticate(user=utilisateur)
        clients[code] = client
    return {**personnes, "projet": projet, "lot": lot, "activite": activite, "clients": clients}


def corps(terrain, **changements):
    data = {
        "projet_id": str(terrain["projet"].id),
        "date": aujourdhui().isoformat(),
        "heure_debut": "07:30",
        "heure_fin": "17:00",
        "arret": None,
        "meteo": {
            "matin": "NUAGEUX",
            "apres_midi": "ORAGEUX",
            "conditions": "DIFFICILES",
            "temperature_min": 22,
            "temperature_max": 31,
            "humidite": 80,
            "vent": "Sud-ouest",
            "prevision": "Pluie",
        },
        "effectifs": [
            {
                "categorie": "Maçons",
                "prevus": 4,
                "presents": 4,
                "retards": 0,
                "heures": 8,
                "observation": "",
            }
        ],
        "lots_travailles": [
            {"lot_id": str(terrain["lot"].id), "observation": "Coulage de la dalle"}
        ],
        "activites": [
            {
                "activite_id": str(terrain["activite"].id),
                "quantite_jour": 12.5,
                "localisation": "Bâtiment B, R+1",
                "observation": "Coulage conforme",
            }
        ],
        "materiaux": [{"designation": "Ciment", "quantite_consommee": 15, "unite": "sacs"}],
        "livraisons": [
            {
                "fournisseur": "Fournisseur CI",
                "designation": "Gravier",
                "quantite": "5 m3",
                "bon_livraison": "BL-01",
                "heure": "09:30",
                "conformite": "CONFORME",
                "observation": "",
            }
        ],
        "besoins": [
            {
                "nature": "URGENT",
                "designation": "Ciment",
                "quantite": "10 sacs",
                "observation": "Pour demain",
            }
        ],
        "equipements": [
            {
                "designation": "Bétonnière",
                "reference": "ENG-1",
                "propriete": "ENTREPRISE",
                "utilisation": "8 h",
                "operateur": "Koné",
                "etat": "BON",
                "duree_arret": 0,
                "observation": "",
            }
        ],
        "incidents": [
            {
                "cle": "evt-1",
                "nature": "INTEMPERIE",
                "type": "MATERIEL",
                "heure_debut": "14:00",
                "heure_fin": "15:00",
                "gravite": "MINEUR",
                "decide_par": "CC",
                "description": "Pluie forte pendant une heure sur le chantier.",
                "action_entreprise": "Protection du matériel",
            }
        ],
        "blocage": {"niveau": "AUCUN", "nature": None, "description": "", "impact": ""},
        "previsions": [
            {
                "activite": "Coffrage",
                "equipe": "Coffreurs",
                "objectif": "Terminer la travée B",
                "prerequis": "Matériel disponible",
            }
        ],
        "note_cc": "Travaux réalisés conformément au planning.",
    }
    return {**data, **changements}


def creer(terrain, data=None):
    response = terrain["clients"]["CC"].post(
        f"{API}/rapports/", data or corps(terrain), format="json"
    )
    assert response.status_code == 201, response.data
    return response.data["id"]


def soumettre(terrain, identifiant):
    response = terrain["clients"]["CC"].post(
        f"{API}/rapports/{identifiant}/soumettre/", {}, format="json"
    )
    assert response.status_code == 200, response.data
    return response


def test_crud_et_reprise_du_formulaire(terrain):
    cc = terrain["clients"]["CC"]
    identifiant = creer(terrain)
    rep = cc.get(f"{API}/rapports/{identifiant}/")
    assert rep.status_code == 200
    assert rep.data["saisie"]["activites"][0]["localisation"] == "Bâtiment B, R+1"
    assert rep.data["travaux"][0]["activites"][0]["quantite_jour"] == 12.5
    assert rep.data["effectif_present"] == 4
    rep = cc.patch(
        f"{API}/rapports/{identifiant}/draft/",
        {"note_cc": "Note mise à jour", "meteo": {"vent": "Faible"}},
        format="json",
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["saisie"]["meteo"]["matin"] == "NUAGEUX"
    assert rep.data["saisie"]["meteo"]["vent"] == "Faible"
    assert len(rep.data["saisie"]["activites"]) == 1
    rep = cc.get(
        f"{API}/rapports/preparation/",
        {"projet": str(terrain["projet"].id), "date": aujourdhui().isoformat()},
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["rapport"]["id"] == identifiant
    assert rep.data["lots"][0]["mode_execution"] == "REGIE_DIRECTE"
    assert rep.data["activites"][0]["activite_id"] == str(terrain["activite"].id)
    assert "EFFECTIFS" in rep.data["sections"]
    rep = cc.get(f"{API}/rapports/", {"auteur": "moi", "projet": str(terrain["projet"].id)})
    assert rep.status_code == 200
    assert rep.data["resultats"][0]["id"] == identifiant


def test_brouillon_incomplet_et_soumission_atomique(terrain):
    cc = terrain["clients"]["CC"]
    identifiant = creer(
        terrain, {"projet_id": str(terrain["projet"].id), "date": aujourdhui().isoformat()}
    )
    rep = cc.post(
        f"{API}/rapports/{identifiant}/soumettre/",
        {"note_cc": "tentative incomplète"},
        format="json",
    )
    assert rep.status_code == 422, rep.data
    journal = JournalChantier.objects.get(rapport_id=identifiant)
    assert journal.saisie["note_cc"] == ""
    assert journal.rapport.statut == "BROUILLON"
    assert journal.rapport.soumis_le is None


def test_circuit_ct_cp_et_verrouillage(terrain):
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    cc, ct, cp = (terrain["clients"][code] for code in ("CC", "CT", "CP"))
    rep = cc.patch(
        f"{API}/rapports/{identifiant}/", {"note_cc": "Modification interdite"}, format="json"
    )
    assert rep.status_code == 422
    rep = cp.post(f"{API}/rapports/{identifiant}/approuver/", {}, format="json")
    assert rep.status_code == 422
    rep = ct.post(
        f"{API}/rapports/{identifiant}/valider/", {"commentaire": "Conforme"}, format="json"
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "VALIDE_CT"
    rep = ct.post(f"{API}/rapports/{identifiant}/approuver/", {}, format="json")
    assert rep.status_code == 403
    rep = cp.post(f"{API}/rapports/{identifiant}/approuver/", {}, format="json")
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "APPROUVE_CP"
    assert [e["etat"] for e in rep.data["circuit"]] == ["SIGNE", "SIGNE", "SIGNE"]
    rep = cp.post(
        f"{API}/rapports/{identifiant}/rejeter/",
        {"motif": "Un rapport approuvé est définitif."},
        format="json",
    )
    assert rep.status_code == 422
    terrain["lot"].refresh_from_db()
    assert terrain["lot"].premier_rapport_soumis


def test_rejet_et_resoumission(terrain):
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    ct = terrain["clients"]["CT"]
    rep = ct.post(f"{API}/rapports/{identifiant}/rejeter/", {"motif": "court"}, format="json")
    assert rep.status_code == 400
    rep = ct.post(
        f"{API}/rapports/{identifiant}/rejeter/",
        {"motif": "Corriger la localisation des travaux réalisés."},
        format="json",
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["statut"] == "REJETE"
    rep = terrain["clients"]["CC"].patch(
        f"{API}/rapports/{identifiant}/draft/",
        {"note_cc": "Localisation corrigée par le rédacteur."},
        format="json",
    )
    assert rep.status_code == 200
    soumettre(terrain, identifiant)
    journal = JournalChantier.objects.get(rapport_id=identifiant)
    assert journal.rapport.commentaire_validation == ""
    assert journal.valide_ct_le is None


def test_doublon_et_suppression_logique_brouillon(terrain):
    identifiant = creer(terrain)
    cc = terrain["clients"]["CC"]
    rep = cc.post(f"{API}/rapports/", corps(terrain), format="json")
    assert rep.status_code == 409
    rep = cc.delete(f"{API}/rapports/{identifiant}/")
    assert rep.status_code == 204, rep.data
    assert cc.get(f"{API}/rapports/{identifiant}/").status_code == 404
    assert RapportJournalier.tous_objets.get(pk=identifiant).supprime_le is not None
    nouveau = creer(terrain)
    assert nouveau != identifiant
    soumettre(terrain, nouveau)
    assert cc.delete(f"{API}/rapports/{nouveau}/").status_code == 422


@pytest.mark.parametrize(
    "changement",
    [
        {
            "effectifs": [
                {"categorie": "Maçons", "prevus": 2, "presents": 3, "retards": 0, "heures": 8}
            ]
        },
        {
            "effectifs": [
                {"categorie": "Maçons", "prevus": 2, "presents": 2, "retards": 3, "heures": 8}
            ]
        },
        {
            "effectifs": [
                {"categorie": "Maçons", "prevus": 2, "presents": 2, "retards": 0, "heures": 25}
            ]
        },
        {"meteo": {"matin": "INCONNU"}},
        {"meteo": {"temperature_min": 40, "temperature_max": 20}},
        {"lots_travailles": [{"lot_id": str(uuid4()), "observation": "Extérieur"}]},
        {"activites": [{"activite_id": str(uuid4()), "quantite_jour": 2}]},
        {"statut": "APPROUVE_CP"},
    ],
)
def test_validation_structure_et_perimetre(terrain, changement):
    rep = terrain["clients"]["CC"].post(
        f"{API}/rapports/", corps(terrain, **changement), format="json"
    )
    assert rep.status_code == 400, rep.data
    assert not JournalChantier.objects.exists()


@pytest.mark.parametrize("jours", [-3, 1])
def test_fenetre_saisie(terrain, jours):
    rep = terrain["clients"]["CC"].post(
        f"{API}/rapports/",
        corps(terrain, date=(aujourdhui() + timedelta(days=jours)).isoformat()),
        format="json",
    )
    assert rep.status_code == 422, rep.data


def test_acces_projet_auteur_et_tenant(terrain):
    identifiant = creer(terrain)
    ct = terrain["clients"]["CT"]
    assert ct.get(f"{API}/rapports/{identifiant}/").status_code == 404
    assert ct.get(f"{API}/rapports/").data["resultats"] == []
    autre = Projet.objects.create(
        reference=f"AUTRE-{uuid4().hex[:6]}", nom="Non affecté", ville="Abidjan", statut="EN_COURS"
    )
    cc = terrain["clients"]["CC"]
    rep = cc.post(
        f"{API}/rapports/",
        {"projet_id": str(autre.id), "date": aujourdhui().isoformat()},
        format="json",
    )
    assert rep.status_code == 404
    soumettre(terrain, identifiant)
    assert ct.get(f"{API}/rapports/{identifiant}/").status_code == 200
    AffectationProjet.objects.filter(projet=terrain["projet"], utilisateur=terrain["CT"]).update(
        est_actif=False
    )
    assert ct.get(f"{API}/rapports/{identifiant}/").status_code == 404
    with schema_context("tenant_b"):
        assert not JournalChantier.objects.filter(rapport_id=identifiant).exists()
    anonyme = APIClient(HTTP_HOST="demo.localhost")
    assert anonyme.get(f"{API}/rapports/{identifiant}/").status_code == 401


def test_absence_motivee_et_journee_arret(terrain):
    identifiant = creer(
        terrain,
        corps(
            terrain,
            effectifs=[
                {
                    "categorie": "Maçons",
                    "prevus": 4,
                    "presents": 3,
                    "retards": 0,
                    "heures": 8,
                    "observation": "",
                }
            ],
        ),
    )
    rep = terrain["clients"]["CC"].post(
        f"{API}/rapports/{identifiant}/soumettre/", {}, format="json"
    )
    assert rep.status_code == 422
    terrain["clients"]["CC"].delete(f"{API}/rapports/{identifiant}/")
    data = {
        "projet_id": str(terrain["projet"].id),
        "date": aujourdhui().isoformat(),
        "heure_debut": "07:30",
        "heure_fin": "17:00",
        "arret": {"motif": "INTEMPERIES", "precision": "Pluie"},
        "meteo": {"matin": "PLUVIEUX", "apres_midi": "ORAGEUX", "conditions": "ARRET"},
    }
    identifiant = creer(terrain, data)
    soumettre(terrain, identifiant)
    terrain["activite"].refresh_from_db()
    assert terrain["activite"].quantite_realisee == 0


def test_medias_embarques_et_protection(terrain):
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="PNG")
    fichier = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
    photo = {
        "cle": "photo-1",
        "fichier": fichier,
        "legende": "Dalle",
        "horodatage_utc": "2026-10-07T14:00:00Z",
        "latitude": 5.3,
        "longitude": -4.0,
    }
    pdf = b"%PDF-1.4\nDocument de test"
    piece = {
        "cle": "doc-1",
        "nom": "plan.pdf",
        "fichier": "data:application/pdf;base64," + base64.b64encode(pdf).decode(),
        "type_mime": "application/pdf",
        "taille": len(pdf),
    }
    identifiant = creer(terrain, corps(terrain, photos=[photo], pieces_jointes=[piece]))
    rep = terrain["clients"]["CC"].get(f"{API}/rapports/{identifiant}/")
    assert rep.data["photos"][0]["url"] == fichier
    assert rep.data["photos"][0]["gps_confirme"] is True
    assert rep.data["pieces_jointes"][0]["nom"] == "plan.pdf"
    assert terrain["clients"]["CT"].get(f"{API}/rapports/{identifiant}/").status_code == 404
    for invalide in (
        {**photo, "fichier": "https://example.com/a.png"},
        {**photo, "longitude": None},
        {**photo, "fichier": "data:image/png;base64,bm90YW5pbWFnZQ=="},
    ):
        rep = terrain["clients"]["CC"].patch(
            f"{API}/rapports/{identifiant}/draft/", {"photos": [invalide]}, format="json"
        )
        assert rep.status_code == 400, rep.data
    rep = terrain["clients"]["CC"].patch(
        f"{API}/rapports/{identifiant}/draft/",
        {"photos": [{**photo, "cle": str(i)} for i in range(6)]},
        format="json",
    )
    assert rep.status_code == 400


def test_snapshot_et_cumul_sans_double_comptage(terrain):
    identifiant = creer(
        terrain, corps(terrain, date=(aujourdhui() - timedelta(days=1)).isoformat())
    )
    soumettre(terrain, identifiant)
    terrain["activite"].libelle = "Nouveau libellé"
    terrain["activite"].save()
    rep = terrain["clients"]["CC"].get(f"{API}/rapports/{identifiant}/")
    assert rep.data["travaux"][0]["activites"][0]["libelle"] == "Béton"
    rep = terrain["clients"]["CC"].get(
        f"{API}/rapports/preparation/",
        {"projet": str(terrain["projet"].id), "date": aujourdhui().isoformat()},
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["activites"][0]["cumul_veille"] == 12.5


def test_journal_rapports_manquants_et_filtres(terrain):
    identifiant = creer(terrain)
    rep = terrain["clients"]["CT"].get(
        f"{API}/journal/",
        {
            "date_debut": (aujourdhui() - timedelta(days=2)).isoformat(),
            "date_fin": aujourdhui().isoformat(),
            "projet": str(terrain["projet"].id),
        },
    )
    assert rep.status_code == 200, rep.data
    assert all(ligne["statut"] == "NON_SOUMIS" for ligne in rep.data["resultats"])
    assert all(ligne["note_chef_chantier"] is None for ligne in rep.data["resultats"])
    soumettre(terrain, identifiant)
    rep = terrain["clients"]["CT"].get(f"{API}/journal/")
    assert any(
        ligne["id"] == identifiant and ligne["statut"] == "SOUMIS"
        for ligne in rep.data["resultats"]
    )
    rep = terrain["clients"]["CC"].get(
        f"{API}/journal/", {"date_debut": "2026-10-08", "date_fin": "2026-10-07"}
    )
    assert rep.status_code == 400


def test_alerte_interne_idempotente(terrain):
    identifiant = creer(terrain)
    cc = terrain["clients"]["CC"]
    data = {
        "cle": "BLOCAGE",
        "type": "BLOCAGE_BLOQUANT",
        "description": "Travaux arrêtés pour raison de sécurité.",
    }
    rep = cc.post(f"{API}/rapports/{identifiant}/alertes/", data, format="json")
    assert rep.status_code == 200, rep.data
    assert rep.data["canal"] == "INTERNE"
    second = cc.post(f"{API}/rapports/{identifiant}/alertes/", data, format="json")
    assert second.data["envoyee_le"] == rep.data["envoyee_le"]
    assert AlerteJournal.objects.count() == 1
    assert set(AlerteJournal.objects.get().destinataires.values_list("id", flat=True)) == {
        terrain["CT"].id,
        terrain["CP"].id,
    }
    rep = terrain["clients"]["CT"].get(f"{API}/alertes/")
    assert rep.status_code == 200, rep.data
    assert rep.data["resultats"][0]["rapport_id"] == identifiant
    assert terrain["clients"]["CC"].get(f"{API}/alertes/").data["resultats"] == []


def test_production_et_masquage_financier(terrain):
    lot = Lot.objects.create(
        projet=terrain["projet"],
        code="ST-01",
        libelle="Tâcherons",
        mode_execution="SOUS_TRAITANCE_INFORMELLE",
    )
    activite = Activite.objects.create(lot=lot, libelle="Peinture", quantite_prevue=50, unite="M2")
    production = [
        {
            "intervenant": "Koné",
            "activite_id": str(activite.id),
            "quantite_jour": 5,
            "prix_unitaire": None,
        }
    ]
    identifiant = creer(terrain, corps(terrain, production=production))
    cc = terrain["clients"]["CC"]
    rep = cc.patch(
        f"{API}/rapports/{identifiant}/draft/",
        {"production": [{**production[0], "prix_unitaire": 5000}]},
        format="json",
    )
    assert rep.status_code == 400, rep.data
    journal = JournalChantier.objects.get(rapport_id=identifiant)
    # Tarif existant provenant d'une saisie financière autorisée.
    journal.saisie["production"][0]["prix_unitaire"] = 5000
    journal.save()
    rep = cc.patch(
        f"{API}/rapports/{identifiant}/draft/", {"production": production}, format="json"
    )
    assert rep.status_code == 200, rep.data
    assert rep.data["saisie"]["production"][0]["prix_unitaire"] is None
    journal.refresh_from_db()
    assert journal.saisie["production"][0]["prix_unitaire"] == 5000
    soumettre(terrain, identifiant)
    assert (
        terrain["clients"]["CT"]
        .get(f"{API}/rapports/{identifiant}/")
        .data["production"][0]["prix_unitaire"]
        is None
    )
    assert (
        terrain["clients"]["CP"]
        .get(f"{API}/rapports/{identifiant}/")
        .data["production"][0]["prix_unitaire"]
        == 5000
    )


def test_audit_signatures_conserve_rejet_et_resoumission(terrain):
    from apps.audit.models import JournalAudit

    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    ct = terrain["clients"]["CT"]
    rep = ct.post(
        f"{API}/rapports/{identifiant}/rejeter/",
        {"motif": "Les observations doivent préciser la zone."},
        format="json",
    )
    assert rep.status_code == 200, rep.data
    soumettre(terrain, identifiant)
    evenements = list(
        JournalAudit.objects.filter(type_entite="JournalChantier", entite_id=identifiant)
        .order_by("horodatage")
        .values_list("valeur_apres", flat=True)
    )
    assert [e["evenement"] for e in evenements] == [
        "BROUILLON_CREE",
        "SOUMISSION_CC",
        "REJET",
        "SOUMISSION_CC",
    ]
    assert evenements[2]["commentaire"] == "Les observations doivent préciser la zone."


def test_autre_redacteur_et_validation_sans_permission(terrain):
    autre = Utilisateur.objects.create_user(
        email=f"journal-autre-{uuid4().hex[:8]}@demo.ci",
        nom="Autre",
        role=Role.objects.get(code="CC"),
        role_global="CC",
        statut="ACTIF",
    )
    AffectationProjet.objects.create(projet=terrain["projet"], utilisateur=autre, role_projet="CC")
    client = APIClient(HTTP_HOST="demo.localhost")
    client.force_authenticate(user=autre)
    identifiant = creer(terrain)
    assert (
        client.patch(
            f"{API}/rapports/{identifiant}/draft/", {"note_cc": "Autre rédacteur"}, format="json"
        ).status_code
        == 404
    )
    soumettre(terrain, identifiant)
    assert (
        client.post(f"{API}/rapports/{identifiant}/soumettre/", {}, format="json").status_code
        == 403
    )
    assert (
        terrain["clients"]["VI"]
        .post(f"{API}/rapports/{identifiant}/valider/", {}, format="json")
        .status_code
        == 403
    )


def test_routes_historiques_ne_contournent_pas_le_circuit(terrain):
    identifiant = creer(terrain)
    soumettre(terrain, identifiant)
    rep = terrain["clients"]["CC"].patch(
        f"/api/v1/rapports/{identifiant}/", {"observations": "Contournement"}, format="json"
    )
    assert rep.status_code == 422
    rep = terrain["clients"]["CT"].post(
        f"/api/v1/rapports/{identifiant}/valider/", {}, format="json"
    )
    assert rep.status_code == 422
    assert RapportJournalier.objects.get(pk=identifiant).statut == "SOUMIS"
