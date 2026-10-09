"""Paramètres publics de la plateforme : tarifs des forfaits et identité.

Lecture publique (pages de connexion et de tarifs), écriture réservée au
superviseur de la plateforme.
"""

from rest_framework import serializers

from apps.billing.models import Plan

# Les forfaits proposés à la vente et réglables ici. Les anciens codes
# (STARTER, PRO, ENTERPRISE) restent liés à d'anciens abonnements mais ne se règlent plus.
CODES_FORFAITS = (Plan.Code.BATISSEUR, Plan.Code.MAITRE_OEUVRE, Plan.Code.PROMOTEUR)

OCTETS_LOGO_MAX = 2 * 1024 * 1024
TYPES_LOGO = ("image/png", "image/jpeg", "image/webp", "image/svg+xml")


class AvantageSerializer(serializers.Serializer):
    libelle = serializers.CharField(max_length=200)
    inclus = serializers.BooleanField()


class TarifPlanEcritureSerializer(serializers.Serializer):
    """Un forfait tel que le back-office l'enregistre (montants en centimes de FCFA)."""

    plan_code = serializers.ChoiceField(choices=[c.value for c in CODES_FORFAITS])
    libelle = serializers.CharField(max_length=100)
    prix_mensuel_centimes = serializers.IntegerField(min_value=1)
    prix_annuel_centimes = serializers.IntegerField(min_value=1)
    remise_annuelle_pourcent = serializers.IntegerField(min_value=0, max_value=100)
    # `null` = illimité, comme partout dans le modèle Plan.
    limite_chantiers = serializers.IntegerField(min_value=1, allow_null=True)
    limite_utilisateurs = serializers.IntegerField(min_value=1, allow_null=True)
    limite_stockage_go = serializers.IntegerField(min_value=1)
    avantages = AvantageSerializer(many=True, max_length=20)


class EcritureTarifsSerializer(serializers.Serializer):
    tarifs = TarifPlanEcritureSerializer(many=True, allow_empty=False)

    def validate_tarifs(self, valeur):
        codes = [t["plan_code"] for t in valeur]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("Un forfait ne peut figurer qu'une fois.")
        return valeur


def tarif_public(plan: Plan) -> dict:
    """La forme lue par les pages publiques et par l'écran de réglage."""
    avancees = plan.limites_avancees or {}
    mo = plan.limite_stockage_mo
    return {
        "plan_code": plan.code,
        "libelle": plan.libelle,
        "prix_mensuel_centimes": plan.prix_mensuel_montant,
        "prix_annuel_centimes": plan.prix_annuel_montant or 0,
        "remise_annuelle_pourcent": avancees.get("remise_annuelle_pourcent", 0),
        "limite_chantiers": plan.limite_projets,
        "limite_utilisateurs": plan.limite_utilisateurs,
        "limite_stockage_go": round(mo / 1024) if mo else 0,
        "avantages": avancees.get("avantages", []),
    }
