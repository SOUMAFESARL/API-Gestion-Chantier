"""Selectors du module « accounts ».

Lectures sur les comptes.
"""

from apps.accounts.models import Utilisateur
from apps.core.contexte import verification_plateforme


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
