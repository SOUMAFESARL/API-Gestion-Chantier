"""Équipes de chantier et registre de main-d'œuvre — entrées et représentations."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.projets.models import (
    AffectationEquipeElement,
    EquipeChantier,
    MembreEquipeChantier,
    PersonneMainOeuvre,
)
from apps.projets.services.referentiels import (
    code_fonction_equipe_valide,
    libelle_fonction_equipe,
    table_fonctions_equipe,
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
    "UtilisateurPourEquipeSerializer",
]


def _valider_code_fonction_champ(valeur: str) -> str:
    code = (valeur or "").strip()
    if not code:
        return ""
    if not code_fonction_equipe_valide(code):
        raise serializers.ValidationError("Fonction invalide ou non autorisée.")
    return code


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
    utilisateur = serializers.SerializerMethodField()

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
            "utilisateur",
            "est_actif",
        ]

    @extend_schema_field(EntrepriseRattachementSerializer)
    def get_entreprise(self, obj):
        return entreprise_de(obj.entreprise_partenaire)

    @extend_schema_field(serializers.BooleanField())
    def get_a_un_compte(self, obj) -> bool:
        return obj.utilisateur_id is not None

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_utilisateur(self, obj):
        if not obj.utilisateur_id:
            return None
        u = obj.utilisateur
        if not u:
            return None
        from apps.core.enums import RoleGlobal

        if getattr(u, "role", None):
            role_libelle = u.role.libelle
            role_code = u.role.code
        elif getattr(u, "role_global", None):
            role_libelle = dict(RoleGlobal.choices).get(u.role_global, u.role_global)
            role_code = u.role_global
        else:
            role_libelle = ""
            role_code = ""

        return {
            "id": u.pk,
            "email": u.email,
            "nom": u.nom,
            "prenom": u.prenom,
            "nom_complet": u.nom_complet,
            "role": role_libelle,
            "role_code": (role_code or "").upper(),
        }


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
    fonction_libelle = serializers.SerializerMethodField()
    en_cours = serializers.SerializerMethodField()

    class Meta:
        model = MembreEquipeChantier
        fields = [
            "id",
            "personne",
            "fonction",
            "fonction_libelle",
            "est_chef",
            "date_arrivee",
            "date_depart",
            "en_cours",
        ]

    @extend_schema_field(serializers.CharField())
    def get_fonction_libelle(self, obj) -> str:
        table = table_fonctions_equipe(cache=self.context)
        return libelle_fonction_equipe(obj.fonction, table=table)

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
        return MembreSerializer(chef, context=self.context).data if chef else None

    @extend_schema_field(MembreSerializer(many=True))
    def get_membres(self, obj):
        historique = self.context.get("historique", False)
        membres = [m for m in self._membres(obj) if historique or m.date_depart is None]
        return MembreSerializer(membres, many=True, context=self.context).data

    @extend_schema_field(serializers.IntegerField())
    def get_effectif(self, obj) -> int:
        return sum(1 for m in self._membres(obj) if m.date_depart is None)

    @extend_schema_field(AffectationEquipeSerializer(many=True))
    def get_affectations(self, obj):
        affectations = [a for a in obj.affectations_elements.all() if a.supprime_le is None]
        return AffectationEquipeSerializer(affectations, many=True).data


class MembreCreationSerializer(serializers.Serializer):
    personne_id = serializers.UUIDField(required=False, allow_null=True)
    personne_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False
    )
    utilisateur_id = serializers.UUIDField(required=False, allow_null=True)
    utilisateur_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False
    )
    fonction = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    est_chef = serializers.BooleanField(required=False, default=False)
    date_arrivee = serializers.DateField(required=False, allow_null=True, default=None)
    date_depart = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_fonction(self, value):
        return _valider_code_fonction_champ(value)

    def validate(self, attrs):
        ids = [i for i in list(dict.fromkeys(attrs.get("personne_ids") or [])) if i]
        if attrs.get("personne_id") and attrs["personne_id"] not in ids:
            ids.insert(0, attrs["personne_id"])

        u_ids = [u for u in list(dict.fromkeys(attrs.get("utilisateur_ids") or [])) if u]
        if attrs.get("utilisateur_id") and attrs["utilisateur_id"] not in u_ids:
            u_ids.insert(0, attrs["utilisateur_id"])

        if not ids and not u_ids:
            raise serializers.ValidationError(
                {
                    "personne_id": (
                        "Sélectionnez au moins une personne du registre ou un "
                        "collaborateur avec compte."
                    )
                }
            )
        total_personnes = len(ids) + len(u_ids)
        est_chef = bool(attrs.get("est_chef"))
        if est_chef and total_personnes > 1:
            raise serializers.ValidationError(
                {"est_chef": "Une équipe n'a qu'un seul chef : sélectionnez une seule personne."}
            )
        attrs["personne_ids"] = ids
        if ids:
            attrs["personne_id"] = ids[0]
        attrs["utilisateur_ids"] = u_ids
        if u_ids:
            attrs["utilisateur_id"] = u_ids[0]
        return attrs


class UtilisateurPourEquipeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nom = serializers.CharField()
    prenom = serializers.CharField(allow_blank=True, default="")
    nom_complet = serializers.CharField()
    email = serializers.EmailField()
    telephone = serializers.CharField(allow_blank=True, default="")
    role = serializers.CharField()
    role_code = serializers.CharField()
    personne_id = serializers.UUIDField(allow_null=True)


class MembreModificationSerializer(serializers.Serializer):
    fonction = serializers.CharField(max_length=60, required=False, allow_blank=True)
    est_chef = serializers.BooleanField(required=False)
    date_arrivee = serializers.DateField(required=False)
    date_depart = serializers.DateField(required=False, allow_null=True)

    def validate_fonction(self, value):
        return _valider_code_fonction_champ(value)


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
