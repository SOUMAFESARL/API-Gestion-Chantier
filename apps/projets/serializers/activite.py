"""Serializers pour la gestion des activités de lot (MLD §6.3)."""

from decimal import Decimal
from rest_framework import serializers

from apps.core.enums import UniteMesure
from apps.projets.models import Activite, Lot


class ActiviteSerializer(serializers.ModelSerializer):
    """Lecture complète d'une activité de chantier."""

    unite_libelle = serializers.CharField(source="get_unite_display", read_only=True)

    class Meta:
        model = Activite
        fields = [
            "id",
            "lot_id",
            "libelle",
            "unite",
            "unite_libelle",
            "quantite_prevue",
            "quantite_realisee",
            "avancement",
            "poids",
            "date_debut_prevue",
            "date_fin_prevue",
            "date_debut_baseline",
            "date_fin_baseline",
            "ordre",
            "est_actif",
            "cree_le",
        ]
        read_only_fields = [
            "id",
            "lot_id",
            "quantite_realisee",
            "avancement",
            "date_debut_baseline",
            "date_fin_baseline",
            "cree_le",
        ]


class ActiviteCreationSerializer(serializers.ModelSerializer):
    """Création d'une activité rattachée à un lot."""

    class Meta:
        model = Activite
        fields = [
            "libelle",
            "unite",
            "quantite_prevue",
            "poids",
            "date_debut_prevue",
            "date_fin_prevue",
            "ordre",
        ]

    def validate(self, attrs):
        lot = self.context.get("lot")
        if not lot:
            raise serializers.ValidationError("Le lot de rattachement est requis.")

        debut = attrs.get("date_debut_prevue")
        fin = attrs.get("date_fin_prevue")

        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                {"date_fin_prevue": "La date de fin prévue doit être postérieure à la date de début."}
            )

        # Vérification des bornes du Lot parent
        if lot.date_debut_prevue and debut and debut < lot.date_debut_prevue:
            raise serializers.ValidationError(
                {
                    "date_debut_prevue": (
                        f"L'activité ne peut pas débuter avant la date de début du lot "
                        f"({lot.date_debut_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
        if lot.date_fin_prevue and fin and fin > lot.date_fin_prevue:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": (
                        f"L'activité ne peut pas se terminer après la date de fin du lot "
                        f"({lot.date_fin_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )

        unite = attrs.get("unite", UniteMesure.UNITE)
        quantite = attrs.get("quantite_prevue")
        if unite == UniteMesure.FORFAIT and quantite != Decimal("1.000"):
            attrs["quantite_prevue"] = Decimal("1.000")

        return attrs

    def create(self, validated_data):
        lot = self.context["lot"]
        request = self.context.get("request")
        utilisateur = getattr(request, "user", None)
        return Activite.objects.create(
            lot=lot,
            cree_par=utilisateur,
            **validated_data,
        )
