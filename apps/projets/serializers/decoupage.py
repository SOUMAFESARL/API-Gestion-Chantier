"""Entrées des routes du découpage : listes, modèles, tableau de démarrage, arbre et gestes.

Les réponses sont construites par les services (`listes_modeles`, `tableau_demarrage`,
`selectors.arbre_api`) ; ces sérialiseurs valident ce qui entre et documentent le contrat.
"""

from rest_framework import serializers

from apps.core.enums import TypeBordereau, UniteMesure
from apps.projets.models import ModeMesure
from apps.projets.serializers.execution import ModeExecutionField

__all__ = [
    "AjoutValeursSerializer",
    "CreationListeSerializer",
    "DeplacementSerializer",
    "DetailSerializer",
    "DqeApplicationSerializer",
    "DqeBilanSerializer",
    "DuplicationSerializer",
    "ElementCreationSerializer",
    "ElementModificationSerializer",
    "InsertionNiveauSerializer",
    "MesureSerializer",
    "ModeleEnregistrementSerializer",
    "MotifSerializer",
    "NiveauCreationSerializer",
    "NiveauModificationSerializer",
    "PlanificationSerializer",
    "ReferenceSerializer",
    "SuspensionSerializer",
    "TableauSerializer",
]

ORIGINES = [("PLATEFORME", "Plateforme"), ("ENTREPRISE", "Entreprise")]


class ReferenceSerializer(serializers.Serializer):
    """Une liste ou un modèle se désigne par son origine et son identifiant, jamais son nom."""

    origine = serializers.ChoiceField(choices=ORIGINES)
    id = serializers.UUIDField()


class NiveauGabaritSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=60, allow_blank=True)
    liste = ReferenceSerializer(required=False, allow_null=True, default=None)
    alerter = serializers.BooleanField(required=False, default=False)


class LigneObjetSerializer(serializers.Serializer):
    cellules = serializers.ListField(child=serializers.CharField(allow_blank=True, max_length=200))
    unite = serializers.ChoiceField(choices=UniteMesure.choices, required=False, allow_null=True)
    quantite = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True, min_value=0
    )
    montant = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, help_text="En centimes de FCFA."
    )
    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin = serializers.DateField(required=False, allow_null=True)


class LigneField(serializers.Field):
    """Une ligne du tableau : une liste de cellules, ou un objet avec ses champs de feuille."""

    def to_internal_value(self, data):
        if isinstance(data, list):
            return [str(c) if c is not None else "" for c in data]
        if isinstance(data, dict):
            ligne = LigneObjetSerializer(data=data)
            ligne.is_valid(raise_exception=True)
            return dict(ligne.validated_data)
        raise serializers.ValidationError("Une ligne est une liste de cellules ou un objet.")

    def to_representation(self, value):
        return value


class TableauSerializer(serializers.Serializer):
    niveaux = NiveauGabaritSerializer(many=True)
    lignes = serializers.ListField(child=LigneField(), allow_empty=True)
    confirmer_avertissements = serializers.BooleanField(required=False, default=False)


class CreationListeSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    valeurs = serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, default=list
    )


class AjoutValeursSerializer(serializers.Serializer):
    valeurs = serializers.ListField(child=serializers.CharField(max_length=200), min_length=1)
    groupe = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)


class ModeleEnregistrementSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    types_projet = serializers.ListField(
        child=serializers.CharField(max_length=60), required=False, default=list
    )
    par_defaut_pour = serializers.ListField(
        child=serializers.CharField(max_length=60), required=False, default=list
    )
    niveaux = NiveauGabaritSerializer(many=True)
    lignes = serializers.ListField(child=LigneField(), allow_empty=True)


class MotifSerializer(serializers.Serializer):
    motif = serializers.CharField(required=False, allow_blank=True, default="")


class ElementCreationSerializer(serializers.Serializer):
    parent_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    niveau_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    libelle = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    mode_mesure = serializers.ChoiceField(choices=ModeMesure.choices, required=False)
    unite = serializers.ChoiceField(choices=UniteMesure.choices, required=False)
    quantite_prevue = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True, min_value=0
    )
    montant = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    enveloppe = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    date_debut_prevue = serializers.DateField(required=False, allow_null=True)
    date_fin_prevue = serializers.DateField(required=False, allow_null=True)
    mode_execution = ModeExecutionField(required=False, allow_blank=True)
    type_bordereau = serializers.ChoiceField(
        choices=TypeBordereau.choices, required=False, allow_blank=True
    )
    titulaire_id = serializers.UUIDField(required=False, allow_null=True)
    motif = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        debut, fin = attrs.get("date_debut_prevue"), attrs.get("date_fin_prevue")
        if debut and fin and fin < debut:
            raise serializers.ValidationError(
                {"date_fin_prevue": "La date de fin ne peut pas précéder la date de début."}
            )
        return attrs


class ElementModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=200, required=False)
    code = serializers.CharField(max_length=30, required=False, allow_blank=True)
    ordre = serializers.IntegerField(required=False, min_value=0)
    mode_mesure = serializers.ChoiceField(choices=ModeMesure.choices, required=False)
    unite = serializers.ChoiceField(choices=UniteMesure.choices, required=False, allow_null=True)
    quantite_prevue = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True, min_value=0
    )
    montant = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    enveloppe = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    mode_execution = ModeExecutionField(required=False, allow_blank=True, allow_null=True)
    type_bordereau = serializers.ChoiceField(
        choices=TypeBordereau.choices, required=False, allow_blank=True, allow_null=True
    )
    titulaire_id = serializers.UUIDField(required=False, allow_null=True)
    motif = serializers.CharField(required=False, allow_blank=True, default="")


class PlanificationSerializer(serializers.Serializer):
    """La première saisie des dates d'une case — ses reports passent par « reprogrammer »."""

    date_debut_prevue = serializers.DateField(allow_null=True)
    date_fin_prevue = serializers.DateField(allow_null=True)
    prolonger = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Confirme la prolongation des cases parentes listées par l'erreur "
        "`prolongation_requise`.",
    )
    motif_id = serializers.UUIDField(required=False, allow_null=True)
    justification = serializers.CharField(required=False, allow_blank=True, default="")


class DeplacementSerializer(serializers.Serializer):
    nouveau_parent_id = serializers.UUIDField(allow_null=True)
    apercu = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Vrai : rend l'aperçu des effets, sans rien écrire.",
    )
    motif = serializers.CharField(required=False, allow_blank=True, default="")
    prolonger = serializers.BooleanField(required=False, default=False)
    motif_id = serializers.UUIDField(required=False, allow_null=True)
    justification = serializers.CharField(required=False, allow_blank=True, default="")


class EnfantDetailSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=30, required=False, allow_blank=True)
    mode_mesure = serializers.ChoiceField(choices=ModeMesure.choices, required=False)
    unite = serializers.ChoiceField(choices=UniteMesure.choices, required=False)
    quantite_prevue = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True, min_value=0
    )
    montant = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    date_debut_prevue = serializers.DateField(required=False, allow_null=True)
    date_fin_prevue = serializers.DateField(required=False, allow_null=True)


class DetailSerializer(serializers.Serializer):
    enfants = EnfantDetailSerializer(many=True, allow_empty=False)
    niveau_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    motif = serializers.CharField(required=False, allow_blank=True, default="")


class SuspensionSerializer(serializers.Serializer):
    suspendu = serializers.BooleanField()
    motif = serializers.CharField(required=False, allow_blank=True, default="")


class MesureSerializer(serializers.Serializer):
    quantite_realisee = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, allow_null=True, min_value=0
    )
    pourcentage_declare = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True, min_value=0, max_value=100
    )
    atteint = serializers.BooleanField(required=False, allow_null=True)
    commentaire = serializers.CharField()


class NiveauModificationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=60, required=False)
    liste = ReferenceSerializer(required=False, allow_null=True)
    alerter = serializers.BooleanField(required=False)


class NiveauCreationSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=60)
    liste = ReferenceSerializer(required=False, allow_null=True, default=None)
    alerter = serializers.BooleanField(required=False, default=False)


class InsertionNiveauSerializer(serializers.Serializer):
    position = serializers.IntegerField(min_value=1)
    libelle = serializers.CharField(max_length=60)
    liste = ReferenceSerializer(required=False, allow_null=True, default=None)
    libelle_intermediaire = serializers.CharField(max_length=200, required=False, default="Général")


class DuplicationSerializer(serializers.Serializer):
    """Dupliquer une branche (§13quinquies.1). Sans `parent_id`, la copie se pose à côté de
    l'original ; `parent_id: null` la pose à la racine."""

    parent_id = serializers.UUIDField(required=False, allow_null=True)
    libelle = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    motif = serializers.CharField(required=False, allow_blank=True, default="")


class LigneDqeField(serializers.Field):
    """Une ligne lue d'un DQE, telle que le bilan l'a rendue. Seule sa forme est vérifiée ici :
    une valeur invalide (unité inconnue, nombre illisible) ne refuse que sa ligne, avec sa raison,
    dans le bilan."""

    CHAMPS = ("unite", "quantite", "montant", "date_debut", "date_fin")

    def to_internal_value(self, data):
        if isinstance(data, list):
            return [str(c) if c is not None else "" for c in data]
        if isinstance(data, dict) and isinstance(data.get("cellules"), list):
            ligne = {"cellules": [str(c) if c is not None else "" for c in data["cellules"]]}
            ligne.update({k: data[k] for k in self.CHAMPS if data.get(k) not in (None, "")})
            return ligne
        raise serializers.ValidationError(
            "Une ligne est une liste de cellules ou un objet portant `cellules`."
        )

    def to_representation(self, value):
        return value


class DqeBilanSerializer(serializers.Serializer):
    """Le bilan d'un import DQE, recalculé sur des lignes déjà lues (sans fichier)."""

    lignes = serializers.ListField(child=LigneDqeField(), allow_empty=False, max_length=5000)


class DqeApplicationSerializer(serializers.Serializer):
    lignes = serializers.ListField(child=LigneDqeField(), allow_empty=False, max_length=5000)
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Obligatoire (10 caractères au moins) quand le bilan dit `motif_requis`.",
    )
