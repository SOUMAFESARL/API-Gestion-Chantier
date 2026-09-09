"""Serializers pour l'application projets."""

import re

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.accounts.services.invitations import creer_invitation
from apps.core.enums import RoleGlobal, RoleProjet, StatutUtilisateur
from apps.core.exceptions import ChefProjetRequis, DgNonAssignableCommeCp
from apps.projets.models import AffectationProjet, Projet
from apps.projets.services.references import generer_reference_projet
from apps.tiers.models import Tiers
from apps.tiers.serializers import TiersSerializer

__all__ = [
    "ChefProjetEnrichiSerializer",
    "ChefProjetInviteSerializer",
    "ProjetCreationSerializer",
    "ProjetSerializer",
]


class ChefProjetEnrichiSerializer(serializers.ModelSerializer):
    nom_complet = serializers.SerializerMethodField()
    lien_whatsapp = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = [
            "id",
            "nom",
            "prenom",
            "nom_complet",
            "email",
            "telephone",
            "statut",
            "lien_whatsapp",
        ]

    def get_nom_complet(self, obj: Utilisateur) -> str:
        return f"{obj.prenom} {obj.nom}".strip() or obj.email

    def get_lien_whatsapp(self, obj: Utilisateur) -> str | None:
        if not obj.telephone:
            return None
        chiffres = re.sub(r"[^\d]", "", str(obj.telephone))
        return f"https://wa.me/{chiffres}" if chiffres else None


class ChefProjetInviteSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    telephone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")


class ProjetSerializer(serializers.ModelSerializer):
    client = TiersSerializer(read_only=True)
    chef_projet = ChefProjetEnrichiSerializer(read_only=True)
    conducteur_travaux = ChefProjetEnrichiSerializer(source="chef_projet", read_only=True)
    budget_consomme_montant = serializers.SerializerMethodField()

    class Meta:
        model = Projet
        fields = [
            "id",
            "reference",
            "nom",
            "description",
            "client",
            "ville",
            "quartier",
            "budget_initial_montant",
            "budget_consomme_montant",
            "date_debut_prevue",
            "date_fin_prevue",
            "date_debut_reelle",
            "date_fin_reelle",
            "chef_projet",
            "conducteur_travaux",
            "statut",
            "avancement_reel",
            "avancement_theorique",
            "indice_sante",
        ]

    def get_budget_consomme_montant(self, obj: Projet) -> int:
        if not obj.budget_initial_montant:
            return 0
        ratio = 0.225
        return int(obj.budget_initial_montant * ratio)


class ProjetCreationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    reference = serializers.CharField(read_only=True)
    nom = serializers.CharField(max_length=200)
    client = serializers.PrimaryKeyRelatedField(queryset=Tiers.objects.all())
    ville = serializers.CharField(max_length=100)
    quartier = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    date_debut_prevue = serializers.DateField()
    date_fin_prevue = serializers.DateField()
    budget_initial_montant = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")

    chef_projet_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    chef_projet_invite = ChefProjetInviteSerializer(required=False, allow_null=True, default=None)
    conducteur_travaux_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    conducteur_travaux_invite = ChefProjetInviteSerializer(
        required=False, allow_null=True, default=None
    )

    def validate(self, attrs):
        debut = attrs.get("date_debut_prevue") or (
            self.instance.date_debut_prevue if self.instance else None
        )
        fin = attrs.get("date_fin_prevue") or (
            self.instance.date_fin_prevue if self.instance else None
        )
        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                {"date_fin_prevue": _("La date de fin doit être postérieure à la date de début.")}
            )

        # Harmonisation conducteur_travaux / chef_projet
        chef_projet_id = attrs.get("conducteur_travaux_id") or attrs.get("chef_projet_id")
        chef_projet_invite = attrs.get("conducteur_travaux_invite") or attrs.get(
            "chef_projet_invite"
        )
        attrs["chef_projet_id"] = chef_projet_id
        attrs["chef_projet_invite"] = chef_projet_invite

        # Si création d'un projet, assignation Conducteur de Travaux obligatoire et règles DG
        if self.instance is None:
            chef_projet_id = attrs.get("chef_projet_id")
            chef_projet_invite = attrs.get("chef_projet_invite")

            if not chef_projet_id and not chef_projet_invite:
                raise ChefProjetRequis()

            if chef_projet_id and chef_projet_invite:
                raise serializers.ValidationError(
                    {
                        "chef_projet": _(
                            "Veuillez spécifier soit chef_projet_id, "
                            "soit chef_projet_invite, pas les deux."
                        )
                    }
                )

            request = self.context.get("request")
            user_connecte = getattr(request, "user", None)

            if chef_projet_id:
                try:
                    target_cp = Utilisateur.objects.get(id=chef_projet_id, supprime_le__isnull=True)
                except Utilisateur.DoesNotExist:
                    raise serializers.ValidationError(
                        {"chef_projet_id": _("Utilisateur introuvable.")}
                    ) from None

                # Règle R-DEMO-03 : Le DG ne peut jamais être sélectionné comme CP
                if target_cp.is_dg or getattr(target_cp, "is_owner", False):
                    raise DgNonAssignableCommeCp()

                if (
                    user_connecte
                    and (
                        getattr(user_connecte, "is_dg", False)
                        or getattr(user_connecte, "is_owner", False)
                    )
                    and target_cp.id == user_connecte.id
                ):
                    raise DgNonAssignableCommeCp()

            if chef_projet_invite:
                email_invite = chef_projet_invite.get("email", "").strip().lower()
                if (
                    user_connecte
                    and user_connecte.email.strip().lower() == email_invite
                    and (
                        getattr(user_connecte, "is_dg", False)
                        or getattr(user_connecte, "is_owner", False)
                    )
                ):
                    raise DgNonAssignableCommeCp()

                existing = Utilisateur.objects.filter(
                    email__iexact=email_invite, supprime_le__isnull=True
                ).first()
                if existing and (existing.is_dg or getattr(existing, "is_owner", False)):
                    raise DgNonAssignableCommeCp()

        else:
            # En cas de modification (PATCH)
            chef_projet_id = attrs.get("chef_projet_id")
            if chef_projet_id:
                try:
                    target_cp = Utilisateur.objects.get(id=chef_projet_id, supprime_le__isnull=True)
                except Utilisateur.DoesNotExist:
                    raise serializers.ValidationError(
                        {"chef_projet_id": _("Utilisateur introuvable.")}
                    ) from None

                if target_cp.is_dg or getattr(target_cp, "is_owner", False):
                    raise DgNonAssignableCommeCp()

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user_connecte = getattr(request, "user", None)

        conducteur_travaux_id = validated_data.pop("conducteur_travaux_id", None)
        conducteur_travaux_invite = validated_data.pop("conducteur_travaux_invite", None)
        chef_projet_id = validated_data.pop("chef_projet_id", None) or conducteur_travaux_id
        chef_projet_invite = (
            validated_data.pop("chef_projet_invite", None) or conducteur_travaux_invite
        )

        if chef_projet_id:
            chef_projet = Utilisateur.objects.get(id=chef_projet_id)
        elif chef_projet_invite:
            email_invite = chef_projet_invite["email"].strip().lower()
            chef_projet = Utilisateur.objects.filter(email__iexact=email_invite).first()
            if not chef_projet:
                chef_projet = Utilisateur.objects.create(
                    email=email_invite,
                    nom=chef_projet_invite["nom"].strip(),
                    prenom=chef_projet_invite["prenom"].strip(),
                    telephone=chef_projet_invite.get("telephone", "").strip(),
                    role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
                    statut=StatutUtilisateur.INVITE,
                )
        else:
            chef_projet = user_connecte

        reference = generer_reference_projet()

        with transaction.atomic():
            projet = Projet.objects.create(
                reference=reference,
                chef_projet=chef_projet,
                **validated_data,
            )

            # Si invité à la volée, déclencher l'invitation liée au projet avec le rôle Conducteur de Travaux
            if chef_projet_invite:
                hote = request.get_host() if request else None
                creer_invitation(
                    email=chef_projet.email,
                    role_propose=RoleGlobal.CONDUCTEUR_TRAVAUX,
                    nom=f"{chef_projet.prenom} {chef_projet.nom}".strip(),
                    emetteur=(
                        user_connecte if user_connecte and user_connecte.is_authenticated else None
                    ),
                    hote=hote,
                    nom_projet=projet.nom,
                    projet_id=projet.id,
                )

            # Affectation automatique comme Conducteur de Travaux responsable
            if chef_projet:
                AffectationProjet.objects.get_or_create(
                    utilisateur=chef_projet,
                    projet=projet,
                    defaults={"role_projet": RoleProjet.CONDUCTEUR_TRAVAUX, "est_actif": True},
                )

        return projet

    def update(self, instance, validated_data):
        conducteur_travaux_id = validated_data.pop("conducteur_travaux_id", None)
        validated_data.pop("conducteur_travaux_invite", None)
        chef_projet_id = validated_data.pop("chef_projet_id", None) or conducteur_travaux_id
        validated_data.pop("chef_projet_invite", None)

        if chef_projet_id:
            instance.chef_projet = Utilisateur.objects.get(id=chef_projet_id)
            AffectationProjet.objects.get_or_create(
                utilisateur=instance.chef_projet,
                projet=instance,
                defaults={"role_projet": RoleProjet.CONDUCTEUR_TRAVAUX, "est_actif": True},
            )

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        return instance
