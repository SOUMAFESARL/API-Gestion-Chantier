"""Serializers du module « referentiels ».

Référentiels partagés par tous les tenants.
"""

from rest_framework import serializers


class RegleMotDePasseItemSerializer(serializers.Serializer):
    """Règle de validation de complexité mot de passe à exécuter côté frontend."""

    code = serializers.CharField(
        help_text="Code de la règle (LONGUEUR, MAJUSCULE, CHIFFRE, SPECIAL)."
    )
    motif = serializers.CharField(
        help_text="Expression régulière ECMAScript (avec flag u) pour validation temps réel."
    )


class ReglesMotDePasseResponseSerializer(serializers.Serializer):
    """Réponse listant les exigences de complexité du mot de passe."""

    regles = RegleMotDePasseItemSerializer(many=True)


class ItemEnumerationSerializer(serializers.Serializer):
    """Option d'une énumération avec son code machine et son libellé en français."""

    code = serializers.CharField(help_text="Valeur technique stockée en base.")
    libelle = serializers.CharField(help_text="Libellé textuel pour affichage.")


class EnumerationsResponseSerializer(serializers.Serializer):
    """Dictionnaire complet des énumérations produit indexé par nom d'énumération."""

    enumerations = serializers.DictField(
        child=ItemEnumerationSerializer(many=True),
        help_text="Dictionnaire des listes de choix : role_global, statut_projet, statut_bon_paiement, etc.",
        required=False,
    )


__all__ = [
    "EnumerationsResponseSerializer",
    "ItemEnumerationSerializer",
    "RegleMotDePasseItemSerializer",
    "ReglesMotDePasseResponseSerializer",
]
