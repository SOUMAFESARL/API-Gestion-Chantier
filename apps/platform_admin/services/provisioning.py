"""Service d'auto-provisioning de la plateforme.

Ce module a servi au bootstrap initial de la table `journal_plateforme` et du
compte Super Admin `support@ccd-digital.ci` en environnement cPanel.
La base de données de production étant désormais alimentée et opérationnelle,
les migrations automatiques sont désactivées.
"""

from __future__ import annotations


def auto_provisionner_super_admin() -> None:
    """Bootstrap désactivé - la base de données est déjà initialisée."""
    return
