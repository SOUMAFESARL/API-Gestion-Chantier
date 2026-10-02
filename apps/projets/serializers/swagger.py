"""Creation form and update contracts."""

from rest_framework import serializers

from apps.core.enums import TypeProjet
from apps.projets.models import Projet
from apps.projets.serializers import ProjetCreationSerializer

CHAMPS_FORMULAIRE = (
    "nom",
    "reference",
    "type_projet",
    "ville",
    "maitre_ouvrage",
    "maitre_oeuvre",
    "date_debut_prevue",
    "date_fin_prevue",
    "duree_jours_ouvres",
    "budget_initial_montant",
    "description",
)


class ProjetPostSerializer(ProjetCreationSerializer):
    """Only visible fields; reference and duration are generated."""

    reference = serializers.CharField(read_only=True)
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)
    type_projet = serializers.ChoiceField(choices=TypeProjet.choices)
    maitre_ouvrage = serializers.CharField(max_length=200)

    def get_fields(self):
        fields = super().get_fields()
        return {name: fields[name] for name in CHAMPS_FORMULAIRE}

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            errors = dict.fromkeys(
                data.keys() - self.fields.keys(), "Ce champ n'est pas accepte a la creation."
            )
            for name in ("reference", "duree_jours_ouvres"):
                if name in data:
                    errors[name] = "Ce champ est calcule automatiquement."
            if errors:
                raise serializers.ValidationError(errors)
        return super().to_internal_value(data)


class ProjetCreationResponseSerializer(serializers.ModelSerializer):
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Projet
        fields = CHAMPS_FORMULAIRE
        read_only_fields = CHAMPS_FORMULAIRE


class ProjetPatchSerializer(ProjetPostSerializer):
    """Same visible fields for PUT and PATCH."""

    def validate(self, attrs):
        if self.instance is not None and not self.partial:
            attrs.setdefault("date_debut_prevue", None)
            attrs.setdefault("date_fin_prevue", None)
        attrs = super().validate(attrs)
        if self.instance is not None and not self.partial:
            for name, default in (
                ("maitre_oeuvre", ""),
                ("description", ""),
                ("budget_initial_montant", None),
                ("date_debut_prevue", None),
                ("date_fin_prevue", None),
            ):
                attrs.setdefault(name, default)
            debut = attrs["date_debut_prevue"]
            fin = attrs["date_fin_prevue"]
            if debut and fin and fin <= debut:
                raise serializers.ValidationError({"date_fin_prevue": "Fin apres debut requise."})
        return attrs
