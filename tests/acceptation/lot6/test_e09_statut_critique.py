"""
[E-09] Tests d'acceptation du Lot 6 : Protection du statut manuel CRITIQUE contre l'évaluation automatique nocturne.
Règles : E-09 (cahier-regles.md).
"""
from datetime import timedelta
from django.utils import timezone
import pytest

from apps.core.enums import StatutProjet
from apps.projets.models import Projet
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
    """[E-09 CA] Après executer_evaluation_quotidienne_schema, un projet CRITIQUE reste CRITIQUE."""
    dg = fab.acteur("DG")
    hier = timezone.localdate() - timedelta(days=5)
    avant_hier = timezone.localdate() - timedelta(days=2)

    # Projet dont les dates indiqueraient calendairement un retard
    projet = fab.creer_projet(
        createur=dg,
        date_debut_prevue=hier,
        date_fin_prevue=avant_hier,
    )
    fab.definir_statut_projet_base(projet, StatutProjet.CRITIQUE)

    # Exécution de la tâche nocturne automatique
    with fab._schema():
        stats = executer_evaluation_quotidienne_schema()
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.CRITIQUE, (
            f"La tâche nocturne ne doit pas écraser CRITIQUE, trouvé : {p_db.statut}"
        )


@CARAC
def test_e09_evaluation_quotidienne_projet_nominal_en_retard(fab):
    """[E-09 Non-régression] Un projet EN_COURS dont la date de fin est dépassée bascule à EN_RETARD."""
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
        executer_evaluation_quotidienne_schema()
        p_db = Projet.objects.get(pk=projet.pk)
        assert p_db.statut == StatutProjet.EN_RETARD
