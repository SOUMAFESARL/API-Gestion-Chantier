"""Contrat de saisie du journal de chantier (refonte unifiée arbre, équipes et permissions)."""

from collections.abc import Mapping

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers as s


class StrictSerializer(s.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            inconnus = set(data) - set(self.fields)
            if inconnus:
                raise s.ValidationError(dict.fromkeys(inconnus, "Champ inconnu ou non modifiable."))
        return super().to_internal_value(data)


def texte(max_length=1000):
    return s.CharField(required=False, allow_blank=True, default="", max_length=max_length)


def nombre(max_value=10**11):
    return s.FloatField(
        required=False, allow_null=True, default=None, min_value=0, max_value=max_value
    )


METEOS = ["ENSOLEILLE", "NUAGEUX", "PLUVIEUX", "ORAGEUX", "BRUMEUX"]
CONDITIONS_METEO = ["FAVORABLES", "DIFFICILES", "ARRET"]
MOTIFS_ARRET = [
    "INTEMPERIES",
    "INCIDENT_SECURITE",
    "RUPTURE_APPROVISIONNEMENT",
    "INJONCTION_ADMINISTRATIVE",
    "GREVE_SOCIAL",
    "AUTRE",
]
NATURES_INCIDENT = [
    "INCIDENT_SECURITE",
    "NON_CONFORMITE",
    "INCIDENT_MATERIEL",
    "DIFFICULTE_TECHNIQUE",
    "VISITE_INSTRUCTION",
    "EVENEMENT_PARTICULIER",
]
TYPES_INCIDENT = ["QUALITE", "SECURITE", "MATERIEL", "APPROVISIONNEMENT", "ADMINISTRATIF"]
GRAVITES_INCIDENT = ["MINEUR", "SIGNIFICATIF", "GRAVE"]
DECIDEURS_INCIDENT = [
    "REDACTION",
    "VALIDATION",
    "APPROBATION",
    "MAITRE_OEUVRE",
    "BUREAU_CONTROLE",
    "CLIENT",
    "AUTORITE",
]
NIVEAUX_BLOCAGE = ["MINEUR", "SIGNIFICATIF", "BLOQUANT"]
NATURES_BLOCAGE = [
    "APPROVISIONNEMENT",
    "METEO",
    "MAIN_OEUVRE",
    "TECHNIQUE",
    "ADMINISTRATIF",
    "SECURITE",
]

PHOTOS_MAX = 10
PIECES_JOINTES_MAX = 3
TAILLE_MAX_PHOTO_OCTETS = 2 * 1024 * 1024
TAILLE_MAX_PIECE_OCTETS = 5 * 1024 * 1024
TAILLE_MAX_RAPPORT_OCTETS = 36 * 1024 * 1024


class MeteoSerializer(StrictSerializer):
    matin = s.ChoiceField(choices=METEOS, allow_blank=True, required=False, default="")
    apres_midi = s.ChoiceField(choices=METEOS, allow_blank=True, required=False, default="")
    conditions = s.ChoiceField(
        choices=CONDITIONS_METEO, allow_blank=True, required=False, default=""
    )


class ArretSerializer(StrictSerializer):
    motif = s.ChoiceField(choices=MOTIFS_ARRET)
    precision = texte()


class EquipeJourSerializer(StrictSerializer):
    """Pointage nominatif des présents d'une équipe (interne, sous-traitant ou tâcheron)."""

    equipe_id = s.UUIDField()
    presents = s.ListField(child=s.UUIDField(), required=False, default=list, max_length=500)
    retards = s.ListField(child=s.UUIDField(), required=False, default=list, max_length=500)
    heures = nombre(24)
    qualite = s.ChoiceField(
        choices=["CONFORME", "NON_CONFORME"], allow_blank=True, required=False, default=""
    )
    observation = texte()

    def validate(self, attrs):
        presents, retards = attrs.get("presents", []), attrs.get("retards", [])
        if len(set(presents)) != len(presents) or len(set(retards)) != len(retards):
            raise s.ValidationError("Une personne n'est cochée qu'une fois.")
        if not set(retards) <= set(presents):
            raise s.ValidationError({"retards": "Une personne en retard est aussi présente."})
        return attrs


class PointLotSerializer(StrictSerializer):
    lot_id = s.UUIDField()
    observation = texte(5000)


@extend_schema_serializer(component_name="JournalActivite")
class ActiviteSerializer(StrictSerializer):
    """Mesure journalière d'une feuille de l'arbre (quantité, pourcentage ou jalon) + équipes."""

    activite_id = s.UUIDField()
    equipe_ids = s.ListField(child=s.UUIDField(), required=False, default=list, max_length=50)
    quantite_jour = nombre()
    pourcentage_jour = nombre(100)
    jalon_atteint = s.BooleanField(required=False, default=False)
    localisation = texte(300)
    observation = texte(5000)

    def validate(self, attrs):
        equipe_ids = attrs.get("equipe_ids", [])
        if len(set(equipe_ids)) != len(equipe_ids):
            raise s.ValidationError({"equipe_ids": "Une équipe n'est rattachée qu'une fois."})
        return attrs


class MateriauSerializer(StrictSerializer):
    designation = texte(200)
    quantite_consommee = nombre()
    unite = texte(30)


class LivraisonSerializer(StrictSerializer):
    fournisseur = texte(200)
    designation = texte(200)
    quantite = nombre()
    unite = texte(30)
    bon_livraison = texte(100)
    heure = texte(5)
    conformite = s.ChoiceField(
        choices=["CONFORME", "PARTIELLE", "NON_CONFORME"],
        allow_blank=True,
        required=False,
        default="",
    )
    observation = texte()


class BesoinSerializer(StrictSerializer):
    nature = s.ChoiceField(choices=["RUPTURE", "URGENT"])
    designation = texte(200)
    quantite = nombre()
    unite = texte(30)
    observation = texte()


class EquipementSerializer(StrictSerializer):
    cle = s.CharField(max_length=100, required=False, allow_blank=True, default="")
    designation = texte(200)
    reference = texte(100)
    propriete = s.ChoiceField(
        choices=["ENTREPRISE", "LOCATION"], allow_blank=True, required=False, default=""
    )
    heures_utilisation = nombre(24)
    usage = texte(200)
    operateur = texte(200)
    etat = s.ChoiceField(
        choices=["BON", "ENTRETIEN", "PANNE"], allow_blank=True, required=False, default=""
    )
    duree_arret = nombre(24)
    observation = texte()


class IncidentSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    nature = s.ChoiceField(choices=NATURES_INCIDENT)
    type = s.ChoiceField(choices=TYPES_INCIDENT, allow_blank=True, required=False, default="")
    heure_debut = texte(5)
    heure_fin = texte(5)
    gravite = s.ChoiceField(choices=GRAVITES_INCIDENT, allow_blank=True, required=False, default="")
    decide_par = s.ChoiceField(
        choices=DECIDEURS_INCIDENT, allow_blank=True, required=False, default=""
    )
    description = texte(5000)
    action_entreprise = texte(5000)


@extend_schema_serializer(component_name="JournalBlocage")
class BlocageLigneSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    blocage_id = s.UUIDField(required=False, allow_null=True, default=None)
    element_id = s.UUIDField(required=False, allow_null=True, default=None)
    titre = texte(200)
    niveau = s.ChoiceField(choices=NIVEAUX_BLOCAGE)
    nature = s.ChoiceField(choices=NATURES_BLOCAGE, allow_blank=True, required=False, default="")
    description = texte(5000)
    impact = texte()


class PhotoSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    element_id = s.UUIDField(required=False, allow_null=True, default=None)
    fichier = s.CharField(max_length=8_000_000)
    legende = texte(500)
    horodatage_utc = s.DateTimeField()
    latitude = s.FloatField(allow_null=True, min_value=-90, max_value=90)
    longitude = s.FloatField(allow_null=True, min_value=-180, max_value=180)


class PieceSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    fichier = s.CharField(max_length=15_000_000)
    nom = s.CharField(max_length=200)
    type_mime = s.ChoiceField(
        choices=[
            "application/pdf",
            "application/msword",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ]
    )
    taille = s.IntegerField(min_value=1, max_value=TAILLE_MAX_PIECE_OCTETS)


class PrevisionSerializer(StrictSerializer):
    activite_id = s.UUIDField(required=False, allow_null=True, default=None)
    equipe_id = s.UUIDField(required=False, allow_null=True, default=None)
    activite = texte(300)
    equipe = texte(200)
    objectif = texte()
    prerequis = texte()


class SaisieJournalSerializer(StrictSerializer):
    projet_id = s.UUIDField()
    date = s.DateField()
    heure_debut = texte(5)
    heure_fin = texte(5)
    arret = ArretSerializer(required=False, allow_null=True, default=None)
    meteo = MeteoSerializer(required=False, default=dict)
    equipes = EquipeJourSerializer(many=True, required=False, default=list, max_length=100)
    lots_travailles = PointLotSerializer(many=True, required=False, default=list, max_length=100)
    activites = ActiviteSerializer(many=True, required=False, default=list, max_length=300)
    materiaux = MateriauSerializer(many=True, required=False, default=list, max_length=200)
    livraisons = LivraisonSerializer(many=True, required=False, default=list, max_length=100)
    besoins = BesoinSerializer(many=True, required=False, default=list, max_length=100)
    equipements = EquipementSerializer(many=True, required=False, default=list, max_length=100)
    incidents = IncidentSerializer(many=True, required=False, default=list, max_length=100)
    blocages = BlocageLigneSerializer(many=True, required=False, default=list, max_length=50)
    photos = PhotoSerializer(many=True, required=False, default=list, max_length=PHOTOS_MAX)
    pieces_jointes = PieceSerializer(
        many=True, required=False, default=list, max_length=PIECES_JOINTES_MAX
    )
    previsions = PrevisionSerializer(many=True, required=False, default=list, max_length=100)
    note_redacteur = texte(10000)


class SynchronisationJournalSerializer(StrictSerializer):
    """L'envoi au retour du réseau : la copie du téléphone, soumise si on le demande."""

    saisie = SaisieJournalSerializer()
    soumettre = s.BooleanField(required=False, default=False)


class FiltresJournalSerializer(StrictSerializer):
    projet = s.UUIDField(required=False)
    date = s.DateField(required=False)
    date_debut = s.DateField(required=False)
    date_fin = s.DateField(required=False)
    auteur = s.CharField(required=False)
    statut = s.ChoiceField(
        choices=[
            "BROUILLON",
            "SOUMIS",
            "VALIDE",
            "APPROUVE",
            "REJETE",
            "VALIDE_CT",
            "APPROUVE_CP",
        ],
        required=False,
    )

    def validate(self, attrs):
        if (
            attrs.get("date_debut")
            and attrs.get("date_fin")
            and attrs["date_debut"] > attrs["date_fin"]
        ):
            raise s.ValidationError({"date_fin": "La fin précède le début."})
        if attrs.get("auteur") not in (None, "moi"):
            raise s.ValidationError({"auteur": "Seule la valeur moi est acceptée."})
        statut = attrs.get("statut")
        if statut == "VALIDE_CT":
            attrs["statut"] = "VALIDE"
        elif statut == "APPROUVE_CP":
            attrs["statut"] = "APPROUVE"
        return attrs


class SignatureJournalSerializer(StrictSerializer):
    commentaire = texte(5000)


class RejetJournalSerializer(StrictSerializer):
    motif = s.CharField(min_length=20, max_length=5000)


class AlerteJournalSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    type = s.ChoiceField(choices=["BLOCAGE_BLOQUANT", "INCIDENT_GRAVE", "EQUIPEMENT_PANNE"])
    description = s.CharField(min_length=1, max_length=5000)
