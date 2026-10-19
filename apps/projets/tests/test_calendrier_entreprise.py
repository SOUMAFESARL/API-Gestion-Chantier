"""Tests pour les modèles du calendrier d'entreprise et la permission calendrier_gerer.

Conformité SFD F3 §6 & Erratum v1.0.1 (E-4) :
- SemaineType : semaine type de l'entreprise (une ligne par tenant, lundi-vendredi par défaut).
- ExceptionCalendrier : exceptions d'entreprise (date, ouvré/non ouvré, motif), unicité active.
- Droits : administration.calendrier_gerer dans REGISTRE et DROITS_ADMIN_AD (DG et AD seuls).
"""

from datetime import date, timedelta
from unittest import mock

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.chantier.models import JournalChantier, RelanceJournal
from apps.chantier.services.relance import relancer_rapports_manquants, verifier_ligne
from apps.core.droits import DROITS_ADMIN_AD, a_permission
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.core.exceptions import ErreurMetier
from apps.core.models import ModeleBase
from apps.core.registre_permissions import REGISTRE
from apps.projets.models import AffectationProjet, ExceptionCalendrier, Projet, SemaineType

pytestmark = pytest.mark.django_db


def test_modeles_heritage_et_export():
    """Vérifie l'héritage de ModeleBase et la configuration des métadonnées."""
    assert issubclass(SemaineType, ModeleBase)
    assert issubclass(ExceptionCalendrier, ModeleBase)
    assert SemaineType._meta.db_table == "semaine_type"
    assert ExceptionCalendrier._meta.db_table == "exception_calendrier"
    assert ExceptionCalendrier._meta.ordering == ["date"]


def test_semaine_type_courante_creation_et_valeurs_par_defaut(schema_demo):
    """SemaineType.courante() crée une ligne par défaut (lundi-vendredi).

    Elle restitue la même ligne aux appels suivants.
    """
    SemaineType.tous_objets.all().delete()

    st1 = SemaineType.courante()
    assert st1.cle == "unique"
    assert st1.lundi is True
    assert st1.mardi is True
    assert st1.mercredi is True
    assert st1.jeudi is True
    assert st1.vendredi is True
    assert st1.samedi is False
    assert st1.dimanche is False
    assert SemaineType.objects.count() == 1

    st2 = SemaineType.courante()
    assert st2.pk == st1.pk
    assert SemaineType.objects.count() == 1


def test_semaine_type_jours_travailles(schema_demo):
    """jours_travailles() retourne les numéros weekday (0=lundi, ..., 6=dimanche)."""
    SemaineType.tous_objets.all().delete()
    st = SemaineType.courante()
    assert st.jours_travailles() == frozenset({0, 1, 2, 3, 4})

    st.samedi = True
    st.save(update_fields=["samedi", "modifie_le"])
    assert st.jours_travailles() == frozenset({0, 1, 2, 3, 4, 5})

    st.lundi = False
    st.save(update_fields=["lundi", "modifie_le"])
    assert st.jours_travailles() == frozenset({1, 2, 3, 4, 5})


def test_semaine_type_contrainte_unicite(schema_demo):
    """La contrainte d'unicité empêche d'insérer une deuxième semaine type avec la même clé."""
    SemaineType.tous_objets.all().delete()
    SemaineType.courante()
    with pytest.raises(IntegrityError), transaction.atomic():
        SemaineType.objects.create(cle="unique")


def test_exception_calendrier_creation(schema_demo):
    """Création d'une exception de calendrier avec date, ouvre et motif."""
    exc = ExceptionCalendrier.objects.create(
        date=date(2025, 5, 1),
        ouvre=True,
        motif="1er mai exceptionnellement travaillé",
    )
    assert exc.date == date(2025, 5, 1)
    assert exc.ouvre is True
    assert exc.motif == "1er mai exceptionnellement travaillé"
    assert str(exc.date) in str(exc)
    assert "ouvré" in str(exc)


def test_exception_calendrier_unicite_date_active(schema_demo):
    """Deux exceptions actives sur la même date sont refusées par la contrainte."""
    ExceptionCalendrier.objects.create(
        date=date(2025, 8, 7),
        ouvre=False,
        motif="Fête nationale",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ExceptionCalendrier.objects.create(
            date=date(2025, 8, 7),
            ouvre=True,
            motif="Doublon même date",
        )


def test_exception_calendrier_autorisee_si_precedente_supprimee_logiquement(schema_demo):
    """Une exception peut être créée sur une date si l'ancienne a été supprimée logiquement."""
    exc1 = ExceptionCalendrier.objects.create(
        date=date(2025, 6, 6),
        ouvre=False,
        motif="Tabaski initiale",
    )
    exc1.delete()
    assert exc1.est_supprime is True
    assert ExceptionCalendrier.objects.filter(date=date(2025, 6, 6)).count() == 0

    exc2 = ExceptionCalendrier.objects.create(
        date=date(2025, 6, 6),
        ouvre=False,
        motif="Tabaski confirmée",
    )
    assert exc2.pk != exc1.pk
    assert ExceptionCalendrier.objects.filter(date=date(2025, 6, 6)).count() == 1
    assert ExceptionCalendrier.tous_objets.filter(date=date(2025, 6, 6)).count() == 2


def test_exception_calendrier_tri_par_date(schema_demo):
    """Les exceptions sont ordonnées chronologiquement par défaut."""
    ExceptionCalendrier.tous_objets.filter(date__year=2025).delete()
    ExceptionCalendrier.objects.create(date=date(2025, 12, 25), ouvre=False, motif="Noël")
    ExceptionCalendrier.objects.create(date=date(2025, 1, 1), ouvre=False, motif="Jour de l'an")
    ExceptionCalendrier.objects.create(date=date(2025, 5, 1), ouvre=False, motif="Fête du Travail")

    dates = list(
        ExceptionCalendrier.objects.filter(date__year=2025).values_list("date", flat=True)
    )
    assert dates == [date(2025, 1, 1), date(2025, 5, 1), date(2025, 12, 25)]


def test_permission_registre_et_droits_ad():
    """Vérifie l'enregistrement de administration.calendrier_gerer et son attribution à l'AD."""
    assert "administration.calendrier_gerer" in REGISTRE
    perm = REGISTRE["administration.calendrier_gerer"]
    assert perm.module == "administration"
    assert perm.rang == 2
    assert perm.reservee_administration is True

    assert "administration.calendrier_gerer" in DROITS_ADMIN_AD
    assert len(DROITS_ADMIN_AD) == 7


def test_permission_dg_ad_et_interdiction_autres_roles(schema_demo):
    """DG et AD obtiennent la permission ; les autres rôles ne peuvent pas l'avoir."""
    dg = Utilisateur.objects.create_user(
        email="dg.calendrier.test@demo.ci",
        password="TestPassword123!",
        nom="DG Test",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        statut=StatutUtilisateur.ACTIF,
    )
    ad = Utilisateur.objects.create_user(
        email="ad.calendrier.test@demo.ci",
        password="TestPassword123!",
        nom="AD Test",
        role_global=RoleGlobal.ADMIN,
        statut=StatutUtilisateur.ACTIF,
    )
    cp = Utilisateur.objects.create_user(
        email="cp.calendrier.test@demo.ci",
        password="TestPassword123!",
        nom="CP Test",
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    ct = Utilisateur.objects.create_user(
        email="ct.calendrier.test@demo.ci",
        password="TestPassword123!",
        nom="CT Test",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
        statut=StatutUtilisateur.ACTIF,
    )

    assert a_permission(dg, "administration.calendrier_gerer") is True
    assert a_permission(ad, "administration.calendrier_gerer") is True
    assert a_permission(cp, "administration.calendrier_gerer") is False
    assert a_permission(ct, "administration.calendrier_gerer") is False


def test_verifier_ligne_samedi_ouvre_attend_rapport(schema_demo):
    """Un samedi déclaré ouvré par exception attend un rapport : verifier_ligne ne lève plus."""
    date_samedi = date(2026, 6, 13)
    assert date_samedi.weekday() == 5

    projet = Projet(
        statut="EN_COURS",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )

    with mock.patch("apps.chantier.services.relance.aujourdhui", return_value=date(2026, 6, 15)):
        with pytest.raises(ErreurMetier) as exc_info:
            verifier_ligne(projet, date_samedi, None)
        assert (
            "Aucun rapport n'est attendu ce jour : "
            "il n'est pas ouvré dans le calendrier de l'entreprise."
            in str(exc_info.value)
        )

        ExceptionCalendrier.objects.create(
            date=date_samedi,
            ouvre=True,
            motif="Samedi travaillé exceptionnel",
        )
        verifier_ligne(projet, date_samedi, None)


def test_verifier_ligne_mardi_ferme_n_attend_pas_rapport(schema_demo):
    """Un mardi fermé par exception n'attend pas de rapport : verifier_ligne lève ErreurMetier."""
    date_mardi = date(2026, 6, 9)
    assert date_mardi.weekday() == 1

    projet = Projet(
        statut="EN_COURS",
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
    )

    with mock.patch("apps.chantier.services.relance.aujourdhui", return_value=date(2026, 6, 15)):
        verifier_ligne(projet, date_mardi, None)

        ExceptionCalendrier.objects.create(
            date=date_mardi,
            ouvre=False,
            motif="Mardi chômé exceptionnel",
        )
        with pytest.raises(ErreurMetier) as exc_info:
            verifier_ligne(projet, date_mardi, None)
        assert (
            "Aucun rapport n'est attendu ce jour : "
            "il n'est pas ouvré dans le calendrier de l'entreprise."
            in str(exc_info.value)
        )


def test_duree_jours_ouvres_suit_exceptions_calendrier(schema_demo):
    """La durée en jours ouvrés diminue d'un jour avec une exception « non ouvré » en semaine

    et augmente d'un jour avec un samedi « ouvré ».
    """
    debut = date(2026, 6, 8)  # Lundi
    fin = date(2026, 6, 14)   # Dimanche
    ExceptionCalendrier.tous_objets.filter(date__gte=debut, date__lte=fin).delete()

    projet = Projet.objects.create(
        reference="PRJ-TEST-DUR-EXC",
        nom="Projet Test Exceptions Durée",
        ville="Abidjan",
        date_debut_prevue=debut,
        date_fin_prevue=fin,
    )

    duree_initiale = projet.duree_jours_ouvres
    assert duree_initiale == 5

    mercredi = date(2026, 6, 10)
    exc_chome = ExceptionCalendrier.objects.create(
        date=mercredi,
        ouvre=False,
        motif="Mercredi chômé",
    )
    assert projet.duree_jours_ouvres == duree_initiale - 1

    samedi = date(2026, 6, 13)
    ExceptionCalendrier.objects.create(
        date=samedi,
        ouvre=True,
        motif="Samedi travaillé",
    )
    assert projet.duree_jours_ouvres == duree_initiale

    exc_chome.delete()
    assert projet.duree_jours_ouvres == duree_initiale + 1


def test_relance_automatique_respecte_calendrier_entreprise(schema_demo):
    """La relance automatique respecte le calendrier de l'entreprise.

    Cas A : un mardi ouvré normal sans exception donne bilan['relances'] == 1.
    Cas B : le même mardi avec ExceptionCalendrier(ouvre=False) donne bilan['relances'] == 0.
    Cas C : un samedi avec ExceptionCalendrier(ouvre=True) donne bilan['relances'] == 1.
    """
    Projet.tous_objets.all().delete()
    ExceptionCalendrier.tous_objets.all().delete()
    RelanceJournal.objects.all().delete()

    user = Utilisateur.objects.create_user(
        email="cp.relance.auto@demo.ci",
        password="TestPassword123!",
        nom="Relance",
        prenom="Auto",
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    debut_chantier = date(2026, 1, 1)
    fin_chantier = date(2026, 12, 31)
    projet = Projet.objects.create(
        reference="PRJ-RELANCE-AUTO",
        nom="Projet Relance Auto",
        ville="Abidjan",
        statut="EN_COURS",
        chef_projet=user,
        date_debut_prevue=debut_chantier,
        date_fin_prevue=fin_chantier,
    )
    # Enregistré avant les dates de test pour que premier_jour_rapport <= date_rapport
    Projet.objects.filter(pk=projet.pk).update(cree_le=timezone.now() - timedelta(days=365))
    projet.refresh_from_db()

    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=user,
        role_projet="CC",
        date_debut=debut_chantier,
        est_actif=True,
    )

    jour_mardi = date(2026, 6, 9)
    assert jour_mardi.weekday() == 1

    # Cas A : un mardi ouvré normal sans exception donne bilan['relances'] == 1.
    with mock.patch("apps.chantier.services.relance.aujourdhui", return_value=jour_mardi):
        bilan_a = relancer_rapports_manquants(jour_mardi)
    assert bilan_a["relances"] == 1
    assert RelanceJournal.objects.filter(projet=projet, date_rapport=jour_mardi).count() == 1

    # Réinitialisation des relances pour tester le même mardi en Cas B
    RelanceJournal.objects.all().delete()

    # Cas B : le même mardi avec ExceptionCalendrier(ouvre=False) donne bilan['relances'] == 0.
    exc_mardi = ExceptionCalendrier.objects.create(
        date=jour_mardi,
        ouvre=False,
        motif="Mardi chômé exceptionnel",
    )
    with mock.patch("apps.chantier.services.relance.aujourdhui", return_value=jour_mardi):
        bilan_b = relancer_rapports_manquants(jour_mardi)
    assert bilan_b["relances"] == 0
    assert RelanceJournal.objects.count() == 0
    exc_mardi.delete()

    # Cas C : un samedi avec ExceptionCalendrier(ouvre=True) donne bilan['relances'] == 1.
    jour_samedi = date(2026, 6, 13)
    assert jour_samedi.weekday() == 5
    ExceptionCalendrier.objects.create(
        date=jour_samedi,
        ouvre=True,
        motif="Samedi ouvré exceptionnel",
    )
    with mock.patch("apps.chantier.services.relance.aujourdhui", return_value=jour_samedi):
        bilan_c = relancer_rapports_manquants(jour_samedi)
    assert bilan_c["relances"] == 1
    assert RelanceJournal.objects.filter(projet=projet, date_rapport=jour_samedi).count() == 1


def test_journal_periode_saute_jours_non_ouvres_par_exception(schema_demo):
    """La liste des rapports attendus du journal saute les jours chômés par exception."""
    from apps.chantier.selectors.journal import journal_periode

    user = Utilisateur.objects.create_user(
        email="cc.journal.cal@demo.ci",
        password="TestPassword123!",
        nom="CC Cal",
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    request = mock.MagicMock()
    request.user = user

    debut = date(2026, 6, 8)
    fin = date(2026, 6, 10)
    projet = Projet.objects.create(
        reference="PRJ-JOURNAL-CAL",
        nom="Projet Journal Calendrier",
        ville="Abidjan",
        statut="EN_COURS",
        chef_projet=user,
        date_debut_prevue=debut,
        date_fin_prevue=fin,
    )

    with mock.patch("apps.chantier.selectors.journal.aujourdhui", return_value=fin), mock.patch(
        "apps.chantier.selectors.journal.projets_visibles",
        return_value=Projet.objects.filter(pk=projet.pk),
    ), mock.patch(
        "apps.chantier.selectors.journal.journaux_visibles",
        return_value=JournalChantier.objects.none(),
    ), mock.patch(
        "apps.chantier.selectors.journal.premier_jour_rapport",
        return_value=debut,
    ):
        entrees = journal_periode(request, debut, fin, projet_id=projet.pk)
        dates_attendues = [e["date"] for e in entrees]
        assert dates_attendues == ["2026-06-10", "2026-06-09", "2026-06-08"]

        ExceptionCalendrier.objects.create(
            date=date(2026, 6, 9),
            ouvre=False,
            motif="Mardi chômé exceptionnel",
        )
        entrees_avec_exc = journal_periode(
            request, debut, fin, projet_id=projet.pk
        )
        dates_avec_exc = [e["date"] for e in entrees_avec_exc]
        assert dates_avec_exc == ["2026-06-10", "2026-06-08"]

