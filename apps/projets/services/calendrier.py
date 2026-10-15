"""Règles d'encadrement calendaire entre Projet, Lot et Activité (D1 à D7).

Hiérarchie stricte : Activité <= Lot <= Projet.
Les dates d'un lot doivent s'inscrire dans le calendrier du projet.
Les dates d'une activité doivent s'inscrire dans le calendrier du lot.
"""

from datetime import date

from rest_framework.exceptions import ValidationError

MSG_EXIGER_DATES_PROJET = (
    "Renseignez d'abord les dates de début et de fin du projet : "
    "un lot se cadre dans le calendrier du projet."
)
MSG_EXIGER_DATES_LOT = (
    "Renseignez d'abord les dates de début et de fin du lot : "
    "une activité se cadre dans le calendrier du lot."
)


def formater_date(valeur: date | None) -> str:
    if not valeur:
        return ""
    return valeur.strftime("%d/%m/%Y")


def exiger_dates_projet(projet, champ: str = "non_field_errors") -> None:
    """Règle D1 / D2 : le projet doit posséder date_debut_prevue et date_fin_prevue."""
    if not projet or not projet.date_debut_prevue or not projet.date_fin_prevue:
        raise ValidationError({champ: MSG_EXIGER_DATES_PROJET})


def exiger_dates_lot(lot, champ: str = "non_field_errors") -> None:
    """Règle D3 : le lot doit posséder date_debut_prevue et date_fin_prevue."""
    if not lot or not lot.date_debut_prevue or not lot.date_fin_prevue:
        raise ValidationError({champ: MSG_EXIGER_DATES_LOT})


def verifier_lot_dans_projet(
    projet,
    debut: date | None,
    fin: date | None,
    suffixe: str = "",
) -> None:
    """Règle D4 / D6 : le lot doit s'inscrire dans les dates du projet.

    Si renseignées sur le lot.
    """
    if not projet:
        return
    if debut and projet.date_debut_prevue and debut < projet.date_debut_prevue:
        date_str = formater_date(projet.date_debut_prevue)
        msg = f"Le lot ne peut pas commencer avant le début du projet ({date_str}).{suffixe}"
        raise ValidationError({"date_debut_prevue": msg})
    if fin and projet.date_fin_prevue and fin > projet.date_fin_prevue:
        date_str = formater_date(projet.date_fin_prevue)
        msg = f"Le lot ne peut pas finir après la fin du projet ({date_str}).{suffixe}"
        raise ValidationError({"date_fin_prevue": msg})


def verifier_activite_dans_lot(
    lot,
    debut: date | None,
    fin: date | None,
    suffixe: str = "",
) -> None:
    """Règle D5 / D6 : l'activité doit s'inscrire dans les dates du lot.

    Si renseignées sur l'activité.
    """
    if not lot:
        return
    if debut and lot.date_debut_prevue and debut < lot.date_debut_prevue:
        date_str = formater_date(lot.date_debut_prevue)
        msg = f"L'activité ne peut pas commencer avant le début du lot ({date_str}).{suffixe}"
        raise ValidationError({"date_debut_prevue": msg})
    if fin and lot.date_fin_prevue and fin > lot.date_fin_prevue:
        date_str = formater_date(lot.date_fin_prevue)
        msg = f"L'activité ne peut pas finir après la fin du lot ({date_str}).{suffixe}"
        raise ValidationError({"date_fin_prevue": msg})


def verifier_enfants_contenus(parent, debut_cible: date, fin_cible: date) -> None:
    """Règle D7 : la reprogrammation du parent ne doit pas exclure ses enfants."""
    from apps.projets.models import Lot, Projet

    if isinstance(parent, Projet):
        lot_avant = parent.lots.filter(
            supprime_le__isnull=True,
            date_debut_prevue__lt=debut_cible,
        ).first()
        if lot_avant:
            raise ValidationError(
                {
                    "date_debut_prevue": (
                        f"Le lot {lot_avant.code} sortirait du calendrier du projet : "
                        "reprogrammez-le d'abord."
                    )
                }
            )
        lot_apres = parent.lots.filter(
            supprime_le__isnull=True,
            date_fin_prevue__gt=fin_cible,
        ).first()
        if lot_apres:
            raise ValidationError(
                {
                    "date_fin_prevue": (
                        f"Le lot {lot_apres.code} sortirait du calendrier du projet : "
                        "reprogrammez-le d'abord."
                    )
                }
            )
    elif isinstance(parent, Lot):
        act_avant = parent.activites.filter(
            supprime_le__isnull=True,
            date_debut_prevue__lt=debut_cible,
        ).first()
        if act_avant:
            raise ValidationError(
                {
                    "date_debut_prevue": (
                        f"L'activité {act_avant.libelle} sortirait du calendrier du lot : "
                        "reprogrammez-la d'abord."
                    )
                }
            )
        act_apres = parent.activites.filter(
            supprime_le__isnull=True,
            date_fin_prevue__gt=fin_cible,
        ).first()
        if act_apres:
            raise ValidationError(
                {
                    "date_fin_prevue": (
                        f"L'activité {act_apres.libelle} sortirait du calendrier du lot : "
                        "reprogrammez-la d'abord."
                    )
                }
            )
