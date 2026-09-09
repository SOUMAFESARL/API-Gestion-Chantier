"""Validateurs communs — Socle Commun §3.3."""

from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator, MinValueValidator
from django.utils.translation import gettext_lazy as _

# Socle Commun §3.3 : plafond métier de 999 999 999 999 FCFA, exprimé en centimes.
MONTANT_MAX_CENTIMES = 999_999_999_999 * 100

LONGUEUR_MIN_JUSTIFICATION = 30  # RG-11
LONGUEUR_MIN_COMMENTAIRE_REJET = 20  # US-042


def valider_montant(valeur: int) -> None:
    """Un montant est un entier de centimes FCFA, positif et plafonné."""
    if valeur is None:
        return
    if valeur < 0:
        raise ValidationError(_("Le montant ne peut pas être négatif."), code="montant_negatif")
    if valeur > MONTANT_MAX_CENTIMES:
        raise ValidationError(
            _("Le montant dépasse le plafond autorisé de 999 999 999 999 FCFA."),
            code="montant_hors_plafond",
        )


def valider_pourcentage(valeur) -> None:
    """Un pourcentage vit dans [0, 100] — bornes comprises."""
    if valeur is None:
        return
    if not (0 <= valeur <= 100):
        raise ValidationError(
            _("La valeur doit être comprise entre 0 et 100."), code="pourcentage_hors_bornes"
        )


validateur_justification = MinLengthValidator(
    LONGUEUR_MIN_JUSTIFICATION,
    message=_("La justification doit faire au moins 30 caractères."),
)

validateur_commentaire_rejet = MinLengthValidator(
    LONGUEUR_MIN_COMMENTAIRE_REJET,
    message=_("Le commentaire de rejet doit faire au moins 20 caractères."),
)

validateur_quantite_positive = MinValueValidator(
    0, message=_("La quantité ne peut pas être négative.")
)


# ---------------------------------------------------------------------------
# Mots de passe — **défaut D-4**
# ---------------------------------------------------------------------------
# Le Socle §2.1 impose, en *obligatoire*, « au moins 1 majuscule, 1 chiffre,
# 1 caractère spécial ». `AUTH_PASSWORD_VALIDATORS` n'appliquait que la
# longueur : `chantier`, `abidjan2026` et `soumafe!!` étaient tous acceptés,
# pendant que la maquette M6 affichait quatre coches à l'écran — dont trois ne
# correspondaient à aucun contrôle serveur.
#
# *Rien ne le signalait : les réglages étaient là, la suite passait, et l'écart
# ne se voyait qu'en comparant une maquette à un fichier de réglages.*
#
# **Les majuscules accentuées comptent.** `É` est une majuscule et `isupper()`
# le sait ; une comparaison à `A-Z` refuserait `Éburnéa2026!` sans pouvoir
# l'expliquer. Le Socle §1.1 range « accents, cédilles, caractères spéciaux
# africains » parmi les caractères pris en charge.


class ValidateurMajuscule:
    """Au moins une lettre majuscule — Socle §2.1."""

    def validate(self, password, user=None):
        if not any(c.isupper() for c in password):
            raise ValidationError(
                _("Le mot de passe doit contenir au moins une majuscule."),
                code="mot_de_passe_sans_majuscule",
            )

    def get_help_text(self):
        return _("Votre mot de passe doit contenir au moins une majuscule.")


class ValidateurChiffre:
    """Au moins un chiffre — Socle §2.1."""

    def validate(self, password, user=None):
        if not any(c.isdigit() for c in password):
            raise ValidationError(
                _("Le mot de passe doit contenir au moins un chiffre."),
                code="mot_de_passe_sans_chiffre",
            )

    def get_help_text(self):
        return _("Votre mot de passe doit contenir au moins un chiffre.")


class ValidateurCaractereSpecial:
    """Au moins un caractère hors lettres et chiffres — Socle §2.1.

    `isalnum()` plutôt qu'une liste de ponctuation : une liste finie finit
    toujours par oublier un caractère qu'un utilisateur emploie.
    """

    def validate(self, password, user=None):
        if all(c.isalnum() for c in password):
            raise ValidationError(
                _("Le mot de passe doit contenir au moins un caractère spécial."),
                code="mot_de_passe_sans_special",
            )

    def get_help_text(self):
        return _("Votre mot de passe doit contenir au moins un caractère spécial.")
