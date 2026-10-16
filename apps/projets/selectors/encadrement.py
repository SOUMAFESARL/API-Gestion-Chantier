"""L'encadrement d'un projet tel que le frontend le lit : chef de projet,
conducteurs de travaux, chefs de chantier.

Le frontend décide qui voit quel chantier — et ce que chacun y peut — d'après
ces trois listes. Le projet ne portait que `chef_projet_id` et
`conducteur_travaux_id` : aucun chef de chantier n'y figurait, si bien qu'un
chef de chantier ne voyait jamais son propre chantier à l'écran, alors que
le serveur le lui renvoyait.

Les chefs de chantier et les conducteurs supplémentaires vivent dans les
affectations ; le chef de projet et le conducteur principal, dans les clés du
projet. Ce module réunit les deux sans requête par ligne de liste.
"""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from apps.core.enums import RoleProjet, StatutUtilisateur
from apps.projets.models import AffectationProjet

#: L'attribut posé par `prefetch_encadrement()` sur chaque projet.
ATTRIBUT_ENCADREMENT = "affectations_encadrement"


def aujourdhui():
    return timezone.localdate(timezone=ZoneInfo(settings.FUSEAU_AFFICHAGE))


def _affectations_vivantes():
    """Les affectations actives de comptes actifs ; la période se juge ensuite."""
    return (
        AffectationProjet.objects.filter(
            est_actif=True,
            utilisateur__supprime_le__isnull=True,
            utilisateur__statut=StatutUtilisateur.ACTIF,
        )
        .select_related("utilisateur")
        .order_by("cree_le", "id")
    )


def prefetch_encadrement() -> Prefetch:
    """À passer à `prefetch_related()` sur toute liste de projets sérialisée."""
    return Prefetch("affectations", queryset=_affectations_vivantes(), to_attr=ATTRIBUT_ENCADREMENT)


def affectations_en_cours(projet) -> list:
    """Les affectations du projet en vigueur aujourd'hui."""
    affectations = getattr(projet, ATTRIBUT_ENCADREMENT, None)
    if affectations is None:
        affectations = list(_affectations_vivantes().filter(projet=projet))
    jour = aujourdhui()
    return [
        a
        for a in affectations
        if (a.date_debut is None or a.date_debut <= jour)
        and (a.date_fin is None or a.date_fin >= jour)
    ]


def conducteurs_travaux(projet) -> list:
    """Le conducteur principal du projet, puis les conducteurs affectés, sans doublon."""
    conducteurs, vus = [], set()
    if projet.conducteur_travaux_id and projet.conducteur_travaux:
        conducteurs.append(projet.conducteur_travaux)
        vus.add(projet.conducteur_travaux_id)
    for affectation in affectations_en_cours(projet):
        role = affectation.role_projet
        if role == RoleProjet.CONDUCTEUR_TRAVAUX and affectation.utilisateur_id not in vus:
            conducteurs.append(affectation.utilisateur)
            vus.add(affectation.utilisateur_id)
    return conducteurs


def chefs_chantier(projet) -> list:
    """Les chefs de chantier affectés au projet, sans doublon."""
    chefs, vus = [], set()
    for affectation in affectations_en_cours(projet):
        role = affectation.role_projet
        if role == RoleProjet.CHEF_CHANTIER and affectation.utilisateur_id not in vus:
            chefs.append(affectation.utilisateur)
            vus.add(affectation.utilisateur_id)
    return chefs


def chef_projet_affectation(projet) -> AffectationProjet | None:
    """L'affectation active de chef de projet en cours aujourd'hui."""
    if not projet.chef_projet_id:
        return None
    for affectation in affectations_en_cours(projet):
        if (
            affectation.role_projet == RoleProjet.CHEF_PROJET
            and affectation.utilisateur_id == projet.chef_projet_id
        ):
            return affectation
    return None


def conducteurs_travaux_avec_affectations(projet) -> list[tuple]:
    """Les conducteurs de travaux du projet avec leur affectation active si présente."""
    resultats = []
    vus = set()
    affectations_ct = {
        aff.utilisateur_id: aff
        for aff in affectations_en_cours(projet)
        if aff.role_projet == RoleProjet.CONDUCTEUR_TRAVAUX
    }
    if projet.conducteur_travaux_id and projet.conducteur_travaux:
        resultats.append(
            (projet.conducteur_travaux, affectations_ct.get(projet.conducteur_travaux_id))
        )
        vus.add(projet.conducteur_travaux_id)
    for user_id, aff in affectations_ct.items():
        if user_id not in vus:
            resultats.append((aff.utilisateur, aff))
            vus.add(user_id)
    return resultats


def chefs_chantier_affectations(projet) -> list[AffectationProjet]:
    """Les affectations actives de chefs de chantier en cours aujourd'hui, sans doublon."""
    chefs, vus = [], set()
    for affectation in affectations_en_cours(projet):
        role = affectation.role_projet
        if role == RoleProjet.CHEF_CHANTIER and affectation.utilisateur_id not in vus:
            chefs.append(affectation)
            vus.add(affectation.utilisateur_id)
    return chefs


def autres_membres_affectations(projet) -> list[AffectationProjet]:
    """Les affectations actives hors CP, CT et CC — VI ou tout autre rôle de portée Projet."""
    encadrement = {
        RoleProjet.CHEF_PROJET,
        RoleProjet.CONDUCTEUR_TRAVAUX,
        RoleProjet.CHEF_CHANTIER,
    }
    membres, vus = [], set()
    for affectation in affectations_en_cours(projet):
        role = affectation.role_projet
        if role not in encadrement and affectation.utilisateur_id not in vus:
            membres.append(affectation)
            vus.add(affectation.utilisateur_id)
    return membres

