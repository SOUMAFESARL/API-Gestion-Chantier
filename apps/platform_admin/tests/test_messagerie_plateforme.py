"""Messagerie de la plateforme : réglage du SMTP par le superviseur et diagnostic d'envoi."""

import smtplib
from unittest import mock

import pytest
from django.conf import settings
from django.core import mail
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.emails import envoyer
from apps.core.email_backend import ConfigurableEmailBackend
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme, ParametresMessagerie
from apps.platform_admin.services import messagerie as service

HOTE = "localhost"
URL = "/api/v1/admins/parametres/messagerie/"
URL_TEST = "/api/v1/admins/parametres/messagerie/tester/"
SECRET = "mdp-application-tres-secret"


@pytest.fixture
def client_api():
    return APIClient(headers={"host": HOTE})


def _agent(email, superuser):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = Utilisateur.objects.create_superuser if superuser else Utilisateur.objects.create_user
        return fabrique(
            email=email,
            password="MotDePasse12345!",
            nom="Agent",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            **({} if superuser else {"is_staff": True}),
        )


@pytest.fixture
def superviseur(client_api):
    client_api.force_authenticate(user=_agent("msg.superviseur@ccd-digital.ci", superuser=True))
    return client_api


def _corps(**changements):
    base = {
        "hote": "smtp.exemple.ci",
        "port": 587,
        "chiffrement": "STARTTLS",
        "identifiant": "envoi@exemple.ci",
        "mot_de_passe": SECRET,
        "expediteur": "CCD Digital <envoi@exemple.ci>",
    }
    base.update(changements)
    return base


def _ligne():
    with schema_context(get_public_schema_name()):
        return ParametresMessagerie.objects.filter(pk=1).first()


@pytest.mark.django_db
def test_support_consulte_mais_ne_modifie_ni_ne_teste(client_api):
    client_api.force_authenticate(user=_agent("msg.support@ccd-digital.ci", superuser=False))
    lecture = client_api.get(URL)
    assert lecture.status_code == 200
    assert lecture.json()["effectif"]["source"] == "serveur"
    assert lecture.json()["saisi"]["mot_de_passe_defini"] is False

    assert client_api.patch(URL, _corps(), format="json").status_code == 403
    assert client_api.delete(URL).status_code == 403
    assert client_api.post(URL_TEST, {"destinataire": "a@exemple.ci"}, format="json").status_code == 403
    assert _ligne() is None


@pytest.mark.django_db
def test_enregistrement_chiffre_le_mot_de_passe_et_ne_le_renvoie_jamais(superviseur):
    reponse = superviseur.patch(URL, _corps(), format="json")
    assert reponse.status_code == 200, reponse.content
    assert SECRET not in reponse.content.decode()

    ligne = _ligne()
    assert ligne.mot_de_passe_chiffre.startswith("v1:")
    assert SECRET not in ligne.mot_de_passe_chiffre
    assert service.dechiffrer(ligne.mot_de_passe_chiffre) == SECRET

    lecture = superviseur.get(URL).json()
    assert SECRET not in str(lecture)
    assert lecture["saisi"]["mot_de_passe_defini"] is True
    assert lecture["effectif"]["source"] == "application"
    assert lecture["effectif"]["hote"] == "smtp.exemple.ci"

    with schema_context(get_public_schema_name()):
        journal = JournalPlateforme.objects.filter(action="MODIFICATION_MESSAGERIE").last()
    assert journal is not None and SECRET not in str(journal.detail)


@pytest.mark.django_db
def test_mot_de_passe_requis_la_premiere_fois_puis_conserve(superviseur):
    sans_mdp = superviseur.patch(URL, _corps(mot_de_passe=""), format="json")
    assert sans_mdp.status_code == 400
    assert _ligne() is None

    assert superviseur.patch(URL, _corps(), format="json").status_code == 200
    avant = _ligne().mot_de_passe_chiffre
    # Changer le port sans ressaisir le mot de passe : il est conservé.
    assert superviseur.patch(URL, _corps(port=465, chiffrement="SSL", mot_de_passe=""), format="json").status_code == 200
    ligne = _ligne()
    assert ligne.mot_de_passe_chiffre == avant and ligne.port == 465


def test_chiffrement_est_authentifie_et_aleatoire():
    a, b = service.chiffrer(SECRET), service.chiffrer(SECRET)
    assert a != b
    assert service.dechiffrer(a) == service.dechiffrer(b) == SECRET
    # Une valeur altérée, tronquée ou étrangère est refusée, jamais « déchiffrée » en bruit.
    altere = a[:-4] + ("AAAA" if not a.endswith("AAAA") else "BBBB")
    assert service.dechiffrer(altere) is None
    assert service.dechiffrer("v1:court") is None
    assert service.dechiffrer("") is None and service.dechiffrer("clair") is None


@pytest.mark.django_db
def test_le_backend_smtp_utilise_le_reglage_saisi_puis_retombe_sur_le_env(superviseur):
    assert ConfigurableEmailBackend().host == settings.EMAIL_HOST

    superviseur.patch(URL, _corps(port=2525), format="json")
    backend = ConfigurableEmailBackend()
    assert (backend.host, backend.port, backend.username, backend.password) == (
        "smtp.exemple.ci", 2525, "envoi@exemple.ci", SECRET,
    )
    assert backend.use_tls is True and backend.use_ssl is False

    superviseur.delete(URL)
    assert _ligne() is None
    assert ConfigurableEmailBackend().host == settings.EMAIL_HOST


@pytest.mark.django_db
def test_mot_de_passe_illisible_retombe_sur_le_env(superviseur):
    superviseur.patch(URL, _corps(), format="json")
    with schema_context(get_public_schema_name()):
        ParametresMessagerie.objects.filter(pk=1).update(mot_de_passe_chiffre="v1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert service.configuration_base() is None
    assert ConfigurableEmailBackend().host == settings.EMAIL_HOST


@pytest.mark.django_db
def test_les_emails_partent_de_l_expediteur_saisi(superviseur):
    superviseur.patch(URL, _corps(expediteur="Soumafe <envoi@exemple.ci>"), format="json")
    mail.outbox = []
    assert envoyer(
        "notification_plateforme", "Sujet", "dest@exemple.ci",
        {"sujet": "Sujet", "message": "Bonjour", "raison_sociale": "ACME"},
    )
    assert mail.outbox[0].from_email == "Soumafe <envoi@exemple.ci>"


@pytest.mark.django_db
def test_diagnostic_reussi_envoie_le_message_de_test(superviseur):
    mail.outbox = []
    reponse = superviseur.post(URL_TEST, {"destinataire": "durel@exemple.ci"}, format="json")
    assert reponse.status_code == 200
    assert reponse.json()["succes"] is True
    assert [m.to for m in mail.outbox] == [["durel@exemple.ci"]]
    assert JournalPlateforme.objects.filter(action="TEST_MESSAGERIE").exists()


@pytest.mark.django_db
def test_diagnostic_en_echec_dit_l_etape_le_conseil_et_masque_le_mot_de_passe(superviseur):
    superviseur.patch(URL, _corps(), format="json")

    class _Connexion:
        def open(self):
            raise smtplib.SMTPAuthenticationError(535, f"Refus pour {SECRET}".encode())

        def close(self):
            pass

    with mock.patch.object(service, "get_connection", return_value=_Connexion()):
        reponse = superviseur.post(URL_TEST, {"destinataire": "durel@exemple.ci"}, format="json")

    corps = reponse.json()
    assert reponse.status_code == 200
    assert corps["succes"] is False and corps["etape"] == "connexion"
    assert "mot de passe d'application" in corps["conseil"]
    assert SECRET not in reponse.content.decode()
    assert "SMTPAuthenticationError" in corps["erreur"]


def test_sonde_dit_l_etape_qui_casse():
    # Le port ne répond pas : l'étape est « tcp », pas un vague « connexion coupée ».
    with mock.patch.object(service.socket, "create_connection", side_effect=ConnectionRefusedError("refusé")):
        sonde = service.sonder_connexion("smtp.exemple.ci", 587, "STARTTLS")
    assert sonde["ok"] is False and sonde["etape"] == "tcp"

    # Le port répond mais le serveur raccroche avant de dire bonjour.
    with mock.patch.object(service.socket, "create_connection"), mock.patch.object(
        service.smtplib, "SMTP", side_effect=smtplib.SMTPServerDisconnected("coupée")
    ):
        sonde = service.sonder_connexion("smtp.exemple.ci", 587, "STARTTLS")
    assert sonde["ok"] is False and sonde["etape"] == "banniere"
    assert "SMTPServerDisconnected" in sonde["detail"]


@pytest.mark.django_db
def test_diagnostic_propose_le_port_qui_passe(superviseur):
    superviseur.patch(URL, _corps(), format="json")

    class _Connexion:
        def open(self):
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

        def close(self):
            pass

    def _sonde(hote, port, chiffrement, *args, **kwargs):
        if port == 465:
            return {"ok": True, "etape": None, "detail": None}
        return {"ok": False, "etape": "banniere", "detail": "coupée"}

    with mock.patch.object(service, "get_connection", return_value=_Connexion()), mock.patch.object(
        service, "sonder_connexion", side_effect=_sonde
    ):
        corps = superviseur.post(URL_TEST, {"destinataire": "durel@exemple.ci"}, format="json").json()

    assert corps["succes"] is False and corps["sonde"]["etape"] == "banniere"
    assert [a["port"] for a in corps["alternatives"]] == [465]
    assert "465" in corps["conseil"] and "SSL" in corps["conseil"]
