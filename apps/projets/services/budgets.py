"""Service de validation et contrôle de cohérence des budgets projet / lot / activité.

Règles (décision 4.4 - US 3.4, 3.9) :
1. Somme des budgets des lots actifs non supprimés d'un projet <= budget du projet.
2. Somme des budgets des activités actives non supprimées d'un lot <= budget du lot.
3. Un parent ne descend pas sous la somme de ses enfants.
4. Un parent sans budget (NULL) ne borne rien ; un enfant sans budget compte pour zéro.
5. Un enfant modifié se compare à (somme des autres enfants + sa nouvelle valeur).
"""

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.core.fields import formater_fcfa


def somme_budgets(qs) -> int:
    """Somme des budgets (centimes) d'un QuerySet de lots ou d'activités ; `NULL` compte zéro."""
    return qs.aggregate(total=Coalesce(Sum("budget_initial_montant"), 0))["total"]


def _verrouiller_projet(projet):
    if projet and getattr(projet, "pk", None) and transaction.get_connection().in_atomic_block:
        from apps.projets.models.projet import Projet

        return Projet.objects.select_for_update().get(pk=projet.pk)
    return projet


def verifier_budget_lot(projet, montant: int | None, *, lot_exclu=None) -> None:
    """Vérifie qu'un budget de lot ne fait pas dépasser le budget du projet."""
    if montant is None or projet is None or projet.budget_initial_montant is None:
        return

    projet = _verrouiller_projet(projet)
    qs = projet.lots.filter(est_actif=True, supprime_le__isnull=True)
    if lot_exclu is not None:
        exclu_id = lot_exclu.pk if hasattr(lot_exclu, "pk") else lot_exclu
        qs = qs.exclude(pk=exclu_id)

    somme_autres = somme_budgets(qs)
    plafond = projet.budget_initial_montant
    disponible = max(0, plafond - somme_autres)

    if somme_autres + montant > plafond:
        raise ValidationError(
            {
                "budget_initial_montant": (
                    f"Le budget des lots dépasserait celui du projet : "
                    f"il reste {formater_fcfa(disponible)} sur un budget projet de "
                    f"{formater_fcfa(plafond)}."
                )
            }
        )


def verifier_budgets_lots_a_creer(projet, montants: list[int | None]) -> None:
    """Vérifie en bloc que l'ajout d'une liste de lots ne fait pas dépasser le budget du projet."""
    if projet is None or projet.budget_initial_montant is None:
        return

    projet = _verrouiller_projet(projet)
    somme_nouveaux = sum(m for m in montants if m is not None)
    qs = projet.lots.filter(est_actif=True, supprime_le__isnull=True)
    somme_existants = somme_budgets(qs)
    plafond = projet.budget_initial_montant
    disponible = max(0, plafond - somme_existants)

    if somme_existants + somme_nouveaux > plafond:
        raise ValidationError(
            {
                "budget_initial_montant": (
                    f"Le budget des lots dépasserait celui du projet : "
                    f"il reste {formater_fcfa(disponible)} sur un budget projet de "
                    f"{formater_fcfa(plafond)}."
                )
            }
        )


def verifier_budget_activite(lot, montant: int | None, *, activite_exclue=None) -> None:
    """Vérifie qu'un budget d'activité ne fait pas dépasser le budget de son lot."""
    if montant is None or lot is None or lot.budget_initial_montant is None:
        return

    if lot.projet:
        _verrouiller_projet(lot.projet)

    qs = lot.activites.filter(est_actif=True, supprime_le__isnull=True)
    if activite_exclue is not None:
        exclu_id = activite_exclue.pk if hasattr(activite_exclue, "pk") else activite_exclue
        qs = qs.exclude(pk=exclu_id)

    somme_autres = somme_budgets(qs)
    plafond = lot.budget_initial_montant
    disponible = max(0, plafond - somme_autres)

    if somme_autres + montant > plafond:
        raise ValidationError(
            {
                "budget_initial_montant": (
                    f"Le budget des activités dépasserait celui du lot : "
                    f"il reste {formater_fcfa(disponible)} sur un budget lot de "
                    f"{formater_fcfa(plafond)}."
                )
            }
        )


def verifier_budget_projet(projet, montant: int | None) -> None:
    """Règle 3 : Un projet ne descend pas sous la somme de ses lots."""
    if montant is None or projet is None or not getattr(projet, "pk", None):
        return

    projet = _verrouiller_projet(projet)
    qs = projet.lots.filter(est_actif=True, supprime_le__isnull=True)
    somme_lots = somme_budgets(qs)

    if montant < somme_lots:
        raise ValidationError(
            {
                "budget_initial_montant": (
                    f"Le budget du projet ne peut pas être inférieur à la somme de ses lots "
                    f"({formater_fcfa(somme_lots)})."
                )
            }
        )


def verifier_budget_parent_lot(lot, montant: int | None) -> None:
    """Règle 3 : Un lot ne descend pas sous la somme de ses activités."""
    if montant is None or lot is None or not getattr(lot, "pk", None):
        return

    qs = lot.activites.filter(est_actif=True, supprime_le__isnull=True)
    somme_activites = somme_budgets(qs)

    if montant < somme_activites:
        raise ValidationError(
            {
                "budget_initial_montant": (
                    f"Le budget du lot ne peut pas être inférieur à la somme de ses activités "
                    f"({formater_fcfa(somme_activites)})."
                )
            }
        )
