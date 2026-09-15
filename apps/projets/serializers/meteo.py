"""Serializers pour la météo et le référentiel des localités."""

from rest_framework import serializers


class MeteoResponseSerializer(serializers.Serializer):
    """Relevé météo temps réel pour la barre d'application ou le tableau de bord."""

    disponible = serializers.BooleanField(
        help_text="True si le relevé de température a pu être obtenu."
    )
    raison = serializers.CharField(
        required=False, allow_null=True, help_text="Raison de l'indisponibilité éventuelle."
    )
    ville = serializers.CharField(help_text="Nom de la ville / commune du relevé.")
    portee = serializers.CharField(help_text="CHANTIER ou ENTREPRISE.")
    temperature = serializers.FloatField(
        required=False, allow_null=True, help_text="Température en °C."
    )
    condition = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Code météo (DEGAGE, NUAGEUX, PLUIE, ORAGE, etc.).",
    )
    code_wmo = serializers.IntegerField(
        required=False, allow_null=True, help_text="Code WMO d'origine."
    )
    praticable = serializers.BooleanField(
        help_text="Indique si les travaux de chantier sont praticables."
    )
    alerte = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Code d'alerte (VIGILANCE_PLUIE, INTEMPERIES, ORAGE).",
    )
    releve_le = serializers.CharField(
        required=False, allow_null=True, help_text="Horodatage ISO de la mesure."
    )


class ReferentielVillesResponseSerializer(serializers.Serializer):
    """Liste des localités répertoriées pour un pays donné."""

    pays = serializers.CharField(help_text="Code pays ISO à deux lettres.")
    agglomeration = serializers.CharField(
        required=False, allow_null=True, help_text="Nom de l'agglomération découpée en communes."
    )
    localites = serializers.ListField(
        child=serializers.CharField(), help_text="Liste des villes ou communes sélectionnables."
    )
