"""Creation form and update contracts."""

from pathlib import Path

from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.core.enums import NatureProjet, StatutProjet
from apps.projets.models import Projet, ProjetContrat
from apps.projets.selectors.configuration import (
    calculer_dates_reelles_projet,
    composantes_du_projet,
    intervenants_externes_projet,
    phases_du_projet,
    resoudre_client_projet,
    synthese_avenants_delai_projet,
)
from apps.projets.selectors.encadrement import (
    autres_membres_affectations,
    chef_projet_affectation,
    chefs_chantier_affectations,
    conducteurs_travaux_avec_affectations,
    role_effectif_affectation,
    role_entreprise_utilisateur,
)
from apps.projets.serializers import (
    ChefProjetEnrichiSerializer,
    DureeProjetSerializer,
    NiveauProjetSimpleSerializer,
    ProjetCreationSerializer,
)
from apps.projets.serializers.statistiques import StatistiquesProjetSerializer
from apps.projets.services.contrats import (
    FORMATS,
    MAX_LOT,
    NOMBRE_MAX_CONTRATS_ACTIFS,
    ajouter_contrats,
    nettoyer_contrats,
    valider_fichier_contrat,
)
from apps.projets.services.statistiques import statistiques_arbre

CHAMPS_FORMULAIRE = (
    "nom",
    "statut",
    "reference",
    "nature_projet",
    "type_projet",
    "ville",
    "quartier",
    "client_id",
    "maitre_ouvrage",
    "maitre_oeuvre",
    "date_debut_prevue",
    "date_fin_prevue",
    "date_debut_reelle",
    "date_fin_reelle",
    "duree_jours_ouvres",
    "duree",
    "budget_initial_montant",
    "budget_contractuel_initial",
    "duree_contractuelle_annees",
    "duree_contractuelle_mois",
    "duree_contractuelle_jours",
    "date_debut_contractuelle",
    "description",
    "informations_complementaires",
    "contrat",
    "ordre_service",
    "chef_projet_id",
    "conducteur_travaux_id",
)
CHAMPS_REPONSE = (
    "id",
    *CHAMPS_FORMULAIRE,
    "client",
    "contact_moa",
    "contrat_actif",
    "historique_contrats",
    "avancement_reel",
    "avancement_theorique",
    "delta_retard",
    "indice_sante",
    "statistiques",
    "sans_chef_projet",
    "peut_renommer",
    "niveaux",
    "decoupage_cree",
    # Données dynamiques de configuration / fiche projet
    "phase_actuelle",
    "phases_disponibles",
    "synthese_avenants_delai",
    "avancement_composantes",
    "intervenants_externes",
    # Cadre contractuel & avenants (23/11/2026)
    "jours_accordes",
    "prolongation_annees",
    "prolongation_mois",
    "prolongation_jours",
    "montant_avenants",
    "duree_contractuelle",
    "date_fin_contractuelle_initiale",
    "date_fin_contractuelle",
    "budget_contractuel",
    # Le budget lu sur l'arbre (08/11/2026) : le réalisé valorisé, et ce que le découpage chiffre
    "budget_consomme_montant",
    "budget_decoupage_montant",
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
    nature_projet = serializers.ChoiceField(
        choices=NatureProjet.choices,
        required=False,
        allow_blank=True,
        help_text="Type de projet : PUBLIC (Projet public) ou PRIVE (Projet privé).",
    )
    type_projet = serializers.CharField(
        max_length=60,
        help_text="Catégorie d'ouvrage (Bâtiment, Route, Pont, VRD...).",
    )
    client_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Identifiant du Tiers client / maître d'ouvrage (optionnel).",
    )
    maitre_ouvrage = serializers.CharField(max_length=200, required=False, allow_blank=True)
    informations_complementaires = serializers.JSONField(
        required=False,
        help_text="Informations complémentaires structurées de la fiche projet (objet JSON).",
    )
    contrat = serializers.ListField(
        child=FichierContratField(validators=[valider_fichier_contrat]),
        required=False,
        max_length=NOMBRE_MAX_CONTRATS_ACTIFS,
        help_text=(
            "Contrat du marché unique (PDF/JPG/JPEG/PNG, max 50 Mo). "
            "Téléverser un nouveau contrat remplace l'actif précédent et conserve l'historique."
        ),
    )
    ordre_service = FichierContratField(
        validators=[valider_fichier_contrat],
        required=False,
        allow_null=True,
        help_text="Ordre de service de démarrage (PDF/JPG/JPEG/PNG, max 50 Mo).",
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        debut = attrs.get("date_debut_reelle", getattr(self.instance, "date_debut_reelle", None))
        fin = attrs.get("date_fin_reelle", getattr(self.instance, "date_fin_reelle", None))
        if debut is not None and fin is not None and fin < debut:
            raise serializers.ValidationError(
                {"date_fin_reelle": _("La fin réelle ne peut pas précéder le début réel.")}
            )
        self._valider_cadre_contractuel(attrs)
        return attrs

    def _valider_cadre_contractuel(self, attrs):
        """Applique la règle d'or : aucune donnée contractuelle sans pièce justificative.

        - I1 : budget contractuel initial ou durée contractuelle exigent un fichier contrat.
        - I2 : une durée contractuelle posée doit être strictement supérieure à zéro.
        - I3 : la date de début contractuelle exige un fichier OS de démarrage.
        - I4 : modifier une date de début contractuelle existante exige un nouvel OS de démarrage.
        - I5 : budget contractuel initial et durée contractuelle sont verrouillés après pose.
        """
        erreurs = {}
        fichiers_contrat = attrs.get("contrat") or []
        a_contrat_existant = self.instance is not None and self.instance.contrats.exists()
        a_contrat_apres = bool(fichiers_contrat) or a_contrat_existant

        # 1. Budget contractuel initial
        budget_envoye_cle = "budget_contractuel_initial" in self.initial_data
        budget_envoye = attrs.get("budget_contractuel_initial")
        if self.instance is not None and self.instance.budget_contractuel_initial is not None:
            if budget_envoye_cle and budget_envoye != self.instance.budget_contractuel_initial:
                erreurs["budget_contractuel_initial"] = _(
                    "Le budget contractuel initial est verrouillé après dépôt du contrat. "
                    "Enregistrez un avenant accompagné de son ordre de service "
                    "pour le faire évoluer."
                )
        elif budget_envoye_cle and budget_envoye is not None and not a_contrat_apres:
            erreurs["budget_contractuel_initial"] = _(
                "Joignez le contrat du marché pour enregistrer le budget contractuel initial."
            )

        # 2. Durée contractuelle (3 champs : années, mois, jours)
        champs_duree = (
            "duree_contractuelle_annees",
            "duree_contractuelle_mois",
            "duree_contractuelle_jours",
        )
        duree_envoyee_cles = [c for c in champs_duree if c in self.initial_data]
        duree_non_nulle = any(attrs.get(c) is not None for c in duree_envoyee_cles)

        if self.instance is not None and self.instance.a_duree_contractuelle:
            for champ in duree_envoyee_cles:
                if (attrs.get(champ) or 0) != (getattr(self.instance, champ) or 0):
                    erreurs[champ] = _(
                        "La durée contractuelle initiale est verrouillée après dépôt du contrat. "
                        "Enregistrez un avenant accompagné de son ordre de service "
                        "pour prolonger le délai."
                    )
        elif duree_non_nulle:
            annees = attrs.get("duree_contractuelle_annees") or 0
            mois = attrs.get("duree_contractuelle_mois") or 0
            jours = attrs.get("duree_contractuelle_jours") or 0
            if annees + mois + jours == 0:
                erreurs["duree_contractuelle_jours"] = _(
                    "La durée contractuelle doit être supérieure à zéro "
                    "(renseignez au moins les années, les mois ou les jours)."
                )
            elif not a_contrat_apres:
                erreurs["duree_contractuelle_annees"] = _(
                    "Joignez le contrat du marché pour enregistrer "
                    "la durée contractuelle d'exécution."
                )

        # 3. Date de début contractuelle ↔ OS de démarrage
        fichier_os_envoye = attrs.get("ordre_service") is not None
        date_os_cle = "date_debut_contractuelle" in self.initial_data
        date_os_envoyee = attrs.get("date_debut_contractuelle")

        if self.instance is None:
            if date_os_cle and date_os_envoyee is not None and not fichier_os_envoye:
                erreurs["date_debut_contractuelle"] = _(
                    "Joignez l'ordre de service de démarrage pour définir "
                    "la date de début contractuelle."
                )
        elif date_os_cle:
            date_actuelle = self.instance.date_debut_contractuelle
            if date_os_envoyee != date_actuelle:
                if date_os_envoyee is None and date_actuelle is not None:
                    erreurs["date_debut_contractuelle"] = _(
                        "La date de début contractuelle ne peut pas être effacée manuellement."
                    )
                elif date_actuelle is None:
                    if not fichier_os_envoye and not bool(self.instance.ordre_service):
                        erreurs["date_debut_contractuelle"] = _(
                            "Joignez l'ordre de service de démarrage pour définir "
                            "la date de début contractuelle."
                        )
                elif not fichier_os_envoye:
                    erreurs["date_debut_contractuelle"] = _(
                        "Pour modifier la date de début contractuelle, importez le nouvel "
                        "ordre de service de démarrage correspondant."
                    )

        if erreurs:
            raise serializers.ValidationError(erreurs)

    def validate_contrat(self, fichiers):
        if len(fichiers) > NOMBRE_MAX_CONTRATS_ACTIFS:
            raise serializers.ValidationError(
                "Un seul contrat du marché peut être déposé à la fois : le nouveau remplace "
                "l'actif précédent tout en conservant l'historique des versions."
            )
        if sum(fichier.size for fichier in fichiers) > MAX_LOT:
            raise serializers.ValidationError("La taille du contrat dépasse 50 Mo.")
        return fichiers

    def _avec_contrats(self, validated_data, operation):
        fichiers = validated_data.pop("contrat", [])
        fichier_os = validated_data.pop("ordre_service", serializers.empty)
        stockes = []
        try:
            with transaction.atomic():
                projet = operation(validated_data)
                user = getattr(self.context.get("request"), "user", None)
                ajouter_contrats(projet, fichiers, user, stockes)
                if fichier_os is not serializers.empty and fichier_os is not None:
                    ext = Path(fichier_os.name).suffix.lower()
                    projet.ordre_service_nom = fichier_os.name[:255]
                    projet.ordre_service_taille = fichier_os.size
                    projet.ordre_service_type = FORMATS.get(
                        ext, getattr(fichier_os, "content_type", "") or "application/pdf"
                    )
                    projet.ordre_service.save(fichier_os.name, fichier_os, save=False)
                    stockes.append((projet.ordre_service.storage, projet.ordre_service.name))
                    projet._auteur_ordre_service = user
                    projet._ordre_service_modifie = True
                    projet.save(
                        update_fields=[
                            "ordre_service",
                            "ordre_service_nom",
                            "ordre_service_taille",
                            "ordre_service_type",
                            "modifie_le",
                        ]
                    )
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
    nom_sans_extension = serializers.CharField(read_only=True)
    cree_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = ProjetContrat
        fields = [
            "id",
            "nom",
            "nom_sans_extension",
            "version",
            "est_actif",
            "taille",
            "type_contenu",
            "url",
            "cree_le",
            "cree_par_nom",
        ]
        read_only_fields = fields

    def get_url(self, obj) -> str:
        path = reverse("projets:projet-detail", kwargs={"pk": obj.projet_id})
        path = f"{path}?contrat={obj.pk}"
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    def get_cree_par_nom(self, obj) -> str:
        auteur = getattr(obj, "cree_par", None)
        if not auteur:
            return ""
        return f"{auteur.prenom} {auteur.nom}".strip() or auteur.email


class ClientResumeProjetSerializer(serializers.Serializer):
    """Coordonnées dynamiques du Tiers client / maître d'ouvrage."""

    id = serializers.UUIDField()
    raison_sociale = serializers.CharField()
    telephone = serializers.CharField(allow_blank=True, default="")
    email = serializers.CharField(allow_blank=True, default="")
    ville = serializers.CharField(allow_blank=True, default="")
    adresse = serializers.CharField(allow_blank=True, default="")
    type_tiers = serializers.CharField(allow_blank=True, default="")


class ChefChantierProjetSerializer(serializers.Serializer):
    """Un chef de chantier du projet."""

    utilisateur = ChefProjetEnrichiSerializer()
    zone = serializers.CharField(allow_null=True)
    affectation_id = serializers.UUIDField(allow_null=True)


class AutreMembreProjetSerializer(serializers.Serializer):
    """Un membre de l'encadrement hors CP / CT / CC, avec son vrai rôle dans l'entreprise."""

    id = serializers.UUIDField()
    nom = serializers.CharField()
    prenom = serializers.CharField()
    nom_complet = serializers.CharField()
    email = serializers.CharField(allow_blank=True, default="")
    telephone = serializers.CharField(allow_blank=True, default="")
    statut = serializers.CharField(default="")
    lien_whatsapp = serializers.CharField(allow_null=True, default=None)
    role_code = serializers.CharField(allow_blank=True, default="")
    role_libelle = serializers.CharField(allow_blank=True, default="")
    fonction_entreprise = serializers.CharField(allow_blank=True, default="")
    fonction = serializers.CharField(allow_blank=True, default="")
    fonction_libelle = serializers.CharField(allow_blank=True, default="")
    affectation_id = serializers.UUIDField()
    utilisateur = ChefProjetEnrichiSerializer(required=False)


class ProjetCreationResponseSerializer(serializers.ModelSerializer):
    chef_projet = serializers.SerializerMethodField(
        help_text="Le chef de projet désigné, en clair ; null si le projet n'en a pas.",
    )
    niveaux = serializers.SerializerMethodField(
        help_text="Le gabarit du découpage (Phase, Ouvrage, Lot…), dans l'ordre ; vide avant."
    )
    decoupage_cree = serializers.SerializerMethodField(
        help_text="Faux tant que le tableau de démarrage n'a pas été appliqué."
    )

    jours_accordes = serializers.IntegerField(
        read_only=True, help_text="Jours accordés par les avenants sur le projet entier."
    )
    prolongation_annees = serializers.IntegerField(read_only=True)
    prolongation_mois = serializers.IntegerField(read_only=True)
    prolongation_jours = serializers.IntegerField(read_only=True)
    montant_avenants = serializers.IntegerField(read_only=True)
    duree_contractuelle = serializers.SerializerMethodField(
        help_text="Durée contractuelle initiale (années, mois, jours), ou null sans contrat."
    )
    date_fin_contractuelle_initiale = serializers.DateField(
        read_only=True,
        allow_null=True,
        help_text="Début contractuel (OS) + durée contractuelle initiale, sans avenants.",
    )
    date_fin_contractuelle = serializers.DateField(
        read_only=True,
        allow_null=True,
        help_text="Début contractuel (OS) + durée contractuelle + prolongations d'avenants.",
    )
    budget_contractuel = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="Budget contractuel initial plus les montants des avenants (null sans contrat).",
    )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_duree_contractuelle(self, obj) -> dict[str, int] | None:
        return obj.duree_contractuelle

    @extend_schema_field(NiveauProjetSimpleSerializer(many=True))
    def get_niveaux(self, obj):
        niveaux = [n for n in obj.niveaux.all() if n.supprime_le is None]
        return NiveauProjetSimpleSerializer(sorted(niveaux, key=lambda n: n.ordre), many=True).data

    @extend_schema_field(serializers.BooleanField())
    def get_decoupage_cree(self, obj) -> bool:
        annote = getattr(obj, "a_un_decoupage", None)
        return bool(annote) if annote is not None else obj.elements.exists()

    def _contexte_enrichi(self) -> dict:
        return {**(self.context or {}), "libelles_roles": self._libelles_roles()}

    @extend_schema_field(ChefProjetEnrichiSerializer(allow_null=True))
    def get_chef_projet(self, obj) -> dict | None:
        if not obj.chef_projet:
            return None
        data = ChefProjetEnrichiSerializer(obj.chef_projet, context=self._contexte_enrichi()).data
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
        help_text="Les autres membres de l'encadrement affectés avec leur vrai rôle dans l'entreprise."
    )

    @extend_schema_field(ChefProjetEnrichiSerializer(many=True))
    def get_conducteurs_travaux(self, obj) -> list:
        resultats = []
        ctx = self._contexte_enrichi()
        for u, aff in conducteurs_travaux_avec_affectations(obj):
            data = ChefProjetEnrichiSerializer(u, context=ctx).data
            data["affectation_id"] = str(aff.id) if aff else None
            resultats.append(data)
        return resultats

    @extend_schema_field(ChefChantierProjetSerializer(many=True))
    def get_chefs_chantier(self, obj) -> list:
        resultats = []
        ctx = self._contexte_enrichi()
        for aff in chefs_chantier_affectations(obj):
            u_data = ChefProjetEnrichiSerializer(aff.utilisateur, context=ctx).data
            u_data["affectation_id"] = str(aff.id)
            resultats.append(
                {
                    "utilisateur": u_data,
                    # Le périmètre du chef, en clair ; vide : il a tout le chantier.
                    "zone": ", ".join(c.libelle for c in aff.perimetres.all()) or None,
                    "affectation_id": str(aff.id),
                }
            )
        return resultats

    @extend_schema_field(AutreMembreProjetSerializer(many=True))
    def get_autres_membres(self, obj) -> list:
        resultats = []
        libelles = self._libelles_roles()
        ctx = self._contexte_enrichi()
        for aff in autres_membres_affectations(obj):
            u_data = ChefProjetEnrichiSerializer(aff.utilisateur, context=ctx).data
            u_data["affectation_id"] = str(aff.id)
            role_code, role_libelle = role_effectif_affectation(aff, libelles)
            _code_ent, fonction_entreprise = role_entreprise_utilisateur(aff.utilisateur, libelles)
            role_final = role_libelle or fonction_entreprise
            fonction_code = (
                aff.fonction_membre
                if aff.fonction_membre and aff.fonction_membre != "AUTRE"
                else ""
            )
            fonction_libelle = (
                aff.get_fonction_membre_display() if fonction_code else role_final
            )
            resultats.append(
                {
                    **u_data,
                    "role_code": role_code,
                    "role_libelle": role_final,
                    "fonction_entreprise": fonction_entreprise or role_final,
                    "fonction": fonction_code,
                    "fonction_libelle": fonction_libelle,
                    "affectation_id": str(aff.id),
                    "utilisateur": u_data,
                }
            )
        return resultats

    def _libelles_roles(self) -> dict[str, str]:
        """Les libellés des rôles, lus une fois pour toute la réponse."""
        from apps.projets.models.projet import libelles_des_roles

        racine = self.root if self.root is not None else self
        if not hasattr(racine, "_libelles_roles_cache"):
            racine._libelles_roles_cache = libelles_des_roles()
        return racine._libelles_roles_cache

    statistiques = serializers.SerializerMethodField(
        help_text="Compteurs et avancement des cases actives de l'arbre du projet."
    )

    def _statistiques(self, obj) -> dict:
        # Un seul chargement de l'arbre par projet et par réponse : deux champs le partagent.
        if not hasattr(obj, "_statistiques_arbre"):
            from apps.projets.selectors.arbre import charger_arbre

            obj._statistiques_arbre = statistiques_arbre(charger_arbre(obj))
        return obj._statistiques_arbre

    @extend_schema_field(StatistiquesProjetSerializer)
    def get_statistiques(self, obj) -> dict:
        return self._statistiques(obj)

    avancement_reel = serializers.SerializerMethodField(
        help_text=(
            "Pourcentage réalisé, calculé sur l'arbre : chaque case pèse son montant "
            "(décisions v1.2, §8). Quand aucun montant n'est connu, l'avancement est "
            "indisponible : `statistiques.avancement_pondere` vaut null et ce champ garde la "
            "valeur stockée (0)."
        )
    )
    indice_sante = serializers.SerializerMethodField(
        help_text=(
            "Indice de santé synthétique (0-100) calculé selon la SFD F3 ; "
            "null si non calculé."
        )
    )
    maitre_ouvrage = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()
    client = serializers.SerializerMethodField()
    contact_moa = serializers.SerializerMethodField()
    date_debut_reelle = serializers.SerializerMethodField()
    date_fin_reelle = serializers.SerializerMethodField()
    duree_jours_ouvres = serializers.SerializerMethodField()
    duree = serializers.SerializerMethodField()
    contrat = serializers.SerializerMethodField(
        help_text="Liste 0..1 contenant uniquement le contrat du marché actif."
    )
    contrat_actif = serializers.SerializerMethodField(
        help_text="Le contrat du marché actif, ou null si aucun contrat n'a été déposé."
    )
    historique_contrats = serializers.SerializerMethodField(
        help_text="Toutes les versions du contrat du marché, de la plus récente à la plus ancienne."
    )
    ordre_service = serializers.SerializerMethodField()
    phase_actuelle = serializers.SerializerMethodField()
    phases_disponibles = serializers.SerializerMethodField()
    synthese_avenants_delai = serializers.SerializerMethodField()
    avancement_composantes = serializers.SerializerMethodField()
    intervenants_externes = serializers.SerializerMethodField()

    def _contrats_ordonnes(self, obj) -> list[ProjetContrat]:
        contrats = [c for c in obj.contrats.all() if c.supprime_le is None]
        return sorted(contrats, key=lambda c: (-c.version, -(c.cree_le.timestamp() if c.cree_le else 0)))

    def _contrat_actif_instance(self, obj) -> ProjetContrat | None:
        contrats = self._contrats_ordonnes(obj)
        actif = next((c for c in contrats if c.est_actif), None)
        return actif or (contrats[0] if contrats else None)

    @extend_schema_field(ContratProjetSerializer(many=True))
    def get_contrat(self, obj) -> list[dict]:
        actif = self._contrat_actif_instance(obj)
        if actif is None:
            return []
        return [ContratProjetSerializer(actif, context=self.context).data]

    @extend_schema_field(ContratProjetSerializer(allow_null=True))
    def get_contrat_actif(self, obj) -> dict | None:
        actif = self._contrat_actif_instance(obj)
        if actif is None:
            return None
        return ContratProjetSerializer(actif, context=self.context).data

    @extend_schema_field(ContratProjetSerializer(many=True))
    def get_historique_contrats(self, obj) -> list[dict]:
        return ContratProjetSerializer(
            self._contrats_ordonnes(obj), many=True, context=self.context
        ).data

    def _tiers_client(self, obj):
        if not hasattr(obj, "_tiers_client_cache"):
            tiers_par_nom = (self.context or {}).get("tiers_par_nom")
            obj._tiers_client_cache = resoudre_client_projet(obj, tiers_par_nom=tiers_par_nom)
        return obj._tiers_client_cache

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_client_id(self, obj):
        tiers = self._tiers_client(obj)
        return str(tiers.pk) if tiers else None

    @extend_schema_field(ClientResumeProjetSerializer(allow_null=True))
    def get_client(self, obj) -> dict | None:
        tiers = self._tiers_client(obj)
        if tiers is None:
            return None
        return {
            "id": str(tiers.pk),
            "raison_sociale": tiers.raison_sociale,
            "telephone": tiers.telephone or "",
            "email": tiers.email or "",
            "ville": tiers.ville or "",
            "adresse": tiers.adresse or "",
            "type_tiers": tiers.type_tiers or "",
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_contact_moa(self, obj) -> dict | None:
        tiers = self._tiers_client(obj)
        if tiers is None:
            return None
        return {
            "tiers_id": str(tiers.pk),
            "raison_sociale": tiers.raison_sociale,
            "telephone": tiers.telephone or "",
            "email": tiers.email or "",
            "ville": tiers.ville or "",
            "adresse": tiers.adresse or "",
        }

    def _arbre_et_calculs(self, obj):
        if not hasattr(obj, "_arbre_et_calculs_cache"):
            from apps.projets.selectors.arbre import charger_arbre
            from apps.projets.services.sante_calculs import calculer_arbre

            arbre = charger_arbre(obj, actifs_seulement=True)
            resultats = calculer_arbre(arbre)
            numeros = arbre.numerotation()
            obj._arbre_et_calculs_cache = (arbre, resultats, numeros)
        return obj._arbre_et_calculs_cache

    def _dates_reelles_calculees(self, obj):
        if not hasattr(obj, "_dates_reelles_cache"):
            arbre, _, _ = self._arbre_et_calculs(obj)
            premiers_rapports = (self.context or {}).get("premiers_rapports")
            if premiers_rapports is not None:
                obj._dates_reelles_cache = calculer_dates_reelles_projet(
                    obj, arbre, premier_rapport=premiers_rapports.get(obj.pk)
                )
            else:
                obj._dates_reelles_cache = calculer_dates_reelles_projet(obj, arbre)
        return obj._dates_reelles_cache

    @extend_schema_field(serializers.DateField(allow_null=True))
    def get_date_debut_reelle(self, obj):
        return self._dates_reelles_calculees(obj)[0]

    @extend_schema_field(serializers.DateField(allow_null=True))
    def get_date_fin_reelle(self, obj):
        return self._dates_reelles_calculees(obj)[1]

    def _phases(self, obj):
        if not hasattr(obj, "_phases_cache"):
            arbre, resultats, numeros = self._arbre_et_calculs(obj)
            obj._phases_cache = phases_du_projet(arbre, resultats, numeros)
        return obj._phases_cache

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_phase_actuelle(self, obj) -> str | None:
        return self._phases(obj)[0]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_phases_disponibles(self, obj) -> list[dict]:
        return self._phases(obj)[1]

    def _montants_visibles(self) -> bool:
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        return bool(peut_voir_montants(user, request))

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_avancement_composantes(self, obj) -> list[dict]:
        arbre, resultats, numeros = self._arbre_et_calculs(obj)
        return composantes_du_projet(
            arbre, resultats, numeros, montants_visibles=self._montants_visibles()
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_synthese_avenants_delai(self, obj) -> dict | None:
        if not (self.context or {}).get("detail", True):
            return None
        return synthese_avenants_delai_projet(obj, montants_visibles=self._montants_visibles())

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_intervenants_externes(self, obj) -> list[dict]:
        if not (self.context or {}).get("detail", True):
            return []
        arbre, _, _ = self._arbre_et_calculs(obj)
        return intervenants_externes_projet(obj, arbre)

    def get_ordre_service(self, obj) -> dict | None:
        if not obj.ordre_service:
            return None
        path = reverse("projets:projet-ordre-service", kwargs={"pk": obj.pk})
        request = self.context.get("request") if getattr(self, "context", None) else None
        url = request.build_absolute_uri(path) if request else path
        return {
            "nom": obj.ordre_service_nom or Path(obj.ordre_service.name).name,
            "taille": obj.ordre_service_taille or 0,
            "type_contenu": obj.ordre_service_type or "application/pdf",
            "url": url,
        }

    avancement_theorique = serializers.SerializerMethodField(
        help_text=(
            "Avancement temporel (SFD F3 formule 4), calculé à chaque appel sur le calendrier "
            "de l'entreprise. Le nom de champ est conservé pour les écrans existants."
        )
    )
    delta_retard = serializers.SerializerMethodField(
        help_text="Avancement temporel - avancement physique, en points (positif = retard)."
    )

    budget_consomme_montant = serializers.SerializerMethodField(
        help_text=(
            "La valeur de ce qui est réalisé (centimes) : Σ montant x avancement des feuilles. "
            "Il n'y a pas de module financier : ce n'est pas du dépensé, et le nom du champ est "
            "gardé pour les écrans existants."
        )
    )
    budget_decoupage_montant = serializers.SerializerMethodField(
        help_text="Ce que le découpage chiffre au total (centimes), à comparer au budget."
    )

    @extend_schema_field(serializers.IntegerField())
    def get_budget_consomme_montant(self, obj) -> int:
        return self._statistiques(obj)["realise_montant"]

    @extend_schema_field(serializers.IntegerField())
    def get_budget_decoupage_montant(self, obj) -> int:
        return self._statistiques(obj)["decoupage_montant"]

    def get_avancement_reel(self, obj) -> float:
        valeur = self._statistiques(obj)["avancement_pondere"]
        return float(valeur) if valeur is not None else float(obj.avancement_reel or 0)

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
            for champ_contractuel in (
                "budget_contractuel_initial",
                "duree_contractuelle_annees",
                "duree_contractuelle_mois",
                "duree_contractuelle_jours",
                "date_debut_contractuelle",
            ):
                if champ_contractuel not in self.initial_data:
                    attrs[champ_contractuel] = getattr(self.instance, champ_contractuel)
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
