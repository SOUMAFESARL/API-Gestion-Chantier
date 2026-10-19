"""Tests unitaires pour le modèle AlerteRetard (SFD F3 §5.4 & §10)."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.projets.models import (
    AlerteRetard,
    Lot,
    NiveauAlerteRetard,
    Projet,
    StatutAlerteRetard,
)


@pytest.mark.django_db
def test_creation_alerte_lot(schema_demo):
    """Vérifie la création d'une alerte de lot avec causes et recommandations."""
    projet = Projet.objects.create(
        reference="PRJ-AL-001",
        nom="Résidence Palmier",
        ville="Abidjan",
    )
    lot = Lot.objects.create(
        projet=projet,
        code="LOT-01",
        libelle="Gros Œuvre",
    )

    alerte = AlerteRetard.objects.create(
        projet=projet,
        lot=lot,
        niveau=NiveauAlerteRetard.ELEVE,
        delta_pts=Decimal("17.50"),
        date_detection=date(2026, 10, 20),
        statut=StatutAlerteRetard.OUVERTE,
        causes={"absences": 4, "intemperies": 2},
        actions_recommandees=["Renfort d'équipes", "Heures supplémentaires"],
    )

    assert alerte.id is not None
    assert alerte.projet == projet
    assert alerte.lot == lot
    assert alerte.niveau == NiveauAlerteRetard.ELEVE
    assert alerte.delta_pts == Decimal("17.50")
    assert alerte.indice_sante is None
    assert alerte.date_detection == date(2026, 10, 20)
    assert alerte.statut == StatutAlerteRetard.OUVERTE
    assert alerte.causes == {"absences": 4, "intemperies": 2}
    assert alerte.actions_recommandees == ["Renfort d'équipes", "Heures supplémentaires"]
    assert not alerte.est_supprime

    # Relations inverses
    assert alerte in projet.alertes_retard.all()
    assert alerte in lot.alertes_retard.all()


@pytest.mark.django_db
def test_creation_alerte_projet_lot_null(schema_demo):
    """Vérifie la création d'une alerte au niveau projet (lot nul)."""
    projet = Projet.objects.create(
        reference="PRJ-AL-002",
        nom="Tour Ivoire",
        ville="Bouaké",
    )

    alerte = AlerteRetard.objects.create(
        projet=projet,
        lot=None,
        niveau=NiveauAlerteRetard.CRITIQUE,
        indice_sante=35,
        date_detection=date(2026, 10, 20),
    )

    assert alerte.id is not None
    assert alerte.projet == projet
    assert alerte.lot is None
    assert alerte.niveau == NiveauAlerteRetard.CRITIQUE
    assert alerte.indice_sante == 35
    assert alerte.delta_pts is None
    assert alerte in projet.alertes_retard.all()


@pytest.mark.django_db
def test_valeurs_par_defaut(schema_demo):
    """Vérifie que les valeurs par défaut sont correctement positionnées."""
    projet = Projet.objects.create(
        reference="PRJ-AL-003",
        nom="Échangeur Nord",
        ville="Yamoussoukro",
    )

    alerte = AlerteRetard.objects.create(
        projet=projet,
        niveau=NiveauAlerteRetard.MODERE,
        date_detection=date(2026, 10, 20),
    )
    alerte.refresh_from_db()

    assert alerte.statut == StatutAlerteRetard.OUVERTE
    assert alerte.statut == "OUVERTE"
    assert alerte.causes == {}
    assert alerte.actions_recommandees == []
    assert alerte.commentaire_resolution == ""
    assert alerte.lot is None
    assert alerte.delta_pts is None
    assert alerte.indice_sante is None
    assert alerte.resolue_par is None
    assert alerte.resolue_le is None
    assert alerte.destinataires.count() == 0
    assert alerte.supprime_le is None


@pytest.mark.django_db
def test_destinataires_many_to_many(schema_demo):
    """Vérifie l'association de destinataires et la relation inverse."""
    projet = Projet.objects.create(
        reference="PRJ-AL-004",
        nom="Hôpital Régional",
        ville="Korhogo",
    )
    user1 = Utilisateur.objects.create_user(
        email="ct_alerte@demo.ci",
        nom="Kouamé",
        prenom="CT",
    )
    user2 = Utilisateur.objects.create_user(
        email="cp_alerte@demo.ci",
        nom="Diallo",
        prenom="CP",
    )

    alerte = AlerteRetard.objects.create(
        projet=projet,
        niveau=NiveauAlerteRetard.MODERE,
        date_detection=date(2026, 10, 20),
    )
    alerte.destinataires.add(user1, user2)

    assert alerte.destinataires.count() == 2
    assert set(alerte.destinataires.all()) == {user1, user2}
    assert alerte in user1.alertes_retard_recues.all()
    assert alerte in user2.alertes_retard_recues.all()


@pytest.mark.django_db
def test_resolution_alerte(schema_demo):
    """Vérifie la mise à jour du statut lors de la résolution."""
    projet = Projet.objects.create(
        reference="PRJ-AL-005",
        nom="Pont Métallique",
        ville="San Pedro",
    )
    resoluteur = Utilisateur.objects.create_user(
        email="do_alerte@demo.ci",
        nom="Koffi",
        prenom="DO",
    )
    alerte = AlerteRetard.objects.create(
        projet=projet,
        niveau=NiveauAlerteRetard.ELEVE,
        date_detection=date(2026, 10, 20),
    )

    moment_resolution = timezone.now()
    alerte.statut = StatutAlerteRetard.RESOLUE
    alerte.resolue_par = resoluteur
    alerte.resolue_le = moment_resolution
    alerte.commentaire_resolution = "Équipes renforcées avec succès."
    alerte.save()

    alerte.refresh_from_db()
    assert alerte.statut == StatutAlerteRetard.RESOLUE
    assert alerte.resolue_par == resoluteur
    assert alerte.resolue_le is not None
    assert alerte.commentaire_resolution == "Équipes renforcées avec succès."
    assert alerte in resoluteur.alertes_retard_resolues.all()


@pytest.mark.django_db
def test_str_representation(schema_demo):
    """Vérifie la représentation textuelle de l'alerte."""
    projet = Projet.objects.create(
        reference="PRJ-AL-006",
        nom="Stade Municipal",
        ville="Daloa",
    )
    lot = Lot.objects.create(
        projet=projet,
        code="LOT-02",
        libelle="Électricité",
    )

    alerte_lot = AlerteRetard.objects.create(
        projet=projet,
        lot=lot,
        niveau=NiveauAlerteRetard.ELEVE,
        date_detection=date(2026, 10, 20),
    )
    assert "ELEVE" in str(alerte_lot)
    assert "LOT-02" in str(alerte_lot)

    alerte_projet = AlerteRetard.objects.create(
        projet=projet,
        lot=None,
        niveau=NiveauAlerteRetard.CRITIQUE,
        date_detection=date(2026, 10, 20),
    )
    assert "CRITIQUE" in str(alerte_projet)
    assert "PRJ-AL-006" in str(alerte_projet)


@pytest.mark.django_db
def test_ordering(schema_demo):
    """Vérifie le tri par défaut par date_detection décroissante."""
    projet = Projet.objects.create(
        reference="PRJ-AL-007",
        nom="Centre Commercial",
        ville="Abidjan",
    )
    a1 = AlerteRetard.objects.create(
        projet=projet,
        niveau=NiveauAlerteRetard.MODERE,
        date_detection=date(2026, 10, 10),
    )
    a2 = AlerteRetard.objects.create(
        projet=projet,
        niveau=NiveauAlerteRetard.ELEVE,
        date_detection=date(2026, 10, 20),
    )

    alertes = list(AlerteRetard.objects.filter(projet=projet))
    assert alertes == [a2, a1]
