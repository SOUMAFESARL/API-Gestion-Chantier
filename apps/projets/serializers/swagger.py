"""Creation form and update contracts."""

from django.db import transaction
from django.urls import reverse
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.core.enums import TypeProjet
from apps.projets.models import Projet, ProjetContrat
from apps.projets.serializers import ProjetCreationSerializer
from apps.projets.services.contrats import (
    MAX_LOT,
    ajouter_contrats,
    nettoyer_contrats,
    valider_fichier_contrat,
)

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
    "contrat",
)
CHAMPS_REPONSE = ("id", *CHAMPS_FORMULAIRE)


@extend_schema_field(OpenApiTypes.BINARY)
class FichierContratField(serializers.FileField):
    """An uploaded binary file, not a URL in the OpenAPI request body."""


class ProjetPostSerializer(ProjetCreationSerializer):
    """Only visible fields; reference and duration are generated."""

    reference = serializers.CharField(read_only=True)
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)
    type_projet = serializers.ChoiceField(choices=TypeProjet.choices)
    maitre_ouvrage = serializers.CharField(max_length=200)
    contrat = serializers.ListField(
        child=FichierContratField(validators=[valider_fichier_contrat]),
        required=False,
        max_length=10,
        help_text="Un ou plusieurs PDF/JPG/JPEG/PNG. Repeter contrat en multipart. 10 Mo/fichier.",
    )

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
    maitre_ouvrage = serializers.SerializerMethodField()
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)
    contrat = ContratProjetSerializer(source="contrats", many=True, read_only=True)

    def get_maitre_ouvrage(self, obj) -> str:
        return obj.maitre_ouvrage or (obj.client.raison_sociale if obj.client_id else "")

    class Meta:
        model = Projet
        fields = CHAMPS_REPONSE
        read_only_fields = CHAMPS_REPONSE


class ProjetPatchSerializer(ProjetPostSerializer):
    """Same visible fields for PUT and PATCH."""

    def validate(self, attrs):
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
