"""Serializers pour la gestion des activités de lot (MLD §6.3)."""

from decimal import Decimal, InvalidOperation

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur, UniteMesure
from apps.projets.models import Activite, AffectationProjet, MiseAJourInline
from apps.projets.services.statistiques import pourcentage_realise

MOTIF_AVANCEMENT_IMMUABLE = (
    "L'avancement se met à jour par un rapport approuvé ou par la mise à jour manuelle."
)

__all__ = [
    "MOTIF_AVANCEMENT_IMMUABLE",
    "ActiviteAvancementSerializer",
    "ActiviteCreationSerializer",
    "ActiviteModificationSerializer",
    "ActiviteSerializer",
    "MiseAJourInlineSerializer",
]


class ActiviteSerializer(serializers.ModelSerializer):
    """Lecture complète d'une activité de chantier."""

    responsable_id = serializers.PrimaryKeyRelatedField(
        source="colaborateur", read_only=True, allow_null=True
    )

    unite_libelle = serializers.CharField(source="get_unite_display", read_only=True)
    statut = serializers.CharField(read_only=True)
    # Attention : equipe_ids désigne les collaborateurs (Utilisateur) de l'activité,
    # distincts des équipes de chantier (EquipeChantier). Ne pas le modifier.
    equipe_ids = serializers.PrimaryKeyRelatedField(source="equipe", many=True, read_only=True)
    equipe_chantier = serializers.SerializerMethodField()

    def get_avancement(self, obj) -> float:
        return float(round(pourcentage_realise(obj), 2))

    def get_equipe_chantier(self, obj) -> dict | None:
        """L'équipe de chantier affectée à cette activité, avec son affectation active."""
        aff = (
            obj.affectations_equipes.filter(
                supprime_le__isnull=True,
                equipe__supprime_le__isnull=True,
                equipe__est_actif=True,
            )
            .select_related("equipe")
            .first()
        )
        if not aff or not aff.equipe:
            return None
        equipe = aff.equipe
        effectif = equipe.membres.filter(supprime_le__isnull=True).count()
        return {
            "id": str(equipe.id),
            "nom": equipe.nom,
            "effectif": effectif,
            "affectation_id": str(aff.id),
        }

    class Meta:
        model = Activite
        fields = [
            "id",
            "lot_id",
            "libelle",
            "motif",
            "statut",
            "responsable_id",
            "equipe_ids",
            "equipe_chantier",
            "budget_initial_montant",
            "unite",
            "unite_libelle",
            "quantite_prevue",
            "quantite_realisee",
            "avancement",
            "poids",
            "date_debut_prevue",
            "date_fin_prevue",
            "date_debut_baseline",
            "date_fin_baseline",
            "ordre",
            "est_actif",
            "cree_le",
        ]
        read_only_fields = [
            "id",
            "lot_id",
            "quantite_realisee",
            "avancement",
            "equipe_chantier",
            "date_debut_baseline",
            "date_fin_baseline",
            "cree_le",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request") if getattr(self, "context", None) else None
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(user, request):
            from apps.core.purger_montants import purger_montants_recursif

            data = purger_montants_recursif(data)
        return data


class ActiviteCreationSerializer(serializers.ModelSerializer):
    """Création d'une activité rattachée à un lot."""

    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        help_text="Motif informatif facultatif ; texte libre, chaîne vide pour l'effacer.",
    )

    statut = serializers.CharField(
        required=False,
        trim_whitespace=False,
        help_text="Statut d'évolution libre envoyé par le frontend ; chaîne non vide.",
    )

    quantite_prevue = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
        required=False,
        default=Decimal("1.000"),
    )
    budget_initial_montant = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=9223372036854775807,
        help_text="Budget prévisionnel facultatif en centimes FCFA, utilisé pour la pondération.",
    )
    responsable_id = serializers.PrimaryKeyRelatedField(
        source="colaborateur",
        queryset=Utilisateur.objects.filter(
            is_active=True, statut=StatutUtilisateur.ACTIF, supprime_le__isnull=True
        ),
        required=False,
        allow_null=True,
        help_text="UUID du responsable actif affecté au projet, ou null.",
    )
    equipe_ids = serializers.PrimaryKeyRelatedField(
        source="equipe",
        many=True,
        required=False,
        queryset=Utilisateur.objects.filter(is_active=True, statut=StatutUtilisateur.ACTIF),
        help_text="UUID des collaborateurs actifs affectés au projet ; facultatif.",
    )

    class Meta:
        model = Activite
        fields = [
            "libelle",
            "motif",
            "statut",
            "responsable_id",
            "equipe_ids",
            "budget_initial_montant",
            "unite",
            "quantite_prevue",
            "poids",
            "date_debut_prevue",
            "date_fin_prevue",
            "ordre",
        ]

    def validate_budget_initial_montant(self, value):
        request = self.context.get("request") if getattr(self, "context", None) else None
        from apps.core.purger_montants import valider_ecriture_montant

        return valider_ecriture_montant(value, request=request, champ="budget_initial_montant")

    def to_internal_value(self, data):
        if isinstance(data, dict):
            champs_avancement = {"quantite_realisee", "avancement"}
            presents = champs_avancement.intersection(data.keys())
            if presents:
                # RG-F3-01 : la modification ordinaire refuse avancement en 403
                if self.instance is not None:
                    raise PermissionDenied(MOTIF_AVANCEMENT_IMMUABLE)

                # À la création, seule la valeur 0 est autorisée
                for champ in presents:
                    val = data[champ]
                    try:
                        if Decimal(str(val)) != Decimal("0"):
                            raise PermissionDenied(MOTIF_AVANCEMENT_IMMUABLE)
                    except (InvalidOperation, TypeError, ValueError) as err:
                        raise PermissionDenied(MOTIF_AVANCEMENT_IMMUABLE) from err

                data = data.copy()
                for champ in presents:
                    data.pop(champ, None)

        inconnus = set(data.keys()) - set(self.fields)
        if inconnus:
            raise serializers.ValidationError(dict.fromkeys(inconnus, "Champ non accepté."))
        return super().to_internal_value(data)

    def validate(self, attrs):
        request = self.context.get("request") if getattr(self, "context", None) else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(getattr(request, "user", None) if request else None, request):
            if "budget_initial_montant" in attrs and attrs["budget_initial_montant"] is None:
                attrs.pop("budget_initial_montant")

        lot = self.context.get("lot")
        if not lot:
            raise serializers.ValidationError("Le lot de rattachement est requis.")

        debut = attrs.get("date_debut_prevue")
        fin = attrs.get("date_fin_prevue")

        if debut and fin and fin < debut:
            raise serializers.ValidationError(
                {"date_fin_prevue": "La fin prévue ne peut pas précéder le début."}
            )

        equipe = attrs.get("equipe", [])
        if len(equipe) > 50:
            raise serializers.ValidationError({"equipe_ids": "Maximum 50 collaborateurs."})
        autorises = set(
            AffectationProjet.objects.filter(
                projet_id=lot.projet_id,
                est_actif=True,
            ).values_list("utilisateur_id", flat=True)
        )
        autorises.update((lot.projet.chef_projet_id, lot.projet.conducteur_travaux_id))
        colaborateur = attrs.get("colaborateur")
        if colaborateur is not None and colaborateur.pk not in autorises:
            raise serializers.ValidationError(
                {"responsable_id": "Responsable non affecté au projet."}
            )
        if any(user.pk not in autorises for user in equipe):
            raise serializers.ValidationError(
                {"equipe_ids": "Collaborateur non affecté au projet."}
            )

        from apps.projets.services.calendrier import exiger_dates_lot, verifier_activite_dans_lot

        if self.instance is None:
            exiger_dates_lot(lot)
        # En modification, seules les dates **écrites** se contrôlent : une activité déjà hors
        # cadre en base (données antérieures à la règle D5) reste modifiable pour le reste.
        initiales = getattr(self, "initial_data", None) or {}
        dates_ecrites = "date_debut_prevue" in initiales or "date_fin_prevue" in initiales
        if self.instance is None or dates_ecrites:
            verifier_activite_dans_lot(lot, debut, fin)

        unite = attrs.get("unite", UniteMesure.UNITE)
        quantite = attrs.get("quantite_prevue")
        if unite == UniteMesure.FORFAIT and quantite != Decimal("1.000"):
            attrs["quantite_prevue"] = Decimal("1.000")

        if self.instance is None and "budget_initial_montant" in attrs:
            from apps.projets.services.budgets import verifier_budget_activite

            verifier_budget_activite(lot, attrs.get("budget_initial_montant"))

        return attrs

    def create(self, validated_data):
        lot = self.context["lot"]
        request = self.context.get("request")
        utilisateur = getattr(request, "user", None)
        equipe = validated_data.pop("equipe", [])
        activite = Activite.objects.create(
            lot=lot,
            cree_par=utilisateur,
            **validated_data,
        )
        activite.equipe.set(equipe)
        return activite


class ActiviteModificationSerializer(ActiviteCreationSerializer):
    """Réutilise la validation métier sur l'état final d'une modification partielle."""

    def validate(self, attrs):
        request = self.context.get("request") if getattr(self, "context", None) else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(getattr(request, "user", None) if request else None, request):
            if "budget_initial_montant" in attrs and attrs["budget_initial_montant"] is None:
                attrs.pop("budget_initial_montant")

        for champ in ("date_debut_prevue", "date_fin_prevue"):
            ancienne = getattr(self.instance, champ)
            if champ in attrs and ancienne is not None and attrs[champ] != ancienne:
                raise serializers.ValidationError(
                    {champ: "RG-11 : reprogrammez l'activité avec motif et justification."}
                )
        valeurs = {
            champ.source: getattr(self.instance, champ.source)
            for champ in self.fields.values()
            if champ.source != "equipe"
        }
        valeurs.update(attrs)
        valeurs = super().validate(valeurs)
        if valeurs["quantite_prevue"] < self.instance.quantite_realisee:
            raise serializers.ValidationError(
                {"quantite_prevue": "Quantité inférieure au réalisé."}
            )
        fin = valeurs.get("date_fin_prevue")
        if fin and self.instance.successeurs.filter(date_debut_prevue__lt=fin).exists():
            raise serializers.ValidationError(
                {"date_fin_prevue": "La fin dépasse le début d'une activité suivante."}
            )
        # FORFAIT normalise la quantité à 1 ; les autres valeurs absentes restent intactes.
        if valeurs["quantite_prevue"] != self.instance.quantite_prevue:
            attrs["quantite_prevue"] = valeurs["quantite_prevue"]

        if "budget_initial_montant" in attrs:
            from apps.projets.services.budgets import verifier_budget_activite

            lot = self.context.get("lot") or getattr(self.instance, "lot", None)
            verifier_budget_activite(
                lot, attrs["budget_initial_montant"], activite_exclue=self.instance
            )
        return attrs


class ActiviteAvancementSerializer(serializers.Serializer):
    """Payload de mise à jour manuelle de l'avancement d'une activité (F3)."""

    quantite_realisee = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.000"),
        required=True,
        help_text="Nouvelle quantité cumulée réalisée (doit être non décroissante).",
    )
    commentaire = serializers.CharField(
        required=True,
        min_length=10,
        trim_whitespace=True,
        help_text="Commentaire explicatif obligatoire (au moins 10 caractères).",
    )

    def validate_commentaire(self, value: str) -> str:
        propre = value.strip()
        if len(propre) < 10:
            raise serializers.ValidationError(
                "Le commentaire doit comporter au moins 10 caractères."
            )
        return propre


class MiseAJourInlineSerializer(serializers.ModelSerializer):
    """Représentation d'une mise à jour manuelle d'avancement (F3)."""

    activite_id = serializers.UUIDField(source="activite.id", read_only=True)
    auteur_id = serializers.UUIDField(source="auteur.id", read_only=True)
    auteur = serializers.SerializerMethodField()
    date = serializers.DateTimeField(source="cree_le", read_only=True)
    avant = serializers.SerializerMethodField()
    apres = serializers.SerializerMethodField()

    class Meta:
        model = MiseAJourInline
        fields = [
            "id",
            "activite_id",
            "auteur",
            "auteur_id",
            "date",
            "quantite_avant",
            "quantite_apres",
            "avancement_avant",
            "avancement_apres",
            "avant",
            "apres",
            "commentaire",
            "source",
        ]
        read_only_fields = fields

    def get_auteur(self, obj) -> str:
        if not obj.auteur:
            return "Système"
        nom = f"{getattr(obj.auteur, 'prenom', '')} {getattr(obj.auteur, 'nom', '')}".strip()
        return nom or getattr(obj.auteur, "email", "Utilisateur")

    def get_avant(self, obj) -> dict:
        return {
            "quantite": obj.quantite_avant,
            "avancement": obj.avancement_avant,
        }

    def get_apres(self, obj) -> dict:
        return {
            "quantite": obj.quantite_apres,
            "avancement": obj.avancement_apres,
        }
