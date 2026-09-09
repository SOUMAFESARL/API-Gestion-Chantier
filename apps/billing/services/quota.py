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

__all__ = ["limite_du_plan", "sieges_occupes", "verifier_quota_avant_invitation"]


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
    puis dépasser sa limite au fur et à mesure des activations — c'est-à-dire
    trop tard pour le dire, et sans personne à qui le dire.
    """
    from apps.accounts.models import Invitation, Utilisateur
    from apps.core.enums import StatutUtilisateur

    comptes = Utilisateur.objects.filter(
        statut__in=[StatutUtilisateur.ACTIF, StatutUtilisateur.INVITE]
    ).count()
    invitations = Invitation.objects.filter(
        statut=Invitation.Statut.ENVOYEE, utilise_le__isnull=True
    ).count()
    return comptes + invitations


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
