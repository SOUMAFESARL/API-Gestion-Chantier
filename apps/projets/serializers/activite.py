"""Serializers pour la gestion des activités de lot (MLD §6.3)."""

from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur, UniteMesure
from apps.projets.models import Activite, AffectationProjet
from apps.projets.services.statistiques import pourcentage_realise


class ActiviteSerializer(serializers.ModelSerializer):
    """Lecture complète d'une activité de chantier."""

    unite_libelle = serializers.CharField(source="get_unite_display", read_only=True)
    statut = serializers.CharField(read_only=True)
    avancement = serializers.SerializerMethodField()
    equipe_ids = serializers.PrimaryKeyRelatedField(source="equipe", many=True, read_only=True)

    def get_avancement(self, obj) -> float:
        return float(round(pourcentage_realise(obj), 2))

    class Meta:
        model = Activite
        fields = [
            "id",
            "lot_id",
            "libelle",
            "motif",
            "statut",
            "dependance",
            "equipe_ids",
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
            "date_debut_baseline",
            "date_fin_baseline",
            "cree_le",
        ]


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
    dependance = serializers.PrimaryKeyRelatedField(
        queryset=Activite.objects.all(),
        required=False,
        allow_null=True,
        help_text="Activité précédente active appartenant au même projet, ou null.",
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
            "dependance",
            "equipe_ids",
            "budget_initial_montant",
            "unite",
            "quantite_prevue",
            "poids",
            "date_debut_prevue",
            "date_fin_prevue",
            "ordre",
        ]

    def to_internal_value(self, data):
        inconnus = set(data.keys()) - set(self.fields)
        if inconnus:
            raise serializers.ValidationError(dict.fromkeys(inconnus, "Champ non accepté."))
        return super().to_internal_value(data)

    def validate(self, attrs):
        lot = self.context.get("lot")
        if not lot:
            raise serializers.ValidationError("Le lot de rattachement est requis.")

        debut = attrs.get("date_debut_prevue")
        fin = attrs.get("date_fin_prevue")

        if debut and fin and fin < debut:
            raise serializers.ValidationError(
                {"date_fin_prevue": "La fin prévue ne peut pas précéder le début."}
            )

        dependance = attrs.get("dependance")
        if dependance:
            if dependance.projet_id != lot.projet_id or not dependance.est_actif:
                raise serializers.ValidationError(
                    {"dependance": "Activité hors projet ou inactive."}
                )
            if debut and dependance.date_fin_prevue and debut < dependance.date_fin_prevue:
                raise serializers.ValidationError(
                    {"date_debut_prevue": "Le début doit suivre la fin de l'activité précédente."}
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
        if any(user.pk not in autorises for user in equipe):
            raise serializers.ValidationError(
                {"equipe_ids": "Collaborateur non affecté au projet."}
            )

        # Vérification des bornes du Lot parent
        if lot.date_debut_prevue and debut and debut < lot.date_debut_prevue:
            raise serializers.ValidationError(
                {
                    "date_debut_prevue": (
                        f"L'activité ne peut pas débuter avant la date de début du lot "
                        f"({lot.date_debut_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
        if lot.date_fin_prevue and fin and fin > lot.date_fin_prevue:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": (
                        f"L'activité ne peut pas se terminer après la date de fin du lot "
                        f"({lot.date_fin_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )

        unite = attrs.get("unite", UniteMesure.UNITE)
        quantite = attrs.get("quantite_prevue")
        if unite == UniteMesure.FORFAIT and quantite != Decimal("1.000"):
            attrs["quantite_prevue"] = Decimal("1.000")

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
        dependance = valeurs.get("dependance")
        visites = {self.instance.pk}
        while dependance:
            if dependance.pk in visites:
                raise serializers.ValidationError({"dependance": "Dépendance cyclique interdite."})
            visites.add(dependance.pk)
            dependance = dependance.dependance
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
        return attrs

