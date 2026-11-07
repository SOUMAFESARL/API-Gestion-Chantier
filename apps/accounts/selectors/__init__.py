"""Selectors du module « accounts ».

Utilisateurs, rôles, invitations, appareils.
"""

from apps.accounts.models import Appareil, Invitation, Utilisateur
from apps.core.contexte import verification_plateforme


def utilisateur_par_email(email):
    """Retourne l'utilisateur actif correspondant a l'adresse email."""
    return Utilisateur.objects.filter(
        email__iexact=email,
    ).first()


def utilisateurs_actifs():
    """Retourne les utilisateurs actuellement actifs"""
    return Utilisateur.objects.filter(
        statut="ACTIF",
        is_active=True,
    )


def invitations_en_attente():
    """Retourne les invitations encore enoyees et non traitees."""
    return Invitation.objects.filter(
        statut=Invitation.Statut.ENVOYEE,
    )


def appareils_utilisateur(utilisateur):
    """Retourne les appareils connus d'un utilisateur."""
    return Appareil.objects.filter(
        utilisateur=utilisateur,
    )


def adresse_prise_sur_la_plateforme(email: str) -> bool:
    """Vrai si un compte vivant porte déjà cette adresse, **dans n'importe quelle entreprise**.

    L'adresse est unique sur toute la plateforme (contrainte `uq_utilisateur_email`, D9) : la
    vérifier dans la seule entreprise active laisserait passer l'adresse d'un collaborateur d'une
    autre entreprise, et l'insertion échouerait sur la contrainte. Ce test d'existence traverse
    donc les entreprises — la RLS comprise, par `verification_plateforme` — et ne rend qu'un
    booléen, jamais un compte. C'est ce que garantissait le registre global des e-mails, retiré
    au lot 5.
    """
    with verification_plateforme(motif="unicité d'une adresse e-mail sur la plateforme"):
        return Utilisateur._base_manager.filter(
            email__iexact=(email or "").strip(), supprime_le__isnull=True
        ).exists()
