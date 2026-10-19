"""
[E-09] Tests d'acceptation du Lot 6 : Statut CRITIQUE et évaluation quotidienne (SFD F3 §7).
Règles : E-09 (cahier-regles.md) et SFD F3 §7 (statut automatique, retour par EN_RETARD).
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.enums import StatutProjet
from apps.projets.models import Lot, Projet
from apps.projets.services.machine_etats import executer_evaluation_quotidienne_schema

CARAC = pytest.mark.caracterisation
NOUVEAU = pytest.mark.nouveau


@NOUVEAU
def test_e09_cp_peut_passer_projet_a_critique(fab):
    """[E-09] Un CP affecté peut positionner manuellement le statut CRITIQUE (200)."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    cp = fab.acteur("CP")
    fab.affecter(projet, cp, role_projet="CP")

    client_cp = fab.client_pour(cp)
    r = client_cp.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.CRITIQUE),
        format="json",
    )
    assert r.status_code == 200, f"CP doit pouvoir passer le projet à CRITIQUE, reçu {r.status_code}"

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.CRITIQUE


@NOUVEAU
def test_e09_vi_ne_peut_pas_passer_a_critique(fab):
    """[E-09] Un utilisateur non habilité (VI) reçoit 403 en tentant de passer un projet à CRITIQUE."""
    dg = fab.acteur("DG")
    projet = fab.creer_projet(createur=dg)
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    vi = fab.acteur("VI")
    fab.affecter(projet, vi, role_projet="VI")

    client_vi = fab.client_pour(vi)
    r = client_vi.patch(
        fab.url_projet_detail(projet),
        fab.corps_statut(StatutProjet.CRITIQUE),
        format="json",
    )
    assert r.status_code == 403

    with fab._schema():
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.EN_COURS


@NOUVEAU
def test_e09_tache_nocturne_n_ecrase_pas_statut_critique(fab):
    """[E-09 / SFD §7] Évaluation quotidienne d'un projet CRITIQUE.

    SFD §7 : Le statut CRITIQUE est automatique. Un projet avec un lot dont le delta dépasse
    25 pts reste CRITIQUE. En revanche, lorsqu'il ne l'est plus (aucun lot en retard critique,
    indice >= 40), la règle de retour SFD §7 impose qu'il passe à EN_RETARD et non à EN_COURS.
    """
    dg = fab.acteur("DG")
    hier = timezone.localdate() - timedelta(days=5)
    avant_hier = timezone.localdate() - timedelta(days=2)

    # 1. Cas 1 : Projet CRITIQUE avec un lot dont le delta dépasse 25 pts -> reste CRITIQUE
    projet = fab.creer_projet(
        createur=dg,
        date_debut_prevue=hier,
        date_fin_prevue=avant_hier,
    )
    fab.definir_statut_projet_base(projet, StatutProjet.CRITIQUE)

    # 2. Cas 2 : projet CRITIQUE sans lot en retard, indice >= 40 -> EN_RETARD (SFD §7)
    projet2 = fab.creer_projet(
        createur=dg,
        date_debut_prevue=hier,
        date_fin_prevue=avant_hier,
    )
    fab.definir_statut_projet_base(projet2, StatutProjet.CRITIQUE)

    with fab._schema():
        Lot.objects.create(
            projet=projet,
            code="LOT-CRITIQUE",
            libelle="Lot en retard critique",
            budget_initial_montant=10000000,
            date_debut_prevue=hier,
            date_fin_prevue=avant_hier,
            date_debut_baseline=hier,
            date_fin_baseline=avant_hier,
            avancement=0,
        )

        projet2.indice_sante = 80
        projet2.save(update_fields=["indice_sante"])
        Lot.objects.create(
            projet=projet2,
            code="LOT-CONFORME",
            libelle="Lot à jour",
            budget_initial_montant=10000000,
            date_debut_prevue=hier,
            date_fin_prevue=avant_hier,
            date_debut_baseline=hier,
            date_fin_baseline=avant_hier,
            avancement=100,
        )

        executer_evaluation_quotidienne_schema()

        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.CRITIQUE, (
            "Selon SFD §7, un projet avec delta > 25 pts doit rester CRITIQUE, "
            f"trouvé : {p_db.statut}"
        )

        p2_db = Projet.objects.get(pk=projet2.pk)
        assert p2_db.statut == StatutProjet.EN_RETARD, (
            "Selon SFD §7, un projet CRITIQUE rétabli passe à EN_RETARD et non EN_COURS, "
            f"trouvé : {p2_db.statut}"
        )


@CARAC
def test_e09_evaluation_quotidienne_projet_nominal_en_retard(fab):
    """[E-09 Non-régression / SFD §7] Un projet EN_COURS avec un lot ayant un delta
    entre 5 et 25 pts bascule à EN_RETARD.
    """
    dg = fab.acteur("DG")
    hier = timezone.localdate() - timedelta(days=10)
    avant_hier = timezone.localdate() - timedelta(days=2)

    projet = fab.creer_projet(
        createur=dg,
        date_debut_prevue=hier,
        date_fin_prevue=avant_hier,
    )
    fab.definir_statut_projet_base(projet, StatutProjet.EN_COURS)

    with fab._schema():
        Lot.objects.create(
            projet=projet,
            code="LOT-RETARD",
            libelle="Lot en retard modéré",
            budget_initial_montant=10000000,
            date_debut_prevue=hier,
            date_fin_prevue=avant_hier,
            date_debut_baseline=hier,
            date_fin_baseline=avant_hier,
            avancement=85,
        )
        executer_evaluation_quotidienne_schema()
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.EN_RETARD
