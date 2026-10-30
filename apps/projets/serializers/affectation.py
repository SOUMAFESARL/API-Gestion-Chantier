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
    """Le rôle demandé sur le projet existe dans l'entreprise.

    **Le rôle est propre à l'affectation** (décisions v1.2, §13bis) : il prend par défaut le rôle
    du collaborateur sur la plateforme, mais peut différer d'un projet à l'autre. Cela revient
    sur l'arbitrage du 16/10/2026, qui imposait le rôle de la plateforme sur chaque projet.
    """
    from apps.accounts.models import Role

    code = (role_projet or "").upper()
    if code in RoleProjet.values:
        return
    if not Role.objects.filter(code__iexact=code, est_actif=True, supprime_le__isnull=True).exists():
        raise serializers.ValidationError(
            {"role_projet": "Ce rôle n'existe pas dans l'entreprise."},
            code="role_inconnu",
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


class PerimetreAffectationSerializer(serializers.Serializer):
    """Une case du périmètre d'une affectation, avec le chemin qui y mène."""

    id = serializers.UUIDField()
    libelle = serializers.CharField()
    niveau = serializers.CharField()
    chemin = serializers.ListField(child=serializers.CharField())


class AffectationProjetResponseSerializer(serializers.ModelSerializer):
    """Représentation détaillée d'une affectation de chantier avec masquage PII (C-05)."""

    utilisateur = serializers.SerializerMethodField()
    role_projet_libelle = serializers.CharField(source="get_role_projet_display", read_only=True)
    role_plateforme = serializers.SerializerMethodField(
        help_text="Le rôle du collaborateur sur la plateforme ; celui du projet peut différer."
    )
    perimetres = serializers.SerializerMethodField(
        help_text="Les cases de l'arbre où s'exercent ses permissions ; vide : tout le projet."
    )
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
            "role_plateforme",
            "perimetres",
            "fonction_membre",
            "date_debut",
            "date_fin",
            "est_actif",
            "modifiable",
            "cree_le",
            "modifie_le",
        ]

    @extend_schema_field(serializers.CharField())
    def get_role_plateforme(self, obj) -> str:
        return code_role_plateforme(obj.utilisateur) if obj.utilisateur_id else ""

    @extend_schema_field(PerimetreAffectationSerializer(many=True))
    def get_perimetres(self, obj):
        cases = [e for e in obj.perimetres.all() if e.supprime_le is None]
        if not cases:
            return []
        from apps.projets.models import Element

        ids = {i for e in cases for i in e.ancetres_ids}
        libelles = dict(Element.objects.filter(pk__in=ids).values_list("pk", "libelle"))
        return [
            {
                "id": e.pk,
                "libelle": e.libelle,
                "niveau": e.niveau.libelle,
                "chemin": [libelles.get(i, "") for i in _uuids(e.ancetres_ids)] + [e.libelle],
            }
            for e in cases
        ]

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


def _uuids(ids):
    import uuid

    return [uuid.UUID(str(i)) for i in ids]


class AffectationProjetCreateSerializer(serializers.Serializer):
    """Données pour affecter un nouveau collaborateur au projet (E-05 / B4)."""

    utilisateur_id = serializers.UUIDField(required=True)
    # Facultatif : par défaut, le rôle du collaborateur sur la plateforme.
    role_projet = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    # Les cases de l'arbre où s'exercent ses permissions ; vide : tout le projet. Leur cohérence
    # (projet, suppression) est vérifiée par le service.
    perimetres_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
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

        from apps.projets.services.affectations import role_par_defaut

        role_projet = (attrs.get("role_projet") or role_par_defaut(user)).upper()
        attrs["role_projet"] = role_projet
        fonction_membre = attrs.get("fonction_membre", "")

        if (
            fonction_membre
            and role_projet != RoleProjet.VISITEUR
        ):
            raise serializers.ValidationError(
                {"fonction_membre": "La fonction de membre ne concerne qu'un invité / consultant."}
            )

        if role_projet == RoleProjet.VISITEUR and not fonction_membre:
            attrs["fonction_membre"] = "AUTRE"

        verifier_role_coherent(user, role_projet)

        date_debut = attrs.get("date_debut")
        date_fin = attrs.get("date_fin")
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError(
                {"date_fin": "La date de fin ne peut pas précéder la date de début."}
            )

        return attrs


class AffectationProjetUpdateSerializer(serializers.Serializer):
    """Données pour modifier rôle, dates, périmètre, fonction ou statut d'une affectation."""

    role_projet = serializers.CharField(max_length=50, required=False)
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)
    est_actif = serializers.BooleanField(required=False)
    perimetres_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    fonction_membre = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        nouveau_role = attrs.get("role_projet", getattr(instance, "role_projet", None))
        if "role_projet" in attrs and instance is not None:
            verifier_role_coherent(instance.utilisateur, attrs["role_projet"])

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
