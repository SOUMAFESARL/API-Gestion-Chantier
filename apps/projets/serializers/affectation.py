"""Sérialiseurs pour l'API d'affectation des collaborateurs aux projets (US-04)."""

from rest_framework import serializers

from apps.accounts.models import Role, Utilisateur
from apps.core.enums import RoleProjet
from apps.projets.models import AffectationProjet


class IntervenantProjetDetailSerializer(serializers.Serializer):
    """Informations de base sur le collaborateur affecté."""

    id = serializers.UUIDField()
    nom = serializers.CharField()
    prenom = serializers.CharField(allow_blank=True, default="")
    nom_complet = serializers.CharField()
    email = serializers.EmailField()
    telephone = serializers.CharField(allow_blank=True, default="")
    statut = serializers.CharField()


class AffectationProjetResponseSerializer(serializers.ModelSerializer):
    """Représentation détaillée d'une affectation de chantier."""

    utilisateur = IntervenantProjetDetailSerializer(read_only=True)
    role_projet_libelle = serializers.CharField(source="get_role_projet_display", read_only=True)
    role_personnalise_id = serializers.UUIDField(source="role.id", read_only=True, default=None)
    role_personnalise_code = serializers.CharField(source="role.code", read_only=True, default=None)
    role_personnalise_libelle = serializers.CharField(source="role.libelle", read_only=True, default=None)

    class Meta:
        model = AffectationProjet
        fields = [
            "id",
            "projet_id",
            "utilisateur",
            "role_projet",
            "role_projet_libelle",
            "role_personnalise_id",
            "role_personnalise_code",
            "role_personnalise_libelle",
            "date_debut",
            "date_fin",
            "est_actif",
            "cree_le",
            "modifie_le",
        ]


class AffectationProjetCreateSerializer(serializers.Serializer):
    """Données pour affecter un nouveau collaborateur au projet."""

    utilisateur_id = serializers.UUIDField(required=True)
    role_projet = serializers.ChoiceField(choices=RoleProjet.choices, required=True)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    role_personnalise_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        user_id = attrs.get("utilisateur_id")
        user = Utilisateur.objects.filter(id=user_id, supprime_le__isnull=True).first()
        if not user:
            raise serializers.ValidationError({"utilisateur_id": "Collaborateur introuvable dans cette organisation."})
        attrs["utilisateur_instance"] = user

        role_id = attrs.get("role_personnalise_id")
        if role_id:
            role = Role.objects.filter(id=role_id, supprime_le__isnull=True).first()
            if not role:
                raise serializers.ValidationError({"role_personnalise_id": "Rôle personnalisé introuvable."})
            attrs["role_instance"] = role
        else:
            attrs["role_instance"] = None

        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({"date_fin": "La date de fin ne peut pas précéder la date de début."})

        return attrs


class AffectationProjetUpdateSerializer(serializers.Serializer):
    """Données pour modifier le rôle, les dates ou le statut d'une affectation."""

    role_projet = serializers.ChoiceField(choices=RoleProjet.choices, required=False)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    role_personnalise_id = serializers.UUIDField(required=False, allow_null=True)
    est_actif = serializers.BooleanField(required=False)

    def validate(self, attrs):
        role_id = attrs.get("role_personnalise_id")
        if role_id:
            role = Role.objects.filter(id=role_id, supprime_le__isnull=True).first()
            if not role:
                raise serializers.ValidationError({"role_personnalise_id": "Rôle personnalisé introuvable."})
            attrs["role"] = role
        elif "role_personnalise_id" in attrs and role_id is None:
            attrs["role"] = None

        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({"date_fin": "La date de fin ne peut pas précéder la date de début."})

        return attrs
