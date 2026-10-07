"""La limite d'utilisateurs du plan — US-013.

*L'exception `QuotaPlanAtteint` existait dans `apps/core/exceptions.py` depuis le
socle, et **n'était levée nulle part**.* Le critère d'acceptation — « limite
utilisateurs atteinte, l'invitation répond 403 avec un appel à changer de
plan » — n'existait donc que dans le document. Une entreprise au plan Starter
pouvait inviter sans fin.

La maquette M7 dessine l'état depuis le Sprint 1 : bandeau « Quota atteint —
20 utilisateurs sur 20 » et bouton d'invitation refusé. Il ne manquait que la
règle derrière.
"""

from __future__ import annotations

from django.db import connection
from django_tenants.utils import get_public_schema_name

__all__ = [
    "limite_du_plan",
    "sieges_occupes",
    "verifier_quota_avant_invitation",
    "limite_projets_du_plan",
    "projets_comptes_quota",
    "verifier_quota_avant_projet",
]


def limite_du_plan(entreprise=None) -> int | None:
    """Le nombre de sièges du plan souscrit. `None` signifie **illimité**.

    `None` n'est pas « zéro » : les confondre ferait du plan Enterprise le plus
    restrictif de tous.
    """
    from apps.billing.models import Abonnement

    if entreprise is None:
        entreprise = _entreprise_courante()
    if entreprise is None:
        return None

    abonnement = (
        Abonnement.objects.filter(entreprise=entreprise)
        .select_related("plan")
        .order_by("-date_debut")
        .first()
    )
    if abonnement is None or abonnement.plan is None:
        return None
    return abonnement.plan.limite_utilisateurs


def sieges_occupes() -> int:
    """Les sièges consommés dans le schéma courant.

    **Une invitation en attente occupe un siège.** Ne compter que les comptes
    créés laisserait une entreprise au plan Starter envoyer trente invitations,
    puis dépasser sa limite au fur et à mesure des activations.
    On exclut les invitations dont l'email correspond déjà à un compte ACTIF ou INVITE
    pour éviter le double comptage de la même personne.
    """
    from apps.accounts.models import Invitation, Utilisateur
    from apps.core.enums import StatutUtilisateur

    comptes_emails = set(
        Utilisateur.objects.filter(
            statut__in=[StatutUtilisateur.ACTIF, StatutUtilisateur.INVITE],
            supprime_le__isnull=True,
        ).values_list("email", flat=True)
    )
    invitations_seules = (
        Invitation.objects.filter(
            statut=Invitation.Statut.ENVOYEE, utilise_le__isnull=True
        )
        .exclude(email__in=comptes_emails)
        .count()
    )
    return len(comptes_emails) + invitations_seules


def verifier_quota_avant_invitation(entreprise=None) -> None:
    """Lève `QuotaPlanAtteint` si un siège de plus dépasserait le plan.

    Appelée **avant** de créer l'invitation : refuser après création laisserait
    une ligne morte en base et un email déjà parti.
    """
    from apps.core.exceptions import QuotaPlanAtteint

    limite = limite_du_plan(entreprise)
    if limite is None:
        return

    occupes = sieges_occupes()
    if occupes >= limite:
        raise QuotaPlanAtteint(
            detail=(
                f"La limite de votre abonnement est atteinte : {occupes} utilisateurs "
                f"sur {limite}. Changez de plan pour inviter davantage de collaborateurs."
            ),
            details={"sieges_occupes": occupes, "limite": limite},
        )


def _entreprise_courante():
    """L'entreprise du schéma courant, ou `None` sur `public`."""
    from apps.tenants.models import Entreprise

    schema = getattr(connection, "schema_name", None)
    if not schema or schema == get_public_schema_name():
        return None
    return Entreprise.objects.filter(schema_name=schema).first()


def limite_projets_du_plan(entreprise=None) -> int | None:
    """La limite de projets du plan souscrit. `None` signifie illimité."""
    from apps.billing.models import Abonnement

    if entreprise is None:
        entreprise = _entreprise_courante()
    if entreprise is None:
        return None

    abonnement = (
        Abonnement.objects.filter(entreprise=entreprise)
        .select_related("plan")
        .order_by("-date_debut")
        .first()
    )
    if abonnement is None or abonnement.plan is None:
        return None
    return abonnement.plan.limite_projets


def projets_comptes_quota() -> int:
    """Les projets comptés dans le quota (hors fin de vie : RESILIE, ARCHIVE, DESACTIVE)."""
    from apps.projets.models import Projet

    statuts_fin_de_vie = {"RESILIE", "ARCHIVE", "DESACTIVE"}
    return (
        Projet.objects.filter(supprime_le__isnull=True)
        .exclude(statut__in=statuts_fin_de_vie)
        .count()
    )


def verifier_quota_avant_projet(entreprise=None) -> None:
    """Lève `QuotaPlanAtteint` si la création d'un projet supplémentaire dépasserait le quota."""
    from apps.core.exceptions import QuotaPlanAtteint

    limite = limite_projets_du_plan(entreprise)
    if limite is None:
        return

    utilises = projets_comptes_quota()
    if utilises >= limite:
        raise QuotaPlanAtteint(
            detail=(
                f"La limite de votre abonnement est atteinte : {utilises} projets "
                f"sur {limite}. Changez de plan pour créer de nouveaux projets."
            ),
            details={
                "ressource": "projets",
                "utilises": utilises,
                "limite": limite,
            },
        )

