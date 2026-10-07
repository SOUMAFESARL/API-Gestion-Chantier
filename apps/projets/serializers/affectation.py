"""Sérialiseurs pour l'API d'affectation des collaborateurs aux projets (US-04 / E-05 / C-05)."""

from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleProjet, StatutUtilisateur
from apps.core.permissions import obtenir_portee_role
from apps.projets.models import AffectationProjet


class AffectationProjetResponseSerializer(serializers.ModelSerializer):
    """Représentation détaillée d'une affectation de chantier avec masquage PII conditionnel (C-05)."""

    utilisateur = serializers.SerializerMethodField()
    role_projet_libelle = serializers.CharField(source="get_role_projet_display", read_only=True)

    class Meta:
        model = AffectationProjet
        fields = [
            "id",
            "projet_id",
            "utilisateur",
            "role_projet",
            "role_projet_libelle",
            "date_debut",
            "date_fin",
            "est_actif",
            "cree_le",
            "modifie_le",
        ]

    def get_utilisateur(self, obj):
        u = obj.utilisateur
        if not u:
            return None
        data = {
            "id": u.id,
            "nom": u.nom,
            "prenom": u.prenom or "",
            "nom_complet": f"{u.prenom} {u.nom}".strip() or u.nom,
            "statut": u.statut,
        }
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        from apps.core.droits import a_permission, est_dg

        peut_voir_pii = False
        if user and user.is_authenticated:
            if user.is_superuser or est_dg(user):
                peut_voir_pii = True
            elif (
                getattr(user, "is_owner", False)
                or getattr(user, "is_dg", False)
                or getattr(user, "role_global", None) in ("DG", "ADMIN", "AD")
            ):
                peut_voir_pii = True
            elif a_permission(user, "projets.affecter_membres", request=request) or a_permission(
                user, "projets.gerer_equipes", request=request
            ):
                peut_voir_pii = True

        if peut_voir_pii:
            data["email"] = u.email
            data["telephone"] = getattr(u, "telephone", "") or ""

        return data


class AffectationProjetCreateSerializer(serializers.Serializer):
    """Données pour affecter un nouveau collaborateur au projet (E-05)."""

    utilisateur_id = serializers.UUIDField(required=True)
    role_projet = serializers.ChoiceField(choices=RoleProjet.choices, required=True)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        user_id = attrs.get("utilisateur_id")
        user = Utilisateur.objects.filter(id=user_id, supprime_le__isnull=True).first()
        if not user:
            raise serializers.ValidationError(
                {"code": "candidat_invalide", "detail": "Collaborateur introuvable ou inexistant."},
                code="candidat_invalide",
            )

        if not user.is_active or user.statut != StatutUtilisateur.ACTIF:
            raise serializers.ValidationError(
                {"code": "candidat_invalide", "detail": "Le collaborateur est inactif ou suspendu."},
                code="candidat_invalide",
            )

        if obtenir_portee_role(user) == "ENTREPRISE":
            raise serializers.ValidationError(
                {
                    "code": "candidat_invalide",
                    "detail": "Un collaborateur à portée ENTREPRISE ne peut pas être affecté à un projet.",
                },
                code="candidat_invalide",
            )

        attrs["utilisateur_instance"] = user

        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )

        return attrs


class AffectationProjetUpdateSerializer(serializers.Serializer):
    """Données pour modifier le rôle, les dates ou le statut d'une affectation."""

    role_projet = serializers.ChoiceField(choices=RoleProjet.choices, required=False)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    est_actif = serializers.BooleanField(required=False)

    def validate(self, attrs):
        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )

        return attrs
