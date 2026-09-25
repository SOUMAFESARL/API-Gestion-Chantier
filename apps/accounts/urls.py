from django.urls import path

from apps.accounts.views import (
    ConnexionView,
    DeconnexionView,
    DemandeReinitialisationView,
    InvitationAccepterView,
    InvitationListCreateView,
    InvitationVerifierView,
    ParametresCollaborateurListCreateView,
    ParametresRoleDetailUpdateView,
    ParametresRoleListCreateView,
    ParametresRoleSupprimerReassignerView,
    ReinitialisationView,
    AvatarProfilView,
    ChangerMotDePasseView,
    ProfilView,
    RenouvellementView,
    RoleDetailUpdateView,
    RoleListCreateView,
    RoleSupprimerReassignerView,
    VerificationJetonView,
    VerifierAccesSuperAdminView,
)

app_name = "accounts"

urlpatterns = [
    path("admins/verifier-acces/", VerifierAccesSuperAdminView.as_view(), name="admins-verifier-acces"),
    path("super-admin/verifier-acces/", VerifierAccesSuperAdminView.as_view(), name="super-admin-verifier-acces"),
    path("auth/token/", ConnexionView.as_view(), name="connexion"),
    path("auth/token/refresh/", RenouvellementView.as_view(), name="jeton-renouveler"),
    path("auth/deconnexion/", DeconnexionView.as_view(), name="deconnexion"),
    path("auth/profil/", ProfilView.as_view(), name="auth-profil"),
    path("auth/profil/mot-de-passe/", ChangerMotDePasseView.as_view(), name="auth-profil-mot-de-passe"),
    path("auth/profil/avatar/", AvatarProfilView.as_view(), name="auth-profil-avatar"),
    path("utilisateurs/moi/", ProfilView.as_view(), name="utilisateur-moi"),
    path("invitations/", InvitationListCreateView.as_view(), name="invitations-liste-creer"),
    path("invitations/verifier/", InvitationVerifierView.as_view(), name="invitation-verifier"),
    path("invitations/accepter/", InvitationAccepterView.as_view(), name="invitation-accepter"),
    # Collaborateurs — Paramètres (/api/v1/parametres/collaborateurs/)
    path(
        "parametres/collaborateurs/",
        ParametresCollaborateurListCreateView.as_view(),
        name="parametres-collaborateurs-liste-creer",
    ),
    # Rôles et habilitations par module — Paramètres (/api/v1/parametres/roles/)
    path("parametres/roles/", ParametresRoleListCreateView.as_view(), name="parametres-roles-liste-creer"),
    path("parametres/roles/<uuid:pk>/", ParametresRoleDetailUpdateView.as_view(), name="parametres-role-detail-modifier"),
    path(
        "parametres/roles/<uuid:pk>/supprimer/",
        ParametresRoleSupprimerReassignerView.as_view(),
        name="parametres-role-supprimer-reassigner",
    ),
    # Rôles — Routes directes (rétrocompatibilité)
    path("roles/", RoleListCreateView.as_view(), name="roles-liste-creer"),
    path("roles/<uuid:pk>/", RoleDetailUpdateView.as_view(), name="role-detail-modifier"),
    path(
        "roles/<uuid:pk>/supprimer/",
        RoleSupprimerReassignerView.as_view(),
        name="role-supprimer-reassigner",
    ),
    # Réinitialisation du mot de passe — les trois portes d'un seul couloir.
    path(
        "auth/mot-de-passe/demande/",
        DemandeReinitialisationView.as_view(),
        name="mot-de-passe-demande",
    ),
    path(
        "auth/mot-de-passe/verifier/",
        VerificationJetonView.as_view(),
        name="mot-de-passe-verifier",
    ),
    path(
        "auth/mot-de-passe/reinitialiser/",
        ReinitialisationView.as_view(),
        name="mot-de-passe-reinitialiser",
    ),
]
