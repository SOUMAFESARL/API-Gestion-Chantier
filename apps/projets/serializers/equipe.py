from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur
from apps.projets.models import AffectationProjet, EquipeChantier, MembreEquipeChantier


class PersonneEquipeSerializer(serializers.Serializer):
    utilisateur_id = serializers.PrimaryKeyRelatedField(
        source="utilisateur",
        required=False,
        allow_null=True,
        queryset=Utilisateur.objects.filter(is_active=True, statut=StatutUtilisateur.ACTIF),
    )
    nom = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if bool(attrs.get("utilisateur")) == bool(attrs.get("nom")):
            raise serializers.ValidationError("Choisir un collaborateur OU saisir un nom.")
        return attrs


class MembreEquipeSerializer(PersonneEquipeSerializer):
    fonction = serializers.CharField(max_length=50, required=False, default="OUVRIER")


class EquipeCreationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=200)
    nature = serializers.ChoiceField(choices=["INTERNE", "SOUS_TRAITANTE"])
    corps_etat = serializers.CharField(max_length=200)
    chef = PersonneEquipeSerializer()
    membres = MembreEquipeSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        projet = self.context["projet"]
        personnes = [attrs["chef"], *attrs["membres"]]
        if len(personnes) > 100:
            raise serializers.ValidationError({"membres": "Maximum 100 personnes, chef compris."})
        autorises = set(
            AffectationProjet.objects.filter(
                projet=projet,
                est_actif=True,
            ).values_list("utilisateur_id", flat=True)
        )
        autorises.update((projet.chef_projet_id, projet.conducteur_travaux_id))
        vus = set()
        for personne in personnes:
            utilisateur = personne.get("utilisateur")
            if utilisateur and utilisateur.pk not in autorises:
                raise serializers.ValidationError("Collaborateur non affecté à ce projet.")
            cle = ("id", utilisateur.pk) if utilisateur else ("nom", personne["nom"].casefold())
            if cle in vus:
                raise serializers.ValidationError("Une personne ne peut apparaître deux fois.")
            vus.add(cle)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        chef = validated_data.pop("chef")
        membres = validated_data.pop("membres", [])
        createur = self.context["request"].user
        equipe = EquipeChantier.objects.create(
            projet=self.context["projet"],
            chef_utilisateur=chef.get("utilisateur"),
            chef_nom=chef.get("nom", ""),
            cree_par=createur,
            **validated_data,
        )
        for membre in membres:
            MembreEquipeChantier.objects.create(equipe=equipe, cree_par=createur, **membre)
        return equipe


class MembreEquipeResponseSerializer(serializers.ModelSerializer):
    utilisateur_id = serializers.UUIDField(read_only=True, allow_null=True)
    nom = serializers.SerializerMethodField()

    def get_nom(self, obj) -> str:
        return (
            f"{obj.utilisateur.prenom} {obj.utilisateur.nom}".strip()
            if obj.utilisateur
            else obj.nom
        )

    class Meta:
        model = MembreEquipeChantier
        fields = ["id", "utilisateur_id", "nom", "fonction"]
        read_only_fields = fields


class EquipeResponseSerializer(serializers.ModelSerializer):
    membres = MembreEquipeResponseSerializer(many=True, read_only=True)
    chef_nom = serializers.SerializerMethodField()
    effectif = serializers.SerializerMethodField()

    def get_chef_nom(self, obj) -> str:
        user = obj.chef_utilisateur
        return f"{user.prenom} {user.nom}".strip() if user else obj.chef_nom

    def get_effectif(self, obj) -> int:
        return 1 + len(obj.membres.all())

    class Meta:
        model = EquipeChantier
        fields = [
            "id",
            "projet",
            "nom",
            "nature",
            "corps_etat",
            "chef_utilisateur",
            "chef_nom",
            "membres",
            "effectif",
            "est_actif",
        ]
        read_only_fields = fields
