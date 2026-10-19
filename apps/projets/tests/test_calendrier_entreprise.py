"""Tests pour les modèles du calendrier d'entreprise et la permission calendrier_gerer.

Conformité SFD F3 §6 & Erratum v1.0.1 (E-4) :
- SemaineType : semaine type de l'entreprise (une ligne par tenant, lundi-vendredi par défaut).
- ExceptionCalendrier : exceptions d'entreprise (date, ouvré/non ouvré, motif), unicité active.
- Droits : administration.calendrier_gerer dans REGISTRE et DROITS_ADMIN_AD (DG et AD seuls).
"""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Utilisateur
from apps.core.droits import DROITS_ADMIN_AD, a_permission
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.core.models import ModeleBase
from apps.core.registre_permissions import REGISTRE
from apps.projets.models import ExceptionCalendrier, SemaineType

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
