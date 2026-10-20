"""Tests d'intégration API pour le calendrier d'entreprise (SFD F3 §6 & Erratum E-4)."""

from __future__ import annotations

from datetime import date

import pytest
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.roles import initialiser_roles_par_defaut
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal
from apps.projets.models.calendrier import ExceptionCalendrier
from apps.referentiels.models import JourFerie

HOTE = "demo.localhost"


@pytest.fixture
def setup_utilisateurs(schema_demo):
    """Initialise les rôles par défaut et quatre utilisateurs pour les tests."""
    initialiser_roles_par_defaut()
    role_dg = Role.objects.filter(code=RoleGlobal.DIRECTEUR_GENERAL).first()
    role_ad = Role.objects.filter(code=RoleGlobal.ADMIN).first()
    role_cp = Role.objects.filter(code=RoleGlobal.CHEF_PROJET).first()
    role_ct = Role.objects.filter(code=RoleGlobal.CONDUCTEUR_TRAVAUX).first()

    dg = Utilisateur.objects.create_user(
        email="dg_cal@demo.ci",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        role=role_dg,
        nom="DG",
        prenom="Directeur",
    )
    ad = Utilisateur.objects.create_user(
        email="ad_cal@demo.ci",
        role_global=RoleGlobal.ADMIN,
        role=role_ad,
        nom="AD",
        prenom="Admin",
    )
    cp = Utilisateur.objects.create_user(
        email="cp_cal@demo.ci",
        role_global=RoleGlobal.CHEF_PROJET,
        role=role_cp,
        nom="CP",
        prenom="ChefProjet",
    )
    ct = Utilisateur.objects.create_user(
        email="ct_cal@demo.ci",
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
        role=role_ct,
        nom="CT",
        prenom="Conducteur",
    )
    return {"dg": dg, "ad": ad, "cp": cp, "ct": ct}


@pytest.mark.django_db
def test_lecture_calendrier_par_ct(setup_utilisateurs):
    """La consultation du calendrier est ouverte à tout utilisateur (ex. CT)."""
    ct = setup_utilisateurs["ct"]
    client = APIClient()
    client.force_authenticate(user=ct)

    rep = client.get("/api/v1/calendrier/", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK

    data = rep.json()
    assert "semaine_type" in data
    assert "feries_nationaux" in data
    assert "exceptions" in data

    semaine = data["semaine_type"]
    assert semaine["lundi"] is True
    assert semaine["mardi"] is True
    assert semaine["mercredi"] is True
    assert semaine["jeudi"] is True
    assert semaine["vendredi"] is True
    assert semaine["samedi"] is False
    assert semaine["dimanche"] is False

    assert isinstance(data["feries_nationaux"], list)
    assert isinstance(data["exceptions"], list)


@pytest.mark.django_db
def test_ecriture_par_dg_et_ad(setup_utilisateurs):
    """Le DG et l'AD ont le droit de modifier la semaine type et de créer des exceptions."""
    dg = setup_utilisateurs["dg"]
    ad = setup_utilisateurs["ad"]
    client = APIClient()

    # 1. DG modifie la semaine type (200)
    client.force_authenticate(user=dg)
    rep_patch_dg = client.patch(
        "/api/v1/calendrier/semaine-type/",
        {"samedi": True},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_patch_dg.status_code == status.HTTP_200_OK
    assert rep_patch_dg.json()["samedi"] is True

    # 2. DG crée une exception (201)
    rep_post_dg = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-06-01", "ouvre": False, "motif": "Fermeture pont de la Pentecôte"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_post_dg.status_code == status.HTTP_201_CREATED
    assert rep_post_dg.json()["date"] == "2026-06-01"
    assert rep_post_dg.json()["ouvre"] is False
    assert rep_post_dg.json()["motif"] == "Fermeture pont de la Pentecôte"

    # 3. AD modifie la semaine type (200)
    client.force_authenticate(user=ad)
    rep_patch_ad = client.patch(
        "/api/v1/calendrier/semaine-type/",
        {"samedi": False},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_patch_ad.status_code == status.HTTP_200_OK
    assert rep_patch_ad.json()["samedi"] is False

    # 4. AD crée une exception (201)
    rep_post_ad = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-06-02", "ouvre": True, "motif": "Rattrapage chantier exceptionnel"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_post_ad.status_code == status.HTTP_201_CREATED
    assert rep_post_ad.json()["date"] == "2026-06-02"
    assert rep_post_ad.json()["ouvre"] is True


@pytest.mark.django_db
def test_ecriture_refusee_pour_cp(setup_utilisateurs):
    """Un CP ne possède pas administration.calendrier_gerer : écritures refusées en 403."""
    dg = setup_utilisateurs["dg"]
    cp = setup_utilisateurs["cp"]
    client = APIClient()

    # Créer au préalable une exception avec le DG
    client.force_authenticate(user=dg)
    rep_post = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-07-01", "ouvre": False, "motif": "Exception initiale DG"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_post.status_code == status.HTTP_201_CREATED
    exc_id = rep_post.json()["id"]

    # Authentifier en tant que CP
    client.force_authenticate(user=cp)

    # 1. Tentative PATCH semaine type -> 403
    rep_patch = client.patch(
        "/api/v1/calendrier/semaine-type/",
        {"samedi": True},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_patch.status_code == status.HTTP_403_FORBIDDEN
    assert rep_patch.json()["erreur"]["code"] == "acces_refuse"

    # 2. Tentative POST exception -> 403
    rep_post_cp = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-07-02", "ouvre": True, "motif": "Tentative CP"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_post_cp.status_code == status.HTTP_403_FORBIDDEN
    assert rep_post_cp.json()["erreur"]["code"] == "acces_refuse"

    # 3. Tentative DELETE exception -> 403
    rep_del_cp = client.delete(
        f"/api/v1/calendrier/exceptions/{exc_id}/",
        HTTP_HOST=HOTE,
    )
    assert rep_del_cp.status_code == status.HTTP_403_FORBIDDEN
    assert rep_del_cp.json()["erreur"]["code"] == "acces_refuse"


@pytest.mark.django_db
def test_semaine_vide_refusee_422(setup_utilisateurs):
    """Une semaine type sans aucun jour travaillé est refusée avec ErreurMetier (422)."""
    dg = setup_utilisateurs["dg"]
    client = APIClient()
    client.force_authenticate(user=dg)

    rep = client.patch(
        "/api/v1/calendrier/semaine-type/",
        {
            "lundi": False,
            "mardi": False,
            "mercredi": False,
            "jeudi": False,
            "vendredi": False,
            "samedi": False,
            "dimanche": False,
        },
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = rep.json()
    assert data["erreur"]["code"] == "regle_metier"
    assert (
        data["erreur"]["message"]
        == "La semaine type doit comporter au moins un jour travaillé."
    )


@pytest.mark.django_db
def test_exception_double_refusee_409(setup_utilisateurs):
    """Une exception active sur la même date est refusée avec le statut 409 (ErreurConflit)."""
    dg = setup_utilisateurs["dg"]
    client = APIClient()
    client.force_authenticate(user=dg)

    # Première création -> 201
    rep1 = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-08-15", "ouvre": False, "motif": "Assomption chômée"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep1.status_code == status.HTTP_201_CREATED

    # Deuxième création sur la même date -> 409
    rep2 = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-08-15", "ouvre": True, "motif": "Assomption travaillée"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep2.status_code == status.HTTP_409_CONFLICT
    assert rep2.json()["erreur"]["code"] == "conflit"


@pytest.mark.django_db
def test_suppression_logique_exception(setup_utilisateurs):
    """DELETE /api/v1/calendrier/exceptions/{id}/ effectue une suppression logique pure."""
    dg = setup_utilisateurs["dg"]
    client = APIClient()
    client.force_authenticate(user=dg)

    # Création de l'exception
    rep_create = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-09-01", "ouvre": False, "motif": "Fermeture rentrée"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_create.status_code == status.HTTP_201_CREATED
    exc_id = rep_create.json()["id"]

    # Suppression logique via l'API
    rep_del = client.delete(f"/api/v1/calendrier/exceptions/{exc_id}/", HTTP_HOST=HOTE)
    assert rep_del.status_code == status.HTTP_204_NO_CONTENT

    # Vérification base : invisible pour objects (ManagerActif), visible pour tous_objets
    assert not ExceptionCalendrier.objects.filter(pk=exc_id).exists()
    assert ExceptionCalendrier.tous_objets.filter(pk=exc_id).exists()

    instance = ExceptionCalendrier.tous_objets.get(pk=exc_id)
    assert instance.est_supprime is True
    assert instance.supprime_le is not None
    assert instance.supprime_par == dg

    # Après suppression logique, la création d'une nouvelle exception sur la même date réussit
    rep_recreate = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-09-01", "ouvre": True, "motif": "Rentrée finalement travaillée"},
        format="json",
        HTTP_HOST=HOTE,
    )
    assert rep_recreate.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_periode_trop_longue_400(setup_utilisateurs):
    """Une période de plus de 366 jours ou avec fin < debut renvoie 400 Bad Request."""
    ct = setup_utilisateurs["ct"]
    client = APIClient()
    client.force_authenticate(user=ct)

    # 1. Période supérieure à 366 jours (du 2025-01-01 au 2026-01-03 -> 368 jours) -> 400
    rep_trop_long = client.get(
        "/api/v1/calendrier/?debut=2025-01-01&fin=2026-01-03",
        HTTP_HOST=HOTE,
    )
    assert rep_trop_long.status_code == status.HTTP_400_BAD_REQUEST
    assert rep_trop_long.json()["erreur"]["code"] == "validation"

    # 2. Date de fin antérieure à la date de début -> 400
    rep_inverse = client.get(
        "/api/v1/calendrier/?debut=2026-05-10&fin=2026-05-01",
        HTTP_HOST=HOTE,
    )
    assert rep_inverse.status_code == status.HTTP_400_BAD_REQUEST
    assert rep_inverse.json()["erreur"]["code"] == "validation"


@pytest.mark.django_db
def test_trace_audit_ecritures(setup_utilisateurs):
    """Toute écriture sur le calendrier est journalisée dans l'audit avec IP et appareil."""
    dg = setup_utilisateurs["dg"]
    client = APIClient()
    client.force_authenticate(user=dg)

    navigateur_test = "Mozilla/5.0 TestBrowser/1.0"
    ip_test = "203.0.113.7"

    # 1. Modification semaine type
    rep1 = client.patch(
        "/api/v1/calendrier/semaine-type/",
        {"samedi": True},
        format="json",
        HTTP_HOST=HOTE,
        HTTP_USER_AGENT=navigateur_test,
        REMOTE_ADDR=ip_test,
    )
    assert rep1.status_code == status.HTTP_200_OK

    journal_semaine = JournalAudit.objects.filter(
        type_entite="semaine_type",
        action=ActionAudit.MODIFICATION,
    ).order_by("-id").first()
    assert journal_semaine is not None
    assert journal_semaine.utilisateur_id == dg.pk
    assert journal_semaine.appareil == navigateur_test
    assert journal_semaine.adresse_ip == ip_test
    assert journal_semaine.valeur_apres["samedi"] is True

    # 2. Création d'exception
    rep2 = client.post(
        "/api/v1/calendrier/exceptions/",
        {"date": "2026-11-15", "ouvre": True, "motif": "Journée de la Paix travaillée"},
        format="json",
        HTTP_HOST=HOTE,
        HTTP_USER_AGENT=navigateur_test,
        REMOTE_ADDR=ip_test,
    )
    assert rep2.status_code == status.HTTP_201_CREATED
    exc_id = rep2.json()["id"]

    journal_creation = JournalAudit.objects.filter(
        type_entite="exception_calendrier",
        action=ActionAudit.CREATION,
        entite_id=exc_id,
    ).order_by("-id").first()
    assert journal_creation is not None
    assert journal_creation.utilisateur_id == dg.pk
    assert journal_creation.appareil == navigateur_test
    assert journal_creation.adresse_ip == ip_test
    assert journal_creation.valeur_apres["date"] == "2026-11-15"
    assert journal_creation.valeur_apres["ouvre"] is True

    # 3. Suppression d'exception
    rep3 = client.delete(
        f"/api/v1/calendrier/exceptions/{exc_id}/",
        HTTP_HOST=HOTE,
        HTTP_USER_AGENT=navigateur_test,
        REMOTE_ADDR=ip_test,
    )
    assert rep3.status_code == status.HTTP_204_NO_CONTENT

    journal_suppression = JournalAudit.objects.filter(
        type_entite="exception_calendrier",
        action=ActionAudit.SUPPRESSION,
        entite_id=exc_id,
    ).order_by("-id").first()
    assert journal_suppression is not None
    assert journal_suppression.utilisateur_id == dg.pk
    assert journal_suppression.appareil == navigateur_test
    assert journal_suppression.adresse_ip == ip_test
    assert journal_suppression.valeur_avant["date"] == "2026-11-15"
    assert journal_suppression.valeur_apres == {"supprime": True}


@pytest.mark.django_db
def test_ferie_national_present_dans_lecture(setup_utilisateurs):
    """Un jour férié présent en base est bien renvoyé dans la réponse de consultation."""
    ct = setup_utilisateurs["ct"]
    client = APIClient()
    client.force_authenticate(user=ct)

    # Insérer un jour férié national dans le schéma public
    with schema_context(get_public_schema_name()):
        JourFerie.objects.get_or_create(
            pays="CI",
            date_ferie=date(2026, 1, 1),
            defaults={"libelle": "Jour de l'An"},
        )

    rep = client.get("/api/v1/calendrier/?debut=2026-01-01&fin=2026-01-31", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_200_OK

    data = rep.json()
    feries = data["feries_nationaux"]
    assert any(f["date"] == "2026-01-01" and f["libelle"] == "Jour de l'An" for f in feries)


@pytest.mark.django_db
def test_semaine_type_delete_refusee(setup_utilisateurs):
    """La semaine type ne se supprime JAMAIS : DELETE retourne 405 Method Not Allowed."""
    dg = setup_utilisateurs["dg"]
    client = APIClient()
    client.force_authenticate(user=dg)

    rep = client.delete("/api/v1/calendrier/semaine-type/", HTTP_HOST=HOTE)
    assert rep.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
