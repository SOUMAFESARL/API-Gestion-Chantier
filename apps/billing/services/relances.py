"""Ce qu'une relance d'essai a besoin de savoir — et qui vit dans le schéma client.

Ces deux fonctions **s'exécutent dans le schéma d'une entreprise**, jamais dans
`public` : c'est l'appelant qui a posé le `schema_context`. Elles ne le font pas
elles-mêmes, pour qu'une seule bascule couvre les deux lectures au lieu de deux.
"""

from __future__ import annotations

from apps.core.enums import RoleGlobal, StatutUtilisateur

__all__ = ["bilan_du_schema", "destinataires_relance"]


def bilan_du_schema() -> dict[str, int]:
    """Ce que l'entreprise a construit pendant son essai.

    **C'est ce rappel qui donne sa valeur au message** — parcours §2.3. Un email
    qui dit seulement « votre essai se termine » demande sans rien rappeler ;
    « 2 projets, 14 rapports journaliers, 3 collaborateurs » rappelle ce que le
    client perdrait l'usage de, et c'est la seule chose qu'un concurrent ne peut
    pas copier.
    """
    from apps.accounts.models import Utilisateur
    from apps.chantier.models import RapportJournalier
    from apps.projets.models import Projet

    return {
        "projets": Projet.objects.count(),
        "rapports": RapportJournalier.objects.count(),
        "collaborateurs": Utilisateur.objects.filter(statut=StatutUtilisateur.ACTIF).count(),
    }


def destinataires_relance() -> list[str]:
    """Les adresses à qui écrire : les `AD` actifs et le `DG`, personne d'autre.

    **Un chef de chantier n'a rien à faire d'un email de facturation, et il n'a
    pas les moyens d'y répondre** (parcours §2.2). Lui écrire trois fois en une
    semaine au sujet d'un abonnement qu'il ne décide pas est le meilleur moyen
    de lui apprendre à ignorer les messages du produit — y compris l'alerte du
    soir sur son rapport journalier, qui, elle, le concerne.

    Le badge dans l'en-tête, lui, reste visible de tous : il informe sans
    solliciter.
    """
    from apps.accounts.models import Utilisateur

    adresses = (
        Utilisateur.objects.filter(
            role_global__in=[RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL],
            statut=StatutUtilisateur.ACTIF,
            is_active=True,
        )
        .values_list("email", flat=True)
        .distinct()
    )
    return [a for a in adresses if a]
