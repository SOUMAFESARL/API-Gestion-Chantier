"""Tests de la refonte du journal de chantier et de sa synthèse périodique."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.models import Role, RoleModulePermission, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.catalogue.models import CataloguePermission
from apps.chantier.models import Blocage, JournalChantier, RapportJournalier
from apps.chantier.selectors.journal import document, preparation
from apps.chantier.selectors.synthese import calculer as calculer_synthese
from apps.chantier.selectors.synthese import projection as projection_synthese
from apps.chantier.services.journal import (
    RapportIncomplet,
    creer_journal,
    jours_saisissables_ouvres,
    modifier_journal,
    rejeter_journal,
    signer_journal,
    soumettre_journal,
    statut_journal,
)
from apps.chantier.services.synthese import approuver_synthese, soumettre_synthese
from apps.core.enums import (
    ModeExecution,
    RoleGlobal,
    RoleProjet,
    SeveriteBlocage,
    StatutProjet,
    StatutRapport,
    StatutUtilisateur,
)
from apps.core.exceptions import ErreurMetier
from apps.projets.models import (
    AffectationEquipeElement,
    AffectationProjet,
    Element,
    EquipeChantier,
    MembreEquipeChantier,
    ModeMesure,
    NiveauProjet,
    PersonneMainOeuvre,
    Projet,
)
from apps.projets.services.avancement import synchroniser_rapport_approuve
from apps.projets.services.meteo import meteo_suggeree_journal


def _creer_utilisateur(email: str, prenom: str, nom: str, role_code: str) -> Utilisateur:
    role = Role.objects.filter(code__iexact=role_code, supprime_le__isnull=True).first()
    return Utilisateur.objects.create_user(
        email=email,
        password="TestPassword123!",
        prenom=prenom,
        nom=nom,
        role_global=role_code,
        role=role,
        statut=StatutUtilisateur.ACTIF,
    )


@pytest.fixture
def contexte_chantier(db, schema_demo):
    """Chantier complet avec arbre à 2 niveaux, 3 feuilles (3 modes de mesure) et 2 équipes."""
    initialiser_roles_par_defaut()
    cp = _creer_utilisateur(
        f"cp-{uuid.uuid4().hex[:6]}@demo.ci", "Awa", "Koné", RoleGlobal.CHEF_PROJET
    )
    ct = _creer_utilisateur(
        f"ct-{uuid.uuid4().hex[:6]}@demo.ci", "Moussa", "Traoré", RoleGlobal.CONDUCTEUR_TRAVAUX
    )
    cc = _creer_utilisateur(
        f"cc-{uuid.uuid4().hex[:6]}@demo.ci", "Kouadio", "Yao", RoleGlobal.CHEF_CHANTIER
    )

    projet = Projet.objects.create(
        reference=f"PRJ-{uuid.uuid4().hex[:4].upper()}",
        nom="Résidence Cocody",
        ville="Abidjan",
        quartier="Riviera",
        statut=StatutProjet.EN_COURS,
        budget_initial_montant=10_000_000_00,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
        chef_projet=cp,
        conducteur_travaux=ct,
    )
    # Reculer cree_le pour autoriser les tests sur octobre 2026
    Projet.objects.filter(pk=projet.pk).update(
        cree_le=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Africa/Abidjan"))
    )
    projet.refresh_from_db()

    debut_aff = date(2026, 10, 1)
    AffectationProjet.objects.create(
        projet=projet, utilisateur=cp, role_projet=RoleProjet.CHEF_PROJET, date_debut=debut_aff
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=ct,
        role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
        date_debut=debut_aff,
    )
    AffectationProjet.objects.create(
        projet=projet, utilisateur=cc, role_projet=RoleProjet.CHEF_CHANTIER, date_debut=debut_aff
    )

    niv_lot = NiveauProjet.objects.create(projet=projet, ordre=1, libelle="Lot", alerter=True)
    niv_tache = NiveauProjet.objects.create(projet=projet, ordre=2, libelle="Tâche", alerter=False)

    lot = Element.objects.create(
        projet=projet,
        niveau=niv_lot,
        libelle="Gros œuvre",
        mode_execution=ModeExecution.REGIE,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    f_qte = Element.objects.create(
        projet=projet,
        parent=lot,
        niveau=niv_tache,
        libelle="Fouilles en rigoles",
        mode_mesure=ModeMesure.QUANTITE,
        unite="m3",
        quantite_prevue=Decimal("100.000"),
        montant=5_000_000_00,
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 11, 30),
    )
    f_pct = Element.objects.create(
        projet=projet,
        parent=lot,
        niveau=niv_tache,
        libelle="Ferraillage semelles",
        mode_mesure=ModeMesure.POURCENTAGE,
        montant=3_000_000_00,
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 11, 30),
    )
    f_jalon = Element.objects.create(
        projet=projet,
        parent=lot,
        niveau=niv_tache,
        libelle="Validation implantation géomètre",
        mode_mesure=ModeMesure.JALON,
        montant=2_000_000_00,
        date_debut_prevue=date(2026, 11, 15),  # Future -> non attendue le 26/10
        date_fin_prevue=date(2026, 11, 20),
    )

    p1 = PersonneMainOeuvre.objects.create(prenom="Bakary", nom="Coulibaly", metier="Maçon")
    p2 = PersonneMainOeuvre.objects.create(prenom="Seydou", nom="Bamba", metier="Ferrailleur")

    eq_macons = EquipeChantier.objects.create(projet=projet, nom="Équipe Maçonnerie")
    MembreEquipeChantier.objects.create(
        equipe=eq_macons, personne=p1, fonction="CHEF_EQUIPE", est_chef=True, date_arrivee=debut_aff
    )
    AffectationEquipeElement.objects.create(equipe=eq_macons, element=lot)

    eq_inutilisee = EquipeChantier.objects.create(projet=projet, nom="Équipe Finitions")
    MembreEquipeChantier.objects.create(
        equipe=eq_inutilisee, personne=p2, fonction="OUVRIER", est_chef=True, date_arrivee=debut_aff
    )

    return {
        "projet": projet,
        "cp": cp,
        "ct": ct,
        "cc": cc,
        "niv_tache": niv_tache,
        "lot": lot,
        "f_qte": f_qte,
        "f_pct": f_pct,
        "f_jalon": f_jalon,
        "eq_macons": eq_macons,
        "eq_inutilisee": eq_inutilisee,
        "p1": p1,
        "p2": p2,
    }


@pytest.mark.tenant
def test_calendrier_ouvre_et_fenetre_lundi_accepte_vendredi(contexte_chantier):
    """Un lundi ouvré, la fenêtre de 3 jours ouvrés inclut jeudi et vendredi et refuse dimanche."""
    projet = contexte_chantier["projet"]
    cc = contexte_chantier["cc"]
    lundi = date(2026, 10, 26)
    dimanche = date(2026, 10, 25)
    vendredi = date(2026, 10, 23)

    with patch("apps.chantier.services.journal.aujourdhui", return_value=lundi):
        fenetre = jours_saisissables_ouvres(lundi)
        assert fenetre == [date(2026, 10, 22), vendredi, lundi]

        with pytest.raises(ErreurMetier) as exc_dim:
            creer_journal(projet=projet, utilisateur=cc, jour=dimanche, data={})
        assert exc_dim.value.details == {"date": "jour_non_ouvre"}

        # Vendredi (J-3 calendaire mais J-1 ouvré) passe sans erreur !
        journal_ven = creer_journal(projet=projet, utilisateur=cc, jour=vendredi, data={})
        assert journal_ven.rapport.date_rapport == vendredi


@pytest.mark.tenant
def test_preparation_exclut_suspendues_et_marque_attendues_ce_jour(contexte_chantier):
    projet = contexte_chantier["projet"]
    cc = contexte_chantier["cc"]
    lundi = date(2026, 10, 26)
    f_suspendue = Element.objects.create(
        projet=projet,
        parent=contexte_chantier["lot"],
        niveau=contexte_chantier["niv_tache"],
        libelle="Voile suspendu",
        mode_mesure=ModeMesure.QUANTITE,
        unite="m2",
        quantite_prevue=Decimal("50.000"),
        suspendu=True,
    )

    with (
        patch("apps.chantier.services.journal.aujourdhui", return_value=lundi),
        patch("apps.chantier.selectors.journal.aujourdhui", return_value=lundi),
        patch("apps.chantier.selectors.journal.meteo_suggeree_journal", return_value=None),
    ):
        prep = preparation(projet, lundi, utilisateur=cc)
        ids = {a["activite_id"]: a for a in prep["activites"]}
        assert str(f_suspendue.id) not in ids
        assert ids[str(contexte_chantier["f_qte"].id)]["attendue_ce_jour"] is True
        assert ids[str(contexte_chantier["f_pct"].id)]["attendue_ce_jour"] is True
        # Prévue en novembre et non commencée -> non attendue ce jour, mais disponible dans l'arbre
        assert ids[str(contexte_chantier["f_jalon"].id)]["attendue_ce_jour"] is False


@pytest.mark.tenant
def test_garde_fou_equipe_a3_et_trois_modes_mesure_f3(contexte_chantier):
    """Vérifie le garde-fou A3, le circuit sans _CT/_CP et la synchronisation F3 des 3 modes."""
    c = contexte_chantier
    lundi = date(2026, 10, 26)

    with patch("apps.chantier.services.journal.aujourdhui", return_value=lundi):
        journal = creer_journal(projet=c["projet"], utilisateur=c["cc"], jour=lundi, data={})

        # 1) Avancement sans équipe rattachée -> refusé à la soumission
        saisie_sans_eq = {
            "heure_debut": "07:30",
            "heure_fin": "17:00",
            "meteo": {"matin": "ENSOLEILLE", "apres_midi": "NUAGEUX", "conditions": "FAVORABLES"},
            "activites": [
                {
                    "activite_id": str(c["f_qte"].id),
                    "equipe_ids": [],
                    "quantite_jour": 25,
                }
            ],
            "note_redacteur": "Avancement normal sur les fouilles en rigoles.",
        }
        with pytest.raises(RapportIncomplet) as exc_eq:
            soumettre_journal(journal=journal, utilisateur=c["cc"], data=saisie_sans_eq)
        assert "activites" in exc_eq.value.details

        # 2) Avec équipe rattachée et présente (> 0 h), l'autre équipe inutilisée ne bloque pas !
        saisie_valide = {
            **saisie_sans_eq,
            "equipes": [
                {
                    "equipe_id": str(c["eq_macons"].id),
                    "presents": [str(c["p1"].id)],
                    "retards": [],
                    "heures": 8,
                }
            ],
            "activites": [
                {
                    "activite_id": str(c["f_qte"].id),
                    "equipe_ids": [str(c["eq_macons"].id)],
                    "quantite_jour": 40,
                },
                {
                    "activite_id": str(c["f_pct"].id),
                    "equipe_ids": [str(c["eq_macons"].id)],
                    "pourcentage_jour": 50,
                },
                {
                    "activite_id": str(c["f_jalon"].id),
                    "equipe_ids": [str(c["eq_macons"].id)],
                    "jalon_atteint": True,
                },
            ],
        }
        journal = soumettre_journal(journal=journal, utilisateur=c["cc"], data=saisie_valide)
        assert statut_journal(journal) == "SOUMIS"

        journal = signer_journal(
            journal=journal, utilisateur=c["ct"], etape="VALIDATION", commentaire="Vérifié terrain"
        )
        assert statut_journal(journal) == "VALIDE"

        journal = signer_journal(
            journal=journal, utilisateur=c["cp"], etape="APPROBATION", commentaire="Approuvé"
        )
        assert statut_journal(journal) == "APPROUVE"

        # Synchronisation F3 (normalement déclenchée sur transaction.on_commit)
        assert synchroniser_rapport_approuve(journal.rapport_id) is True

        c["f_qte"].refresh_from_db()
        c["f_pct"].refresh_from_db()
        c["f_jalon"].refresh_from_db()
        c["lot"].refresh_from_db()
        c["projet"].refresh_from_db()

        assert c["f_qte"].quantite_realisee == Decimal("40.000")
        assert c["f_qte"].date_debut_reelle == lundi
        assert c["f_pct"].pourcentage_declare == Decimal("50.00")
        assert c["f_jalon"].cloture is True
        assert c["f_jalon"].date_fin_reelle == lundi

        # Pondération par montant : (40% * 5M + 50% * 3M + 100% * 2M) / 10M = 55.00 %
        assert c["lot"].avancement == Decimal("55.00")
        assert c["projet"].avancement_reel == Decimal("55.00")


@pytest.mark.tenant
def test_piege_rejet_hors_fenetre_et_deduplication_blocage(contexte_chantier):
    """Un rapport rejeté reste modifiable après J-2 et ne duplique pas ses lignes Blocage."""
    c = contexte_chantier
    jour_initial = date(2026, 10, 15)
    dix_jours_apres = date(2026, 10, 27)

    with patch("apps.chantier.services.journal.aujourdhui", return_value=jour_initial):
        journal = creer_journal(projet=c["projet"], utilisateur=c["cc"], jour=jour_initial, data={})
        saisie_arret_avec_blocage = {
            "arret": {"motif": "RUPTURE_APPROVISIONNEMENT", "precision": ""},
            "meteo": {"matin": "PLUVIEUX", "apres_midi": "PLUVIEUX", "conditions": "ARRET"},
            "blocages": [
                {
                    "cle": "blc-1",
                    "element_id": str(c["f_qte"].id),
                    "titre": "Rupture ciment CPJ 42.5",
                    "niveau": "BLOQUANT",
                    "nature": "APPROVISIONNEMENT",
                    "description": (
                        "Aucun sac de ciment disponible sur le chantier depuis ce matin."
                    ),
                    "impact": "Arrêt complet du bétonnage des semelles.",
                }
            ],
            "note_redacteur": "Journée d'arrêt mais preuves et blocage transmis.",
        }
        journal = soumettre_journal(
            journal=journal, utilisateur=c["cc"], data=saisie_arret_avec_blocage
        )

    assert Blocage.objects.filter(projet=c["projet"]).count() == 1
    premier_blocage = Blocage.objects.get(projet=c["projet"])
    assert premier_blocage.severite == SeveriteBlocage.CRITIQUE
    assert journal.saisie["blocages"][0]["blocage_id"] == str(premier_blocage.id)

    # Le CT rejette 12 jours plus tard ; le CC corrige et re-soumet hors fenêtre J-2 !
    with patch("apps.chantier.services.journal.aujourdhui", return_value=dix_jours_apres):
        journal = rejeter_journal(
            journal=journal,
            utilisateur=c["ct"],
            motif="Merci de préciser le numéro de commande fournisseur dans la description.",
        )
        assert statut_journal(journal) == "REJETE"

        saisie_corrigee = dict(journal.saisie)
        saisie_corrigee["blocages"][0]["titre"] = "Rupture ciment (BC-2026-88)"
        journal = modifier_journal(journal=journal, utilisateur=c["cc"], data=saisie_corrigee)
        journal = soumettre_journal(journal=journal, utilisateur=c["cc"], data={})

    assert statut_journal(journal) == "SOUMIS"
    assert Blocage.objects.filter(projet=c["projet"]).count() == 1
    premier_blocage.refresh_from_db()
    assert premier_blocage.titre == "Rupture ciment (BC-2026-88)"


@pytest.mark.tenant
def test_compatibilite_rapport_historique_et_synthese_consolidee(contexte_chantier):
    """Vérifie la lecture d'un rapport ancien et l'exclusion des SOUMIS des chiffres consolidés."""
    c = contexte_chantier
    j1 = date(2026, 10, 19)  # Lundi
    j2 = date(2026, 10, 20)  # Mardi

    # J1 : rapport historique (ancien format JSON) VALIDÉ
    rap1 = RapportJournalier.objects.create(
        projet=c["projet"],
        date_rapport=j1,
        auteur=c["cc"],
        cree_par=c["cc"],
        statut=StatutRapport.SOUMIS,
        soumis_le=timezone.now(),
    )
    jour1 = JournalChantier.objects.create(
        rapport=rap1,
        valide_ct_par=c["ct"],
        valide_ct_le=timezone.now(),
        saisie={
            "projet_id": str(c["projet"].id),
            "date": j1.isoformat(),
            "heure_debut": "08:00",
            "heure_fin": "17:00",
            "arret": None,
            "meteo": {
                "matin": "ENSOLEILLE",
                "apres_midi": "ENSOLEILLE",
                "conditions": "FAVORABLES",
                "temperature_min": 25,
            },
            "equipes": [
                {
                    "equipe_id": str(c["eq_macons"].id),
                    "presents": [str(c["p1"].id)],
                    "retards": [],
                    "heures": 8,
                    "qualite": "",
                    "observation": "",
                }
            ],
            "lots_travailles": [{"lot_id": str(c["lot"].id), "observation": ""}],
            "activites": [
                {"activite_id": str(c["f_qte"].id), "quantite_jour": 20, "observation": ""}
            ],
            "materiaux": [{"designation": "Ciment", "quantite_consommee": 10, "unite": "sacs"}],
            "livraisons": [
                {
                    "fournisseur": "SOCIMAT",
                    "designation": "Ciment",
                    "quantite": "50 sacs",
                    "bon_livraison": "BL-01",
                    "heure": "09:00",
                    "conformite": "CONFORME",
                    "observation": "",
                }
            ],
            "equipements": [
                {
                    "designation": "Bétonnière",
                    "reference": "BET-1",
                    "propriete": "ENTREPRISE",
                    "utilisation": "6 h gâchage",
                    "operateur": "Koffi",
                    "etat": "BON",
                    "duree_arret": None,
                    "observation": "",
                }
            ],
            "blocage": {
                "niveau": "SIGNIFICATIF",
                "nature": "METEO",
                "description": "Forte averse en fin d'après-midi ralentissant le coulage.",
                "impact": "2h perdues",
            },
            "note_cc": "Ancienne note du chef de chantier conservée intacte.",
        },
    )

    doc1 = document(jour1)
    assert doc1["statut"] == "VALIDE"
    assert doc1["note_redacteur"] == "Ancienne note du chef de chantier conservée intacte."
    assert [et["role"] for et in doc1["circuit"]] == ["REDACTION", "VALIDATION", "APPROBATION"]
    assert doc1["materiaux"][0]["livre"] == 50.0
    assert doc1["materiaux"][0]["utilise"] == 10.0
    assert len(doc1["blocages"]) == 1

    # J2 : rapport SOUMIS mais NON validé -> compte dans reçus, PAS dans les consolidés !
    rap2 = RapportJournalier.objects.create(
        projet=c["projet"],
        date_rapport=j2,
        auteur=c["cc"],
        cree_par=c["cc"],
        statut=StatutRapport.SOUMIS,
        soumis_le=timezone.now(),
    )
    JournalChantier.objects.create(
        rapport=rap2,
        saisie={
            "projet_id": str(c["projet"].id),
            "date": j2.isoformat(),
            "heure_debut": "08:00",
            "heure_fin": "17:00",
            "meteo": {"matin": "NUAGEUX", "apres_midi": "NUAGEUX", "conditions": "FAVORABLES"},
            "equipes": [
                {
                    "equipe_id": str(c["eq_macons"].id),
                    "presents": [str(c["p1"].id)],
                    "retards": [],
                    "heures": 9,
                }
            ],
            "activites": [{"activite_id": str(c["f_qte"].id), "quantite_jour": 60}],
            "livraisons": [
                {
                    "fournisseur": "SOCIMAT",
                    "designation": "Ciment",
                    "quantite": 100,
                    "unite": "sacs",
                    "conformite": "CONFORME",
                }
            ],
            "note_redacteur": "Rapport soumis non encore validé.",
        },
    )

    rf = RequestFactory()
    req = rf.get("/api/v1/chantier/syntheses/")
    req.user = c["ct"]

    lundi_suivant = date(2026, 10, 26)
    with (
        patch("apps.chantier.selectors.synthese.aujourdhui", return_value=lundi_suivant),
        patch("apps.chantier.selectors.journal.aujourdhui", return_value=lundi_suivant),
        patch("apps.chantier.services.synthese.aujourdhui", return_value=lundi_suivant),
    ):
        calc = calculer_synthese(
            req, c["projet"], "HEBDOMADAIRE", date(2026, 10, 19), date(2026, 10, 25)
        )
        assert calc["chiffres"]["jours_ouvres"] == 5
        assert calc["chiffres"]["rapports_recus"] == 2
        assert calc["chiffres"]["rapports_valides"] == 1
        # Seul J1 (VALIDE) compte dans les heures, livraisons et matériaux !
        assert calc["chiffres"]["heures"] == 8
        assert calc["chiffres"]["livraisons"] == 1
        assert calc["materiaux"][0]["livre"] == 50.0

        # Test interdiction d'auto-approbation de la synthèse si le signataire a les 2 permissions
        AffectationProjet.objects.filter(projet=c["projet"], utilisateur=c["cp"]).delete()
        AffectationProjet.objects.create(
            projet=c["projet"],
            utilisateur=c["cp"],
            role_projet=RoleProjet.CHEF_PROJET,
            date_debut=date(2026, 10, 1),
        )
        # Donnons temporairement synthese_rediger aussi au rôle CP pour vérifier le garde-fou
        role_cp = Role.objects.get(code=RoleGlobal.CHEF_PROJET, supprime_le__isnull=True)
        perm_red = CataloguePermission.objects.get(code="chantier.synthese_rediger")
        rmp_cp = RoleModulePermission.objects.filter(
            role=role_cp, module_code="chantier", supprime_le__isnull=True
        ).first()
        assert rmp_cp is not None
        rmp_cp.permissions_catalogue.add(perm_red)

        req_cp = rf.post("/api/v1/chantier/syntheses/soumettre/")
        req_cp.user = c["cp"]
        synthese = soumettre_synthese(
            request=req_cp,
            projet=c["projet"],
            type_="HEBDOMADAIRE",
            debut=date(2026, 10, 19),
            fin=date(2026, 10, 25),
            utilisateur=c["cp"],
            appreciation=(
                "Semaine conforme sur les fouilles validées, en attente du rapport de mardi."
            ),
            objectifs=[],
        )
        proj = projection_synthese(
            req_cp, c["projet"], "HEBDOMADAIRE", date(2026, 10, 19), date(2026, 10, 25)
        )
        assert proj["etape_a_signer"] is None

        with pytest.raises(ErreurMetier):
            approuver_synthese(
                synthese=synthese, utilisateur=c["cp"], commentaire="Auto-approbation"
            )


def test_meteo_suggeree_open_meteo(cache_propre):
    """Vérifie la traduction Open-Meteo vers les choix du journal."""
    faux_json = json.dumps(
        {
            "current": {"temperature_2m": 25.0, "weather_code": 65},
        }
    ).encode()

    class FausseReponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return faux_json

    with patch("apps.projets.services.meteo.urllib.request.urlopen", return_value=FausseReponse()):
        suggestion = meteo_suggeree_journal("Abidjan")
        assert suggestion is not None
        assert suggestion["source_auto"] is True
        assert suggestion["matin"] == "PLUVIEUX"
        assert suggestion["apres_midi"] == "PLUVIEUX"
        assert suggestion["conditions"] == "DIFFICILES"
