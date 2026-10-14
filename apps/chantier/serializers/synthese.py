"""Contrats de la synthèse périodique (ChargeSynthese côté frontend)."""

import calendar
from datetime import timedelta

from rest_framework import serializers as s

from apps.chantier.serializers.journal import StrictSerializer, texte

TYPES_PERIODE = ["HEBDOMADAIRE", "MENSUELLE", "PERSONNALISEE"]

#: Une synthèse personnalisée couvre au plus une année.
DUREE_MAX_JOURS = 366


class DemandeSyntheseSerializer(StrictSerializer):
    """La période d'un chantier, telle que le frontend la met dans l'adresse.

    Une semaine va du lundi au vendredi, un mois du premier au dernier jour :
    ce sont les deux périodes qui se signent, et qu'on ne doit pas pouvoir
    signer deux fois sous deux bornes différentes.
    """

    projet = s.UUIDField()
    type = s.ChoiceField(choices=TYPES_PERIODE)
    date_debut = s.DateField()
    date_fin = s.DateField()

    def validate(self, attrs):
        from apps.chantier.services.journal import aujourdhui

        debut, fin, type_ = attrs["date_debut"], attrs["date_fin"], attrs["type"]
        if fin < debut:
            raise s.ValidationError({"date_fin": "La fin précède le début."})
        if debut > aujourdhui():
            raise s.ValidationError({"date_debut": "Une période future ne se synthétise pas."})
        if type_ == "HEBDOMADAIRE" and (debut.weekday() != 0 or fin != debut + timedelta(days=4)):
            raise s.ValidationError(
                {"date_debut": "Une semaine de chantier va du lundi au vendredi."}
            )
        if type_ == "MENSUELLE":
            dernier = calendar.monthrange(debut.year, debut.month)[1]
            if debut.day != 1 or fin != debut.replace(day=dernier):
                raise s.ValidationError(
                    {"date_debut": "Un mois va de son premier à son dernier jour."}
                )
        if (fin - debut).days > DUREE_MAX_JOURS:
            raise s.ValidationError({"date_fin": "Une synthèse couvre au plus 366 jours."})
        return attrs


class ObjectifSuivantSerializer(StrictSerializer):
    lot_code = texte(20)
    activite = s.CharField(max_length=300)
    objectif = s.CharField(max_length=300)
    cible = s.FloatField(min_value=0, max_value=100)
    prerequis = texte(1000)


class RedactionSyntheseSerializer(DemandeSyntheseSerializer):
    """Ce qu'écrit le conducteur de travaux : son appréciation et les objectifs suivants."""

    appreciation = texte(10000)
    objectifs = ObjectifSuivantSerializer(many=True, required=False, default=list, max_length=30)
