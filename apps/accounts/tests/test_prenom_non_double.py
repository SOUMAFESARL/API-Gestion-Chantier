"""« Awa Awa Traoré » : l'activation ne doit pas recopier le nom complet de l'invitation.

`invitation.nom` porte « prénom nom » ; l'activation l'écrivait dans `utilisateur.nom`
alors que le prénom était déjà rangé à part, et l'affichage prénom + nom doublait le prénom.
"""

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.accounts.services.invitations import accepter_invitation, creer_invitation
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
ADRESSE = "awa.traore@exemple.ci"


@pytest.mark.django_db
def test_activation_garde_nom_et_prenom_saisis_a_l_ajout():
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email=ADRESSE).delete()
        collaborateur = Utilisateur(
            email=ADRESSE,
            nom="Traoré",
            prenom="Awa",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.INVITE,
        )
        collaborateur.set_unusable_password()
        collaborateur.save()

        invitation = creer_invitation(ADRESSE, RoleGlobal.CHEF_CHANTIER, nom="Awa Traoré")
        accepter_invitation(invitation.jeton_clair, mot_de_passe="MotDePasse1!")

        collaborateur.refresh_from_db()
        assert collaborateur.prenom == "Awa"
        assert collaborateur.nom == "Traoré"
        assert collaborateur.nom_complet == "Awa Traoré"
