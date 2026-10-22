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
    StatutProjet,
    StatutUtilisateur,
    TypeBordereau,
    TypeProjet,
)
from apps.projets.models import AffectationProjet, Lot, Projet
from apps.projets.serializers.activite import (
    ActiviteAvancementSerializer,
    ActiviteCreationSerializer,
    ActiviteModificationSerializer,
    ActiviteSerializer,
    MiseAJourInlineSerializer,
)
from apps.projets.serializers.arret_chantier import (
    ArretChantierCreateSerializer,
    ArretChantierSerializer,
    ArretChantierUpdateSerializer,
)
from apps.projets.serializers.calendrier import (
    CalendrierQuerySerializer,
    CalendrierResponseSerializer,
    ExceptionCalendrierCreateSerializer,
    ExceptionCalendrierResponseSerializer,
    JourFerieResponseSerializer,
    SemaineTypeSerializer,
    SemaineTypeUpdateSerializer,
)
from apps.projets.serializers.dashboard import TableauDeBordResponseSerializer
from apps.projets.serializers.meteo import (
    MeteoResponseSerializer,
    ReferentielVillesResponseSerializer,
)
from apps.projets.serializers.reprogrammation import (
    HistoriqueDateSerializer,
    MotifReportCreationSerializer,
    MotifReportSerializer,
    ReprogrammationRequestSerializer,
    ReprogrammationResponseSerializer,
)
from apps.projets.serializers.sante import (
    SanteApercuSerializer,
    SanteDetailResponseSerializer,
    SanteHistoriqueItemSerializer,
)
from apps.projets.services.affectations import affecter_collaborateur_projet, verifier_affectable
from apps.projets.services.references import generer_reference_projet
from apps.tiers.models import Tiers
from apps.tiers.serializers import TiersSerializer

__all__ = [
    "ActiviteAvancementSerializer",
    "ActiviteCreationSerializer",
    "ActiviteModificationSerializer",
    "ActiviteSerializer",
    "ArretChantierCreateSerializer",
    "ArretChantierSerializer",
    "ArretChantierUpdateSerializer",
    "CalendrierQuerySerializer",
    "CalendrierResponseSerializer",
    "ChefProjetEnrichiSerializer",
    "ChefProjetInviteSerializer",
    "DureeProjetSerializer",
    "EquipeCreationSerializer",
    "ExceptionCalendrierCreateSerializer",
    "ExceptionCalendrierResponseSerializer",
    "HistoriqueDateSerializer",
    "JourFerieResponseSerializer",
    "LotCreationProjetSerializer",
    "LotSimpleSerializer",
    "MeteoResponseSerializer",
    "MiseAJourInlineSerializer",
    "MotifReportCreationSerializer",
    "MotifReportSerializer",
    "ProjetCreationSerializer",
    "ProjetSerializer",
    "ReferentielVillesResponseSerializer",
    "ReprogrammationRequestSerializer",
    "ReprogrammationResponseSerializer",
    "SanteApercuSerializer",
    "SanteDetailResponseSerializer",
    "SanteHistoriqueItemSerializer",
    "SemaineTypeSerializer",
    "SemaineTypeUpdateSerializer",
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


class DureeProjetSerializer(serializers.Serializer):
    """Durée calendaire et ouvrée d'un projet."""

    annees = serializers.IntegerField(read_only=True)
    mois = serializers.IntegerField(read_only=True)
    jours = serializers.IntegerField(read_only=True)
    jours_ouvres = serializers.IntegerField(read_only=True)


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
            "date_debut_baseline",
            "date_fin_baseline",
            "avancement",
            "statut",
            "premier_rapport_soumis",
        ]


class ProjetSerializer(serializers.ModelSerializer):
    maitre_ouvrage = serializers.SerializerMethodField()
    cree_par = ChefProjetEnrichiSerializer(read_only=True)
    entreprise = serializers.SerializerMethodField()
    client = TiersSerializer(read_only=True)
    chef_projet = ChefProjetEnrichiSerializer(read_only=True, allow_null=True)
    conducteur_travaux = ChefProjetEnrichiSerializer(read_only=True, allow_null=True)
    lots = LotSimpleSerializer(many=True, read_only=True)
    duree_jours_ouvres = serializers.IntegerField(read_only=True)
    duree = DureeProjetSerializer(source="duree_calendaire", read_only=True, allow_null=True)
    peut_renommer = serializers.SerializerMethodField()
    avancement_theorique = serializers.SerializerMethodField()
    delta_retard = serializers.SerializerMethodField()

    class Meta:
        model = Projet
        fields = [
            "id",
            "cree_par",
            "entreprise",
            "reference",
            "nom",
            "peut_renommer",
            "type_projet",
            "description",
            "client",
            "maitre_ouvrage",
            "maitre_oeuvre",
            "ville",
            "quartier",
            "budget_initial_montant",
            "date_debut_prevue",
            "date_fin_prevue",
            "date_debut_baseline",
            "date_fin_baseline",
            "duree_jours_ouvres",
            "duree",
            "date_debut_reelle",
            "date_fin_reelle",
            "chef_projet",
            "conducteur_travaux",
            "sans_chef_projet",
            "statut",
            "avancement_reel",
            "avancement_theorique",
            "delta_retard",
            "indice_sante",
            "lots",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_peut_renommer(self, obj) -> bool:
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        if not user or not getattr(user, "is_authenticated", False):
            return False
        from apps.core.droits import est_administrateur, est_dg

        return bool(est_dg(user) or est_administrateur(user))

    def get_maitre_ouvrage(self, obj) -> str:
        return obj.maitre_ouvrage or (obj.client.raison_sociale if obj.client_id else "")

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

    def _get_indicateurs(self, obj) -> dict:
        cache_attr = "_indicateurs_temporels_cache"
        if not hasattr(obj, cache_attr):
            from apps.projets.services.indicateurs_temporels import indicateurs_temporels_projet

            ctx = getattr(self, "context", None)
            cal = ctx.get("calendrier_temporel") if ctx else None
            setattr(obj, cache_attr, indicateurs_temporels_projet(obj, calendrier=cal))
        return getattr(obj, cache_attr)

    @extend_schema_field(serializers.FloatField())
    def get_avancement_theorique(self, obj) -> float:
        return self._get_indicateurs(obj)["avancement_temporel"]

    @extend_schema_field(serializers.FloatField())
    def get_delta_retard(self, obj) -> float:
        return self._get_indicateurs(obj)["delta_retard"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(user, request):
            from apps.core.purger_montants import purger_montants_recursif

            data = purger_montants_recursif(data)
        return data


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
    budget_initial_montant = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )

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
    # Un code des référentiels (plateforme + entreprise) — voir `validate_type_projet`.
    type_projet = serializers.CharField(
        max_length=60, required=False, default=TypeProjet.BATIMENT_RESIDENTIEL
    )
    statut = serializers.ChoiceField(
        choices=StatutProjet.choices, required=False, default=StatutProjet.EN_ATTENTE
    )
    client = serializers.PrimaryKeyRelatedField(queryset=Tiers.objects.all(), required=False)
    maitre_ouvrage = serializers.CharField(max_length=200, required=False)
    maitre_oeuvre = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    ville = serializers.CharField(max_length=100)
    quartier = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    date_debut_prevue = serializers.DateField(required=False, allow_null=True)
    date_fin_prevue = serializers.DateField(required=False, allow_null=True)
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

    def validate_budget_initial_montant(self, value):
        request = self.context.get("request") if getattr(self, "context", None) else None
        from apps.core.purger_montants import valider_ecriture_montant

        return valider_ecriture_montant(value, request=request, champ="budget_initial_montant")

    def _responsable_coherent(self, value, role_projet):
        """Règle du 16/10/2026 : le CP (ou CT) désigné a ce rôle sur la plateforme."""
        if value:
            from apps.projets.serializers.affectation import verifier_role_coherent

            user = Utilisateur.objects.filter(pk=value).select_related("role").first()
            # Le DG garde son refus dédié (422, DgNonAssignableCommeCp), posé plus loin.
            if user is not None and not (user.is_dg or user.is_owner):
                try:
                    verifier_role_coherent(user, role_projet)
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError(exc.detail["role_projet"]) from exc
        return value

    def validate_chef_projet_id(self, value):
        return self._responsable_coherent(value, RoleProjet.CHEF_PROJET)

    def validate_conducteur_travaux_id(self, value):
        return self._responsable_coherent(value, RoleProjet.CONDUCTEUR_TRAVAUX)

    def validate_type_projet(self, value: str) -> str:
        from apps.projets.services.referentiels import code_type_projet_valide

        if not code_type_projet_valide(value):
            raise serializers.ValidationError(
                _("Choisissez un type de projet dans la liste, ou ajoutez-le.")
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request") if getattr(self, "context", None) else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(getattr(request, "user", None) if request else None, request):
            if "budget_initial_montant" in attrs and attrs["budget_initial_montant"] is None:
                attrs.pop("budget_initial_montant")

        if "client" in attrs and "maitre_ouvrage" in attrs:
            raise serializers.ValidationError(
                {
                    "maitre_ouvrage": _(
                        "Envoyez le nom du maître d'ouvrage ou un client, pas les deux."
                    )
                }
            )
        if self.instance is None and not attrs.get("maitre_ouvrage") and not attrs.get("client"):
            raise serializers.ValidationError({"maitre_ouvrage": _("Ce champ est obligatoire.")})
        if self.instance is None and "lots_supprimer_ids" in attrs:
            raise serializers.ValidationError(
                {"lots_supprimer_ids": _("Disponible uniquement en modification.")}
            )
        if self.instance is None:
            budget_projet = attrs.get("budget_initial_montant")
            lots = attrs.get("lots", [])
            if lots:
                debut_p = attrs.get("date_debut_prevue")
                fin_p = attrs.get("date_fin_prevue")
                if not debut_p or not fin_p:
                    from apps.projets.services.calendrier import MSG_EXIGER_DATES_PROJET

                    raise serializers.ValidationError({"lots": MSG_EXIGER_DATES_PROJET})
                from apps.projets.services.calendrier import formater_date

                for lot in lots:
                    debut_l = lot.get("date_debut_prevue")
                    fin_l = lot.get("date_fin_prevue")
                    if debut_l and debut_p and debut_l < debut_p:
                        raise serializers.ValidationError(
                            {"lots": f"Le lot ne peut pas commencer avant le début du projet ({formater_date(debut_p)})."}
                        )
                    if fin_l and fin_p and fin_l > fin_p:
                        raise serializers.ValidationError(
                            {"lots": f"Le lot ne peut pas finir après la fin du projet ({formater_date(fin_p)})."}
                        )
            if budget_projet is not None and lots:
                somme_lots = sum(
                    lot.get("budget_initial_montant")
                    for lot in lots
                    if lot.get("budget_initial_montant") is not None
                )
                if somme_lots > budget_projet:
                    from apps.core.fields import formater_fcfa

                    disponible = max(0, budget_projet)
                    raise serializers.ValidationError(
                        {
                            "budget_initial_montant": (
                                f"Le budget des lots dépasserait celui du projet : "
                                f"il reste {formater_fcfa(disponible)} sur un budget projet de "
                                f"{formater_fcfa(budget_projet)}."
                            )
                        }
                    )
        if self.instance is not None and "lots" in attrs:
            # Le PATCH du parent ne rend pas facultatifs les champs des nouveaux lots.
            nouveaux = LotCreationProjetSerializer(data=self.initial_data["lots"], many=True)
            nouveaux.is_valid(raise_exception=True)
            attrs["lots"] = nouveaux.validated_data
            if attrs["lots"]:
                if not self.instance.date_debut_prevue or not self.instance.date_fin_prevue:
                    from apps.projets.services.calendrier import MSG_EXIGER_DATES_PROJET

                    raise serializers.ValidationError({"lots": MSG_EXIGER_DATES_PROJET})
                from apps.projets.services.calendrier import formater_date

                for lot in attrs["lots"]:
                    debut_l = lot.get("date_debut_prevue")
                    fin_l = lot.get("date_fin_prevue")
                    if (
                        debut_l
                        and self.instance.date_debut_prevue
                        and debut_l < self.instance.date_debut_prevue
                    ):
                        d_proj = formater_date(self.instance.date_debut_prevue)
                        raise serializers.ValidationError(
                            {"lots": f"Le lot ne peut pas commencer avant le début du projet ({d_proj})."}
                        )
                    if (
                        fin_l
                        and self.instance.date_fin_prevue
                        and fin_l > self.instance.date_fin_prevue
                    ):
                        f_proj = formater_date(self.instance.date_fin_prevue)
                        raise serializers.ValidationError(
                            {"lots": f"Le lot ne peut pas finir après la fin du projet ({f_proj})."}
                        )
            from apps.projets.services.budgets import verifier_budgets_lots_a_creer

            verifier_budgets_lots_a_creer(
                self.instance,
                [lot.get("budget_initial_montant") for lot in attrs["lots"]],
            )
        if self.instance is not None:
            if "budget_initial_montant" in attrs:
                from apps.projets.services.budgets import verifier_budget_projet

                verifier_budget_projet(self.instance, attrs.get("budget_initial_montant"))
            if "date_debut_baseline" in self.initial_data or "date_fin_baseline" in self.initial_data:
                raise serializers.ValidationError(
                    {"date_debut_baseline": _("La Baseline v0 est immuable et ne peut être modifiée.")}
                )
            if (
                (
                    "date_debut_prevue" in self.initial_data
                    and self.instance.date_debut_prevue is not None
                    and attrs.get("date_debut_prevue") != self.instance.date_debut_prevue
                )
                or (
                    "date_fin_prevue" in self.initial_data
                    and self.instance.date_fin_prevue is not None
                    and attrs.get("date_fin_prevue") != self.instance.date_fin_prevue
                )
            ):
                raise serializers.ValidationError(
                    {
                        "date_fin_prevue": _(
                            "La modification des dates prévisionnelles requiert un motif et une justification (RG-11). "
                            "Veuillez utiliser la route dédiée : POST /api/v1/projets/{id}/reprogrammer/."
                        )
                    }
                )
            if "nom" in attrs and attrs["nom"] != self.instance.nom:
                from rest_framework.exceptions import PermissionDenied

                from apps.core.droits import est_administrateur, est_dg

                request = self.context.get("request") if getattr(self, "context", None) else None
                user = getattr(request, "user", None) if request else None
                if not (est_dg(user) or est_administrateur(user)):
                    msg = (
                        "Seuls le Directeur Général et l'administrateur de "
                        "l'entreprise peuvent renommer un projet."
                    )
                    raise PermissionDenied(msg)
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
            responsables = {
                "chef_projet_id": attrs.get("chef_projet_id", self.instance.chef_projet_id),
                "conducteur_travaux_id": attrs.get(
                    "conducteur_travaux_id", self.instance.conducteur_travaux_id
                ),
            }
            if (
                responsables["chef_projet_id"]
                and responsables["conducteur_travaux_id"]
                and responsables["chef_projet_id"] == responsables["conducteur_travaux_id"]
            ):
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
        debut = attrs.get(
            "date_debut_prevue", self.instance.date_debut_prevue if self.instance else None
        )
        fin = attrs.get("date_fin_prevue", self.instance.date_fin_prevue if self.instance else None)
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

        if (
            self.instance is None
            and attrs.get("chef_projet_id")
            and attrs.get("chef_projet_invite")
        ):
            raise serializers.ValidationError(
                {
                    "chef_projet": _(
                        "Veuillez spécifier soit chef_projet_id, "
                        "soit chef_projet_invite, pas les deux."
                    )
                }
            )

        # Le DG ne tient aucune fonction sur un chantier (décision du 14/10/2026) :
        # ni chef de projet, ni conducteur de travaux, ni chef de chantier.
        introuvables = {
            "chef_projet_id": _("Utilisateur introuvable."),
            "conducteur_travaux_id": _("Conducteur de travaux introuvable."),
        }
        for champ, message in introuvables.items():
            pk = attrs.get(champ)
            if not pk:
                continue
            cible = Utilisateur.objects.filter(id=pk, supprime_le__isnull=True).first()
            if cible is None:
                raise serializers.ValidationError({champ: message})
            verifier_affectable(cible)
        if self.instance is None:
            for invite in (attrs.get("chef_projet_invite"), attrs.get("conducteur_travaux_invite")):
                if invite:
                    email = invite.get("email", "").strip().lower()
                    verifier_affectable(
                        Utilisateur.objects.filter(
                            email__iexact=email, supprime_le__isnull=True
                        ).first()
                    )
            for pk in [*attrs.get("chefs_chantier_ids", []), *attrs.get("visiteurs_ids", [])]:
                verifier_affectable(
                    Utilisateur.objects.filter(pk=pk, supprime_le__isnull=True).first()
                )

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

        # 1. Résolution Chef de Projet (optionnel)
        chef_projet = None
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
            if chef_projet and chef_projet_invite:
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

            # Affectation du Chef de Projet (rôle CHEF_PROJET) si spécifié
            if chef_projet:
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
                    budget_initial_montant=ldata.get("budget_initial_montant"),
                    ordre=idx,
                )

        return projet

    @transaction.atomic
    def update(self, instance, validated_data):
        # Sérialise les changements de responsables concurrents sur ce projet.
        instance = Projet.objects.select_for_update().get(pk=instance.pk)
        if "maitre_ouvrage" in validated_data:
            instance.client = None
        elif "client" in validated_data:
            instance.maitre_ouvrage = ""
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
        ancien_nom = instance.nom
        ancien_budget = instance.budget_initial_montant
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if "nom" in validated_data and ancien_nom != instance.nom:
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            request = self.context.get("request") if getattr(self, "context", None) else None
            user = getattr(request, "user", None) if request else None
            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="projet",
                entite_id=instance.pk,
                utilisateur_id=user.pk if user and user.is_authenticated else None,
                valeur_avant={"nom": ancien_nom},
                valeur_apres={"nom": instance.nom},
                adresse_ip=getattr(request, "META", {}).get("REMOTE_ADDR") if request else None,
                appareil=getattr(request, "META", {}).get("HTTP_USER_AGENT", "") if request else "",
            )
        if (
            "budget_initial_montant" in validated_data
            and ancien_budget != instance.budget_initial_montant
        ):
            from apps.audit.services import journaliser
            from apps.core.enums import ActionAudit

            request = self.context.get("request") if getattr(self, "context", None) else None
            user = getattr(request, "user", None) if request else None
            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="projet",
                entite_id=instance.pk,
                utilisateur_id=user.pk if user and user.is_authenticated else None,
                valeur_avant={"budget_initial_montant": ancien_budget},
                valeur_apres={"budget_initial_montant": instance.budget_initial_montant},
                adresse_ip=getattr(request, "META", {}).get("REMOTE_ADDR") if request else None,
                appareil=getattr(request, "META", {}).get("HTTP_USER_AGENT", "") if request else "",
            )
        return instance
