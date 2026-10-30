"""Une permission s'exerce dans un périmètre (décisions v1.2, §13bis).

**La règle.** Une personne peut agir sur une case du projet **si le rôle de son affectation à ce
projet a la permission ET si la case est dans son périmètre** — la case elle-même ou l'un de
ses ancêtres. Aucune case dans le périmètre : tout le projet.

- **Le rôle est celui de l'affectation**, pas forcément celui de la plateforme : conducteur de
  travaux ici, chef de chantier là. C'est la correction de la logique précédente, qui lisait
  toujours le rôle de la plateforme, quel que soit le projet.
- **La direction et les rôles de portée Entreprise** ont tout le projet pour périmètre ; leurs
  permissions sont celles de leur rôle sur la plateforme.
- **Une action de niveau projet** (appliquer le tableau de démarrage, insérer un niveau) exige
  tout le projet : un périmètre réduit à une branche ne suffit pas.
- **La lecture suit la même logique** : `projets.voir_tout` donne tout le projet ; sans elle, on
  voit son périmètre et le **chemin** qui y mène (les intitulés des ancêtres, sans leurs données).

Le module doit en outre être ouvert à l'entreprise : `permissions_du_role` ne rend que les
permissions des modules que le super admin laisse ouverts.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.core.droits import a_permission, est_dg, permissions_du_role
from apps.core.permissions import obtenir_portee_role

__all__ = [
    "Perimetre",
    "a_tout_le_projet",
    "exiger",
    "perimetre_de",
    "peut",
]


class Perimetre:
    """Ce qu'une personne peut faire sur un projet, et où.

    `entier` : tout le projet pour ces permissions. `branches` : pour chaque permission, les
    chemins des cases où elle s'exerce.
    """

    def __init__(self):
        self.entier: set[str] = set()
        self.branches: dict[str, list[str]] = {}

    def peut(self, code: str, element=None) -> bool:
        if code in self.entier:
            return True
        if element is None:
            return False
        return any(element.chemin.startswith(c) for c in self.branches.get(code, []))

    def peut_quelque_part(self, code: str) -> bool:
        return code in self.entier or bool(self.branches.get(code))

    def chemins(self, code: str) -> list[str] | None:
        """None : tout le projet. Sinon les chemins des branches (liste vide : rien)."""
        if code in self.entier:
            return None
        return list(self.branches.get(code, []))


def _acces_entreprise(utilisateur) -> bool:
    return bool(
        utilisateur.is_superuser
        or est_dg(utilisateur)
        or obtenir_portee_role(utilisateur) == "ENTREPRISE"
    )


def _affectations_actives(utilisateur, projet):
    from django.db.models import Q

    from apps.projets.models import AffectationProjet

    aujourd_hui = timezone.localdate()
    return (
        AffectationProjet.objects.filter(
            projet=projet, utilisateur=utilisateur, est_actif=True, supprime_le__isnull=True
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=aujourd_hui))
        .prefetch_related("perimetres")
    )


def perimetre_de(utilisateur, projet, request=None) -> Perimetre:
    """Le périmètre d'une personne sur un projet, mis en cache sur la requête."""
    cle = f"_perimetre_{getattr(projet, 'pk', projet)}"
    if request is not None and hasattr(request, cle):
        return getattr(request, cle)

    perimetre = Perimetre()
    if utilisateur and getattr(utilisateur, "is_authenticated", False):
        if _acces_entreprise(utilisateur):
            from apps.core.droits import permissions_effectives

            perimetre.entier = set(permissions_effectives(utilisateur, request=request))
        else:
            from apps.accounts.models import Role

            roles = {}
            for affectation in _affectations_actives(utilisateur, projet):
                code_role = (affectation.role_projet or "").upper()
                if code_role not in roles:
                    role = Role.objects.filter(
                        code__iexact=code_role, supprime_le__isnull=True
                    ).first()
                    roles[code_role] = permissions_du_role(role) if role else set()
                codes = roles[code_role]
                branches = [e.chemin for e in affectation.perimetres.all() if e.supprime_le is None]
                if not branches:
                    perimetre.entier |= codes
                else:
                    for code in codes:
                        perimetre.branches.setdefault(code, []).extend(branches)

    if request is not None:
        setattr(request, cle, perimetre)
    return perimetre


def peut(utilisateur, code: str, projet, element=None, request=None) -> bool:
    """La permission `code` s'exerce-t-elle sur cette case (ou sur tout le projet) ?"""
    return perimetre_de(utilisateur, projet, request).peut(code, element)


def a_tout_le_projet(utilisateur, code: str, projet, request=None) -> bool:
    return perimetre_de(utilisateur, projet, request).peut(code, None)


def exiger(utilisateur, code: str, projet, element=None, request=None) -> None:
    """Lève un 403 explicite quand la permission manque, ou que la case est hors périmètre."""
    perimetre = perimetre_de(utilisateur, projet, request)
    if perimetre.peut(code, element):
        return
    if perimetre.peut_quelque_part(code):
        raise PermissionDenied(
            "Cette case est en dehors de votre périmètre sur ce projet."
            if element is not None
            else "Cette action porte sur tout le projet : votre périmètre ne le couvre pas."
        )
    if not a_permission(utilisateur, "projets.lire", request=request):
        raise PermissionDenied("Vous n'avez pas accès au module des projets.")
    raise PermissionDenied(f"Votre rôle sur ce projet n'a pas la permission « {code} ».")
