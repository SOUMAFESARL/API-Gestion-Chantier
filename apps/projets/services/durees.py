"""Calculs des durées calendaires et ouvrées des projets."""

import calendar
from datetime import date, timedelta

__all__ = ["ajouter_duree_calendaire", "decaler_mois", "duree_calendaire", "duree_en_jours_approx"]


def decaler_mois(d: date, n: int) -> date:
    """Décale une date de `n` mois.

    Le quantième est ramené au dernier jour du mois cible si nécessaire
    (par ex. 31 janvier + 1 mois -> 28 ou 29 février).
    """
    total_mois = (d.year * 12 + (d.month - 1)) + n
    annee_cible = total_mois // 12
    mois_cible = (total_mois % 12) + 1
    dernier_jour = calendar.monthrange(annee_cible, mois_cible)[1]
    jour_cible = min(d.day, dernier_jour)
    return date(annee_cible, mois_cible, jour_cible)


def ajouter_duree_calendaire(
    debut: date | None,
    *,
    annees: int = 0,
    mois: int = 0,
    jours: int = 0,
) -> date | None:
    """Calcule la date de fin à partir d'un début et d'une durée (années, mois, jours).

    Règle bornes comprises (inverse exact de `duree_calendaire`) :
    - 1er janvier + (1 an, 0 mois, 0 jour) -> 31 décembre.
    - 1er janvier + (0 an, 0 mois, 30 jours) -> 30 janvier.
    - Retourne `None` si `debut` manque ou si la durée totale est nulle.
    - Refuse toute composante négative.
    """
    if debut is None:
        return None
    if annees < 0 or mois < 0 or jours < 0:
        raise ValueError("Les composantes d'une durée contractuelle ne peuvent pas être négatives.")
    if annees == 0 and mois == 0 and jours == 0:
        return None
    total_mois = annees * 12 + mois
    arrivee = decaler_mois(debut, total_mois) + timedelta(days=jours)
    return arrivee - timedelta(days=1)


def duree_en_jours_approx(*, annees: int = 0, mois: int = 0, jours: int = 0) -> int:
    """Conversion indicative en jours pour les cumuls sur cases (`Element.jours_accordes`)."""
    return max(0, annees) * 365 + max(0, mois) * 30 + max(0, jours)


def duree_calendaire(
    debut: date | None,
    fin: date | None,
) -> dict[str, int] | None:
    """Calcule la durée calendaire entre deux dates, bornes comprises.

    Accepte des objets datetime.date ou None.

    Règle (identique à `dureeProjet` côté frontend) :
    - Bornes comprises (du 1er janvier au 31 décembre = 1 an).
    - Ajoute un jour à la date de fin (borne exclue).
    - Compte les mois pleins entre le début et ce lendemain.
    - Un mois « décalé » tombant sur un jour inexistant est ramené
      au dernier jour du mois (calendar.monthrange).
    - Puis compte les jours restants.
    - Le résultat est None si une des deux dates manque ou si la fin précède le début.
    """
    if debut is None or fin is None:
        return None

    if fin < debut:
        return None

    arrivee = fin + timedelta(days=1)
    depart = debut

    mois_pleins = (arrivee.year - depart.year) * 12 + (arrivee.month - depart.month)
    if decaler_mois(depart, mois_pleins) > arrivee:
        mois_pleins -= 1

    date_apres_mois = decaler_mois(depart, mois_pleins)
    jours = (arrivee - date_apres_mois).days

    return {
        "annees": mois_pleins // 12,
        "mois": mois_pleins % 12,
        "jours": jours,
    }
