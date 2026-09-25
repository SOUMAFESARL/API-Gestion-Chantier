"""Serializers du module « accounts ».

Utilisateurs, rôles, invitations, appareils.
"""

from .appareil import AppareilSerializer
from .authentification import InscriptionSerializer
from .collaborateur import (
    CollaborateurCreateSerializer,
    CollaborateurResponseSerializer,
    ProjetAssocieCollaborateurSerializer,
    RolePersonnaliseCollaborateurSerializer,
)
from .connexion import (
    ConnexionSerializer,
    DeconnexionSerializer,
    JetonsSerializer,
    ProfilConnexionSerializer,
    RenouvellementSerializer,
)
from .invitation import (
    AccepterInvitationSerializer,
    ContenuInvitationSerializer,
    InvitationSerializer,
    ReponseAccepterInvitationSerializer,
    VerificationInvitationSerializer,
)
from .reinitialisation import (
    ContenuJetonSerializer,
    DemandeReinitialisationSerializer,
    ReinitialisationSerializer,
    VerificationJetonSerializer,
)
from .profil import (
    AvatarReponseSerializer,
    AvatarUploadSerializer,
    ChangerMotDePasseReponseSerializer,
    ChangerMotDePasseSerializer,
    ProfilDetailResponseSerializer,
    ProfilUpdateSerializer,
)
from .role import (
    RoleCreationSerializer,
    RoleDetailSerializer,
    RoleModificationSerializer,
    RoleModulePermissionSerializer,
    RoleSerializer,
    RoleSuppressionSerializer,
)
from .utilisateur import UtilisateurSerializer

__all__ = [
    "AccepterInvitationSerializer",
    "AppareilSerializer",
    "AvatarReponseSerializer",
    "AvatarUploadSerializer",
    "ChangerMotDePasseReponseSerializer",
    "ChangerMotDePasseSerializer",
    "CollaborateurCreateSerializer",
    "CollaborateurResponseSerializer",
    "ConnexionSerializer",
    "ContenuInvitationSerializer",
    "ContenuJetonSerializer",
    "DeconnexionSerializer",
    "DemandeReinitialisationSerializer",
    "InscriptionSerializer",
    "InvitationSerializer",
    "JetonsSerializer",
    "ProfilConnexionSerializer",
    "ProfilDetailResponseSerializer",
    "ProfilUpdateSerializer",
    "ProjetAssocieCollaborateurSerializer",
    "ReinitialisationSerializer",
    "RenouvellementSerializer",
    "ReponseAccepterInvitationSerializer",
    "RoleCreationSerializer",
    "RoleDetailSerializer",
    "RoleModificationSerializer",
    "RoleModulePermissionSerializer",
    "RolePersonnaliseCollaborateurSerializer",
    "RoleSerializer",
    "RoleSuppressionSerializer",
    "UtilisateurSerializer",
    "VerificationInvitationSerializer",
    "VerificationJetonSerializer",
]
