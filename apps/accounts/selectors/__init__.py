"""Selectors du module « accounts ».

Utilisateurs, rôles, invitations, appareils.
"""

from apps.accounts.models import Appareil, Invitation, Utilisateur


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
