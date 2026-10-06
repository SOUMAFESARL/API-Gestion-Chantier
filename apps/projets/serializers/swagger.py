"""Creation form and update contracts."""

from django.db import transaction
from django.urls import reverse
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.core.enums import StatutProjet, TypeProjet
from apps.projets.models import Projet, ProjetContrat
from apps.projets.serializers import ProjetCreationSerializer
from apps.projets.serializers.statistiques import StatistiquesProjetSerializer
from apps.projets.services.contrats import (
    MAX_LOT,
    ajouter_contrats,
    nettoyer_contrats,
    valider_fichier_contrat,
)
from apps.projets.services.indicateurs import calculer_sante
from apps.projets.services.statistiques import statistiques_lots

CHAMPS_FORMULAIRE = (
    "nom",
    "statut",
    "reference",
    "type_projet",
    "ville",
    "maitre_ouvrage",
    "maitre_oeuvre",
    "date_debut_prevue",
    "date_fin_prevue",
    "date_debut_reelle",
    "date_fin_reelle",
    "duree_jours_ouvres",
    "budget_initial_montant",
    "description",
    "contrat",
)
CHAMPS_REPONSE = (
    "id",
    *CHAMPS_FORMULAIRE,
    "avancement_reel",
    "indice_sante",
    "statistiques",
)


@extend_schema_field(OpenApiTypes.BINARY)
class FichierContratField(serializers.FileField):
    """An uploaded binary file, not a URL in the OpenAPI request body."""


class ProjetPostSerializer(ProjetCreationSerializer):
    """Only visible fields; reference and duration are generated."""

    reference = serializers.CharField(read_only=True)
    date_debut_reelle = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Début réel facultatif (YYYY-MM-DD). Omission : conserver ; null : effacer.",
    )
    date_fin_reelle = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Fin réelle facultative, au plus tôt le jour du début réel. null : effacer.",
    )
    statut = serializers.ChoiceField(
        choices=StatutProjet.choices,
        required=False,
        default=StatutProjet.EN_ATTENTE,
        help_text=(
            "État du projet entier. EN_ATTENTE par défaut à la création. "
            "Utiliser EN_COURS pour réactiver. Ces états ne bloquent pas les opérations."
        ),
    )
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)
    type_projet = serializers.ChoiceField(choices=TypeProjet.choices)
    maitre_ouvrage = serializers.CharField(max_length=200)
    contrat = serializers.ListField(
        child=FichierContratField(validators=[valider_fichier_contrat]),
        required=False,
        max_length=10,
        help_text="Un ou plusieurs PDF/JPG/JPEG/PNG. Repeter contrat en multipart. 10 Mo/fichier.",
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        debut = attrs.get("date_debut_reelle", getattr(self.instance, "date_debut_reelle", None))
        fin = attrs.get("date_fin_reelle", getattr(self.instance, "date_fin_reelle", None))
        if debut is not None and fin is not None and fin < debut:
            raise serializers.ValidationError(
                {"date_fin_reelle": "La fin réelle ne peut pas précéder le début réel."}
            )
        return attrs

    def validate_contrat(self, fichiers):
        if sum(fichier.size for fichier in fichiers) > MAX_LOT:
            raise serializers.ValidationError("La taille totale des contrats depasse 50 Mo.")
        return fichiers

    def _avec_contrats(self, validated_data, operation):
        fichiers = validated_data.pop("contrat", [])
        stockes = []
        try:
            with transaction.atomic():
                projet = operation(validated_data)
                user = getattr(self.context.get("request"), "user", None)
                ajouter_contrats(projet, fichiers, user, stockes)
                return projet
        except Exception:
            nettoyer_contrats(stockes)
            raise

    def create(self, validated_data):
        return self._avec_contrats(validated_data, super().create)

    def update(self, instance, validated_data):
        return self._avec_contrats(
            validated_data,
            lambda donnees: super(ProjetPostSerializer, self).update(instance, donnees),
        )

    def get_fields(self):
        fields = super().get_fields()
        return {name: fields[name] for name in CHAMPS_FORMULAIRE}

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            errors = dict.fromkeys(
                data.keys() - self.fields.keys(), "Ce champ n'est pas accepte dans le formulaire."
            )
            for name in ("date_debut_baseline", "date_fin_baseline"):
                if self.instance is not None and name in data:
                    errors[name] = "La Baseline v0 est immuable et ne peut etre modifiee."
            for name in ("reference", "duree_jours_ouvres"):
                if name in data:
                    errors[name] = "Ce champ est calcule automatiquement."
            if errors:
                raise serializers.ValidationError(errors)
        return super().to_internal_value(data)


class ContratProjetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProjetContrat
        fields = ["id", "nom", "taille", "type_contenu", "url"]
        read_only_fields = fields

    def get_url(self, obj) -> str:
        path = reverse("projets:projet-detail", kwargs={"pk": obj.projet_id})
        path = f"{path}?contrat={obj.pk}"
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path


class ProjetCreationResponseSerializer(serializers.ModelSerializer):
    statistiques = serializers.SerializerMethodField(
        help_text="Compteurs et avancement des lots et activités actifs du projet."
    )

    @extend_schema_field(StatistiquesProjetSerializer)
    def get_statistiques(self, obj) -> dict:
        return statistiques_lots(obj.lots.all())

    avancement_reel = serializers.SerializerMethodField(
        help_text=(
            "Pourcentage réalisé automatique : 0 à la création, jusqu'à 100 selon les activités. "
            "Pondéré par les budgets complets des activités, sinon moyenne simple."
        )
    )
    indice_sante = serializers.SerializerMethodField(
        help_text="Note sur 100 comparant réalisation et budget consommé ; null si non calculable."
    )
    maitre_ouvrage = serializers.SerializerMethodField()
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)
    contrat = ContratProjetSerializer(source="contrats", many=True, read_only=True)

    def get_avancement_reel(self, obj) -> float:
        return statistiques_lots(obj.lots.all())["avancement_pondere"]

    def get_indice_sante(self, obj) -> int | None:
        # Aucun registre de dépenses réelles n'est encore relié aux projets.
        return calculer_sante(100 - self.get_avancement_reel(obj), obj.budget_initial_montant, None)

    def get_maitre_ouvrage(self, obj) -> str:
        return obj.maitre_ouvrage or (obj.client.raison_sociale if obj.client_id else "")

    class Meta:
        model = Projet
        fields = CHAMPS_REPONSE
        read_only_fields = CHAMPS_REPONSE

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(user, request):
            from apps.core.purger_montants import purger_montants_recursif

            data = purger_montants_recursif(data)
        return data


class ProjetPatchSerializer(ProjetPostSerializer):
    """Same visible fields for PUT and PATCH."""

    def validate(self, attrs):
        if self.instance is not None and "statut" not in self.initial_data:
            attrs["statut"] = self.instance.statut
        if self.instance is not None and not self.partial:
            attrs.setdefault("date_debut_prevue", None)
            attrs.setdefault("date_fin_prevue", None)
            for name in ("date_debut_prevue", "date_fin_prevue"):
                stored = getattr(self.instance, name)
                if stored is not None and attrs[name] != stored:
                    raise serializers.ValidationError(
                        {name: "RG-11 : utilisez la route de reprogrammation des dates."}
                    )
        attrs = super().validate(attrs)
        nouveau_statut = attrs.get("statut")
        if self.instance is not None and nouveau_statut == StatutProjet.RECEPTIONNE:
            from apps.projets.services.machine_etats import valider_transition_reception

            valider_transition_reception(self.instance)
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

    def update(self, instance, validated_data):
        ancien_statut = instance.statut
        nouveau_statut = validated_data.pop("statut", ancien_statut)
        user = getattr(self.context.get("request"), "user", None)

        projet = super().update(instance, validated_data)

        if nouveau_statut != ancien_statut:
            from apps.projets.services.machine_etats import changer_statut_projet

            projet = changer_statut_projet(projet, nouveau_statut, user)

        return projet
