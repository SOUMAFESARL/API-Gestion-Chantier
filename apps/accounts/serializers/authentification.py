from rest_framework import serializers

from apps.accounts.models import Utilisateur


class InscriptionSerializer(serializers.ModelSerializer):
    mot_de_passe = serializers.CharField(
        write_only=True,
        min_length=8,
    )
    confirmation_mot_de_passe = serializers.CharField(
        write_only=True,
    )

    class Meta:
        model = Utilisateur
        fields = [
            "email",
            "nom",
            "prenom",
            "telephone",
            "langue",
            "mot_de_passe",
            "confirmation_mot_de_passe",
        ]

    def validate(self, attrs):
        if attrs["mot_de_passe"] != attrs["confirmation_mot_de_passe"]:
            raise serializers.ValidationError(
                {"confirmation_mot_de_passe": ("Les mots de passe ne correspondent pas.")}
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop("confirmation_mot_de_passe")
        password = validated_data.pop("mot_de_passe")

        utilisateur = Utilisateur.objects.create_user(
            password=password,
            **validated_data,
        )

        return utilisateur
