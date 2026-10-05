"""Validation sans PostgreSQL : contrats PATCH et règles métier."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from apps.projets.models import AffectationProjet
from apps.projets.serializers.activite import ActiviteModificationSerializer
from apps.projets.serializers.lot import ActivationSerializer, LotModificationSerializer


@pytest.fixture
def objets(monkeypatch):
    monkeypatch.setattr(AffectationProjet.objects, "filter", Mock())
    AffectationProjet.objects.filter.return_value.values_list.return_value = []
    enfants = Mock()
    enfants.all.return_value.filter.return_value.exists.return_value = False
    lot = SimpleNamespace(
        pk=uuid4(),
        projet_id=uuid4(),
        projet=SimpleNamespace(chef_projet_id=None, conducteur_travaux_id=None),
        libelle="Lot",
        mode_execution="REGIE",
        type_bordereau="FORFAIT",
        budget_initial_montant=None,
        date_debut_prevue=date(2026, 10, 1),
        date_fin_prevue=date(2026, 10, 31),
        date_debut_reelle=date(2026, 10, 2),
        date_fin_reelle=date(2026, 10, 10),
        activites=enfants,
    )
    successeurs = Mock()
    successeurs.filter.return_value.exists.return_value = False
    activite = SimpleNamespace(
        pk=uuid4(),
        libelle="Activité",
        dependance=None,
        budget_initial_montant=None,
        unite="U",
        quantite_prevue=Decimal("10"),
        quantite_realisee=Decimal("0"),
        poids=None,
        date_debut_prevue=date(2026, 10, 5),
        date_fin_prevue=date(2026, 10, 10),
        ordre=1,
        successeurs=successeurs,
    )
    return lot, activite


@pytest.mark.parametrize("ressource", ["lot", "activite"])
def test_partial_rename_does_not_inject_defaults(objets, ressource):
    lot, activite = objets
    serializer = (
        LotModificationSerializer(lot, data={"nom": "Nouveau"}, partial=True)
        if ressource == "lot"
        else ActiviteModificationSerializer(
            activite, data={"libelle": "Nouveau"}, partial=True, context={"lot": lot}
        )
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"libelle": "Nouveau"}


@pytest.mark.parametrize("ressource", ["lot", "activite"])
@pytest.mark.parametrize(
    "data",
    [
        {"date_fin_prevue": "2026-10-11"},
        {"date_fin_prevue": None},
        {"budget_initial_montant": -1},
        {"est_actif": False},
        {"avancement": 10},
    ],
)
def test_invalid_or_protected_fields_rejected(objets, ressource, data):
    lot, activite = objets
    serializer = (
        LotModificationSerializer(lot, data=data, partial=True)
        if ressource == "lot"
        else ActiviteModificationSerializer(activite, data=data, partial=True, context={"lot": lot})
    )
    assert not serializer.is_valid()


def test_partial_real_dates_use_existing_start(objets):
    lot, _ = objets
    serializer = LotModificationSerializer(
        lot, data={"date_fin_reelle": "2026-10-01"}, partial=True
    )
    assert not serializer.is_valid()
    assert "date_fin_reelle" in serializer.errors


def test_initial_dates_and_lot_bounds(objets):
    lot, activite = objets
    activite.date_debut_prevue = None
    activite.date_fin_prevue = None
    serializer = ActiviteModificationSerializer(
        activite,
        data={"date_debut_prevue": "2026-09-30"},
        partial=True,
        context={"lot": lot},
    )
    assert not serializer.is_valid()
    serializer = ActiviteModificationSerializer(
        activite,
        data={"date_debut_prevue": "2026-10-05"},
        partial=True,
        context={"lot": lot},
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"date_debut_prevue": date(2026, 10, 5)}


def test_quantity_and_forfait_validation(objets):
    lot, activite = objets
    serializer = ActiviteModificationSerializer(
        activite, data={"unite": "FORFAIT"}, partial=True, context={"lot": lot}
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["quantite_prevue"] == 1
    activite.quantite_realisee = Decimal("5")
    serializer = ActiviteModificationSerializer(
        activite, data={"quantite_prevue": "4"}, partial=True, context={"lot": lot}
    )
    assert not serializer.is_valid()


def test_dependency_cycle_and_successor_dates(objets):
    lot, activite = objets
    suivant = SimpleNamespace(
        pk=uuid4(),
        projet_id=lot.projet_id,
        est_actif=True,
        date_fin_prevue=None,
        dependance=activite,
    )
    serializer = ActiviteModificationSerializer(activite, partial=True, context={"lot": lot})
    with pytest.raises(ValidationError, match="cyclique"):
        serializer.validate({"dependance": suivant})
    activite.successeurs.filter.return_value.exists.return_value = True
    with pytest.raises(ValidationError, match="suivante"):
        serializer.validate({"libelle": "Nouveau"})


@pytest.mark.parametrize(
    "data", [{}, {"est_actif": None}, {"est_actif": "invalide"}, {"est_actif": True, "nom": "X"}]
)
def test_activation_rejects_missing_invalid_and_unknown_fields(data):
    assert not ActivationSerializer(data=data).is_valid()


@pytest.mark.parametrize("etat", [True, False])
def test_activation_accepts_both_states(etat):
    serializer = ActivationSerializer(data={"est_actif": etat})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["est_actif"] is etat
