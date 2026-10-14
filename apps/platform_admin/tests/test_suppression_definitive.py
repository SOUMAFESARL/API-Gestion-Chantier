"""Suppression définitive d'une entreprise cliente (phase de test du MVP)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from django.db import connection
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme
from apps.platform_admin.services.notifications import SUJET_SUPPRESSION_ENTREPRISE
from apps.tenants.models import Entreprise, RegistreEmail
from apps.tenants.services.sauvegarde_schema import SauvegardeImpossible

HOTE = "localhost"
# `tenant_b` est créé une fois par session (conftest.py). DROP SCHEMA est transactionnel : le retour
# arrière de pytest le restaure après le test, ce qui évite de rejouer les migrations ici.
SCHEMA = "tenant_b"
EMAIL_A = "dirigeant.sup.a@example.com"
MOTIF_VALIDE = "Demande écrite de résiliation reçue le 12/10/2026, accordée."


@pytest.fixture
def client_api():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def faux_sauvegarder(tmp_path, settings, monkeypatch):
    settings.SAUVEGARDES_SUPPRESSION_DIR = str(tmp_path)

    def _faux(entreprise, complement):
        dossier = Path(settings.SAUVEGARDES_SUPPRESSION_DIR)
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"{entreprise.schema_name}_20261014_101500.dump"
        chemin.write_text("dump simulé")
        return chemin

    monkeypatch.setattr(
        "apps.platform_admin.views.suppression.sauvegarder_schema", _faux
    )
    return _faux


def _agent(email, superuser):
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = (
            Utilisateur.objects.create_superuser
            if superuser
            else Utilisateur.objects.create_user
        )
        return fabrique(
            email=email,
            password="MotDePasse12345!",
            nom="Agent",
            prenom="Plateforme",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            **({} if superuser else {"is_staff": True}),
        )


def _entreprise_de_test():
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(schema_name=SCHEMA)
        ent.statut = StatutEntreprise.SUSPENDU
        ent.save(update_fields=["statut"])
        RegistreEmail.objects.get_or_create(email=EMAIL_A, defaults={"entreprise": ent})
        Utilisateur.objects.create_user(
            email=EMAIL_A,
            password="MotDePasse12345!",
            nom="Reste",
            prenom="Public",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
    with schema_context(SCHEMA):
        u = Utilisateur.objects.create_user(
            email=EMAIL_A,
            password="MotDePasse12345!",
            nom="Dirigeant",
            prenom="A",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        u.is_owner = True
        u.save(update_fields=["is_owner", "modifie_le"])
    return ent


def _schema_existe(nom):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s;", [nom]
        )
        return cursor.fetchone() is not None


@pytest.mark.django_db
def test_refus_demo_support_et_interrupteur(client_api, settings):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    with schema_context(get_public_schema_name()):
        demo = Entreprise.objects.get(schema_name="demo")
    url = f"/api/v1/admins/clients/{demo.id}/supprimer-definitivement/"

    client_api.force_authenticate(
        user=_agent("sup.refus.a@ccd-digital.ci", superuser=False)
    )
    assert (
        client_api.post(
            url, {"confirmation": "demo", "motif": MOTIF_VALIDE}, format="json"
        ).status_code
        == 403
    )  # SUPPORT

    client_api.force_authenticate(
        user=_agent("sup.refus.b@ccd-digital.ci", superuser=True)
    )
    reponse = client_api.post(
        url, {"confirmation": "demo", "motif": MOTIF_VALIDE}, format="json"
    )
    assert (
        reponse.status_code == 403
        and reponse.json()["erreur"]["code"] == "entreprise_protegee"
    )
    assert _schema_existe("demo")

    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = False
    apercu = client_api.get(
        f"/api/v1/admins/clients/{demo.id}/suppression/apercu/"
    ).json()
    assert apercu["protegee"] is True and apercu["suppression_activee"] is False


@pytest.mark.django_db
def test_suppression_complete_avec_temoin_et_adresse_liberee(
    client_api, settings, faux_sauvegarder
):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.suppr@ccd-digital.ci", superuser=True)
    )
    ent = _entreprise_de_test()
    with schema_context(get_public_schema_name()):
        demo = Entreprise.objects.get(schema_name="demo")
        registre_demo_avant = RegistreEmail.objects.filter(entreprise=demo).count()
    with schema_context("demo"):
        utilisateurs_demo_avant = Utilisateur.objects.count()

    apercu = client_api.get(
        f"/api/v1/admins/clients/{ent.id}/suppression/apercu/"
    ).json()
    assert EMAIL_A in apercu["adresses"]
    assert any(d["email"] == EMAIL_A for d in apercu["dirigeants"])

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    mauvais = client_api.post(
        url, {"confirmation": "autre", "motif": MOTIF_VALIDE}, format="json"
    )
    assert mauvais.status_code == 400 and _schema_existe(SCHEMA)

    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": MOTIF_VALIDE}, format="json"
    )
    assert reponse.status_code == 200, reponse.content

    # L'entreprise a disparu, partout.
    assert not _schema_existe(SCHEMA)
    with schema_context(get_public_schema_name()):
        assert not Entreprise.objects.filter(schema_name=SCHEMA).exists()
        assert not Entreprise.objects.filter(
            domains__domain="tenant-b.localhost"
        ).exists()
        assert not RegistreEmail.objects.filter(email__iexact=EMAIL_A).exists()
        assert not Utilisateur.tous_objets.filter(email__iexact=EMAIL_A).exists()
        assert JournalPlateforme.objects.filter(
            action="SUPPRESSION_DEFINITIVE_ENTREPRISE"
        ).exists()

        # Le témoin est intact.
        assert Entreprise.objects.filter(schema_name="demo").exists()
        assert RegistreEmail.objects.filter(entreprise=demo).count() == registre_demo_avant
    with schema_context("demo"):
        assert Utilisateur.objects.count() == utilisateurs_demo_avant

    # L'adresse est libre : une autre entreprise peut la reprendre.
    with schema_context(get_public_schema_name()):
        RegistreEmail.objects.create(email=EMAIL_A, entreprise=demo)
        assert RegistreEmail.objects.filter(email__iexact=EMAIL_A).count() == 1


@pytest.mark.django_db
def test_entreprise_active_non_supprimable(client_api, settings, faux_sauvegarder):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.active@ccd-digital.ci", superuser=True)
    )
    ent = _entreprise_de_test()
    with schema_context(get_public_schema_name()):
        ent.statut = StatutEntreprise.ACTIF
        ent.save(update_fields=["statut"])

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": MOTIF_VALIDE}, format="json"
    )
    assert reponse.status_code == 409
    assert reponse.json()["erreur"]["code"] == "entreprise_non_suspendue"
    assert _schema_existe(SCHEMA)


@pytest.mark.django_db
def test_motif_trop_court_refuse(client_api, settings, faux_sauvegarder):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.court@ccd-digital.ci", superuser=True)
    )
    ent = _entreprise_de_test()

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    motif_court = "1234567890123456789"  # 19 caractères
    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": motif_court}, format="json"
    )
    assert reponse.status_code == 400
    assert reponse.json()["erreur"]["code"] == "motif_invalide"
    assert _schema_existe(SCHEMA)


@pytest.mark.django_db
def test_sauvegarde_en_echec_bloque_la_suppression(
    client_api, settings, monkeypatch
):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.echec@ccd-digital.ci", superuser=True)
    )
    ent = _entreprise_de_test()

    def faux_erreur(entreprise, complement):
        raise SauvegardeImpossible("Échec simulé")

    monkeypatch.setattr(
        "apps.platform_admin.views.suppression.sauvegarder_schema", faux_erreur
    )

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": MOTIF_VALIDE}, format="json"
    )
    assert reponse.status_code == 503
    assert reponse.json()["erreur"]["code"] == "sauvegarde_impossible"
    assert _schema_existe(SCHEMA)

    with schema_context(get_public_schema_name()):
        assert not JournalPlateforme.objects.filter(
            action="SUPPRESSION_DEFINITIVE_ENTREPRISE", entreprise_id=ent.id
        ).exists()

    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_suppression_journalise_motif_et_sauvegarde(
    client_api, settings, faux_sauvegarder
):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.journal@ccd-digital.ci", superuser=True)
    )
    ent = _entreprise_de_test()

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": MOTIF_VALIDE}, format="json"
    )
    assert reponse.status_code == 200
    donnees = reponse.json()
    assert "sauvegarde" in donnees

    with schema_context(get_public_schema_name()):
        journal = JournalPlateforme.objects.filter(
            action="SUPPRESSION_DEFINITIVE_ENTREPRISE"
        ).last()
        assert journal is not None
        assert journal.detail["motif"] == MOTIF_VALIDE
        assert journal.detail["sauvegarde"] == donnees["sauvegarde"]


@pytest.mark.django_db
def test_dg_prevenu_avant_suppression_sans_motif(
    client_api, settings, faux_sauvegarder
):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.mail@ccd-digital.ci", superuser=True)
    )
    ent = _entreprise_de_test()

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": MOTIF_VALIDE}, format="json"
    )
    assert reponse.status_code == 200

    courriel = [c for c in mail.outbox if c.subject == SUJET_SUPPRESSION_ENTREPRISE]
    assert len(courriel) == 1
    m = courriel[0]
    assert EMAIL_A in m.to
    assert MOTIF_VALIDE not in m.body


def test_interrupteur_eteint_par_defaut():
    fichier_base = settings.BASE_DIR / "config" / "settings" / "base.py"
    texte = fichier_base.read_text(encoding="utf-8")
    motif = re.compile(
        r'SUPPRESSION_ENTREPRISE_ACTIVEE\s*=\s*config\([^)]*default\s*=\s*False',
        re.MULTILINE,
    )
    assert motif.search(texte), (
        "SUPPRESSION_ENTREPRISE_ACTIVEE doit avoir default=False dans base.py"
    )


@pytest.mark.django_db
def test_apercu_dit_suspendue_et_regles(client_api, settings):
    client_api.force_authenticate(
        user=_agent("sup.apercu@ccd-digital.ci", superuser=True)
    )
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(schema_name=SCHEMA)
        ent.statut = StatutEntreprise.SUSPENDU
        ent.save(update_fields=["statut"])

    url = f"/api/v1/admins/clients/{ent.id}/suppression/apercu/"
    apercu = client_api.get(url).json()

    assert apercu["suspendue"] is True
    assert apercu["motif_longueur_min"] == 20
    assert apercu["sauvegarde_conservee_jours"] == 30


@pytest.mark.django_db
def test_ordre_des_controles(client_api, settings):
    settings.SUPPRESSION_ENTREPRISE_ACTIVEE = True
    client_api.force_authenticate(
        user=_agent("sup.ordre@ccd-digital.ci", superuser=True)
    )
    with schema_context(get_public_schema_name()):
        ent = Entreprise.objects.get(schema_name=SCHEMA)
        ent.statut = StatutEntreprise.ACTIF  # Non suspendue
        ent.save(update_fields=["statut"])

    url = f"/api/v1/admins/clients/{ent.id}/supprimer-definitivement/"
    # Motif trop court ET entreprise active
    reponse = client_api.post(
        url, {"confirmation": SCHEMA, "motif": "trop court"}, format="json"
    )
    # Le contrôle 5 (non suspendue) doit l'emporter sur le contrôle 6 (motif invalide)
    assert reponse.status_code == 409
    assert reponse.json()["erreur"]["code"] == "entreprise_non_suspendue"
