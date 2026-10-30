"""Serializers pour l'application chantier — rapports journaliers."""

from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.chantier.models import RapportJournalier
from apps.chantier.services.rapport_journalier import (
    creer_rapport_journalier,
    modifier_rapport_journalier,
)
from apps.core.enums import Meteo, StatutRapport
from apps.projets.models import Projet

__all__ = [
    "AuteurSimpleSerializer",
    "ProjetSimpleSerializer",
    "RapportJournalierCreateSerializer",
    "RapportJournalierDetailSerializer",
    "RapportJournalierListSerializer",
    "RapportJournalierUpdateSerializer",
    "RapportRejetSerializer",
    "RapportValidationSerializer",
]


class ProjetSimpleSerializer(serializers.ModelSerializer):
    """Représentation allégée d'un projet pour l'imbrication."""

    class Meta:
        model = Projet
        fields = ["id", "reference", "nom"]


class AuteurSimpleSerializer(serializers.ModelSerializer):
    """Représentation allégée d'un utilisateur intervenant sur le rapport."""

    nom_complet = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = ["id", "nom", "prenom", "nom_complet", "email", "role_global"]

    def get_nom_complet(self, obj: Utilisateur) -> str:
        return f"{obj.prenom} {obj.nom}".strip() or obj.email


class RapportJournalierListSerializer(serializers.ModelSerializer):
    """Serializer pour les listes paginées de rapports."""

    projet = ProjetSimpleSerializer(read_only=True)
    auteur = AuteurSimpleSerializer(read_only=True)
    valide_par = AuteurSimpleSerializer(read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    meteo_libelle = serializers.CharField(source="get_meteo_display", read_only=True)

    class Meta:
        model = RapportJournalier
        fields = [
            "id",
            "date_rapport",
            "projet",
            "auteur",
            "meteo",
            "meteo_libelle",
            "effectif_regie",
            "effectif_tacherons",
            "effectif_present",
            "blocages_critiques",
            "statut",
            "statut_libelle",
            "soumis_le",
            "valide_par",
            "valide_le",
            "origine",
            "cree_le",
        ]


class RapportJournalierDetailSerializer(serializers.ModelSerializer):
    """Serializer pour le détail complet d'un rapport de chantier."""

    projet = ProjetSimpleSerializer(read_only=True)
    auteur = AuteurSimpleSerializer(read_only=True)
    valide_par = AuteurSimpleSerializer(read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    meteo_libelle = serializers.CharField(source="get_meteo_display", read_only=True)

    class Meta:
        model = RapportJournalier
        fields = [
            "id",
            "date_rapport",
            "projet",
            "auteur",
            "meteo",
            "meteo_libelle",
            "effectif_regie",
            "effectif_tacherons",
            "effectif_present",
            "observations",
            "blocages_critiques",
            "statut",
            "statut_libelle",
            "soumis_le",
            "valide_par",
            "valide_le",
            "commentaire_validation",
            "origine",
            "cree_le",
            "modifie_le",
        ]


class RapportJournalierCreateSerializer(serializers.Serializer):
    """Validation des entrées pour la création d'un rapport journalier."""

    projet_id = serializers.UUIDField(required=True)
    date_rapport = serializers.DateField(required=True)
    meteo = serializers.ChoiceField(choices=Meteo.choices, default=Meteo.ENSOLEILLE)
    effectif_regie = serializers.IntegerField(min_value=0, default=0)
    effectif_tacherons = serializers.IntegerField(min_value=0, default=0)
    effectif_present = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    observations = serializers.CharField(required=False, allow_blank=True, default="")
    blocages_critiques = serializers.IntegerField(min_value=0, default=0)
    statut = serializers.ChoiceField(
        choices=[StatutRapport.BROUILLON, StatutRapport.SOUMIS],
        default=StatutRapport.SOUMIS,
    )
    origine = serializers.CharField(default="WEB", max_length=10)

    def validate_projet_id(self, value):
        try:
            return Projet.objects.get(id=value)
        except Projet.DoesNotExist:
            raise serializers.ValidationError("Le projet spécifié n'existe pas.")

    def validate(self, attrs):
        projet = attrs["projet_id"]
        # Contrôle du cloisonnement des chantiers (Niveau 2)
        request = self.context.get("request")
        user = request.user if request else None
        if user and user.is_authenticated:
            from apps.core.droits import a_permission

            if not a_permission(user, "projets.voir_tous", request=request):
                from apps.core.permissions import obtenir_projets_ids_actifs_utilisateur

                projets_actifs = obtenir_projets_ids_actifs_utilisateur(user, request=request)
                if projet.id not in projets_actifs and str(projet.id) not in [str(p) for p in projets_actifs]:
                    raise serializers.ValidationError(
                        {"projet_id": "Vous n'êtes pas affecté à ce chantier."}
                    )

        from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

        verifier_statut_projet_pour_ecriture(projet, action="NOUVEAU_RAPPORT")

        attrs["projet"] = projet
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        utilisateur = request.user if request else None

        projet = validated_data["projet"]

        return creer_rapport_journalier(
            projet=projet,
            auteur=utilisateur,
            date_rapport=validated_data["date_rapport"],
            meteo=validated_data.get("meteo", Meteo.ENSOLEILLE),
            effectif_regie=validated_data.get("effectif_regie", 0),
            effectif_tacherons=validated_data.get("effectif_tacherons", 0),
            effectif_present=validated_data.get("effectif_present"),
            observations=validated_data.get("observations", ""),
            blocages_critiques=validated_data.get("blocages_critiques", 0),
            statut=validated_data.get("statut", StatutRapport.SOUMIS),
            origine=validated_data.get("origine", "WEB"),
            cree_par=utilisateur,
        )


class RapportJournalierUpdateSerializer(serializers.Serializer):
    """Validation des entrées pour la modification partielle d'un rapport."""

    projet_id = serializers.UUIDField(required=False)
    date_rapport = serializers.DateField(required=False)
    meteo = serializers.ChoiceField(choices=Meteo.choices, required=False)
    effectif_regie = serializers.IntegerField(min_value=0, required=False)
    effectif_tacherons = serializers.IntegerField(min_value=0, required=False)
    effectif_present = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    observations = serializers.CharField(required=False, allow_blank=True)
    blocages_critiques = serializers.IntegerField(min_value=0, required=False)
    origine = serializers.CharField(required=False, max_length=10)

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        projet = instance.projet if instance else None
        if "projet_id" in attrs:
            try:
                projet = Projet.objects.get(id=attrs["projet_id"])
                attrs["projet"] = projet
            except Projet.DoesNotExist:
                raise serializers.ValidationError({"projet_id": "Le projet spécifié n'existe pas."})

            # Contrôle du cloisonnement des chantiers (Niveau 2)
            request = self.context.get("request")
            user = request.user if request else None
            if user and user.is_authenticated:
                from apps.core.droits import a_permission

                if not a_permission(user, "projets.voir_tous", request=request):
                    from apps.core.permissions import obtenir_projets_ids_actifs_utilisateur

                    projets_actifs = obtenir_projets_ids_actifs_utilisateur(user, request=request)
                    if projet.id not in projets_actifs and str(projet.id) not in [str(p) for p in projets_actifs]:
                        raise serializers.ValidationError(
                            {"projet_id": "Vous n'êtes pas affecté à ce chantier."}
                        )

        return attrs

    def update(self, instance, validated_data):
        request = self.context.get("request")
        utilisateur = request.user if request else instance.auteur

        champs_modifiables = {}
        for k, v in validated_data.items():
            if k != "projet_id":
                champs_modifiables[k] = v

        return modifier_rapport_journalier(
            rapport=instance,
            modifie_par=utilisateur,
            **champs_modifiables,
        )


class RapportValidationSerializer(serializers.Serializer):
    """Validation d'un commentaire optionnel lors de la validation du CT."""

    commentaire = serializers.CharField(required=False, allow_blank=True, default="")


class RapportRejetSerializer(serializers.Serializer):
    """Validation du motif obligatoire (≥ 20 caractères) lors d'un rejet par le CT."""

    motif = serializers.CharField(
        required=True,
        min_length=20,
        error_messages={
            "required": "Le motif de rejet est obligatoire.",
            "blank": "Le motif de rejet ne peut pas être vide.",
            "min_length": "Le motif de rejet doit comporter au moins 20 caractères.",
        },
    )
