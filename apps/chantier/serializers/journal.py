"""Contrat exact de ChargeSaisie (frontend), avec brouillons incomplets."""

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


def entier():
    return s.IntegerField(
        required=False, allow_null=True, default=None, min_value=0, max_value=32767
    )


METEOS = ["ENSOLEILLE", "NUAGEUX", "PLUVIEUX", "ORAGEUX", "BRUMEUX"]


class MeteoSerializer(StrictSerializer):
    matin = s.ChoiceField(choices=METEOS, allow_blank=True, required=False, default="")
    apres_midi = s.ChoiceField(choices=METEOS, allow_blank=True, required=False, default="")
    conditions = s.ChoiceField(
        choices=["FAVORABLES", "DIFFICILES", "ARRET"], allow_blank=True, required=False, default=""
    )
    temperature_min = s.FloatField(
        required=False, allow_null=True, default=None, min_value=-80, max_value=80
    )
    temperature_max = s.FloatField(
        required=False, allow_null=True, default=None, min_value=-80, max_value=80
    )
    humidite = nombre(100)
    vent = texte(200)
    prevision = texte()

    def validate(self, attrs):
        mini, maxi = attrs.get("temperature_min"), attrs.get("temperature_max")
        if mini is not None and maxi is not None and mini > maxi:
            raise s.ValidationError(
                {"temperature_max": "Doit être supérieure ou égale au minimum."}
            )
        return attrs


class ArretSerializer(StrictSerializer):
    motif = s.ChoiceField(choices=["INTEMPERIES", "JOUR_FERIE", "AUTRE"])
    precision = texte()


class EffectifSerializer(StrictSerializer):
    categorie = texte(200)
    prevus = entier()
    presents = entier()
    retards = entier()
    heures = nombre(24)
    observation = texte()

    def validate(self, attrs):
        prevus, presents, retards = (attrs.get(k) for k in ("prevus", "presents", "retards"))
        if prevus is not None and presents is not None and presents > prevus:
            raise s.ValidationError(
                {"presents": "L'effectif présent dépasse le personnel affecté."}
            )
        if retards is not None and presents is not None and retards > presents:
            raise s.ValidationError({"retards": "Les retards dépassent l'effectif présent."})
        return attrs


class PresenceSerializer(StrictSerializer):
    presence = s.ChoiceField(choices=["PRESENT", "PARTIEL", "ABSENT"], allow_blank=True)
    motif = texte()
    qualite = s.ChoiceField(choices=["CONFORME", "NON_CONFORME"], allow_blank=True)
    observation = texte()


class ProductionSerializer(StrictSerializer):
    intervenant = texte(200)
    activite_id = s.UUIDField()
    quantite_jour = nombre()
    prix_unitaire = s.IntegerField(
        min_value=0, max_value=10**15, required=False, default=None, allow_null=True
    )


class PointLotSerializer(StrictSerializer):
    lot_id = s.UUIDField()
    observation = texte(5000)


@extend_schema_serializer(component_name="JournalActivite")
class ActiviteSerializer(StrictSerializer):
    activite_id = s.UUIDField()
    quantite_jour = nombre()
    localisation = texte(300)
    observation = texte(5000)


class MateriauSerializer(StrictSerializer):
    designation = texte(200)
    quantite_consommee = nombre()
    unite = texte(30)


class LivraisonSerializer(StrictSerializer):
    fournisseur = texte(200)
    designation = texte(200)
    quantite = texte(100)
    bon_livraison = texte(100)
    heure = texte(5)
    conformite = s.ChoiceField(choices=["CONFORME", "PARTIELLE", "NON_CONFORME"], allow_blank=True)
    observation = texte()


class BesoinSerializer(StrictSerializer):
    nature = s.ChoiceField(choices=["RUPTURE", "URGENT"])
    designation = texte(200)
    quantite = texte(100)
    observation = texte()


class EquipementSerializer(StrictSerializer):
    designation = texte(200)
    reference = texte(100)
    propriete = s.ChoiceField(choices=["ENTREPRISE", "LOCATION"], allow_blank=True)
    utilisation = texte(100)
    operateur = texte(200)
    etat = s.ChoiceField(choices=["BON", "ENTRETIEN", "PANNE"], allow_blank=True)
    duree_arret = nombre(24)
    observation = texte()


class IncidentSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    nature = s.ChoiceField(
        choices=[
            "INCIDENT",
            "DIFFICULTE_TECHNIQUE",
            "NON_CONFORMITE",
            "RETARD",
            "INTEMPERIE",
            "ARRET_TRAVAUX",
            "INSTRUCTION",
            "EVENEMENT_PARTICULIER",
        ]
    )
    type = s.ChoiceField(
        choices=["QUALITE", "SECURITE", "MATERIEL", "APPROVISIONNEMENT", "ADMINISTRATIF"],
        allow_blank=True,
    )
    heure_debut = texte(5)
    heure_fin = texte(5)
    gravite = s.ChoiceField(choices=["MINEUR", "SIGNIFICATIF", "GRAVE"], allow_blank=True)
    decide_par = s.ChoiceField(choices=["CC", "CT", "CP"], allow_blank=True)
    description = texte(5000)
    action_entreprise = texte(5000)


@extend_schema_serializer(component_name="JournalBlocage")
class BlocageSerializer(StrictSerializer):
    niveau = s.ChoiceField(
        choices=["AUCUN", "MINEUR", "SIGNIFICATIF", "BLOQUANT"],
        allow_blank=True,
        required=False,
        default="AUCUN",
    )
    nature = s.ChoiceField(
        choices=[
            "APPROVISIONNEMENT",
            "METEO",
            "MAIN_OEUVRE",
            "TECHNIQUE",
            "ADMINISTRATIF",
            "SECURITE",
        ],
        required=False,
        default=None,
        allow_null=True,
    )
    description = texte(5000)
    impact = texte()


class PhotoSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
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
    taille = s.IntegerField(min_value=1, max_value=2 * 1024 * 1024)


class PrevisionSerializer(StrictSerializer):
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
    effectifs = EffectifSerializer(many=True, required=False, default=list, max_length=100)
    presence_sous_traitant = PresenceSerializer(required=False, allow_null=True, default=None)
    production = ProductionSerializer(many=True, required=False, default=list, max_length=200)
    lots_travailles = PointLotSerializer(many=True, required=False, default=list, max_length=100)
    activites = ActiviteSerializer(many=True, required=False, default=list, max_length=300)
    materiaux = MateriauSerializer(many=True, required=False, default=list, max_length=200)
    livraisons = LivraisonSerializer(many=True, required=False, default=list, max_length=100)
    besoins = BesoinSerializer(many=True, required=False, default=list, max_length=100)
    equipements = EquipementSerializer(many=True, required=False, default=list, max_length=100)
    incidents = IncidentSerializer(many=True, required=False, default=list, max_length=100)
    blocage = BlocageSerializer(required=False, default=dict)
    photos = PhotoSerializer(many=True, required=False, default=list, max_length=5)
    pieces_jointes = PieceSerializer(many=True, required=False, default=list, max_length=3)
    previsions = PrevisionSerializer(many=True, required=False, default=list, max_length=100)
    note_cc = texte(10000)


class FiltresJournalSerializer(StrictSerializer):
    projet = s.UUIDField(required=False)
    date = s.DateField(required=False)
    date_debut = s.DateField(required=False)
    date_fin = s.DateField(required=False)
    auteur = s.CharField(required=False)
    statut = s.ChoiceField(
        choices=["BROUILLON", "SOUMIS", "VALIDE_CT", "APPROUVE_CP", "REJETE"], required=False
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
        return attrs


class SignatureJournalSerializer(StrictSerializer):
    commentaire = texte(5000)


class RejetJournalSerializer(StrictSerializer):
    motif = s.CharField(min_length=20, max_length=5000)


class AlerteJournalSerializer(StrictSerializer):
    cle = s.CharField(max_length=100)
    type = s.ChoiceField(choices=["BLOCAGE_BLOQUANT", "INCIDENT_GRAVE"])
    description = s.CharField(min_length=1, max_length=5000)
