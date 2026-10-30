"""Entrées du back-office des listes de valeurs et des modèles de découpage de la plateforme.

Les corps reprennent ceux des routes de l'entreprise (`apps.projets.serializers.decoupage`) :
un même tableau (niveaux et lignes types) construit un modèle chez le super admin comme dans
l'entreprise (décisions v1.2, §3.10). Seul ajout : un modèle plateforme peut être désactivé
(`est_actif`), et une liste ou une valeur se corrige.
"""

from rest_framework import serializers

from apps.projets.serializers.decoupage import (
    AjoutValeursSerializer,
    CreationListeSerializer,
    ModeleEnregistrementSerializer,
)

__all__ = [
    "AjoutValeursSerializer",
    "CreationListeSerializer",
    "ModelePlateformeEnregistrementSerializer",
    "ModificationListeSerializer",
    "ModificationValeurSerializer",
]


class ModificationListeSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)


class ModificationValeurSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=200, required=False)
    groupe = serializers.CharField(max_length=100, required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)


class ModelePlateformeEnregistrementSerializer(ModeleEnregistrementSerializer):
    est_actif = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Faux : le modèle n'est plus proposé aux entreprises, sans être retiré.",
    )
