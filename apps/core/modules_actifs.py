"""Les modules ouverts à une entreprise — une seule source : le catalogue de la plateforme.

**Le super admin décide seul.** Un module est ouvert à une entreprise si, et seulement si :

1. il est actif et non supprimé dans le catalogue (`CatalogueModule`, table de plateforme) ;
2. le super admin ne l'a pas fermé pour cette entreprise (`EntrepriseModule.est_actif=False`).

*Ce que cela corrige.* Le calcul précédent ajoutait aux modules actifs du catalogue ceux auxquels
l'entreprise était « abonnée » (`EntrepriseModule.est_actif=True`). Or la création d'un module
abonne d'office toutes les entreprises : désactiver ensuite le module dans le catalogue ne le
retirait donc à personne. Il se repliait aussi, à défaut, sur la copie locale `Module` du schéma
de l'entreprise, que rien ne tient à jour. Désormais, aucune copie locale n'entre dans la décision.

« Administration » n'est pas un module qu'on souscrit : il reste toujours ouvert.
"""

import uuid

__all__ = [
    "MODULES_SYSTEME",
    "codes_modules_actifs",
    "resoudre_entreprise",
    "module_ouvert",
]

MODULES_SYSTEME = frozenset({"administration"})


def resoudre_entreprise(entreprise=None):
    """L'entreprise passée (objet ou identifiant), sinon l'entreprise active ; `None` sans elle."""
    from apps.entreprises.models import Entreprise

    if isinstance(entreprise, Entreprise):
        return entreprise
    if isinstance(entreprise, (uuid.UUID, str)) and entreprise:
        return Entreprise.objects.filter(pk=entreprise).first()
    from apps.entreprises.selectors import entreprise_courante as active

    return active()


def codes_modules_actifs(entreprise=None) -> set[str]:
    """Codes (en minuscules) des modules ouverts à l'entreprise, « administration » compris."""
    from apps.catalogue.models import CatalogueModule, EntrepriseModule

    actifs = {
        code.lower()
        for code in CatalogueModule.objects.filter(
            est_actif=True, supprime_le__isnull=True
        ).values_list("code", flat=True)
    }
    if not actifs:
        # Catalogue vide : installation pas encore semée (ses migrations le peuplent). On ouvre
        # les modules du registre plutôt que de fermer tout le produit.
        from apps.core.registre_permissions import REGISTRE

        actifs = {p.module for p in REGISTRE.values()}

    entreprise = resoudre_entreprise(entreprise)
    if entreprise is not None:
        fermes = {
            code.lower()
            for code in EntrepriseModule.objects.filter(
                entreprise=entreprise, est_actif=False, supprime_le__isnull=True
            ).values_list("module__code", flat=True)
        }
        actifs -= fermes

    return actifs | MODULES_SYSTEME


def module_ouvert(code_module: str, entreprise=None) -> bool:
    return (code_module or "").lower() in codes_modules_actifs(entreprise)
