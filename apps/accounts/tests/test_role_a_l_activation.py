"""Le rôle activé est celui de l'invitation — US-013.

*Les deux branches de `accepter_invitation` posaient `RoleGlobal.ADMIN` en dur,
avec le commentaire qui l'avouait : « pour le moment, accès à tous les
modules ». Ce n'était pas un défaut d'affichage — la barre disait vrai. **Toute
personne invitée devenait réellement administratrice de l'entreprise**, quel que
soit le rôle choisi : un conducteur de travaux obtenait la gestion des comptes,
et la matrice de permissions de T-029 devenait décorative.*

Le défaut ne pouvait se voir qu'en regardant le rôle **après** activation :
l'invitation, elle, portait bien le bon code. Aucun test ne franchissait cette
étape.
"""

import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.accounts.services.invitations import accepter_invitation, creer_invitation
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
MOT_DE_PASSE = "MotDePasse1!"

# Un rôle de chantier, un rôle de bureau, un rôle en lecture seule : trois
# familles, pour qu'un correctif qui n'en traiterait qu'une se voie.
ROLES = [
    RoleGlobal.CONDUCTEUR_TRAVAUX,
    RoleGlobal.CHEF_CHANTIER,
    RoleGlobal.RESPONSABLE_FINANCIER,
    RoleGlobal.VISITEUR,
]


@pytest.mark.django_db
@pytest.mark.parametrize("role", ROLES)
def test_le_role_active_est_celui_de_l_invitation(role):
    adresse = f"role.{role.lower()}@exemple.ci"
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email=adresse).delete()

        invitation = creer_invitation(adresse, role, nom="Test Invité")
        accepter_invitation(
            invitation.jeton_clair, nom="Diallo", prenom="Ali", mot_de_passe=MOT_DE_PASSE
        )

        utilisateur = Utilisateur.objects.get(email=adresse)
        assert utilisateur.role_global == role, (
            f"invité comme {role}, activé comme {utilisateur.role_global}"
        )
        assert utilisateur.statut == StatutUtilisateur.ACTIF
        # Une personne invitée n'est jamais le fondateur de l'entreprise.
        assert utilisateur.is_owner is False


@pytest.mark.django_db
def test_une_personne_invitee_ne_devient_pas_administratrice():
    """La formulation inverse du même test — c'est elle qui échouait avant.

    Écrite séparément parce qu'elle dit la conséquence, pas le mécanisme : ce
    qu'il ne faut pas que le produit fasse.
    """
    adresse = "pas.admin@exemple.ci"
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email=adresse).delete()

        invitation = creer_invitation(adresse, RoleGlobal.CHEF_CHANTIER, nom="Terrain")
        accepter_invitation(invitation.jeton_clair, mot_de_passe=MOT_DE_PASSE)

        utilisateur = Utilisateur.objects.get(email=adresse)
        assert utilisateur.role_global != RoleGlobal.ADMIN
        assert utilisateur.is_dg is False, "un chef de chantier ne dirige pas l'entreprise"


@pytest.mark.django_db
def test_le_profil_porte_le_libelle_du_role():
    """La barre d'application lit ce libellé — elle ne le devine plus.

    Elle traduisait le code par une cascade de six comparaisons, pour treize
    rôles : « Responsable Financier » s'y affichait « RF ».
    """
    from apps.accounts.services.authentification import profil_de_connexion

    adresse = "libelle.role@exemple.ci"
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email=adresse).delete()
        utilisateur = Utilisateur.objects.create_user(
            email=adresse,
            password=MOT_DE_PASSE,
            nom="Bah",
            prenom="Fatou",
            role_global=RoleGlobal.RESPONSABLE_FINANCIER,
            statut=StatutUtilisateur.ACTIF,
        )

        profil = profil_de_connexion(utilisateur)
        assert profil["role_global"] == "RF"
        assert profil["role_libelle"] == "Responsable Financier"
