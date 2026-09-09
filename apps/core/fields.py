"""Champs métier — CCD Digital.

Décision D5 : **un montant est un entier de centimes de FCFA**, jamais un
décimal. Ce champ existe pour qu'il soit impossible d'en douter en lisant
un modèle, et pour que le plafond du Socle Commun §3.3 s'applique partout
sans avoir à y penser.
"""

from django.db import models

from .validators import validateur_quantite_positive, valider_montant, valider_pourcentage


class MontantField(models.BigIntegerField):
    """Montant en **centimes de FCFA**.

    875 000 000 FCFA se stocke `87_500_000_000`.
    Le formatage à l'affichage (espaces insécables, abréviations M / Md)
    relève de la couche de présentation, pas du modèle.
    """

    description = "Montant en centimes de FCFA"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("validators", [])
        if valider_montant not in kwargs["validators"]:
            kwargs["validators"] = [*kwargs["validators"], valider_montant]
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        nom, chemin, args, kwargs = super().deconstruct()
        kwargs.pop("validators", None)
        return nom, chemin, args, kwargs


class PourcentageField(models.DecimalField):
    """Pourcentage dans [0, 100], deux décimales — avancement, taux."""

    description = "Pourcentage entre 0 et 100"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("validators", [])
        if valider_pourcentage not in kwargs["validators"]:
            kwargs["validators"] = [*kwargs["validators"], valider_pourcentage]
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        nom, chemin, args, kwargs = super().deconstruct()
        kwargs.pop("validators", None)
        return nom, chemin, args, kwargs


class QuantiteField(models.DecimalField):
    """Quantité métier : trois décimales, suffisant pour les m³ et les tonnes."""

    description = "Quantité (3 décimales)"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 14)
        kwargs.setdefault("decimal_places", 3)
        kwargs.setdefault("validators", [])
        if validateur_quantite_positive not in kwargs["validators"]:
            kwargs["validators"] = [*kwargs["validators"], validateur_quantite_positive]
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        nom, chemin, args, kwargs = super().deconstruct()
        kwargs.pop("validators", None)
        return nom, chemin, args, kwargs
