"""Création indépendante de lots pour un projet existant."""

from rest_framework import serializers

from apps.core.enums import ModeExecution, TypeBordereau
from apps.projets.models import Lot
from apps.projets.services.statistiques import statistiques_lots


class LotCreationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=200, source="libelle")
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        help_text="Motif informatif facultatif ; texte libre, chaîne vide pour l'effacer.",
    )
    statut = serializers.CharField(
        required=False,
        trim_whitespace=False,
        help_text="Statut d'évolution libre envoyé par le frontend ; chaîne non vide.",
    )
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
    date_debut_reelle = serializers.DateField(required=False, allow_null=True)
    date_fin_reelle = serializers.DateField(required=False, allow_null=True)

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
        debut_reel = attrs.get("date_debut_reelle")
        fin_reelle = attrs.get("date_fin_reelle")
        if debut_reel and fin_reelle and fin_reelle < debut_reel:
            raise serializers.ValidationError({"date_fin_reelle": "Fin avant début interdite."})
        return attrs


class LotModificationSerializer(LotCreationSerializer):
    """Valide le résultat du PATCH sans réécrire les champs absents."""

    def validate(self, attrs):
        for champ in ("date_debut_prevue", "date_fin_prevue"):
            ancienne = getattr(self.instance, champ)
            if champ in attrs and ancienne is not None and attrs[champ] != ancienne:
                raise serializers.ValidationError(
                    {champ: "RG-11 : reprogrammez le lot avec motif et justification."}
                )
        valeurs = {
            champ.source: getattr(self.instance, champ.source) for champ in self.fields.values()
        }
        valeurs.update(attrs)
        super().validate(valeurs)
        debut = valeurs.get("date_debut_prevue")
        fin = valeurs.get("date_fin_prevue")
        activites = self.instance.activites.all()
        if debut and activites.filter(date_debut_prevue__lt=debut).exists():
            raise serializers.ValidationError(
                {"date_debut_prevue": "Une activité débute avant cette date."}
            )
        if fin and activites.filter(date_fin_prevue__gt=fin).exists():
            raise serializers.ValidationError(
                {"date_fin_prevue": "Une activité finit après cette date."}
            )
        return attrs

    def update(self, instance, validated_data):
        for champ, valeur in validated_data.items():
            setattr(instance, champ, valeur)
        instance.save()
        return instance


class ActivationSerializer(serializers.Serializer):
    est_actif = serializers.BooleanField(required=True)

    def to_internal_value(self, data):
        inconnus = set(data.keys()) - set(self.fields)
        if inconnus:
            raise serializers.ValidationError(dict.fromkeys(inconnus, "Champ non accepté."))
        return super().to_internal_value(data)


class LotResponseSerializer(serializers.ModelSerializer):
    projet_id = serializers.UUIDField(read_only=True)
    nom = serializers.CharField(source="libelle", read_only=True)
    statut = serializers.CharField(read_only=True)
    avancement = serializers.SerializerMethodField()
    activites_count = serializers.SerializerMethodField()

    def get_avancement(self, obj) -> float:
        return statistiques_lots([obj])["avancement_pondere"]

    def get_activites_count(self, obj) -> int:
        return statistiques_lots([obj])["activites_count"]

    class Meta:
        model = Lot
        fields = (
            "id",
            "projet_id",
            "code",
            "nom",
            "motif",
            "statut",
            "mode_execution",
            "type_bordereau",
            "budget_initial_montant",
            "date_debut_prevue",
            "date_fin_prevue",
            "date_debut_reelle",
            "date_fin_reelle",
            "avancement",
            "activites_count",
            "ordre",
            "est_actif",
        )
        read_only_fields = fields
