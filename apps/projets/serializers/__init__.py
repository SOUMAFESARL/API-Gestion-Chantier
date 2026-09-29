"""Serializers pour l'application projets."""

import re

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.accounts.serializers.profil import ProfilEntrepriseSerializer
from apps.accounts.services.invitations import creer_invitation
from apps.core.enums import (
    ModeExecution,
    RoleGlobal,
    RoleProjet,
    StatutUtilisateur,
    TypeBordereau,
    TypeProjet,
)
from apps.core.exceptions import ChefProjetRequis, DgNonAssignableCommeCp
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.projets.serializers.dashboard import TableauDeBordResponseSerializer
from apps.projets.serializers.meteo import (
    MeteoResponseSerializer,
    ReferentielVillesResponseSerializer,
)
from apps.projets.services.affectations import affecter_collaborateur_projet
from apps.projets.services.references import generer_reference_projet
from apps.tiers.models import Tiers
from apps.tiers.serializers import TiersSerializer

__all__ = [
    "ChefProjetEnrichiSerializer",
    "ChefProjetInviteSerializer",
    "EquipeCreationSerializer",
    "LotCreationProjetSerializer",
    "LotSimpleSerializer",
    "MeteoResponseSerializer",
    "ProjetCreationSerializer",
    "ProjetSerializer",
    "ReferentielVillesResponseSerializer",
    "TableauDeBordResponseSerializer",
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


@extend_schema_serializer(component_name="LotProjet")
class LotSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lot
        fields = [
            "id",
            "code",
            "libelle",
            "mode_execution",
            "type_bordereau",
            "date_debut_prevue",
            "date_fin_prevue",
            "avancement",
            "premier_rapport_soumis",
        ]


class ProjetSerializer(serializers.ModelSerializer):
    cree_par = ChefProjetEnrichiSerializer(read_only=True)
    entreprise = serializers.SerializerMethodField()
    client = TiersSerializer(read_only=True)
    chef_projet = ChefProjetEnrichiSerializer(read_only=True)
    conducteur_travaux = ChefProjetEnrichiSerializer(read_only=True)
    lots = LotSimpleSerializer(many=True, read_only=True)
    duree_jours_ouvres = serializers.IntegerField(read_only=True)
    budget_consomme_montant = serializers.SerializerMethodField()

    class Meta:
        model = Projet
        fields = [
            "id",
            "cree_par",
            "entreprise",
            "reference",
            "nom",
            "type_projet",
            "description",
            "client",
            "maitre_oeuvre",
            "ville",
            "quartier",
            "budget_initial_montant",
            "budget_consomme_montant",
            "date_debut_prevue",
            "date_fin_prevue",
            "duree_jours_ouvres",
            "date_debut_reelle",
            "date_fin_reelle",
            "chef_projet",
            "conducteur_travaux",
            "statut",
            "avancement_reel",
            "avancement_theorique",
            "indice_sante",
            "lots",
        ]

    @extend_schema_field(ProfilEntrepriseSerializer(allow_null=True))
    def get_entreprise(self, obj):
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None)
        if tenant is None or tenant.schema_name == "public":
            return None
        logo_url = request.build_absolute_uri(tenant.logo.url) if tenant.logo else None
        return {
            "id": str(tenant.pk),
            "raison_sociale": tenant.raison_sociale,
            "schema_name": tenant.schema_name,
            "logo_url": logo_url,
        }

    def get_budget_consomme_montant(self, obj: Projet) -> int:
        if not obj.budget_initial_montant:
            return 0
        ratio = 0.225
        return int(obj.budget_initial_montant * ratio)


class LotCreationProjetSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    libelle = serializers.CharField(max_length=200)
    mode_execution = serializers.ChoiceField(
        choices=ModeExecution.choices, default=ModeExecution.REGIE
    )
    type_bordereau = serializers.ChoiceField(
        choices=TypeBordereau.choices, default=TypeBordereau.FORFAIT
    )
    date_debut_prevue = serializers.DateField(required=False, allow_null=True, default=None)
    date_fin_prevue = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        debut = attrs.get("date_debut_prevue")
        fin = attrs.get("date_fin_prevue")
        if debut and fin and fin < debut:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": _(
                        "La date de fin du lot ne peut pas précéder sa date de début."
                    )
                }
            )
        return attrs


class EquipeCreationSerializer(serializers.Serializer):
    chef_projet_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    chef_projet_invite = ChefProjetInviteSerializer(required=False, allow_null=True, default=None)
    conducteur_travaux_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    conducteur_travaux_invite = ChefProjetInviteSerializer(
        required=False, allow_null=True, default=None
    )
    chefs_chantier_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    visiteurs_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )


class ProjetCreationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    reference = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    nom = serializers.CharField(max_length=200)
    type_projet = serializers.ChoiceField(
        choices=TypeProjet.choices, required=False, default=TypeProjet.BATIMENT_RESIDENTIEL
    )
    client = serializers.PrimaryKeyRelatedField(queryset=Tiers.objects.all())
    maitre_oeuvre = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    ville = serializers.CharField(max_length=100)
    quartier = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    date_debut_prevue = serializers.DateField()
    date_fin_prevue = serializers.DateField()
    budget_initial_montant = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")

    # Lots (Étape 2) — 0 à N lots acceptés
    lots = LotCreationProjetSerializer(many=True, required=False, default=list)
    lots_supprimer_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="UUID des lots à supprimer logiquement, uniquement en PATCH.",
    )

    # Équipe (Étape 3) — groupée ou à plat
    equipe = EquipeCreationSerializer(required=False, allow_null=True, default=None)

    # Champs à plat pour rétrocompatibilité
    chef_projet_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    chef_projet_invite = ChefProjetInviteSerializer(required=False, allow_null=True, default=None)
    conducteur_travaux_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    conducteur_travaux_invite = ChefProjetInviteSerializer(
        required=False, allow_null=True, default=None
    )
    chefs_chantier_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    visiteurs_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )

    def validate(self, attrs):
        if self.instance is None and "lots_supprimer_ids" in attrs:
            raise serializers.ValidationError(
                {"lots_supprimer_ids": _("Disponible uniquement en modification.")}
            )
        if self.instance is not None and "lots" in attrs:
            # Le PATCH du parent ne rend pas facultatifs les champs des nouveaux lots.
            nouveaux = LotCreationProjetSerializer(data=self.initial_data["lots"], many=True)
            nouveaux.is_valid(raise_exception=True)
            attrs["lots"] = nouveaux.validated_data
        if self.instance is not None:
            non_modifiables = {
                "equipe",
                "chefs_chantier_ids",
                "visiteurs_ids",
                "chef_projet_invite",
                "conducteur_travaux_invite",
            }
            erreurs = {
                champ: _(
                    "Champ réservé à la création. "
                    "Pour l'équipe, utilisez les routes d'affectations."
                )
                for champ in non_modifiables
                if champ in self.initial_data
            }
            if erreurs:
                raise serializers.ValidationError(erreurs)
            if "reference" in attrs and not attrs["reference"].strip():
                raise serializers.ValidationError(
                    {"reference": _("La référence ne peut être vide.")}
                )
            if "chef_projet_id" in attrs and attrs["chef_projet_id"] is None:
                raise ChefProjetRequis()
            responsables = {
                "chef_projet_id": attrs.get("chef_projet_id", self.instance.chef_projet_id),
                "conducteur_travaux_id": attrs.get(
                    "conducteur_travaux_id", self.instance.conducteur_travaux_id
                ),
            }
            if responsables["chef_projet_id"] == responsables["conducteur_travaux_id"]:
                raise serializers.ValidationError(
                    {"conducteur_travaux_id": _("Les responsables doivent être distincts.")}
                )
            for champ, pk in responsables.items():
                if champ not in attrs or pk is None:
                    continue
                if not Utilisateur.objects.filter(
                    pk=pk,
                    is_active=True,
                    statut__in=[StatutUtilisateur.ACTIF, StatutUtilisateur.INVITE],
                ).exists():
                    raise serializers.ValidationError(
                        {champ: _("Utilisateur introuvable ou inactif.")}
                    )
                role = (
                    RoleProjet.CHEF_PROJET
                    if champ == "chef_projet_id"
                    else RoleProjet.CONDUCTEUR_TRAVAUX
                )
                if (
                    AffectationProjet.objects.filter(
                        projet=self.instance,
                        utilisateur_id=pk,
                        est_actif=True,
                    )
                    .exclude(role_projet=role)
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {champ: _("Ce membre occupe déjà un autre rôle sur le projet.")}
                    )
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

        # Contrôle d'unicité de la référence si fournie
        ref = attrs.get("reference")
        if ref and str(ref).strip():
            ref_clean = str(ref).strip()
            qs_ref = Projet.objects.filter(reference=ref_clean)
            if self.instance:
                qs_ref = qs_ref.exclude(pk=self.instance.pk)
            if qs_ref.exists():
                raise serializers.ValidationError(
                    {"reference": _("Cette référence de projet est déjà utilisée.")}
                )

        # Fusion de l'objet equipe s'il est spécifié
        equipe = attrs.get("equipe")
        if equipe:
            for cle in [
                "chef_projet_id",
                "chef_projet_invite",
                "conducteur_travaux_id",
                "conducteur_travaux_invite",
                "chefs_chantier_ids",
                "visiteurs_ids",
            ]:
                if equipe.get(cle) is not None and not attrs.get(cle):
                    attrs[cle] = equipe[cle]

        # Validation de l'unicité des codes de lots si fournis
        lots = attrs.get("lots", [])
        codes_vus = set()
        for lot in lots:
            c = lot.get("code")
            if c and str(c).strip():
                c_clean = str(c).strip().upper()
                if c_clean in codes_vus:
                    raise serializers.ValidationError(
                        {"lots": _(f"Le code de lot '{c_clean}' est présent en doublon.")}
                    )
                codes_vus.add(c_clean)

        # Si création d'un projet, assignation Chef de Projet obligatoire et règles DG
        if self.instance is None:
            chef_projet_id = attrs.get("chef_projet_id")
            chef_projet_invite = attrs.get("chef_projet_invite")
            conducteur_travaux_id = attrs.get("conducteur_travaux_id")
            conducteur_travaux_invite = attrs.get("conducteur_travaux_invite")

            # Rétrocompatibilité : si seul conducteur_travaux est spécifié sans chef_projet
            if not chef_projet_id and not chef_projet_invite:
                if conducteur_travaux_id:
                    chef_projet_id = conducteur_travaux_id
                    attrs["chef_projet_id"] = chef_projet_id
                    attrs["conducteur_travaux_id"] = None
                    conducteur_travaux_id = None
                elif conducteur_travaux_invite:
                    chef_projet_invite = conducteur_travaux_invite
                    attrs["chef_projet_invite"] = chef_projet_invite
                    attrs["conducteur_travaux_invite"] = None
                    conducteur_travaux_invite = None

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

            # Vérification du Chef de Projet
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

            # Vérification du Conducteur de Travaux (s'il est spécifié)
            if conducteur_travaux_id:
                try:
                    target_ct = Utilisateur.objects.get(
                        id=conducteur_travaux_id, supprime_le__isnull=True
                    )
                except Utilisateur.DoesNotExist:
                    raise serializers.ValidationError(
                        {"conducteur_travaux_id": _("Conducteur de travaux introuvable.")}
                    ) from None

                if target_ct.is_dg or getattr(target_ct, "is_owner", False):
                    raise DgNonAssignableCommeCp()

            if conducteur_travaux_invite:
                email_invite_ct = conducteur_travaux_invite.get("email", "").strip().lower()
                existing_ct = Utilisateur.objects.filter(
                    email__iexact=email_invite_ct, supprime_le__isnull=True
                ).first()
                if existing_ct and (existing_ct.is_dg or getattr(existing_ct, "is_owner", False)):
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

            conducteur_travaux_id = attrs.get("conducteur_travaux_id")
            if conducteur_travaux_id:
                try:
                    target_ct = Utilisateur.objects.get(
                        id=conducteur_travaux_id, supprime_le__isnull=True
                    )
                except Utilisateur.DoesNotExist:
                    raise serializers.ValidationError(
                        {"conducteur_travaux_id": _("Conducteur de travaux introuvable.")}
                    ) from None

                if target_ct.is_dg or getattr(target_ct, "is_owner", False):
                    raise DgNonAssignableCommeCp()

        if self.instance is None:
            # Tous les UUID sont résolus dans le schéma de l'entreprise courante.
            membres = {
                "chef_projet_id": [attrs["chef_projet_id"]] if attrs.get("chef_projet_id") else [],
                "conducteur_travaux_id": (
                    [attrs["conducteur_travaux_id"]] if attrs.get("conducteur_travaux_id") else []
                ),
                "chefs_chantier_ids": attrs.get("chefs_chantier_ids", []),
                "visiteurs_ids": attrs.get("visiteurs_ids", []),
            }
            ids = {pk for valeurs in membres.values() for pk in valeurs}
            disponibles = set(
                Utilisateur.objects.filter(
                    pk__in=ids,
                    is_active=True,
                    statut__in=[StatutUtilisateur.ACTIF, StatutUtilisateur.INVITE],
                ).values_list("pk", flat=True)
            )
            erreurs = {
                champ: _("Un membre est introuvable ou inactif dans cette entreprise.")
                for champ, valeurs in membres.items()
                if set(valeurs) - disponibles
            }
            if erreurs:
                raise serializers.ValidationError(erreurs)
            vus = set()
            for champ, valeurs in membres.items():
                if vus.intersection(valeurs):
                    raise serializers.ValidationError(
                        {champ: _("Un utilisateur ne peut occuper qu'un rôle par projet.")}
                    )
                vus.update(valeurs)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        user_connecte = getattr(request, "user", None)

        validated_data.pop("equipe", None)
        lots_data = validated_data.pop("lots", [])
        chefs_chantier_ids = validated_data.pop("chefs_chantier_ids", [])
        visiteurs_ids = validated_data.pop("visiteurs_ids", [])

        conducteur_travaux_id = validated_data.pop("conducteur_travaux_id", None)
        conducteur_travaux_invite = validated_data.pop("conducteur_travaux_invite", None)
        chef_projet_id = validated_data.pop("chef_projet_id", None)
        chef_projet_invite = validated_data.pop("chef_projet_invite", None)

        # Référence automatique si non renseignée
        reference = validated_data.pop("reference", None)
        if not reference or not str(reference).strip():
            reference = generer_reference_projet()
        else:
            reference = str(reference).strip()

        # 1. Résolution Chef de Projet (responsable obligatoire)
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
                    role_global=RoleGlobal.CHEF_PROJET,
                    statut=StatutUtilisateur.INVITE,
                )
        else:
            chef_projet = user_connecte

        # 2. Résolution Conducteur de Travaux (optionnel, distinct du CP)
        conducteur_travaux = None
        if conducteur_travaux_id:
            conducteur_travaux = Utilisateur.objects.get(id=conducteur_travaux_id)
        elif conducteur_travaux_invite:
            email_invite_ct = conducteur_travaux_invite["email"].strip().lower()
            conducteur_travaux = Utilisateur.objects.filter(email__iexact=email_invite_ct).first()
            if not conducteur_travaux:
                conducteur_travaux = Utilisateur.objects.create(
                    email=email_invite_ct,
                    nom=conducteur_travaux_invite["nom"].strip(),
                    prenom=conducteur_travaux_invite["prenom"].strip(),
                    telephone=conducteur_travaux_invite.get("telephone", "").strip(),
                    role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
                    statut=StatutUtilisateur.INVITE,
                )

        hote = request.get_host() if request else None

        with transaction.atomic():
            projet = Projet.objects.create(
                reference=reference,
                cree_par=user_connecte,
                chef_projet=chef_projet,
                conducteur_travaux=conducteur_travaux,
                **validated_data,
            )

            # Invitation du Chef de Projet si invité à la volée
            if chef_projet_invite:
                creer_invitation(
                    email=chef_projet.email,
                    role_propose=RoleGlobal.CHEF_PROJET,
                    nom=f"{chef_projet.prenom} {chef_projet.nom}".strip(),
                    emetteur=(
                        user_connecte if user_connecte and user_connecte.is_authenticated else None
                    ),
                    hote=hote,
                    nom_projet=projet.nom,
                    projet_id=projet.id,
                )

            # Affectation du Chef de Projet (rôle CHEF_PROJET)
            AffectationProjet.objects.get_or_create(
                utilisateur=chef_projet,
                projet=projet,
                defaults={
                    "role_projet": RoleProjet.CHEF_PROJET,
                    "est_actif": True,
                    "cree_par": user_connecte,
                },
            )

            # Affectation et invitation éventuelle du Conducteur de Travaux
            if conducteur_travaux:
                if conducteur_travaux_invite:
                    creer_invitation(
                        email=conducteur_travaux.email,
                        role_propose=RoleGlobal.CONDUCTEUR_TRAVAUX,
                        nom=f"{conducteur_travaux.prenom} {conducteur_travaux.nom}".strip(),
                        emetteur=(
                            user_connecte
                            if user_connecte and user_connecte.is_authenticated
                            else None
                        ),
                        hote=hote,
                        nom_projet=projet.nom,
                        projet_id=projet.id,
                    )

                AffectationProjet.objects.get_or_create(
                    utilisateur=conducteur_travaux,
                    projet=projet,
                    defaults={
                        "role_projet": RoleProjet.CONDUCTEUR_TRAVAUX,
                        "est_actif": True,
                        "cree_par": user_connecte,
                    },
                )

            # Affectation des Chefs de Chantier
            for cc_id in chefs_chantier_ids:
                try:
                    cc_user = Utilisateur.objects.get(id=cc_id)
                    AffectationProjet.objects.get_or_create(
                        utilisateur=cc_user,
                        projet=projet,
                        defaults={
                            "role_projet": RoleProjet.CHEF_CHANTIER,
                            "est_actif": True,
                            "cree_par": user_connecte,
                        },
                    )
                except Utilisateur.DoesNotExist:
                    pass

            # Affectation des Visiteurs
            for vis_id in visiteurs_ids:
                try:
                    vis_user = Utilisateur.objects.get(id=vis_id)
                    AffectationProjet.objects.get_or_create(
                        utilisateur=vis_user,
                        projet=projet,
                        defaults={
                            "role_projet": RoleProjet.VISITEUR,
                            "est_actif": True,
                            "cree_par": user_connecte,
                        },
                    )
                except Utilisateur.DoesNotExist:
                    pass

            # Création des lots initiaux (0 à N lots)
            codes_reserves = {
                str(lot.get("code", "")).strip().upper()
                for lot in lots_data
                if lot.get("code", "").strip()
            }
            for idx, ldata in enumerate(lots_data, start=1):
                code = ldata.get("code")
                if not code or not str(code).strip():
                    numero = idx
                    while f"L-{numero:02d}" in codes_reserves:
                        numero += 1
                    code = f"L-{numero:02d}"
                code = str(code).strip().upper()
                codes_reserves.add(code)
                Lot.objects.create(
                    projet=projet,
                    cree_par=user_connecte,
                    code=str(code).strip(),
                    libelle=ldata["libelle"].strip(),
                    mode_execution=ldata.get("mode_execution", ModeExecution.REGIE),
                    type_bordereau=ldata.get("type_bordereau", TypeBordereau.FORFAIT),
                    date_debut_prevue=ldata.get("date_debut_prevue"),
                    date_fin_prevue=ldata.get("date_fin_prevue"),
                    ordre=idx,
                )

        return projet

    @transaction.atomic
    def update(self, instance, validated_data):
        # Sérialise les changements de responsables concurrents sur ce projet.
        instance = Projet.objects.select_for_update().get(pk=instance.pk)
        user = getattr(self.context.get("request"), "user", None)
        nouveaux_lots = validated_data.pop("lots", [])
        supprimer_ids = set(validated_data.pop("lots_supprimer_ids", []))
        lots_actifs = list(Lot.objects.filter(projet=instance).select_for_update())
        if supprimer_ids - {lot.pk for lot in lots_actifs}:
            raise serializers.ValidationError(
                {"lots_supprimer_ids": _("Lot introuvable ou extérieur à ce projet.")}
            )
        codes = {lot.code.upper() for lot in lots_actifs if lot.pk not in supprimer_ids}
        # Réserver tous les codes explicites avant de générer les codes automatiques.
        for lot in nouveaux_lots:
            code = lot.get("code", "").strip().upper()
            if code:
                if code in codes:
                    raise serializers.ValidationError({"lots": _("Code de lot déjà utilisé.")})
                codes.add(code)
        ordre = max((lot.ordre for lot in lots_actifs), default=0)
        for lot in lots_actifs:
            if lot.pk in supprimer_ids:
                lot.est_actif = False
                lot.save(update_fields=["est_actif"])
                lot.delete(utilisateur=user)
        for donnees in nouveaux_lots:
            donnees = dict(donnees)
            code = donnees.pop("code", "").strip().upper()
            if not code:
                numero = 1
                while f"L-{numero:02d}" in codes:
                    numero += 1
                code = f"L-{numero:02d}"
                codes.add(code)
            ordre += 1
            Lot.objects.create(
                projet=instance,
                cree_par=user,
                code=code,
                ordre=ordre,
                **donnees,
            )
        for champ, role in (
            ("chef_projet_id", RoleProjet.CHEF_PROJET),
            ("conducteur_travaux_id", RoleProjet.CONDUCTEUR_TRAVAUX),
        ):
            if champ not in validated_data:
                continue
            nouveau_id = validated_data.pop(champ)
            ancien_id = getattr(instance, champ)
            if ancien_id != nouveau_id and ancien_id:
                AffectationProjet.objects.filter(
                    projet=instance,
                    utilisateur_id=ancien_id,
                    role_projet=role,
                ).update(est_actif=False)
            setattr(instance, champ, nouveau_id)
            if nouveau_id:
                affecter_collaborateur_projet(
                    projet=instance,
                    utilisateur=Utilisateur.objects.get(pk=nouveau_id),
                    role_projet=role,
                    modifie_par=user,
                )
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        return instance
