"""Calculs des durées calendaires et ouvrées des projets."""

import calendar
from datetime import date, timedelta

__all__ = ["decaler_mois", "duree_calendaire"]


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
