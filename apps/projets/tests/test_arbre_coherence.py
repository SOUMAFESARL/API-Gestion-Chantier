"""La cohérence de l'arbre : un parent ne porte rien en propre qu'il puisse lire chez ses enfants.

Feuilles = les faits (dates, montant, mesure). Parents = ce que leurs enfants disent :

- **dates** : début le plus tôt, fin la plus tard — tant que personne ne les a posées à la main ;
- **montant** : la somme des enfants ;
- **statut** : clôturé quand tous les enfants le sont, et la feuille se clôt d'elle-même à 100 %.

Une fois posées à la main, les dates d'un parent bornent ses enfants : aucun ne déborde sans
prolongation confirmée.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.core.enums import StatutActivite, StatutProjet
from apps.projets.models import Element, ModeMesure, NiveauProjet, Projet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services.arbre import mesurer_feuille, modifier_element
from apps.projets.services.machine_etats import evaluer_statuts_arbre
from apps.projets.services.reprogrammation import ProlongationRequise, planifier_element
from apps.projets.services.sante_calculs import calculer_arbre


@pytest.fixture
def auteur(db, entreprise_demo):
    """Celui qui agit : mesurer et reprogrammer se tracent à son nom."""
    from apps.accounts.models import Utilisateur
    from apps.core.enums import StatutUtilisateur

    return Utilisateur.objects.create_user(
        email=f"cp-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        prenom="Awa",
        nom="Koné",
        role_global="CHEF_PROJET",
        statut=StatutUtilisateur.ACTIF,
    )


@pytest.fixture
def chantier(db, entreprise_demo):
    """Installation de chantier > Installation > {Clôture et baraquement, Implantation}."""
    projet = Projet.objects.create(
        reference=f"PRJ-{uuid.uuid4().hex[:4].upper()}",
        nom="Résidence Plateau",
        ville="Abidjan",
        quartier="Plateau",
        statut=StatutProjet.EN_COURS,
        budget_initial_montant=10_000_000_00,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 12, 31),
    )
    niv = [
        NiveauProjet.objects.create(projet=projet, ordre=i, libelle=lib)
        for i, lib in enumerate(("Phase", "Ouvrage", "Tâche"), start=1)
    ]
    phase = Element.objects.create(projet=projet, niveau=niv[0], libelle="Installation de chantier")
    ouvrage = Element.objects.create(
        projet=projet, parent=phase, niveau=niv[1], libelle="Installation"
    )
    cloture = Element.objects.create(
        projet=projet,
        parent=ouvrage,
        niveau=niv[2],
        libelle="Clôture et baraquement",
        mode_mesure=ModeMesure.POURCENTAGE,
        montant=3_000_000_00,
        ordre=1,
    )
    implantation = Element.objects.create(
        projet=projet,
        parent=ouvrage,
        niveau=niv[2],
        libelle="Implantation et piquetage",
        mode_mesure=ModeMesure.QUANTITE,
        unite="u",
        quantite_prevue=Decimal("10"),
        montant=1_000_000_00,
        ordre=2,
    )
    return {
        "projet": projet,
        "phase": phase,
        "ouvrage": ouvrage,
        "cloture": cloture,
        "implantation": implantation,
    }


def _relire(*elements):
    for e in elements:
        e.refresh_from_db()


# --------------------------------------------------------------------------
# Montants : le parent affiche la somme de ses enfants
# --------------------------------------------------------------------------
@pytest.mark.carac
@pytest.mark.entreprise
def test_le_montant_du_parent_est_la_somme_de_ses_enfants(chantier):
    c = chantier
    resultats = calculer_arbre(charger_arbre(c["projet"], actifs_seulement=True))

    assert resultats[c["ouvrage"].pk].poids == Decimal(4_000_000_00)
    assert resultats[c["phase"].pk].poids == Decimal(4_000_000_00)


@pytest.mark.carac
@pytest.mark.entreprise
def test_l_enveloppe_ne_masque_pas_la_somme_quand_tout_est_chiffre(chantier):
    """Une enveloppe plus grande que la somme : le poids reste la somme (§8)."""
    c = chantier
    Element.objects.filter(pk=c["ouvrage"].pk).update(enveloppe=9_000_000_00)

    resultats = calculer_arbre(charger_arbre(c["projet"], actifs_seulement=True))

    assert resultats[c["ouvrage"].pk].poids == Decimal(4_000_000_00)


@pytest.mark.entreprise
def test_la_somme_suit_le_montant_d_une_feuille(chantier):
    c = chantier
    modifier_element(c["implantation"], donnees={"montant": 2_000_000_00})

    resultats = calculer_arbre(charger_arbre(c["projet"], actifs_seulement=True))

    assert resultats[c["ouvrage"].pk].poids == Decimal(5_000_000_00)
    assert resultats[c["phase"].pk].poids == Decimal(5_000_000_00)


# --------------------------------------------------------------------------
# Dates : le parent les déduit de ses enfants
# --------------------------------------------------------------------------
@pytest.mark.regle
@pytest.mark.entreprise
def test_un_parent_sans_dates_prend_celles_de_son_seul_enfant_date(chantier):
    c = chantier
    planifier_element(c["cloture"], date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 20))
    _relire(c["ouvrage"], c["phase"])

    for parent in (c["ouvrage"], c["phase"]):
        assert parent.date_debut_prevue == date(2026, 10, 5)
        assert parent.date_fin_prevue == date(2026, 10, 20)
        assert parent.dates_calculees is True
        # Sa baseline est celle de ses enfants : elle ne dépend pas de l'ordre de saisie.
        assert parent.date_debut_baseline == date(2026, 10, 5)
        assert parent.date_fin_baseline == date(2026, 10, 20)


@pytest.mark.regle
@pytest.mark.entreprise
def test_avec_deux_enfants_le_parent_va_du_debut_le_plus_tot_a_la_fin_la_plus_tard(chantier):
    c = chantier
    planifier_element(c["cloture"], date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 20))
    planifier_element(c["implantation"], date_debut=date(2026, 10, 10), date_fin=date(2026, 11, 3))
    _relire(c["ouvrage"], c["phase"])

    assert (c["ouvrage"].date_debut_prevue, c["ouvrage"].date_fin_prevue) == (
        date(2026, 10, 5),
        date(2026, 11, 3),
    )
    assert (c["phase"].date_debut_prevue, c["phase"].date_fin_prevue) == (
        date(2026, 10, 5),
        date(2026, 11, 3),
    )
    # La baseline du parent est l'enveloppe des baselines de ses enfants.
    assert c["ouvrage"].date_fin_baseline == date(2026, 11, 3)


@pytest.mark.regle
@pytest.mark.entreprise
def test_un_enfant_reprogramme_deplace_le_parent_sans_toucher_a_sa_baseline(chantier, auteur):
    from apps.projets.models.motif_report import MotifReport
    from apps.projets.services.reprogrammation import reprogrammer_date_instance

    c = chantier
    planifier_element(c["cloture"], date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 20))
    motif = MotifReport.objects.create(code="METEO", libelle="Intempéries")

    reprogrammer_date_instance(
        c["cloture"],
        nouvelle_date_fin=date(2026, 11, 10),
        motif_id=str(motif.pk),
        justification="Pluies continues pendant trois semaines sur le site.",
        auteur=auteur,
    )
    _relire(c["ouvrage"])

    assert c["ouvrage"].date_fin_prevue == date(2026, 11, 10)
    assert c["ouvrage"].date_fin_baseline == date(2026, 10, 20)


@pytest.mark.regle
@pytest.mark.entreprise
def test_un_enfant_qui_deborde_d_un_parent_calcule_ne_demande_aucune_prolongation(chantier):
    """Le parent n'a rien promis : il s'étire. Pas d'alerte, pas de motif."""
    c = chantier
    planifier_element(c["cloture"], date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 20))

    planifier_element(c["implantation"], date_debut=date(2026, 10, 25), date_fin=date(2026, 12, 1))
    _relire(c["ouvrage"])

    assert c["ouvrage"].date_fin_prevue == date(2026, 12, 1)


@pytest.mark.regle
@pytest.mark.entreprise
def test_un_enfant_ne_deborde_pas_d_un_parent_date_a_la_main(chantier):
    """Les dates posées à la main sont un engagement : on ne déborde qu'en le prolongeant."""
    c = chantier
    planifier_element(c["ouvrage"], date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 31))
    _relire(c["ouvrage"])
    assert c["ouvrage"].dates_calculees is False

    with pytest.raises(ProlongationRequise):
        planifier_element(
            c["implantation"], date_debut=date(2026, 10, 10), date_fin=date(2026, 11, 20)
        )

    # Dans la fenêtre, tout va bien, et le parent ne bouge pas.
    planifier_element(c["implantation"], date_debut=date(2026, 10, 10), date_fin=date(2026, 10, 31))
    _relire(c["ouvrage"])
    assert (c["ouvrage"].date_debut_prevue, c["ouvrage"].date_fin_prevue) == (
        date(2026, 10, 5),
        date(2026, 10, 31),
    )


@pytest.mark.regle
@pytest.mark.entreprise
def test_un_ancetre_date_a_la_main_borne_toujours_un_parent_calcule(chantier):
    """La phase est datée à la main, l'ouvrage est calculé : le débordement remonte à la phase."""
    c = chantier
    planifier_element(c["phase"], date_debut=date(2026, 10, 1), date_fin=date(2026, 10, 31))

    with pytest.raises(ProlongationRequise) as erreur:
        planifier_element(
            c["implantation"], date_debut=date(2026, 10, 10), date_fin=date(2026, 11, 20)
        )

    cibles = [p["id"] for p in erreur.value.details["prolongations"]]
    assert str(c["phase"].pk) in cibles
    # L'ouvrage, calculé, n'est pas à prolonger : il suivra.
    assert str(c["ouvrage"].pk) not in cibles


@pytest.mark.regle
@pytest.mark.entreprise
def test_un_parent_date_a_la_main_ne_se_recalcule_plus(chantier):
    c = chantier
    planifier_element(c["ouvrage"], date_debut=date(2026, 10, 1), date_fin=date(2026, 12, 15))

    planifier_element(c["cloture"], date_debut=date(2026, 10, 5), date_fin=date(2026, 10, 20))
    _relire(c["ouvrage"])

    assert c["ouvrage"].date_fin_prevue == date(2026, 12, 15)


# --------------------------------------------------------------------------
# Statuts : la clôture se déduit, et la feuille se clôt à 100 %
# --------------------------------------------------------------------------
@pytest.mark.regle
@pytest.mark.entreprise
def test_la_feuille_se_cloture_d_elle_meme_a_cent_pour_cent(chantier, auteur):
    c = chantier
    feuille = c["cloture"]

    mesurer_feuille(feuille, auteur=auteur, commentaire="Fin des travaux", pourcentage_declare=100)
    _relire(feuille)

    assert feuille.cloture is True
    assert feuille.cloture_le is not None


@pytest.mark.regle
@pytest.mark.entreprise
def test_la_feuille_en_quantite_se_cloture_quand_le_prevu_est_atteint(chantier, auteur):
    c = chantier
    feuille = c["implantation"]

    mesurer_feuille(feuille, auteur=auteur, commentaire="Moitié", quantite_realisee=5)
    _relire(feuille)
    assert feuille.cloture is False

    mesurer_feuille(feuille, auteur=auteur, commentaire="Terminé", quantite_realisee=10)
    _relire(feuille)
    assert feuille.cloture is True


@pytest.mark.regle
@pytest.mark.entreprise
def test_le_parent_est_cloture_quand_ses_deux_feuilles_le_sont_puis_son_parent(chantier, auteur):
    """L'exemple fondateur : clôture et baraquement + implantation → installation → phase."""
    c = chantier
    mesurer_feuille(c["cloture"], auteur=auteur, commentaire="Fait", pourcentage_declare=100)
    _relire(c["ouvrage"])
    assert c["ouvrage"].statut != StatutActivite.CLOTURE

    mesurer_feuille(c["implantation"], auteur=auteur, commentaire="Fait", quantite_realisee=10)
    evaluer_statuts_arbre(c["projet"])
    _relire(c["ouvrage"], c["phase"])

    assert c["ouvrage"].statut == StatutActivite.CLOTURE
    assert c["phase"].statut == StatutActivite.CLOTURE
    assert c["phase"].avancement == Decimal("100.00")


@pytest.mark.regle
@pytest.mark.entreprise
def test_ajouter_une_feuille_rouvre_le_parent_cloture(chantier, auteur):
    from apps.projets.services.arbre import ajouter_element

    c = chantier
    mesurer_feuille(c["cloture"], auteur=auteur, commentaire="Fait", pourcentage_declare=100)
    mesurer_feuille(c["implantation"], auteur=auteur, commentaire="Fait", quantite_realisee=10)
    evaluer_statuts_arbre(c["projet"])
    _relire(c["ouvrage"])
    assert c["ouvrage"].statut == StatutActivite.CLOTURE

    ajouter_element(
        c["projet"],
        parent=c["ouvrage"],
        libelle="Branchement provisoire",
        auteur=auteur,
        motif="Branchement provisoire oublié au marché",  # sous une case commencée (§12.2)
    )
    evaluer_statuts_arbre(c["projet"])
    _relire(c["ouvrage"], c["phase"])

    assert c["ouvrage"].statut != StatutActivite.CLOTURE
    assert c["phase"].statut != StatutActivite.CLOTURE


@pytest.mark.regle
@pytest.mark.entreprise
def test_on_cloture_a_la_main_une_tache_terminee_avant_son_prevu(chantier, auteur):
    """Le bouton reste pour ce cas : 5 m3 sur 10 prévus, et c'est fini."""
    from apps.projets.services.arbre import cloturer_feuille

    c = chantier
    feuille = c["implantation"]
    mesurer_feuille(feuille, auteur=auteur, commentaire="Moitié", quantite_realisee=5)

    cloturer_feuille(feuille, auteur=auteur)
    _relire(feuille)

    assert feuille.cloture is True
    assert feuille.date_fin_reelle is not None
    assert feuille.avancement == Decimal("100.00")


@pytest.mark.regle
@pytest.mark.entreprise
def test_rouvrir_une_tache_efface_sa_fin_reelle(chantier, auteur):
    from apps.projets.services.arbre import rouvrir_feuille

    c = chantier
    feuille = c["cloture"]
    mesurer_feuille(feuille, auteur=auteur, commentaire="Fait", pourcentage_declare=100)
    _relire(feuille)
    assert feuille.date_fin_reelle is not None

    rouvrir_feuille(feuille, auteur=auteur, motif="Une réserve du maître d'ouvrage")
    _relire(feuille)

    assert feuille.cloture is False
    assert feuille.date_fin_reelle is None


@pytest.mark.regle
@pytest.mark.entreprise
def test_la_commande_rattrape_des_donnees_ecrites_avant_la_regle(chantier):
    """Des feuilles datées et clôturées **en base**, sans passer par les gestes de l'arbre : leurs
    parents n'ont ni dates ni statut juste. `recalculer_arbres` les rattrape."""
    from django.core.management import call_command

    c = chantier
    Element.objects.filter(pk=c["cloture"].pk).update(
        date_debut_prevue=date(2026, 9, 8), date_fin_prevue=date(2026, 9, 17), cloture=True
    )
    Element.objects.filter(pk=c["implantation"].pk).update(
        date_debut_prevue=date(2026, 9, 10), date_fin_prevue=date(2026, 9, 20), cloture=True
    )
    _relire(c["ouvrage"], c["phase"])
    assert c["ouvrage"].date_debut_prevue is None

    call_command("recalculer_arbres", entreprise="demo")
    _relire(c["ouvrage"], c["phase"])

    for parent in (c["ouvrage"], c["phase"]):
        assert (parent.date_debut_prevue, parent.date_fin_prevue) == (
            date(2026, 9, 8),
            date(2026, 9, 20),
        )
        assert parent.dates_calculees is True
        assert parent.statut == StatutActivite.CLOTURE

    # Idempotente : relancée, elle ne change plus rien.
    call_command("recalculer_arbres", entreprise="demo")
    _relire(c["ouvrage"])
    assert c["ouvrage"].date_fin_prevue == date(2026, 9, 20)
