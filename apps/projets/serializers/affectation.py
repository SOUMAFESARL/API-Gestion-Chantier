from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleProjet, StatutUtilisateur
from apps.core.permissions import obtenir_portee_role
from apps.projets.models import AffectationProjet
from apps.projets.services.affectations import est_chef_projet, peut_gerer_chef_projet


def code_role_plateforme(user) -> str:
    """Le code du rôle du collaborateur sur la plateforme (CP, CT, QSE…)."""
    return ((user.role.code if getattr(user, "role", None) else user.role_global) or "").upper()


def verifier_role_coherent(user, role_projet) -> None:
    """Règle du 16/10/2026 : on tient sur un projet le rôle qu'on a sur la plateforme.

    Valable pour **tout** rôle de portée Projet, présent ou à venir : un CT n'est affecté
    que comme CT, un « Responsable QSE » que comme Responsable QSE.
    """
    if (role_projet or "").upper() != code_role_plateforme(user):
        raise serializers.ValidationError(
            {
                "role_projet": (
                    "Ce collaborateur n'a pas ce rôle sur la plateforme : il ne peut pas le "
                    "tenir sur un projet."
                )
            },
            code="role_incoherent",
        )


class IntervenantAffectationSerializer(serializers.Serializer):
    """Représentation de l'utilisateur affecté."""

    id = serializers.UUIDField()
    nom = serializers.CharField()
    prenom = serializers.CharField(allow_blank=True)
    nom_complet = serializers.CharField()
    statut = serializers.CharField()
    email = serializers.EmailField(required=False)
    telephone = serializers.CharField(required=False, allow_blank=True)


class LotAffectationSerializer(serializers.Serializer):
    """Le lot d'un chef de chantier, tel que l'écran l'affiche."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    libelle = serializers.CharField()


class AffectationProjetResponseSerializer(serializers.ModelSerializer):
    """Représentation détaillée d'une affectation de chantier avec masquage PII (C-05)."""

    utilisateur = serializers.SerializerMethodField()
    role_projet_libelle = serializers.CharField(source="get_role_projet_display", read_only=True)
    lot = serializers.SerializerMethodField()
    modifiable = serializers.SerializerMethodField(
        help_text=(
            "Faux quand l'affectation est celle du chef de projet et que l'utilisateur "
            "courant n'est ni le DG ni un rôle de portée entreprise qui affecte les membres."
        )
    )

    class Meta:
        model = AffectationProjet
        fields = [
            "id",
            "projet_id",
            "utilisateur",
            "role_projet",
            "role_projet_libelle",
            "zone",
            "lot",
            "fonction_membre",
            "date_debut",
            "date_fin",
            "est_actif",
            "modifiable",
            "cree_le",
            "modifie_le",
        ]

    @extend_schema_field(LotAffectationSerializer(allow_null=True))
    def get_lot(self, obj):
        lot = obj.lot if obj.lot_id else None
        if lot is None or lot.supprime_le is not None:
            return None
        return {"id": lot.id, "code": lot.code, "libelle": lot.libelle}

    @extend_schema_field(serializers.BooleanField())
    def get_modifiable(self, obj) -> bool:
        # Le même sérialiseur sert toute une liste : les droits se calculent une seule fois.
        if not hasattr(self, "_peut_affecter_membres"):
            from apps.core.droits import a_permission, est_dg

            request = self.context.get("request")
            user = getattr(request, "user", None)
            self._peut_affecter_membres = bool(
                user
                and getattr(user, "is_authenticated", False)
                and (
                    user.is_superuser
                    or est_dg(user)
                    or a_permission(user, "projets.affecter_membres", request=request)
                )
            )
            self._peut_gerer_chef_projet = peut_gerer_chef_projet(user, request=request)
        if not self._peut_affecter_membres:
            return False
        if not est_chef_projet(obj.role_projet):
            return True
        return self._peut_gerer_chef_projet

    @extend_schema_field(IntervenantAffectationSerializer)
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
        if user and user.is_authenticated and (
            user.is_superuser
            or est_dg(user)
            or getattr(user, "is_owner", False)
            or getattr(user, "is_dg", False)
            or getattr(user, "role_global", None) in ("DG", "ADMIN", "AD")
            or a_permission(user, "projets.affecter_membres", request=request)
            or a_permission(user, "projets.gerer_equipes", request=request)
        ):
            peut_voir_pii = True

        if peut_voir_pii:
            data["email"] = u.email
            data["telephone"] = getattr(u, "telephone", "") or ""

        return data


class AffectationProjetCreateSerializer(serializers.Serializer):
    """Données pour affecter un nouveau collaborateur au projet (E-05 / B4)."""

    utilisateur_id = serializers.UUIDField(required=True)
    role_projet = serializers.CharField(max_length=50, required=True)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    zone = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    # Le lot d'un chef de chantier ; sa cohérence (projet, suppression, rôle) est vérifiée par
    # le service, qui répond 400 avec un message lisible. S'il est fourni, il fixe la zone.
    lot_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    fonction_membre = serializers.CharField(
        required=False, allow_blank=True, max_length=20, default=""
    )

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
                {
                    "code": "candidat_invalide",
                    "detail": "Le collaborateur est inactif ou suspendu.",
                },
                code="candidat_invalide",
            )

        if obtenir_portee_role(user) == "ENTREPRISE":
            raise serializers.ValidationError(
                {
                    "code": "candidat_invalide",
                    "detail": (
                        "Un collaborateur à portée ENTREPRISE ne peut pas être affecté à un projet."
                    ),
                },
                code="candidat_invalide",
            )

        attrs["utilisateur_instance"] = user

        role_projet = attrs.get("role_projet")
        zone = attrs.get("zone", "")
        fonction_membre = attrs.get("fonction_membre", "")

        if zone and role_projet != RoleProjet.CHEF_CHANTIER:
            raise serializers.ValidationError(
                {"zone": "La zone ne concerne qu'un chef de chantier."}
            )

        if (
            fonction_membre
            and role_projet != RoleProjet.VISITEUR
        ):
            raise serializers.ValidationError(
                {"fonction_membre": "La fonction de membre ne concerne qu'un invité / consultant."}
            )

        if role_projet == RoleProjet.VISITEUR and not fonction_membre:
            attrs["fonction_membre"] = "AUTRE"

        # Après les contrôles de forme (zone, fonction) : leur message reste le plus précis.
        verifier_role_coherent(user, role_projet)

        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )

        return attrs


class AffectationProjetUpdateSerializer(serializers.Serializer):
    """Données pour modifier rôle, dates, zone, fonction ou statut d'une affectation."""

    role_projet = serializers.CharField(max_length=50, required=False)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    est_actif = serializers.BooleanField(required=False)
    zone = serializers.CharField(required=False, allow_blank=True, max_length=120)
    lot_id = serializers.UUIDField(required=False, allow_null=True)
    fonction_membre = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        nouveau_role = attrs.get("role_projet", getattr(instance, "role_projet", None))
        if "role_projet" in attrs and instance is not None:
            verifier_role_coherent(instance.utilisateur, attrs["role_projet"])

        if "zone" in attrs and attrs["zone"] and nouveau_role != RoleProjet.CHEF_CHANTIER:
            raise serializers.ValidationError(
                {"zone": "La zone ne concerne qu'un chef de chantier."}
            )

        if (
            "fonction_membre" in attrs
            and attrs["fonction_membre"]
            and nouveau_role != RoleProjet.VISITEUR
        ):
            raise serializers.ValidationError(
                {"fonction_membre": "La fonction de membre ne concerne qu'un invité / consultant."}
            )

        if nouveau_role == RoleProjet.VISITEUR:
            sans_fonction = "fonction_membre" in attrs and not attrs["fonction_membre"]
            nouveau_vi = (
                instance
                and getattr(instance, "role_projet", None) != RoleProjet.VISITEUR
                and "fonction_membre" not in attrs
            )
            if sans_fonction or nouveau_vi:
                attrs["fonction_membre"] = "AUTRE"

        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )

        return attrs
