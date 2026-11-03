"""Équipes de chantier et registre de main-d'œuvre — entrées et représentations."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.projets.models import (
    AffectationEquipeElement,
    EquipeChantier,
    MembreEquipeChantier,
    PersonneMainOeuvre,
)
from apps.tiers.models import Tiers

__all__ = [
    "AffectationEquipeCreationSerializer",
    "AffectationEquipeSerializer",
    "EquipeCreationSerializer",
    "EquipeModificationSerializer",
    "EquipeSerializer",
    "ImportPersonnesResultatSerializer",
    "ImportPersonnesSerializer",
    "ImportPersonnesVerifieSerializer",
    "MembreCreationSerializer",
    "MembreModificationSerializer",
    "MembreSerializer",
    "PersonneCreationSerializer",
    "PersonneModificationSerializer",
    "PersonneSerializer",
]

FONCTIONS = [c[0] for c in MembreEquipeChantier.FONCTION_CHOICES]


class EntrepriseRattachementSerializer(serializers.Serializer):
    """L'entreprise de rattachement : la nôtre (`id` nul) ou un partenaire."""

    id = serializers.UUIDField(allow_null=True)
    nom = serializers.CharField()
    interne = serializers.BooleanField()


def entreprise_de(tiers) -> dict:
    if tiers is None:
        return {"id": None, "nom": "", "interne": True}
    return {"id": tiers.pk, "nom": tiers.raison_sociale, "interne": False}


# --------------------------------------------------------------------------
# Registre de main-d'œuvre
# --------------------------------------------------------------------------
class PersonneSerializer(serializers.ModelSerializer):
    nom_complet = serializers.CharField(read_only=True)
    entreprise = serializers.SerializerMethodField()
    a_un_compte = serializers.SerializerMethodField()

    class Meta:
        model = PersonneMainOeuvre
        fields = [
            "id",
            "nom",
            "prenom",
            "nom_complet",
            "telephone",
            "metier",
            "entreprise",
            "a_un_compte",
            "utilisateur_id",
            "est_actif",
        ]

    @extend_schema_field(EntrepriseRattachementSerializer)
    def get_entreprise(self, obj):
        return entreprise_de(obj.entreprise_partenaire)

    @extend_schema_field(serializers.BooleanField())
    def get_a_un_compte(self, obj) -> bool:
        return obj.utilisateur_id is not None


class PersonneCreationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=150)
    prenom = serializers.CharField(max_length=150)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    metier = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    # Vide : notre entreprise ; sinon un tiers sous-traitant, tâcheron ou prestataire.
    entreprise_partenaire_id = serializers.PrimaryKeyRelatedField(
        queryset=Tiers.objects.all(), required=False, allow_null=True, default=None
    )
    # Un collaborateur avec un compte sur la plateforme.
    utilisateur_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class PersonneModificationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=150, required=False)
    prenom = serializers.CharField(max_length=150, required=False)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    metier = serializers.CharField(max_length=100, required=False, allow_blank=True)
    entreprise_partenaire_id = serializers.PrimaryKeyRelatedField(
        queryset=Tiers.objects.all(), required=False, allow_null=True
    )
    est_actif = serializers.BooleanField(required=False)


# --------------------------------------------------------------------------
# Équipes
# --------------------------------------------------------------------------
class MembreSerializer(serializers.ModelSerializer):
    personne = PersonneSerializer(read_only=True)
    en_cours = serializers.SerializerMethodField()

    class Meta:
        model = MembreEquipeChantier
        fields = [
            "id",
            "personne",
            "fonction",
            "est_chef",
            "date_arrivee",
            "date_depart",
            "en_cours",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_en_cours(self, obj) -> bool:
        return obj.date_depart is None


class AffectationEquipeSerializer(serializers.ModelSerializer):
    element = serializers.SerializerMethodField()

    class Meta:
        model = AffectationEquipeElement
        fields = ["id", "equipe_id", "element", "cree_le"]

    @extend_schema_field(serializers.DictField())
    def get_element(self, obj):
        e = obj.element
        return {"id": e.pk, "libelle": e.libelle, "niveau": e.niveau.libelle}


class EquipeSerializer(serializers.ModelSerializer):
    entreprise = serializers.SerializerMethodField()
    nature = serializers.CharField(read_only=True)
    chef = serializers.SerializerMethodField()
    membres = serializers.SerializerMethodField()
    effectif = serializers.SerializerMethodField()
    affectations = serializers.SerializerMethodField()

    class Meta:
        model = EquipeChantier
        fields = [
            "id",
            "projet_id",
            "nom",
            "corps_etat",
            "entreprise",
            "nature",
            "chef",
            "effectif",
            "membres",
            "affectations",
            "est_actif",
            "cree_le",
        ]

    def _membres(self, obj):
        return [m for m in obj.membres.all() if m.supprime_le is None]

    @extend_schema_field(EntrepriseRattachementSerializer)
    def get_entreprise(self, obj):
        return entreprise_de(obj.entreprise_partenaire)

    @extend_schema_field(MembreSerializer(allow_null=True))
    def get_chef(self, obj):
        chef = next((m for m in self._membres(obj) if m.est_chef and m.date_depart is None), None)
        return MembreSerializer(chef).data if chef else None

    @extend_schema_field(MembreSerializer(many=True))
    def get_membres(self, obj):
        historique = self.context.get("historique", False)
        membres = [m for m in self._membres(obj) if historique or m.date_depart is None]
        return MembreSerializer(membres, many=True).data

    @extend_schema_field(serializers.IntegerField())
    def get_effectif(self, obj) -> int:
        return sum(1 for m in self._membres(obj) if m.date_depart is None)

    @extend_schema_field(AffectationEquipeSerializer(many=True))
    def get_affectations(self, obj):
        affectations = [a for a in obj.affectations_elements.all() if a.supprime_le is None]
        return AffectationEquipeSerializer(affectations, many=True).data


class MembreCreationSerializer(serializers.Serializer):
    personne_id = serializers.UUIDField(required=False)
    personne_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False
    )
    fonction = serializers.ChoiceField(choices=FONCTIONS, required=False, default="OUVRIER")
    est_chef = serializers.BooleanField(required=False, default=False)
    date_arrivee = serializers.DateField(required=False, allow_null=True, default=None)
    date_depart = serializers.DateField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        ids = list(dict.fromkeys(attrs.get("personne_ids") or []))
        if attrs.get("personne_id") and attrs["personne_id"] not in ids:
            ids.insert(0, attrs["personne_id"])
        if not ids:
            raise serializers.ValidationError(
                {"personne_id": "Sélectionnez au moins une personne du registre."}
            )
        if (attrs.get("est_chef") or attrs.get("fonction") == "CHEF_EQUIPE") and len(ids) > 1:
            raise serializers.ValidationError(
                {"est_chef": "Une équipe n'a qu'un seul chef : sélectionnez une seule personne."}
            )
        attrs["personne_ids"] = ids
        attrs["personne_id"] = ids[0]
        return attrs


class MembreModificationSerializer(serializers.Serializer):
    fonction = serializers.ChoiceField(choices=FONCTIONS, required=False)
    est_chef = serializers.BooleanField(required=False)
    date_arrivee = serializers.DateField(required=False)
    date_depart = serializers.DateField(required=False, allow_null=True)


class EquipeCreationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=200)
    corps_etat = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    # Vide : équipe de notre entreprise ; sinon un partenaire (sous-traitant, tâcheron…).
    entreprise_partenaire_id = serializers.PrimaryKeyRelatedField(
        queryset=Tiers.objects.all(), required=False, allow_null=True, default=None
    )
    membres = MembreCreationSerializer(many=True, required=False, default=list)


class EquipeModificationSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=200, required=False)
    corps_etat = serializers.CharField(max_length=200, required=False, allow_blank=True)
    entreprise_partenaire_id = serializers.PrimaryKeyRelatedField(
        queryset=Tiers.objects.all(), required=False, allow_null=True
    )
    est_actif = serializers.BooleanField(required=False)


class AffectationEquipeCreationSerializer(serializers.Serializer):
    equipe_id = serializers.UUIDField()
    element_id = serializers.UUIDField()


# --------------------------------------------------------------------------
# Import du registre depuis Excel
# --------------------------------------------------------------------------
class LigneImportPersonneSerializer(serializers.Serializer):
    """Une ligne d'import, telle que l'écran la renvoie après correction. Les champs sont permissifs
    à dessein : la vérification dit ce qui ne va pas, ligne par ligne, sans tout refuser."""

    numero = serializers.IntegerField(required=False, allow_null=True, default=None)
    nom = serializers.CharField(required=False, allow_blank=True, default="")
    prenom = serializers.CharField(required=False, allow_blank=True, default="")
    telephone = serializers.CharField(required=False, allow_blank=True, default="")
    metier = serializers.CharField(required=False, allow_blank=True, default="")
    entreprise_partenaire_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    entreprise_saisie = serializers.CharField(required=False, allow_blank=True, default="")


class ImportPersonnesSerializer(serializers.Serializer):
    lignes = LigneImportPersonneSerializer(many=True, allow_empty=False, max_length=5000)


class LigneImportVerifieeSerializer(LigneImportPersonneSerializer):
    statut = serializers.ChoiceField(choices=["VALIDE", "DOUBLON", "ERREUR", "CREEE"])
    erreurs = serializers.DictField(child=serializers.CharField())
    message = serializers.CharField(allow_blank=True)


class PartenaireImportSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nom = serializers.CharField()


class ImportPersonnesVerifieSerializer(serializers.Serializer):
    lignes = LigneImportVerifieeSerializer(many=True)
    partenaires = PartenaireImportSerializer(many=True)


class ImportPersonnesResultatSerializer(serializers.Serializer):
    creees = serializers.IntegerField()
    doublons = serializers.IntegerField()
    erreurs = serializers.IntegerField()
    lignes = LigneImportVerifieeSerializer(many=True)
