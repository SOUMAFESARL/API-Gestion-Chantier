"""Champs partagés de l'exécution d'une case : le mode d'exécution et son libellé."""

from rest_framework import serializers

__all__ = ["ModeExecutionField", "ModeExecutionLibelleMixin"]


class ModeExecutionField(serializers.CharField):
    """Un code du référentiel des modes d'exécution, ou déjà porté par une case (400 sinon)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 60)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        from apps.projets.services.referentiels import (
            code_mode_execution_valide,
            table_modes_execution,
        )

        valeur = super().to_internal_value(data)
        if valeur and not code_mode_execution_valide(valeur, table_modes_execution(self.context)):
            raise serializers.ValidationError(
                "Choisissez un mode d'exécution dans la liste, ou ajoutez-le."
            )
        return valeur


class ModeExecutionLibelleMixin(serializers.Serializer):
    """Ajoute `mode_execution_libelle` ; la table des libellés se calcule une fois par requête."""

    mode_execution_libelle = serializers.SerializerMethodField()

    def get_mode_execution_libelle(self, obj) -> str:
        from apps.projets.services.referentiels import libelle_mode_execution, table_modes_execution

        table = table_modes_execution(self.context)
        return libelle_mode_execution(obj.mode_execution, table)
