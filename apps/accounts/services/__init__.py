"""Services du module « accounts ».

Utilisateurs, rôles, invitations, appareils.
"""

from .roles import rattacher_collaborateur_a_role
from .utilisateurs import desactiver_collaborateur_plateforme

__all__ = ["desactiver_collaborateur_plateforme", "rattacher_collaborateur_a_role"]
