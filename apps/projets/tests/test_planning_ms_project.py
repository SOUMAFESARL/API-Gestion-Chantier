"""Tests du planning enrichi et de l'import Microsoft Project (.xml) — Tâches 2.18 & 2.19."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.authentification import emettre_jetons
from apps.audit.models import JournalAudit
from apps.chantier.models import Blocage, RapportJournalier
from apps.core.contexte import contexte_entreprise, reinitialiser_contexte
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutActivite,
    StatutProjet,
    StatutUtilisateur,
)
from apps.projets.models import (
    AffectationEquipeElement,
    AffectationProjet,
    Avenant,
    Dependance,
    Element,
    EquipeChantier,
    MiseAJourInline,
    ModeMesure,
    NiveauProjet,
    Projet,
)
from apps.projets.services.ms_project import (
    TAILLE_MAX,
    ImportMsProjectBloque,
    RemplacementDecoupageRequis,
    analyser_ms_project,
    etat_import_ms_project,
    importer_ms_project,
)
from apps.stock.models import DemandeApprovisionnement

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _contexte_propre():
    reinitialiser_contexte()
    yield
    reinitialiser_contexte()


def _client_pour(utilisateur: Utilisateur) -> APIClient:
    jeton = emettre_jetons(utilisateur)["access"]
    client = APIClient(HTTP_HOST="localhost")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {jeton}")
    return client


def _fichier_xml(contenu: str | bytes, nom: str = "planning.xml") -> SimpleUploadedFile:
    donnees = contenu.encode("utf-8") if isinstance(contenu, str) else contenu
    return SimpleUploadedFile(nom, donnees, content_type="application/xml")


def _creer_projet(*, avec_dates: bool = True, statut: str = StatutProjet.EN_ATTENTE) -> Projet:
    return Projet.objects.create(
        reference=f"PRJ-{uuid.uuid4().hex[:6].upper()}",
        nom="Immeuble Plateau",
        ville="Abidjan",
        quartier="Plateau",
        statut=statut,
        date_debut_prevue=date(2026, 5, 1) if avec_dates else None,
        date_fin_prevue=date(2026, 8, 31) if avec_dates else None,
    )


def _creer_decoupage_non_demarre(projet: Projet) -> dict:
    niv1 = NiveauProjet.objects.create(projet=projet, ordre=1, libelle="Phase", alerter=True)
    niv2 = NiveauProjet.objects.create(projet=projet, ordre=2, libelle="Tâche", alerter=False)
    phase = Element.objects.create(
        projet=projet,
        niveau=niv1,
        libelle="Préparation",
        date_debut_prevue=date(2026, 5, 1),
        date_fin_prevue=date(2026, 5, 20),
        dates_calculees=True,
        ordre=1,
    )
    t1 = Element.objects.create(
        projet=projet,
        parent=phase,
        niveau=niv2,
        libelle="Installation",
        mode_mesure=ModeMesure.POURCENTAGE,
        date_debut_prevue=date(2026, 5, 1),
        date_fin_prevue=date(2026, 5, 10),
        ordre=1,
    )
    t2 = Element.objects.create(
        projet=projet,
        parent=phase,
        niveau=niv2,
        libelle="Implantation",
        mode_mesure=ModeMesure.JALON,
        date_debut_prevue=date(2026, 5, 11),
        date_fin_prevue=date(2026, 5, 20),
        ordre=2,
    )
    dep = Dependance.objects.create(projet=projet, predecesseur=t1, successeur=t2)
    return {"niv1": niv1, "niv2": niv2, "phase": phase, "t1": t1, "t2": t2, "dep": dep}


@pytest.fixture
def dg(entreprise_demo) -> Utilisateur:
    utilisateur = Utilisateur.objects.create_user(
        email=f"dg-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        prenom="Moussa",
        nom="Diallo",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        statut=StatutUtilisateur.ACTIF,
    )
    utilisateur.is_owner = True
    utilisateur.save(update_fields=["is_owner", "modifie_le"])
    return utilisateur


@pytest.fixture
def visiteur(entreprise_demo) -> Utilisateur:
    role_vi = Role.objects.filter(code=RoleGlobal.VISITEUR).first()
    return Utilisateur.objects.create_user(
        email=f"vi-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        prenom="Amina",
        nom="Koné",
        role_global=RoleGlobal.VISITEUR,
        role=role_vi,
        statut=StatutUtilisateur.ACTIF,
    )


XML_MS_PROJECT_NAMESPACE = """<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Title>Résidence Les Palmiers</Title>
  <StartDate>2026-06-01T08:00:00</StartDate>
  <FinishDate>2026-06-30T17:00:00</FinishDate>
  <MinutesPerDay>480</MinutesPerDay>
  <Tasks>
    <Task>
      <UID>0</UID>
      <ID>0</ID>
      <Name>Résidence Les Palmiers</Name>
      <OutlineLevel>0</OutlineLevel>
      <Start>2026-06-01T08:00:00</Start>
      <Finish>2026-06-30T17:00:00</Finish>
    </Task>
    <Task>
      <UID>999</UID>
      <ID>999</ID>
      <IsNull>1</IsNull>
    </Task>
    <Task>
      <UID>998</UID>
      <ID>998</ID>
      <Name>   </Name>
      <OutlineLevel>1</OutlineLevel>
    </Task>
    <Task>
      <UID>1</UID>
      <ID>1</ID>
      <Name>Gros œuvre</Name>
      <OutlineLevel>1</OutlineLevel>
      <OutlineNumber>1</OutlineNumber>
      <Start>2026-06-01T08:00:00</Start>
      <Finish>2026-06-20T17:00:00</Finish>
    </Task>
    <Task>
      <UID>2</UID>
      <ID>2</ID>
      <Name>Terrassement</Name>
      <OutlineLevel>2</OutlineLevel>
      <OutlineNumber>1.1</OutlineNumber>
      <Start>2026-06-01T08:00:00</Start>
      <Finish>2026-06-05T17:00:00</Finish>
      <Duration>PT40H0M0S</Duration>
      <Milestone>0</Milestone>
      <PercentComplete>25</PercentComplete>
    </Task>
    <Task>
      <UID>3</UID>
      <ID>3</ID>
      <Name>Fondations</Name>
      <OutlineLevel>2</OutlineLevel>
      <OutlineNumber>1.2</OutlineNumber>
      <Start>2026-06-08T08:00:00</Start>
      <Finish>2026-06-15T17:00:00</Finish>
      <Duration>PT48H30M0S</Duration>
      <Milestone>0</Milestone>
      <PercentComplete>0</PercentComplete>
      <PredecessorLink>
        <PredecessorUID>2</PredecessorUID>
        <Type>1</Type>
      </PredecessorLink>
    </Task>
    <Task>
      <UID>4</UID>
      <ID>4</ID>
      <Name>Réception fondations</Name>
      <OutlineLevel>2</OutlineLevel>
      <OutlineNumber>1.3</OutlineNumber>
      <Start>2026-06-16T08:00:00</Start>
      <Finish>2026-06-16T08:00:00</Finish>
      <Duration>PT0H0M0S</Duration>
      <Milestone>1</Milestone>
      <PredecessorLink>
        <PredecessorUID>3</PredecessorUID>
      </PredecessorLink>
    </Task>
  </Tasks>
</Project>
"""

XML_SANS_NAMESPACE_COMPLET = """<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Name>Projet Sans Namespace</Name>
  <Tasks>
    <Task>
      <UID>10</UID>
      <ID>1</ID>
      <Name>Phase A</Name>
      <OutlineLevel>1</OutlineLevel>
      <OutlineNumber>1</OutlineNumber>
    </Task>
    <Task>
      <UID>11</UID>
      <ID>2</ID>
      <Name>Électricité</Name>
      <OutlineLevel>2</OutlineLevel>
      <OutlineNumber>1.1</OutlineNumber>
      <Start>2026-07-01T08:00:00</Start>
      <Finish>2026-07-05T17:00:00</Finish>
      <Duration>PT32H0M0S</Duration>
    </Task>
    <Task>
      <UID>12</UID>
      <ID>3</ID>
      <Name>electricite</Name>
      <OutlineLevel>2</OutlineLevel>
      <OutlineNumber>1.2</OutlineNumber>
      <Start>2026-07-06T08:00:00</Start>
      <Finish>2026-07-10T17:00:00</Finish>
      <Duration>P4D</Duration>
      <PredecessorLink>
        <PredecessorUID>11</PredecessorUID>
        <Type>1</Type>
      </PredecessorLink>
    </Task>
    <Task>
      <UID>13</UID>
      <ID>4</ID>
      <Name>Électricité</Name>
      <OutlineLevel>2</OutlineLevel>
      <OutlineNumber>1.3</OutlineNumber>
      <Start>2026-07-11T08:00:00</Start>
      <Finish>2026-07-15T17:00:00</Finish>
      <PredecessorLink>
        <PredecessorUID>12</PredecessorUID>
        <Type>1</Type>
      </PredecessorLink>
    </Task>
  </Tasks>
</Project>
"""


# --------------------------------------------------------------------------
# 1. Analyseur XML (namespaces, sécurité XXE, doublons, jalons, dépendances)
# --------------------------------------------------------------------------
class TestAnalyseurMsProject:
    def test_parseur_avec_namespace_et_ignorer_racine_et_null(self, entreprise_demo):
        projet = _creer_projet(avec_dates=False)
        analyse = analyser_ms_project(projet, _fichier_xml(XML_MS_PROJECT_NAMESPACE))

        assert analyse["etat_import"] == {
            "autorise": True,
            "decoupage_existant": False,
            "remplacement_requis": False,
            "motif_blocage": None,
        }
        assert analyse["projet_xml"] == {
            "titre": "Résidence Les Palmiers",
            "date_debut": "2026-06-01",
            "date_fin": "2026-06-30",
        }
        assert len(analyse["niveaux"]) == 2
        assert [n["ordre"] for n in analyse["niveaux"]] == [1, 2]

        assert len(analyse["taches"]) == 1
        gros_oeuvre = analyse["taches"][0]
        assert gros_oeuvre["uid"] == "1"
        assert gros_oeuvre["libelle"] == "Gros œuvre"
        assert gros_oeuvre["est_feuille"] is False
        assert len(gros_oeuvre["enfants"]) == 3

        terrassement, fondations, jalon = gros_oeuvre["enfants"]
        assert terrassement["duree_heures"] == 40.0
        assert terrassement["pourcentage_xml"] == 25.0
        assert fondations["duree_heures"] == 48.5
        assert jalon["est_jalon"] is True
        assert jalon["est_feuille"] is True
        assert jalon["debut"] == "2026-06-16"
        assert jalon["fin"] == "2026-06-16"

        assert len(analyse["dependances"]) == 2
        assert analyse["dependances"][0] == {
            "predecesseur_uid": "2",
            "predecesseur_libelle": "Terrassement",
            "successeur_uid": "3",
            "successeur_libelle": "Fondations",
            "type": "FS",
            "respectee": True,
        }
        assert analyse["dependances"][1]["predecesseur_uid"] == "3"
        assert analyse["dependances"][1]["successeur_uid"] == "4"
        assert analyse["dependances"][1]["respectee"] is True

        assert analyse["statistiques"] == {
            "total_taches": 4,
            "feuilles": 3,
            "jalons": 1,
            "dependances_retenues": 2,
            "dependances_ignorees": 0,
        }
        assert Element.objects.filter(projet=projet).count() == 0

    def test_parseur_sans_namespace_et_deduplication_freres(self, entreprise_demo):
        projet = _creer_projet()
        analyse = analyser_ms_project(projet, _fichier_xml(XML_SANS_NAMESPACE_COMPLET))

        enfants = analyse["taches"][0]["enfants"]
        assert [e["libelle"] for e in enfants] == [
            "Électricité",
            "electricite (2)",
            "Électricité (3)",
        ]
        # Parent sans dates XML explicites -> hérite de l'enveloppe des enfants en aperçu
        assert analyse["taches"][0]["debut"] == "2026-07-01"
        assert analyse["taches"][0]["fin"] == "2026-07-15"
        assert enfants[1]["duree_heures"] == 32.0

        codes_warn = [w["code"] for w in analyse["avertissements"]]
        assert codes_warn.count("DOUBLON_FRERE") == 2

    @pytest.mark.parametrize(
        "xml_dangereux",
        [
            '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><Project></Project>',
            '<?xml version="1.0"?><!doctype project><Project></Project>',
            '<?xml version="1.0"?><!ENTITY test "abc"><Project></Project>',
        ],
    )
    def test_rejet_xxe_doctype_et_entity(self, entreprise_demo, xml_dangereux):
        projet = _creer_projet()
        with pytest.raises(ValidationError) as exc:
            analyser_ms_project(projet, _fichier_xml(xml_dangereux))
        assert "fichier" in exc.value.detail

    def test_rejet_extension_et_taille_max(self, entreprise_demo):
        projet = _creer_projet()
        with pytest.raises(ValidationError):
            analyser_ms_project(projet, _fichier_xml("<Project/>", nom="planning.csv"))

        gros_fichier = SimpleUploadedFile("gros.xml", b"a" * (TAILLE_MAX + 1))
        with pytest.raises(ValidationError):
            analyser_ms_project(projet, gros_fichier)

    def test_filtrage_dependances_non_fs_parent_cycle_uid_inconnu(self, entreprise_demo):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <Project>
          <Tasks>
            <Task>
              <UID>1</UID><ID>1</ID><Name>Phase Parent</Name><OutlineLevel>1</OutlineLevel>
            </Task>
            <Task>
              <UID>2</UID><ID>2</ID><Name>Tâche A</Name><OutlineLevel>2</OutlineLevel>
              <Start>2026-06-01T08:00:00</Start><Finish>2026-06-05T17:00:00</Finish>
              <PredecessorLink><PredecessorUID>999</PredecessorUID><Type>1</Type></PredecessorLink>
              <PredecessorLink><PredecessorUID>1</PredecessorUID><Type>1</Type></PredecessorLink>
            </Task>
            <Task>
              <UID>3</UID><ID>3</ID><Name>Tâche B</Name><OutlineLevel>2</OutlineLevel>
              <Start>2026-06-06T08:00:00</Start><Finish>2026-06-10T17:00:00</Finish>
              <PredecessorLink><PredecessorUID>2</PredecessorUID><Type>1</Type></PredecessorLink>
              <PredecessorLink><PredecessorUID>2</PredecessorUID><Type>3</Type></PredecessorLink>
              <PredecessorLink><PredecessorUID>2</PredecessorUID><Type>0</Type></PredecessorLink>
              <PredecessorLink><PredecessorUID>2</PredecessorUID><Type>2</Type></PredecessorLink>
            </Task>
            <Task>
              <UID>4</UID><ID>4</ID><Name>Tâche C</Name><OutlineLevel>2</OutlineLevel>
              <Start>2026-06-09T08:00:00</Start><Finish>2026-06-15T17:00:00</Finish>
              <PredecessorLink><PredecessorUID>3</PredecessorUID><Type>1</Type></PredecessorLink>
            </Task>
            <Task>
              <UID>5</UID><ID>5</ID><Name>Tâche Cycle</Name><OutlineLevel>2</OutlineLevel>
              <Start>2026-06-16T08:00:00</Start><Finish>2026-06-20T17:00:00</Finish>
              <PredecessorLink><PredecessorUID>4</PredecessorUID><Type>1</Type></PredecessorLink>
            </Task>
          </Tasks>
        </Project>
        """
        # Ajout d'un cycle direct 2 -> 3 -> 4 et 4 -> 2 en plaçant le lien sur Tâche A
        xml_cycle = xml.replace(
            "<PredecessorLink><PredecessorUID>1</PredecessorUID><Type>1</Type></PredecessorLink>",
            "<PredecessorLink><PredecessorUID>1</PredecessorUID><Type>1</Type></PredecessorLink>"
            "<PredecessorLink><PredecessorUID>4</PredecessorUID><Type>1</Type></PredecessorLink>",
        )
        projet = _creer_projet()
        analyse = analyser_ms_project(projet, _fichier_xml(xml_cycle))

        # Liens traités dans l'ordre du fichier :
        # - 999 -> 2 : UID inconnu (ignoré)
        # - 1 -> 2 : parent (ignoré)
        # - 4 -> 2 : retenu (FS, respectee=False car 2026-06-01 <= 2026-06-15)
        # - 2 -> 3 : retenu (FS, respectee=True)
        # - 2 -> 3 (SS/FF/SF) : 3 liens ignorés
        # - 3 -> 4 : boucle 4 -> 2 -> 3 -> 4 (ignoré !)
        # - 4 -> 5 : retenu (FS, respectee=True)
        paires = [(d["predecesseur_uid"], d["successeur_uid"]) for d in analyse["dependances"]]
        assert ("4", "2") in paires
        assert ("2", "3") in paires
        assert ("4", "5") in paires
        assert ("3", "4") not in paires

        dep_4_2 = next(
            d
            for d in analyse["dependances"]
            if d["predecesseur_uid"] == "4" and d["successeur_uid"] == "2"
        )
        assert dep_4_2["respectee"] is False

        assert analyse["statistiques"]["dependances_retenues"] == 3
        assert analyse["statistiques"]["dependances_ignorees"] == 6
        codes = {w["code"] for w in analyse["avertissements"]}
        assert {
            "DEPENDANCE_UID_INCONNU",
            "DEPENDANCE_PARENT_IGNOREE",
            "DEPENDANCE_TYPE_NON_SUPPORTE",
            "DEPENDANCE_CYCLE",
        }.issubset(codes)

    def test_niveaux_dynamiques_profondeur_superieure_au_modele(self, entreprise_demo):
        xml_profond = """<?xml version="1.0" encoding="UTF-8"?>
        <Project>
          <Tasks>
            <Task><UID>1</UID><ID>1</ID><Name>N1</Name><OutlineLevel>1</OutlineLevel></Task>
            <Task><UID>2</UID><ID>2</ID><Name>N2</Name><OutlineLevel>2</OutlineLevel></Task>
            <Task><UID>3</UID><ID>3</ID><Name>N3</Name><OutlineLevel>3</OutlineLevel></Task>
            <Task><UID>4</UID><ID>4</ID><Name>N4</Name><OutlineLevel>4</OutlineLevel></Task>
            <Task><UID>5</UID><ID>5</ID><Name>N5</Name><OutlineLevel>5</OutlineLevel></Task>
          </Tasks>
        </Project>
        """
        projet = _creer_projet()
        analyse = analyser_ms_project(projet, _fichier_xml(xml_profond))

        assert [n["ordre"] for n in analyse["niveaux"]] == [1, 2, 3, 4, 5]
        assert analyse["niveaux"][4]["libelle"] == "Niveau 5"


# --------------------------------------------------------------------------
# 2. Import transactionnel (vierge, remplacement soft-delete, blocages)
# --------------------------------------------------------------------------
class TestImportMsProjectService:
    def test_import_projet_vierge_et_calage_dates_projet(self, entreprise_demo, dg):
        projet = _creer_projet(avec_dates=False)
        res = importer_ms_project(projet, _fichier_xml(XML_MS_PROJECT_NAMESPACE), auteur=dg)

        assert res["elements_crees"] == 4
        assert res["niveaux_crees"] == 2
        assert res["dependances_creees"] == 2
        assert res["remplacement_effectue"] is False

        projet.refresh_from_db()
        assert projet.date_debut_prevue == date(2026, 6, 1)
        assert projet.date_fin_prevue == date(2026, 6, 20)
        assert projet.date_debut_baseline == date(2026, 6, 1)
        assert projet.date_fin_baseline == date(2026, 6, 20)

        niveaux = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
        assert len(niveaux) == 2
        assert niveaux[0].alerter is True
        assert niveaux[1].alerter is False

        parent = Element.objects.get(projet=projet, libelle="Gros œuvre")
        assert parent.dates_calculees is True
        assert parent.date_debut_prevue == date(2026, 6, 1)
        assert parent.date_fin_prevue == date(2026, 6, 16)
        assert parent.code == "1"

        jalon = Element.objects.get(projet=projet, libelle="Réception fondations")
        assert jalon.mode_mesure == ModeMesure.JALON
        assert jalon.code == "1.3"

        terrassement = Element.objects.get(projet=projet, libelle="Terrassement")
        assert terrassement.mode_mesure == ModeMesure.POURCENTAGE
        assert terrassement.pourcentage_declare is None

        assert Dependance.objects.filter(projet=projet).count() == 2
        assert JournalAudit.objects.filter(
            type_entite="DecoupageProjet",
            entite_id=projet.pk,
        ).exists()

        # Juste après l'import (rien démarré), un nouvel import reste autorisé avec remplacement
        etat_apres = etat_import_ms_project(projet)
        assert etat_apres == {
            "autorise": True,
            "decoupage_existant": True,
            "remplacement_requis": True,
            "motif_blocage": None,
        }

    def test_remplacement_non_demarre_exige_confirmation_et_soft_delete(self, entreprise_demo, dg):
        projet = _creer_projet(avec_dates=True)
        ancien = _creer_decoupage_non_demarre(projet)

        assert etat_import_ms_project(projet) == {
            "autorise": True,
            "decoupage_existant": True,
            "remplacement_requis": True,
            "motif_blocage": None,
        }

        # Sans confirmation -> RemplacementDecoupageRequis, rien modifié
        with pytest.raises(RemplacementDecoupageRequis) as exc:
            importer_ms_project(
                projet,
                _fichier_xml(XML_MS_PROJECT_NAMESPACE),
                auteur=dg,
                confirmer_remplacement=False,
            )
        assert exc.value.code_metier == "remplacement_decoupage_requis"
        assert Element.objects.filter(projet=projet).count() == 3

        # Avec confirmation -> remplacement avec suppression LOGIQUE uniquement
        res = importer_ms_project(
            projet,
            _fichier_xml(XML_MS_PROJECT_NAMESPACE),
            auteur=dg,
            confirmer_remplacement=True,
        )
        assert res["remplacement_effectue"] is True
        assert res["elements_crees"] == 4

        # Anciennes dates du projet conservées (car déjà renseignées)
        projet.refresh_from_db()
        assert projet.date_debut_prevue == date(2026, 5, 1)
        assert projet.date_fin_prevue == date(2026, 8, 31)

        # Vérification stricte de la suppression logique (aucune suppression physique !)
        for modele, pk in (
            (Dependance, ancien["dep"].pk),
            (Element, ancien["phase"].pk),
            (Element, ancien["t1"].pk),
            (Element, ancien["t2"].pk),
            (NiveauProjet, ancien["niv1"].pk),
            (NiveauProjet, ancien["niv2"].pk),
        ):
            assert not modele.objects.filter(pk=pk).exists()
            archive = modele.tous_objets.get(pk=pk)
            assert archive.supprime_le is not None
            assert archive.supprime_par_id == dg.pk

    def test_blocage_strict_sur_chaque_signal_de_demarrage(self, entreprise_demo, dg):
        # 1. quantite_realisee > 0
        p1 = _creer_projet()
        d1 = _creer_decoupage_non_demarre(p1)
        Element.objects.filter(pk=d1["t1"].pk).update(quantite_realisee=Decimal("1.500"))
        assert etat_import_ms_project(p1)["autorise"] is False

        # 2. pourcentage_declare > 0
        p2 = _creer_projet()
        d2 = _creer_decoupage_non_demarre(p2)
        Element.objects.filter(pk=d2["t1"].pk).update(pourcentage_declare=Decimal("10.00"))
        assert etat_import_ms_project(p2)["autorise"] is False

        # 3. avancement > 0
        p3 = _creer_projet()
        d3 = _creer_decoupage_non_demarre(p3)
        Element.objects.filter(pk=d3["t1"].pk).update(avancement=Decimal("5.00"))
        assert etat_import_ms_project(p3)["autorise"] is False

        # 4. cloture = True
        p4 = _creer_projet()
        d4 = _creer_decoupage_non_demarre(p4)
        Element.objects.filter(pk=d4["t2"].pk).update(cloture=True)
        assert etat_import_ms_project(p4)["autorise"] is False

        # 5. date_debut_reelle / date_fin_reelle
        p5 = _creer_projet()
        d5 = _creer_decoupage_non_demarre(p5)
        Element.objects.filter(pk=d5["t1"].pk).update(date_debut_reelle=date(2026, 5, 2))
        assert etat_import_ms_project(p5)["autorise"] is False

        # 6. statut != PLANIFIE
        p6 = _creer_projet()
        d6 = _creer_decoupage_non_demarre(p6)
        Element.objects.filter(pk=d6["t1"].pk).update(statut=StatutActivite.EN_COURS)
        etat6 = etat_import_ms_project(p6)
        assert etat6["autorise"] is False
        assert etat6["motif_blocage"] is not None
        with pytest.raises(ImportMsProjectBloque) as exc:
            importer_ms_project(
                p6, _fichier_xml(XML_MS_PROJECT_NAMESPACE), auteur=dg, confirmer_remplacement=True
            )
        assert exc.value.code_metier == "import_ms_project_bloque"

        # 7. MiseAJourInline
        p7 = _creer_projet()
        d7 = _creer_decoupage_non_demarre(p7)
        MiseAJourInline.objects.create(
            element=d7["t1"],
            auteur=dg,
            quantite_avant=Decimal("0"),
            quantite_apres=Decimal("0"),
            avancement_avant=Decimal("0"),
            avancement_apres=Decimal("0"),
            commentaire="Pointage initial",
        )
        assert etat_import_ms_project(p7)["autorise"] is False

        # 8. Blocage sur un élément vs blocage global projet
        p8 = _creer_projet()
        d8 = _creer_decoupage_non_demarre(p8)
        Blocage.objects.create(
            projet=p8, element=None, titre="Blocage administratif", ouvert_par=dg
        )
        assert etat_import_ms_project(p8)["autorise"] is True
        Blocage.objects.create(projet=p8, element=d8["t1"], titre="Panne grue", ouvert_par=dg)
        assert etat_import_ms_project(p8)["autorise"] is False

        # 9. RapportJournalier
        p9 = _creer_projet()
        _creer_decoupage_non_demarre(p9)
        RapportJournalier.objects.create(projet=p9, auteur=dg, date_rapport=date(2026, 5, 2))
        assert etat_import_ms_project(p9)["autorise"] is False

        # 10. Avenant lié à un élément vs avenant projet global
        p10 = _creer_projet()
        d10 = _creer_decoupage_non_demarre(p10)
        av_global = Avenant.objects.create(
            projet=p10, numero="AV-01", date_signature=date(2026, 5, 1), objet="Délai global"
        )
        assert etat_import_ms_project(p10)["autorise"] is True
        av_global.elements.add(d10["t1"])
        assert etat_import_ms_project(p10)["autorise"] is False

        # 11. AffectationEquipeElement
        p11 = _creer_projet()
        d11 = _creer_decoupage_non_demarre(p11)
        equipe = EquipeChantier.objects.create(projet=p11, nom="Équipe Maçonnerie")
        AffectationEquipeElement.objects.create(equipe=equipe, element=d11["t1"])
        assert etat_import_ms_project(p11)["autorise"] is False

        # 12. Stock lié à un élément (DemandeApprovisionnement)
        p12 = _creer_projet()
        d12 = _creer_decoupage_non_demarre(p12)
        DemandeApprovisionnement.objects.create(
            reference=f"DA-{uuid.uuid4().hex[:6]}",
            projet=p12,
            lot=d12["t1"],
            emetteur=dg,
        )
        assert etat_import_ms_project(p12)["autorise"] is False


# --------------------------------------------------------------------------
# 3. Routes HTTP : GET /planning/, POST analyser, POST importer
# --------------------------------------------------------------------------
class TestRoutesPlanningMsProject:
    def test_get_planning_enrichi_retrocompatible(self, entreprise_demo, dg):
        projet = _creer_projet(avec_dates=True)
        _creer_decoupage_non_demarre(projet)

        client = _client_pour(dg)
        reponse = client.get(f"/api/v1/projets/{projet.pk}/planning/")
        assert reponse.status_code == 200
        corps = reponse.json()

        assert "aujourdhui" in corps
        assert corps["projet_debut"] == "2026-05-01"
        assert corps["projet_fin"] == "2026-08-31"
        assert corps["import_ms_project"] == {
            "autorise": True,
            "decoupage_existant": True,
            "remplacement_requis": True,
            "motif_blocage": None,
        }

        assert len(corps["cases"]) == 1
        phase = corps["cases"][0]
        assert phase["libelle"] == "Préparation"
        assert phase["est_feuille"] is False
        assert phase["debut_prevu"] == "2026-05-01"
        assert phase["fin_prevue"] == "2026-05-20"
        assert phase["debut_baseline"] == "2026-05-01"
        assert phase["fin_baseline"] == "2026-05-20"
        assert phase["mode_mesure"] == ModeMesure.QUANTITE

        t1, t2 = phase["enfants"]
        assert t1["est_feuille"] is True
        assert t1["mode_mesure"] == ModeMesure.POURCENTAGE
        assert t2["est_feuille"] is True
        assert t2["mode_mesure"] == ModeMesure.JALON
        assert len(corps["dependances"]) == 1
        assert corps["dependances"][0]["respectee"] is True

    def test_parcours_http_analyser_puis_importer_et_blocage_422(self, entreprise_demo, dg):
        projet = _creer_projet(avec_dates=False)
        client = _client_pour(dg)

        # 1. Analyse sans écriture
        rep_analyse = client.post(
            f"/api/v1/projets/{projet.pk}/planning/ms-project/analyser/",
            {"fichier": _fichier_xml(XML_MS_PROJECT_NAMESPACE)},
            format="multipart",
        )
        assert rep_analyse.status_code == 200
        data_analyse = rep_analyse.json()
        assert data_analyse["statistiques"]["total_taches"] == 4
        assert data_analyse["statistiques"]["jalons"] == 1
        assert data_analyse["etat_import"]["remplacement_requis"] is False

        # 2. Import initial -> 201 + planning enrichi
        rep_import = client.post(
            f"/api/v1/projets/{projet.pk}/planning/ms-project/importer/",
            {"fichier": _fichier_xml(XML_MS_PROJECT_NAMESPACE)},
            format="multipart",
        )
        assert rep_import.status_code == 201
        data_import = rep_import.json()
        assert data_import["elements_crees"] == 4
        assert data_import["niveaux_crees"] == 2
        assert data_import["dependances_creees"] == 2
        assert data_import["remplacement_effectue"] is False
        assert data_import["planning"]["projet_debut"] == "2026-06-01"
        assert data_import["planning"]["projet_fin"] == "2026-06-20"
        assert len(data_import["planning"]["cases"]) == 1
        assert len(data_import["planning"]["dependances"]) == 2

        # 3. Second import sans confirmation -> 422 remplacement_decoupage_requis
        rep_sans_conf = client.post(
            f"/api/v1/projets/{projet.pk}/planning/ms-project/importer/",
            {
                "fichier": _fichier_xml(XML_SANS_NAMESPACE_COMPLET),
                "confirmer_remplacement": "false",
            },
            format="multipart",
        )
        assert rep_sans_conf.status_code == 422
        assert rep_sans_conf.json()["erreur"]["code"] == "remplacement_decoupage_requis"

        # 4. Second import avec confirmation -> 201 + remplacement effectué
        rep_avec_conf = client.post(
            f"/api/v1/projets/{projet.pk}/planning/ms-project/importer/",
            {
                "fichier": _fichier_xml(XML_SANS_NAMESPACE_COMPLET),
                "confirmer_remplacement": "true",
            },
            format="multipart",
        )
        assert rep_avec_conf.status_code == 201
        assert rep_avec_conf.json()["remplacement_effectue"] is True
        assert rep_avec_conf.json()["elements_crees"] == 4

        # 5. Démarrage d'un rapport journalier -> 422 import_ms_project_bloque
        with contexte_entreprise(entreprise_demo):
            RapportJournalier.objects.create(
                projet=projet, auteur=dg, date_rapport=date(2026, 7, 2)
            )

        rep_bloque = client.post(
            f"/api/v1/projets/{projet.pk}/planning/ms-project/importer/",
            {
                "fichier": _fichier_xml(XML_MS_PROJECT_NAMESPACE),
                "confirmer_remplacement": "true",
            },
            format="multipart",
        )
        assert rep_bloque.status_code == 422
        assert rep_bloque.json()["erreur"]["code"] == "import_ms_project_bloque"

    def test_permissions_visiteur_refuse_et_projet_clos_refuse(
        self, entreprise_demo, dg, visiteur
    ):
        projet = _creer_projet()
        AffectationProjet.objects.create(
            projet=projet,
            utilisateur=visiteur,
            role_projet=RoleProjet.VISITEUR,
            est_actif=True,
        )

        client_vi = _client_pour(visiteur)
        assert (
            client_vi.post(
                f"/api/v1/projets/{projet.pk}/planning/ms-project/analyser/",
                {"fichier": _fichier_xml(XML_MS_PROJECT_NAMESPACE)},
                format="multipart",
            ).status_code
            == 403
        )
        assert (
            client_vi.post(
                f"/api/v1/projets/{projet.pk}/planning/ms-project/importer/",
                {"fichier": _fichier_xml(XML_MS_PROJECT_NAMESPACE)},
                format="multipart",
            ).status_code
            == 403
        )

        # Projet clos -> 409 sur import
        with contexte_entreprise(entreprise_demo):
            projet_clos = _creer_projet(statut=StatutProjet.ARCHIVE)
        client_dg = _client_pour(dg)
        rep_clos = client_dg.post(
            f"/api/v1/projets/{projet_clos.pk}/planning/ms-project/importer/",
            {"fichier": _fichier_xml(XML_MS_PROJECT_NAMESPACE)},
            format="multipart",
        )
        assert rep_clos.status_code == 409
