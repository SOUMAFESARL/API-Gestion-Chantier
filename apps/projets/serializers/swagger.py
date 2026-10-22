"""Creation form and update contracts."""

from django.db import transaction
from django.urls import reverse
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.core.enums import StatutProjet
from apps.projets.models import Projet, ProjetContrat
from apps.projets.selectors.encadrement import (
    autres_membres_affectations,
    chef_projet_affectation,
    chefs_chantier_affectations,
    conducteurs_travaux_avec_affectations,
)
from apps.projets.serializers import (
    ChefProjetEnrichiSerializer,
    DureeProjetSerializer,
    ProjetCreationSerializer,
)
from apps.projets.serializers.statistiques import StatistiquesProjetSerializer
from apps.projets.services.contrats import (
    MAX_LOT,
    ajouter_contrats,
    nettoyer_contrats,
    valider_fichier_contrat,
)
from apps.projets.services.statistiques import statistiques_lots

CHAMPS_FORMULAIRE = (
    "nom",
    "statut",
    "reference",
    "type_projet",
    "ville",
    "maitre_ouvrage",
    "maitre_oeuvre",
    "date_debut_prevue",
    "date_fin_prevue",
    "date_debut_reelle",
    "date_fin_reelle",
    "duree_jours_ouvres",
    "duree",
    "budget_initial_montant",
    "description",
    "contrat",
    "chef_projet_id",
    "conducteur_travaux_id",
)
CHAMPS_REPONSE = (
    "id",
    *CHAMPS_FORMULAIRE,
    "avancement_reel",
    "avancement_theorique",
    "delta_retard",
    "indice_sante",
    "statistiques",
    "sans_chef_projet",
    "peut_renommer",
    # L'encadrement, en lecture : le frontend en déduit qui voit le chantier.
    "chef_projet",
    "conducteurs_travaux",
    "chefs_chantier",
    "autres_membres",
)


@extend_schema_field(OpenApiTypes.BINARY)
class FichierContratField(serializers.FileField):
    """An uploaded binary file, not a URL in the OpenAPI request body."""


class ProjetPostSerializer(ProjetCreationSerializer):
    """Only visible fields; reference and duration are generated."""

    reference = serializers.CharField(read_only=True)
    date_debut_reelle = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Début réel facultatif (YYYY-MM-DD). Omission : conserver ; null : effacer.",
    )
    date_fin_reelle = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Fin réelle facultative, au plus tôt le jour du début réel. null : effacer.",
    )
    statut = serializers.ChoiceField(
        choices=StatutProjet.choices,
        required=False,
        default=StatutProjet.EN_ATTENTE,
        help_text=(
            "État du projet entier. EN_ATTENTE par défaut à la création. "
            "Utiliser EN_COURS pour réactiver. Ces états ne bloquent pas les opérations."
        ),
    )
    duree_jours_ouvres = serializers.IntegerField(read_only=True, allow_null=True)
    duree = DureeProjetSerializer(source="duree_calendaire", read_only=True, allow_null=True)
    type_projet = serializers.CharField(max_length=60)
    maitre_ouvrage = serializers.CharField(max_length=200)
    contrat = serializers.ListField(
        child=FichierContratField(validators=[valider_fichier_contrat]),
        required=False,
        max_length=10,
        help_text="Un ou plusieurs PDF/JPG/JPEG/PNG. Repeter contrat en multipart. 10 Mo/fichier.",
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        debut = attrs.get("date_debut_reelle", getattr(self.instance, "date_debut_reelle", None))
        fin = attrs.get("date_fin_reelle", getattr(self.instance, "date_fin_reelle", None))
        if debut is not None and fin is not None and fin < debut:
            raise serializers.ValidationError(
                {"date_fin_reelle": "La fin réelle ne peut pas précéder le début réel."}
            )
        return attrs

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
            if "chef_projet" in data and "chef_projet_id" not in data:
                data = dict(data)
                data["chef_projet_id"] = data.pop("chef_projet")
            if "conducteur_travaux" in data and "conducteur_travaux_id" not in data:
                data = dict(data)
                data["conducteur_travaux_id"] = data.pop("conducteur_travaux")
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


class ChefChantierProjetSerializer(serializers.Serializer):
    """Un chef de chantier du projet."""

    utilisateur = ChefProjetEnrichiSerializer()
    zone = serializers.CharField(allow_null=True)
    affectation_id = serializers.UUIDField(allow_null=True)


class AutreMembreProjetSerializer(serializers.Serializer):
    """Un autre membre de l'encadrement (consultant/invité VI)."""

    id = serializers.UUIDField()
    nom = serializers.CharField()
    prenom = serializers.CharField()
    nom_complet = serializers.CharField()
    email = serializers.CharField(allow_blank=True, default="")
    telephone = serializers.CharField(allow_blank=True, default="")
    statut = serializers.CharField(default="")
    lien_whatsapp = serializers.CharField(allow_null=True, default=None)
    fonction = serializers.CharField()
    affectation_id = serializers.UUIDField()
    utilisateur = ChefProjetEnrichiSerializer(required=False)


class ProjetCreationResponseSerializer(serializers.ModelSerializer):
    chef_projet = serializers.SerializerMethodField(
        help_text="Le chef de projet désigné, en clair ; null si le projet n'en a pas.",
    )

    @extend_schema_field(ChefProjetEnrichiSerializer(allow_null=True))
    def get_chef_projet(self, obj) -> dict | None:
        if not obj.chef_projet:
            return None
        data = ChefProjetEnrichiSerializer(obj.chef_projet, context=self.context).data
        aff = chef_projet_affectation(obj)
        data["affectation_id"] = str(aff.id) if aff else None
        return data

    peut_renommer = serializers.SerializerMethodField(
        help_text="Indique si l'utilisateur connecté peut renommer le projet (DG ou AD)."
    )

    @extend_schema_field(serializers.BooleanField())
    def get_peut_renommer(self, obj) -> bool:
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        if not user or not getattr(user, "is_authenticated", False):
            return False
        from apps.core.droits import est_administrateur, est_dg

        return bool(est_dg(user) or est_administrateur(user))

    conducteurs_travaux = serializers.SerializerMethodField(
        help_text="Le conducteur principal puis les conducteurs affectés et en vigueur."
    )
    chefs_chantier = serializers.SerializerMethodField(
        help_text="Les chefs de chantier affectés et en vigueur."
    )
    autres_membres = serializers.SerializerMethodField(
        help_text="Les autres membres de l'encadrement affectés (consultants/invités VI)."
    )

    @extend_schema_field(ChefProjetEnrichiSerializer(many=True))
    def get_conducteurs_travaux(self, obj) -> list:
        resultats = []
        for u, aff in conducteurs_travaux_avec_affectations(obj):
            data = ChefProjetEnrichiSerializer(u, context=self.context).data
            data["affectation_id"] = str(aff.id) if aff else None
            resultats.append(data)
        return resultats

    @extend_schema_field(ChefChantierProjetSerializer(many=True))
    def get_chefs_chantier(self, obj) -> list:
        resultats = []
        for aff in chefs_chantier_affectations(obj):
            u_data = ChefProjetEnrichiSerializer(aff.utilisateur, context=self.context).data
            u_data["affectation_id"] = str(aff.id)
            resultats.append(
                {
                    "utilisateur": u_data,
                    "zone": aff.zone or None,
                    "affectation_id": str(aff.id),
                }
            )
        return resultats

    @extend_schema_field(AutreMembreProjetSerializer(many=True))
    def get_autres_membres(self, obj) -> list:
        resultats = []
        for aff in autres_membres_affectations(obj):
            u_data = ChefProjetEnrichiSerializer(aff.utilisateur, context=self.context).data
            u_data["affectation_id"] = str(aff.id)
            resultats.append(
                {
                    **u_data,
                    "fonction": aff.fonction_membre or "AUTRE",
                    # Le rôle tenu sur le projet : VI ou tout rôle de portée Projet.
                    "role_code": aff.role_projet,
                    "role_libelle": aff.get_role_projet_display(),
                    "affectation_id": str(aff.id),
                    "utilisateur": u_data,
                }
            )
        return resultats

    statistiques = serializers.SerializerMethodField(
        help_text="Compteurs et avancement des lots et activités actifs du projet."
    )

    @extend_schema_field(StatistiquesProjetSerializer)
    def get_statistiques(self, obj) -> dict:
        return statistiques_lots(obj.lots.all())

    avancement_reel = serializers.SerializerMethodField(
        help_text=(
            "Pourcentage réalisé automatique : 0 à la création, jusqu'à 100 selon les activités. "
            "Lots pondérés par leur budget, lots sans budget exclus (RG-F3-05) ; "
            "activités pondérées par leur quantité prévue."
        )
    )
    indice_sante = serializers.SerializerMethodField(
        help_text=(
            "Indice de santé synthétique (0-100) calculé selon la SFD F3 ; "
            "null si non calculé."
        )
    )
    maitre_ouvrage = serializers.SerializerMethodField()
    duree_jours_ouvres = serializers.SerializerMethodField()
    duree = serializers.SerializerMethodField()
    contrat = ContratProjetSerializer(source="contrats", many=True, read_only=True)

    avancement_theorique = serializers.SerializerMethodField(
        help_text=(
            "Avancement temporel (SFD F3 formule 4), calculé à chaque appel sur le calendrier "
            "de l'entreprise. Le nom de champ est conservé pour les écrans existants."
        )
    )
    delta_retard = serializers.SerializerMethodField(
        help_text="Avancement temporel - avancement physique, en points (positif = retard)."
    )

    def get_avancement_reel(self, obj) -> float:
        return statistiques_lots(obj.lots.all())["avancement_pondere"]

    def _calendrier(self):
        """Le calendrier construit une fois par la vue de liste ; None pour un objet isolé."""
        ctx = getattr(self, "context", None)
        return ctx.get("calendrier") if ctx else None

    def _indicateurs_temporels(self, obj) -> dict:
        # Un seul calcul par projet et par réponse : les deux champs le partagent.
        if not hasattr(obj, "_indicateurs_temporels_cache"):
            from apps.projets.services.indicateurs_temporels import indicateurs_temporels_projet

            obj._indicateurs_temporels_cache = indicateurs_temporels_projet(
                obj, calendrier=self._calendrier()
            )
        return obj._indicateurs_temporels_cache

    def _jours_ouvres(self, obj) -> int | None:
        """Jours ouvrés du projet, sur le calendrier partagé s'il existe (sinon celui du modèle)."""
        cal = self._calendrier()
        if cal is None:
            return obj.duree_jours_ouvres
        if not obj.date_debut_prevue or not obj.date_fin_prevue:
            return None
        from apps.projets.services.sante_calculs import compter_jours_ouvres

        return compter_jours_ouvres(obj.date_debut_prevue, obj.date_fin_prevue, cal)

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_duree_jours_ouvres(self, obj) -> int | None:
        return self._jours_ouvres(obj)

    @extend_schema_field(DureeProjetSerializer(allow_null=True))
    def get_duree(self, obj) -> dict | None:
        from apps.projets.services.durees import duree_calendaire

        duree = duree_calendaire(obj.date_debut_prevue, obj.date_fin_prevue)
        if duree is None:
            return None
        return {**duree, "jours_ouvres": self._jours_ouvres(obj)}

    @extend_schema_field(serializers.FloatField())
    def get_avancement_theorique(self, obj) -> float:
        return self._indicateurs_temporels(obj)["avancement_temporel"]

    @extend_schema_field(serializers.FloatField())
    def get_delta_retard(self, obj) -> float:
        return self._indicateurs_temporels(obj)["delta_retard"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_indice_sante(self, obj) -> int | None:
        return obj.indice_sante

    def get_maitre_ouvrage(self, obj) -> str:
        return obj.maitre_ouvrage or (obj.client.raison_sociale if obj.client_id else "")

    class Meta:
        model = Projet
        fields = CHAMPS_REPONSE
        read_only_fields = CHAMPS_REPONSE

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(user, request):
            from apps.core.purger_montants import purger_montants_recursif

            data = purger_montants_recursif(data)
        return data


class ProjetPatchSerializer(ProjetPostSerializer):
    """Same visible fields for PUT and PATCH."""

    def validate(self, attrs):
        if self.instance is not None and "statut" not in self.initial_data:
            attrs["statut"] = self.instance.statut
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
        nouveau_statut = attrs.get("statut")
        if self.instance is not None and nouveau_statut == StatutProjet.RECEPTIONNE:
            from apps.projets.services.machine_etats import valider_transition_reception

            valider_transition_reception(self.instance)
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

    def update(self, instance, validated_data):
        ancien_statut = instance.statut
        nouveau_statut = validated_data.pop("statut", ancien_statut)
        user = getattr(self.context.get("request"), "user", None)

        projet = super().update(instance, validated_data)

        if nouveau_statut != ancien_statut:
            from apps.projets.services.machine_etats import changer_statut_projet

            projet = changer_statut_projet(projet, nouveau_statut, user)

        return projet
