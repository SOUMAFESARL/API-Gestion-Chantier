from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur
from apps.core.exceptions import RequeteRefusee
from apps.projets.models import EquipeChantier, MembreEquipeChantier
from apps.projets.services.equipes import (
    collaborateurs_autorises_projet,
    message_collaborateur_non_affecte,
    synchroniser_chef_equipe,
)


class PersonneEquipeSerializer(serializers.Serializer):
    utilisateur_id = serializers.PrimaryKeyRelatedField(
        source="utilisateur",
        required=False,
        allow_null=True,
        queryset=Utilisateur.objects.filter(is_active=True, statut=StatutUtilisateur.ACTIF),
    )
    collaborateur_id = serializers.PrimaryKeyRelatedField(
        source="utilisateur",
        required=False,
        allow_null=True,
        queryset=Utilisateur.objects.filter(is_active=True, statut=StatutUtilisateur.ACTIF),
    )
    prenom = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    nom = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        user = attrs.get("utilisateur")
        nom = attrs.get("nom", "").strip()
        if bool(user) == bool(nom):
            raise serializers.ValidationError("Choisir un collaborateur OU saisir un nom.")
        return attrs


class MembreEquipeSerializer(PersonneEquipeSerializer):
    role = serializers.ChoiceField(
        choices=[c[0] for c in MembreEquipeChantier.FONCTION_CHOICES],
        required=False,
        default="OUVRIER",
    )
    fonction = serializers.CharField(max_length=50, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "fonction" in data and "role" not in data:
            data = data.copy()
            data["role"] = data["fonction"]
        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "fonction" in attrs and attrs.get("role") == "OUVRIER":
            f = attrs["fonction"]
            if f in [c[0] for c in MembreEquipeChantier.FONCTION_CHOICES]:
                attrs["role"] = f
        return attrs


class EquipeCreationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=200)
    nature = serializers.ChoiceField(choices=["INTERNE", "SOUS_TRAITANT", "SOUS_TRAITANTE"])
    corps_etat = serializers.CharField(max_length=200, required=False)
    specialite = serializers.CharField(max_length=200, required=False)
    chef = PersonneEquipeSerializer(required=False, allow_null=True, default=None)
    membres = MembreEquipeSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        projet = self.context["projet"]
        # Normalisation nature
        if attrs.get("nature") == "SOUS_TRAITANTE":
            attrs["nature"] = "SOUS_TRAITANT"

        # Alias specialite / corps_etat
        if not attrs.get("corps_etat"):
            if attrs.get("specialite"):
                attrs["corps_etat"] = attrs["specialite"]
            else:
                raise serializers.ValidationError(
                    {"corps_etat": "Le corps d'état ou la spécialité est requis."}
                )

        chef = attrs.get("chef")
        membres = attrs.get("membres", [])
        personnes = [chef, *membres] if chef else list(membres)
        if len(personnes) > 100:
            raise serializers.ValidationError({"membres": "Maximum 100 personnes, chef compris."})

        autorises = collaborateurs_autorises_projet(projet)
        vus = set()
        for personne in personnes:
            utilisateur = personne.get("utilisateur")
            if utilisateur and utilisateur.pk not in autorises:
                raise RequeteRefusee(message_collaborateur_non_affecte(utilisateur))
            cle = (
                ("id", utilisateur.pk)
                if utilisateur
                else (
                    "nom",
                    f"{personne.get('prenom', '')} {personne.get('nom', '')}".strip().casefold(),
                )
            )
            if cle in vus:
                raise serializers.ValidationError("Une personne ne peut apparaître deux fois.")
            vus.add(cle)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        chef = validated_data.pop("chef", None)
        membres = validated_data.pop("membres", [])
        validated_data.pop("specialite", None)
        createur = self.context["request"].user

        equipe = EquipeChantier.objects.create(
            projet=self.context["projet"],
            chef_utilisateur=chef.get("utilisateur") if chef else None,
            chef_nom=chef.get("nom", "") if chef else "",
            cree_par=createur,
            **validated_data,
        )

        if chef:
            MembreEquipeChantier.objects.create(
                equipe=equipe,
                utilisateur=chef.get("utilisateur"),
                prenom=chef.get("prenom", ""),
                nom=chef.get("nom", ""),
                fonction="CHEF_EQUIPE",
                cree_par=createur,
            )

        for membre_data in membres:
            role = membre_data.get("role") or membre_data.get("fonction") or "OUVRIER"
            MembreEquipeChantier.objects.create(
                equipe=equipe,
                utilisateur=membre_data.get("utilisateur"),
                prenom=membre_data.get("prenom", ""),
                nom=membre_data.get("nom", ""),
                fonction=role,
                cree_par=createur,
            )

        synchroniser_chef_equipe(equipe)
        return equipe


class MembreEquipeCreateSerializer(serializers.Serializer):
    utilisateur_id = serializers.PrimaryKeyRelatedField(
        source="utilisateur",
        required=False,
        allow_null=True,
        queryset=Utilisateur.objects.filter(is_active=True, statut=StatutUtilisateur.ACTIF),
    )
    collaborateur_id = serializers.PrimaryKeyRelatedField(
        source="utilisateur",
        required=False,
        allow_null=True,
        queryset=Utilisateur.objects.filter(is_active=True, statut=StatutUtilisateur.ACTIF),
    )
    prenom = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    nom = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(
        choices=[c[0] for c in MembreEquipeChantier.FONCTION_CHOICES],
        required=False,
        default="OUVRIER",
    )
    fonction = serializers.CharField(max_length=50, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "fonction" in data and "role" not in data:
            data = data.copy()
            data["role"] = data["fonction"]
        return super().to_internal_value(data)

    def validate(self, attrs):
        user = attrs.get("utilisateur")
        nom = attrs.get("nom", "").strip()
        if bool(user) == bool(nom):
            raise serializers.ValidationError("Choisir un collaborateur OU saisir un nom.")
        if "fonction" in attrs and attrs.get("role") == "OUVRIER":
            f = attrs["fonction"]
            if f in [c[0] for c in MembreEquipeChantier.FONCTION_CHOICES]:
                attrs["role"] = f
        return attrs


class MembreEquipeUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[c[0] for c in MembreEquipeChantier.FONCTION_CHOICES],
        required=True,
    )


class MembreEquipeResponseSerializer(serializers.ModelSerializer):
    collaborateur_id = serializers.UUIDField(
        source="utilisateur_id", read_only=True, allow_null=True
    )
    utilisateur_id = serializers.UUIDField(read_only=True, allow_null=True)
    prenom = serializers.SerializerMethodField()
    nom = serializers.SerializerMethodField()
    role = serializers.CharField(source="fonction", read_only=True)
    fonction = serializers.CharField(read_only=True)

    def get_prenom(self, obj) -> str:
        if obj.utilisateur:
            return obj.utilisateur.prenom
        return obj.prenom or ""

    def get_nom(self, obj) -> str:
        if obj.utilisateur:
            return obj.utilisateur.nom
        return obj.nom or ""

    class Meta:
        model = MembreEquipeChantier
        fields = [
            "id",
            "collaborateur_id",
            "utilisateur_id",
            "prenom",
            "nom",
            "role",
            "fonction",
        ]
        read_only_fields = fields


class EquipeResponseSerializer(serializers.ModelSerializer):
    projet_id = serializers.UUIDField(source="projet.id", read_only=True)
    specialite = serializers.CharField(source="corps_etat", read_only=True)
    chef = serializers.SerializerMethodField()
    membres = serializers.SerializerMethodField()
    chef_nom = serializers.SerializerMethodField()
    effectif = serializers.SerializerMethodField()

    def get_chef(self, obj) -> dict | None:
        chef_membre = (
            obj.membres.filter(
                fonction="CHEF_EQUIPE",
                supprime_le__isnull=True,
            )
            .select_related("utilisateur")
            .first()
        )
        if chef_membre:
            return MembreEquipeResponseSerializer(chef_membre).data
        if obj.chef_utilisateur or (obj.chef_nom and obj.chef_nom.strip()):
            return {
                "id": None,
                "collaborateur_id": str(obj.chef_utilisateur.id) if obj.chef_utilisateur else None,
                "utilisateur_id": str(obj.chef_utilisateur.id) if obj.chef_utilisateur else None,
                "prenom": obj.chef_utilisateur.prenom if obj.chef_utilisateur else "",
                "nom": obj.chef_utilisateur.nom if obj.chef_utilisateur else (obj.chef_nom or ""),
                "role": "CHEF_EQUIPE",
                "fonction": "CHEF_EQUIPE",
            }
        return None

    def get_membres(self, obj) -> list:
        membres_qs = (
            obj.membres.filter(supprime_le__isnull=True)
            .exclude(fonction="CHEF_EQUIPE")
            .select_related("utilisateur")
            .order_by("cree_le", "id")
        )
        return MembreEquipeResponseSerializer(membres_qs, many=True).data

    def get_chef_nom(self, obj) -> str:
        chef_membre = (
            obj.membres.filter(
                fonction="CHEF_EQUIPE",
                supprime_le__isnull=True,
            )
            .select_related("utilisateur")
            .first()
        )
        if chef_membre:
            if chef_membre.utilisateur:
                return f"{chef_membre.utilisateur.prenom} {chef_membre.utilisateur.nom}".strip()
            return f"{chef_membre.prenom} {chef_membre.nom}".strip()
        user = obj.chef_utilisateur
        return f"{user.prenom} {user.nom}".strip() if user else (obj.chef_nom or "")

    def get_effectif(self, obj) -> int:
        return obj.membres.filter(supprime_le__isnull=True).count()

    class Meta:
        model = EquipeChantier
        fields = [
            "id",
            "projet",
            "projet_id",
            "nom",
            "nature",
            "corps_etat",
            "specialite",
            "chef_utilisateur",
            "chef_nom",
            "chef",
            "membres",
            "effectif",
            "est_actif",
        ]
        read_only_fields = fields


class EquipeCandidatEquipeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nom = serializers.CharField()


class CandidatEquipeSerializer(serializers.Serializer):
    """Un collaborateur que l'on peut ajouter à une équipe du projet."""

    id = serializers.UUIDField()
    nom_complet = serializers.CharField()
    role_projet = serializers.CharField(help_text="Code du rôle tenu sur le projet (CP, CT, CC…).")
    equipes = EquipeCandidatEquipeSerializer(
        many=True, help_text="Les équipes du projet dont il est déjà membre."
    )
