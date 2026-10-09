"""Validation pure des payloads : exécution rapide sans PostgreSQL."""

import pytest

from apps.chantier.serializers.journal import SaisieJournalSerializer


@pytest.mark.parametrize(
    "champ,valeur",
    [
        ("meteo", {"humidite": -1}),
        ("effectifs", [{"prevus": 3, "presents": 4}]),
        ("effectifs", [{"prevus": 4, "presents": 3, "retards": 4}]),
        ("production", [{"activite_id": "pas-un-uuid", "prix_unitaire": -1}]),
        ("photos", [{"cle": str(i)} for i in range(6)]),
        ("pieces_jointes", [{"cle": str(i)} for i in range(4)]),
        ("statut", "APPROUVE_CP"),
    ],
)
def test_entrees_invalides(champ, valeur):
    serializer = SaisieJournalSerializer(
        data={
            "projet_id": "c872c588-ec75-4776-9ebd-f0dcf44a84d7",
            "date": "2026-10-07",
            champ: valeur,
        }
    )
    assert not serializer.is_valid()
    assert champ in serializer.errors


def test_brouillon_vide_conserve_nombres_non_renseignes():
    serializer = SaisieJournalSerializer(
        data={
            "projet_id": "c872c588-ec75-4776-9ebd-f0dcf44a84d7",
            "date": "2026-10-07",
            "effectifs": [{"categorie": "Maçons"}],
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.data["effectifs"][0]["presents"] is None
    assert serializer.data["photos"] == []
