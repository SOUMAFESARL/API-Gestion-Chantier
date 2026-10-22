"""Serializers pour le calendrier d'entreprise — SFD F3 §6 & Erratum E-4."""

from __future__ import annotations

from datetime import date

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.projets.models.calendrier import ExceptionCalendrier, SemaineType

__all__ = [
    "CalendrierQuerySerializer",
    "CalendrierResponseSerializer",
    "ExceptionCalendrierCreateSerializer",
    "ExceptionCalendrierResponseSerializer",
    "JourFerieResponseSerializer",
    "SemaineTypeSerializer",
    "SemaineTypeUpdateSerializer",
]


class SemaineTypeSerializer(serializers.ModelSerializer):
    """Sérialiseur de la semaine type (7 booléens)."""

    class Meta:
        model = SemaineType
        fields = [
            "lundi",
            "mardi",
            "mercredi",
            "jeudi",
            "vendredi",
            "samedi",
            "dimanche",
        ]


class SemaineTypeUpdateSerializer(serializers.Serializer):
    """Sérialiseur de modification partielle de la semaine type.

    Refuse une configuration sans aucun jour travaillé (ErreurMetier, 422).
    """

    lundi = serializers.BooleanField(required=False)
    mardi = serializers.BooleanField(required=False)
    mercredi = serializers.BooleanField(required=False)
    jeudi = serializers.BooleanField(required=False)
    vendredi = serializers.BooleanField(required=False)
    samedi = serializers.BooleanField(required=False)
    dimanche = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        instance = getattr(self, "instance", None)
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        valeurs = {}
        for j in jours:
            if j in attrs:
                valeurs[j] = attrs[j]
            elif instance is not None:
                valeurs[j] = getattr(instance, j)
            else:
                valeurs[j] = False
        if not any(valeurs.values()):
            raise ErreurMetier("La semaine type doit comporter au moins un jour travaillé.")
        return attrs


class JourFerieResponseSerializer(serializers.Serializer):
    """Jour férié national pour la consultation du calendrier."""

    date = serializers.DateField()
    libelle = serializers.CharField(max_length=100)


class ExceptionCalendrierResponseSerializer(serializers.ModelSerializer):
    """Exception de calendrier d'entreprise (lecture)."""

    id = serializers.UUIDField()
    date = serializers.DateField()
    ouvre = serializers.BooleanField()
    motif = serializers.CharField(max_length=150)

    class Meta:
        model = ExceptionCalendrier
        fields = ["id", "date", "ouvre", "motif"]


class ExceptionCalendrierCreateSerializer(serializers.ModelSerializer):
    """Création d'une exception de calendrier (écriture)."""

    date = serializers.DateField()
    ouvre = serializers.BooleanField()
    motif = serializers.CharField(max_length=150, allow_blank=False, trim_whitespace=True)

    class Meta:
        model = ExceptionCalendrier
        fields = ["date", "ouvre", "motif"]

    def validate_motif(self, value: str) -> str:
        motif = value.strip()
        if not motif:
            raise serializers.ValidationError(_("Le motif est obligatoire."))
        if len(motif) > 150:
            raise serializers.ValidationError(
                _("Le motif ne peut pas dépasser 150 caractères.")
            )
        return motif

    def validate(self, attrs: dict) -> dict:
        date_val = attrs.get("date")
        if (
            date_val
            and ExceptionCalendrier.objects.filter(
                date=date_val,
                supprime_le__isnull=True,
            ).exists()
        ):
            raise ErreurConflit("Une exception active existe déjà pour cette date.")
        return attrs


class CalendrierResponseSerializer(serializers.Serializer):
    """Réponse globale de consultation du calendrier d'entreprise sur une période."""

    semaine_type = SemaineTypeSerializer()
    feries_nationaux = JourFerieResponseSerializer(many=True)
    exceptions = ExceptionCalendrierResponseSerializer(many=True)


class CalendrierQuerySerializer(serializers.Serializer):
    """Paramètres de filtrage par période pour la consultation du calendrier."""

    debut = serializers.DateField(required=False)
    fin = serializers.DateField(required=False)

    def validate(self, attrs: dict) -> dict:
        debut = attrs.get("debut")
        fin = attrs.get("fin")
        today = timezone.localdate()

        if debut is None and fin is None:
            debut = date(today.year, 1, 1)
            fin = date(today.year, 12, 31)
        elif debut is None:
            debut = date(fin.year, 1, 1)
        elif fin is None:
            fin = date(debut.year, 12, 31)

        if fin < debut:
            raise serializers.ValidationError(
                {"fin": _("La date de fin doit être postérieure ou égale à la date de début.")}
            )

        if (fin - debut).days + 1 > 366:
            raise serializers.ValidationError(
                {"periode": _("La période demandée ne peut pas dépasser 366 jours.")}
            )

        attrs["debut"] = debut
        attrs["fin"] = fin
        return attrs
