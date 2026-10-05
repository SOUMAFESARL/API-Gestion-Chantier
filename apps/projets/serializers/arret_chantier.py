"""Serializers pour la gestion des arrêts de chantier."""

from rest_framework import serializers

from apps.projets.models import ArretChantier


class ArretChantierSerializer(serializers.ModelSerializer):
    """Représentation complète d'un arrêt de chantier."""

    declare_par_nom = serializers.SerializerMethodField()
    est_en_cours = serializers.SerializerMethodField()

    class Meta:
        model = ArretChantier
        fields = [
            "id",
            "projet",
            "date_debut",
            "date_fin",
            "motif",
            "declare_par",
            "declare_par_nom",
            "est_en_cours",
            "cree_le",
            "modifie_le",
        ]
        read_only_fields = [
            "id",
            "projet",
            "declare_par",
            "declare_par_nom",
            "est_en_cours",
            "cree_le",
            "modifie_le",
        ]

    def get_declare_par_nom(self, obj) -> str:
        if obj.declare_par:
            nom_complet = f"{obj.declare_par.prenom} {obj.declare_par.nom}".strip()
            return nom_complet or obj.declare_par.email
        return ""

    def get_est_en_cours(self, obj) -> bool:
        return obj.date_fin is None


class ArretChantierCreateSerializer(serializers.Serializer):
    """Payload de déclaration d'un arrêt de chantier."""

    date_debut = serializers.DateField(help_text="Date de début effectif de l'arrêt.")
    date_fin = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date de fin/reprise (optionnelle, nulle si arrêt en cours).",
    )
    motif = serializers.CharField(help_text="Motif de l'arrêt ou de la suspension.")

    def validate(self, attrs):
        debut = attrs.get("date_debut")
        fin = attrs.get("date_fin")
        if fin and debut and fin < debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )
        return attrs


class ArretChantierUpdateSerializer(serializers.Serializer):
    """Payload de modification d'un arrêt de chantier."""

    date_debut = serializers.DateField(required=False, help_text="Date de début de l'arrêt.")
    date_fin = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date de fin/reprise (nulle si toujours en cours).",
    )
    motif = serializers.CharField(required=False, help_text="Motif de l'arrêt.")

    def validate(self, attrs):
        debut = attrs.get("date_debut")
        fin = attrs.get("date_fin")
        if fin and debut and fin < debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )
        return attrs
