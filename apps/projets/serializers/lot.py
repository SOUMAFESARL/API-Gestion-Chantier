"""Création indépendante de lots pour un projet existant."""

from rest_framework import serializers

from apps.core.enums import ModeExecution, TypeBordereau
from apps.projets.models import Lot


class LotCreationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=200, source="libelle")
    mode_execution = serializers.ChoiceField(choices=ModeExecution.choices)
    type_bordereau = serializers.ChoiceField(choices=TypeBordereau.choices)
    budget_initial_montant = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=9223372036854775807,
        help_text="Centimes de FCFA ; facultatif. Multiplier les FCFA saisis par 100.",
    )
    date_debut_prevue = serializers.DateField(required=False, allow_null=True)
    date_fin_prevue = serializers.DateField(required=False, allow_null=True)

    def to_internal_value(self, data):
        inconnus = set(data.keys()) - set(self.fields)
        if inconnus:
            raise serializers.ValidationError(dict.fromkeys(inconnus, "Champ non accepté."))
        return super().to_internal_value(data)

    def validate(self, attrs):
        debut = attrs.get("date_debut_prevue")
        fin = attrs.get("date_fin_prevue")
        if debut and fin and fin < debut:
            raise serializers.ValidationError({"date_fin_prevue": "Fin avant début interdite."})
        return attrs


class LotResponseSerializer(serializers.ModelSerializer):
    nom = serializers.CharField(source="libelle", read_only=True)

    class Meta:
        model = Lot
        fields = (
            "id",
            "projet",
            "code",
            "nom",
            "mode_execution",
            "type_bordereau",
            "budget_initial_montant",
            "date_debut_prevue",
            "date_fin_prevue",
            "avancement",
            "ordre",
            "est_actif",
        )
        read_only_fields = fields
