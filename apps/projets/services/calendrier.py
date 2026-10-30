"""Les dates dans l'arbre : le parent encadre, l'enfant peut prolonger (décisions v1.2, §11).

**Vers le bas, le parent encadre.** Les dates d'une case s'inscrivent dans celles de son parent —
du projet jusqu'à la feuille. On ne resserre pas un parent en deçà de l'un de ses enfants.

**Vers le haut, l'enfant peut prolonger.** Si les dates d'une case dépassent celles de son
parent, `prolongations_necessaires` liste les cases (puis le projet) qu'il faudrait élargir, de
proche en proche. L'écran l'affiche ; si l'on confirme, chacune est prolongée — c'est une
reprogrammation, tracée avec le motif de l'enfant. Un parent ne rétrécit jamais tout seul.

Une case ou un projet sans dates n'encadre rien : on ne borne que par ce qui est connu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rest_framework.exceptions import ValidationError

MSG_EXIGER_DATES_PROJET = (
    "Renseignez d'abord les dates de début et de fin du projet : "
    "les cases de son découpage se cadrent dans son calendrier."
)


def formater_date(valeur: date | None) -> str:
    if not valeur:
        return ""
    return valeur.strftime("%d/%m/%Y")


def exiger_dates_projet(projet, champ: str = "non_field_errors") -> None:
    """Règle D1 / D2 : le projet doit posséder date_debut_prevue et date_fin_prevue."""
    if not projet or not projet.date_debut_prevue or not projet.date_fin_prevue:
        raise ValidationError({champ: MSG_EXIGER_DATES_PROJET})


@dataclass
class Prolongation:
    """Une case (ou le projet) à élargir pour qu'un enfant y tienne."""

    cible: object
    est_projet: bool
    debut_avant: date | None
    fin_avant: date | None
    debut_apres: date | None
    fin_apres: date | None

    def en_dict(self) -> dict:
        return {
            "type": "PROJET" if self.est_projet else "ELEMENT",
            "id": str(self.cible.pk),
            "libelle": getattr(self.cible, "nom", None) if self.est_projet else self.cible.libelle,
            "date_debut_avant": self.debut_avant,
            "date_fin_avant": self.fin_avant,
            "date_debut_apres": self.debut_apres,
            "date_fin_apres": self.fin_apres,
        }


def chaine_des_parents(element, arbre=None) -> list:
    """Le parent, le grand-parent… puis le projet, du plus proche au plus lointain."""
    if arbre is not None:
        parents = list(reversed(arbre.ancetres(element)))
    else:
        parents = []
        courant = element.parent
        while courant is not None:
            parents.append(courant)
            courant = courant.parent
    return [*parents, element.projet]


def prolongations_necessaires(element, debut: date | None, fin: date | None, arbre=None) -> list:
    """Les parents à élargir pour que [debut, fin] tienne, de proche en proche jusqu'au projet."""
    from apps.projets.models import Projet

    prolongations: list[Prolongation] = []
    for parent in chaine_des_parents(element, arbre):
        p_debut, p_fin = parent.date_debut_prevue, parent.date_fin_prevue
        nouveau_debut = min(p_debut, debut) if (p_debut and debut) else p_debut
        nouvelle_fin = max(p_fin, fin) if (p_fin and fin) else p_fin
        if nouveau_debut != p_debut or nouvelle_fin != p_fin:
            prolongations.append(
                Prolongation(
                    cible=parent,
                    est_projet=isinstance(parent, Projet),
                    debut_avant=p_debut,
                    fin_avant=p_fin,
                    debut_apres=nouveau_debut,
                    fin_apres=nouvelle_fin,
                )
            )
        # Le parent élargi devient la borne de son propre parent.
        debut = nouveau_debut or debut
        fin = nouvelle_fin or fin
    return prolongations


def verifier_enfants_contenus(parent, debut_cible: date | None, fin_cible: date | None) -> None:
    """Règle D7 : on ne resserre pas un parent (case ou projet) en deçà de l'un de ses enfants."""
    from apps.projets.models import Element, Projet

    if isinstance(parent, Projet):
        enfants = Element.objects.filter(projet=parent, parent__isnull=True, est_actif=True)
        nom_parent = "du projet"
    else:
        enfants = parent.enfants.filter(est_actif=True)
        nom_parent = f"de « {parent.libelle} »"
    if debut_cible:
        avant = (
            enfants.filter(date_debut_prevue__lt=debut_cible).order_by("date_debut_prevue").first()
        )
        if avant:
            raise ValidationError(
                {
                    "date_debut_prevue": (
                        f"« {avant.libelle} » commence le {formater_date(avant.date_debut_prevue)} "
                        f"et sortirait du calendrier {nom_parent} : reprogrammez-la d'abord."
                    )
                }
            )
    if fin_cible:
        apres = enfants.filter(date_fin_prevue__gt=fin_cible).order_by("-date_fin_prevue").first()
        if apres:
            raise ValidationError(
                {
                    "date_fin_prevue": (
                        f"« {apres.libelle} » finit le {formater_date(apres.date_fin_prevue)} "
                        f"et sortirait du calendrier {nom_parent} : reprogrammez-la d'abord."
                    )
                }
            )
