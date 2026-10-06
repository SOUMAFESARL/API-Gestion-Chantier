"""Purge récursive des clés de montants financiers (Règle E-11, filet générique P-5)."""

import re

from rest_framework import serializers

__all__ = ["MOTIF_MONTANT", "purger_montants_recursif", "valider_ecriture_montant"]

MOTIF_MONTANT = re.compile(r"(montant|budget|cout|prix)", re.IGNORECASE)


def purger_montants_recursif(obj):
    """Retire récursivement toute clé évoquant une valeur financière ou budgétaire."""
    if isinstance(obj, dict):
        return {
            k: purger_montants_recursif(v)
            for k, v in obj.items()
            if not MOTIF_MONTANT.search(k)
        }
    elif isinstance(obj, list):
        return [purger_montants_recursif(x) for x in obj]
    return obj


def valider_ecriture_montant(valeur, request=None, champ="budget_initial_montant"):
    """Règle E-11 : vérifie que l'utilisateur a le droit d'écrire un montant non-nul."""
    if valeur is not None:
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(user, request):
            raise serializers.ValidationError("Champ non accepté sans la permission projets.voir_montants.")
    return valeur

