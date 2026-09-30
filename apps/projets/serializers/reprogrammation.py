"""Serializers pour la reprogrammation de dates et l'historique (US-033, RG-11)."""

from rest_framework import serializers

from apps.projets.models import HistoriqueDate, MotifReport


class MotifReportSerializer(serializers.ModelSerializer):
    """Représentation d'un motif dynamique de report de date."""

    class Meta:
        model = MotifReport
        fields = ["id", "code", "libelle", "description", "est_actif", "ordre"]
        read_only_fields = ["id"]


class MotifReportCreationSerializer(serializers.ModelSerializer):
    """Création d'un motif dynamique de report."""

    class Meta:
        model = MotifReport
        fields = ["code", "libelle", "description", "est_actif", "ordre"]

    def validate_code(self, value: str) -> str:
        code_propre = value.strip().upper()
        if MotifReport.objects.filter(code=code_propre, supprime_le__isnull=True).exists():
            raise serializers.ValidationError("Un motif avec ce code existe déjà.")
        return code_propre


class ReprogrammationRequestSerializer(serializers.Serializer):
    """Payload attendu lors de la reprogrammation d'une date (Approche A)."""

    date_debut_prevue = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Nouvelle date de début prévue (facultatif si seul la fin est reportée).",
    )
    date_fin_prevue = serializers.DateField(
        required=True,
        help_text="Nouvelle date de fin prévue (obligatoire).",
    )
    motif_id = serializers.UUIDField(
        required=True,
        help_text="Identifiant UUID du motif sélectionné dans la liste dynamique.",
    )
    justification = serializers.CharField(
        required=True,
        min_length=30,
        trim_whitespace=True,
        help_text="Explication détaillée du report (au moins 30 caractères, RG-11).",
    )

    def validate_justification(self, value: str) -> str:
        propre = value.strip()
        if len(propre) < 30:
            raise serializers.ValidationError(
                "La justification doit comporter au moins 30 caractères (RG-11)."
            )
        return propre


class HistoriqueDateSerializer(serializers.ModelSerializer):
    """Historique immuable de traçabilité des décalages."""

    motif = MotifReportSerializer(read_only=True)
    auteur_nom = serializers.SerializerMethodField()

    class Meta:
        model = HistoriqueDate
        fields = [
            "id",
            "type_objet",
            "champ",
            "valeur_avant",
            "valeur_apres",
            "motif",
            "justification",
            "auteur_id",
            "auteur_nom",
            "cree_le",
        ]

    def get_auteur_nom(self, obj: HistoriqueDate) -> str:
        if not obj.auteur:
            return "Système"
        nom_complet = f"{obj.auteur.prenom} {obj.auteur.nom}".strip()
        return nom_complet or obj.auteur.email


class ReprogrammationResponseSerializer(serializers.Serializer):
    """Résultat synthétique après reprogrammation réussie."""

    id = serializers.UUIDField(source="instance.id")
    type_objet = serializers.CharField()
    date_debut_prevue = serializers.DateField()
    date_fin_prevue = serializers.DateField()
    date_debut_baseline = serializers.DateField(allow_null=True)
    date_fin_baseline = serializers.DateField(allow_null=True)
    jours_derive_baseline = serializers.IntegerField()
    alerte_dg_declenchee = serializers.BooleanField()
    historiques = HistoriqueDateSerializer(many=True)
