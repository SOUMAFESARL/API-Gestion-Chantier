from rest_framework import serializers

from apps.accounts.models import Appareil


class AppareilSerializer(serializers.ModelSerializer):
    type_appareil_display = serializers.CharField(
        source="get_type_appareil_display",
        read_only=True,
    )

    class Meta:
        model = Appareil
        fields = [
            "id",
            "utilisateur",
            "type_appareil",
            "type_appareil_display",
            "jeton_push",
            "identifiant_materiel",
            "derniere_activite",
            "cree_le",
            "modifie_le",
        ]

        read_only_fields = [
            "id",
            "type_appareil_display",
            "derniere_activite",
            "cree_le",
            "modifie_le",
        ]
