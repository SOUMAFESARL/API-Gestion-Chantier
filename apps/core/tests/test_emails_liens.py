"""Les e-mails du produit : liens, expéditeur, texte brut.

Chaque cas décrit une panne que rien ne signalait : l'e-mail partait, le rendu était correct,
et seul le clic — ou la réception — échouait.
"""

import pytest
from django.conf import settings
from django.core import mail
from django.test import override_settings
from django_tenants.utils import schema_context

from apps.accounts.models import Invitation, Utilisateur
from apps.accounts.services.invitations import creer_invitation
from apps.core.emails import adresse_frontend, envoyer
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"


def test_adresse_frontend_retire_la_barre_finale():
    with override_settings(FRONTEND_URL="https://soumafe.com/"):
        assert adresse_frontend() == "https://soumafe.com"


@pytest.mark.django_db
def test_invitation_collaborateur_pointe_vers_le_frontend_configure():
    """Le lien d'invitation était écrit `http://localhost:3000` en dur."""
    with override_settings(FRONTEND_URL="https://soumafe.com"), schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="inviteur.liens@demo.ci").delete()
        inviteur = Utilisateur.objects.create_user(
            email="inviteur.liens@demo.ci",
            password="MotDePasse12345!",
            nom="Inviteur",
            prenom="Liens",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        mail.outbox = []
        invitation = creer_invitation(
            email="nouveau.liens@demo.ci",
            role_propose=RoleGlobal.CHEF_PROJET,
            nom="Nouveau Collaborateur",
            emetteur=inviteur,
            verifier_quota=False,
        )
        try:
            assert invitation.email_envoye is True
            assert len(mail.outbox) == 1
            message = mail.outbox[0]
            assert "https://soumafe.com/invitation#jeton=" in message.body
            assert "localhost" not in message.body
            html = message.alternatives[0][0]
            assert "https://soumafe.com/invitation#jeton=" in html
        finally:
            Invitation.objects.filter(emetteur=inviteur).delete()
            Utilisateur.tous_objets.filter(pk=inviteur.pk).delete()


def test_texte_brut_n_est_pas_echappe_comme_du_html():
    """`L'Entreprise & Fils` arrivait en `L&#x27;Entreprise &amp; Fils` dans le corps texte."""
    mail.outbox = []
    assert envoyer(
        "notification_plateforme",
        "Modification de votre espace",
        "dirigeant@exemple.ci",
        {
            "sujet": "Modification de votre espace",
            "message": "Le module 'Projets' a été activé.",
            "raison_sociale": "L'Entreprise & Fils",
        },
    )
    message = mail.outbox[0]
    assert "L'Entreprise & Fils" in message.body
    assert "&#x27;" not in message.body and "&amp;" not in message.body
    assert "Le module 'Projets' a été activé." in message.body
    # L'expéditeur est celui que la configuration déclare, jamais une adresse écrite dans le code.
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert "plateforme.local" not in message.from_email
    # La version HTML, elle, reste échappée.
    assert "L&#x27;Entreprise &amp; Fils" in message.alternatives[0][0]
