"""Tests pour les filtres et la pagination du journal plateforme (B4)."""

import uuid
from datetime import datetime

import pytest
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.platform_admin.models import JournalPlateforme

HOTE_PLATEFORME = "localhost"


@pytest.fixture(autouse=True)
def autoriser_ip_locale(settings):
    """Autorise l'adresse IP de test dans RestrictionIPPlateformeMiddleware."""
    settings.SUPER_ADMIN_IPS = ["127.0.0.1"]


@pytest.fixture
def client_api():
    """Client API configuré sur le domaine de la plateforme."""
    return APIClient(headers={"host": HOTE_PLATEFORME})


def _agent(
    email: str,
    superviseur: bool,
    prenom: str = "Agent",
    nom: str = "Plateforme",
) -> Utilisateur:
    with schema_context(get_public_schema_name()):
        Utilisateur.tous_objets.filter(email=email).delete()
        fabrique = (
            Utilisateur.objects.create_superuser if superviseur else Utilisateur.objects.create_user
        )
        return fabrique(
            email=email,
            password="MotDePasse12345!",
            nom=nom,
            prenom=prenom,
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
            **({} if superviseur else {"is_staff": True}),
        )


@pytest.fixture
def agent_support(db):
    return _agent("support.journal@ccd-digital.ci", superviseur=False)


@pytest.fixture
def agent_superviseur(db):
    return _agent("superviseur.journal@ccd-digital.ci", superviseur=True)


def _creer_entree_journal(
    *,
    utilisateur_id=None,
    entreprise_id=None,
    action="TEST_ACTION",
    detail=None,
    date=None,
):
    with schema_context(get_public_schema_name()):
        entree = JournalPlateforme.objects.create(
            utilisateur_id=utilisateur_id or uuid.uuid4(),
            entreprise_id=entreprise_id or uuid.uuid4(),
            action=action,
            detail=detail or {},
            adresse_ip="127.0.0.1",
            appareil="pytest",
        )
        if date is not None:
            JournalPlateforme.objects.filter(pk=entree.pk).update(horodatage=date)
            entree.refresh_from_db()
        return entree


@pytest.mark.django_db
def test_journal_pagine_au_format_standard(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    for _ in range(25):
        _creer_entree_journal()

    rep = client_api.get("/api/v1/admins/journal-plateforme/")
    assert rep.status_code == status.HTTP_200_OK
    data = rep.data
    assert data["total"] >= 25
    assert len(data["resultats"]) == 20
    assert data["nombre_pages"] >= 2
    assert "suivant" in data
    assert "precedent" in data


@pytest.mark.django_db
def test_taille_page_plafonnee_a_100(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    for _ in range(105):
        _creer_entree_journal()

    rep = client_api.get("/api/v1/admins/journal-plateforme/?taille_page=500")
    assert rep.status_code == status.HTTP_200_OK
    assert len(rep.data["resultats"]) == 100


@pytest.mark.django_db
def test_filtre_par_periode_bornes_incluses(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    d1 = timezone.make_aware(datetime(2026, 10, 1, 10, 0))
    d2 = timezone.make_aware(datetime(2026, 10, 5, 12, 0))
    d3 = timezone.make_aware(datetime(2026, 10, 10, 18, 0))

    _creer_entree_journal(action="ACTION_01", date=d1)
    e2 = _creer_entree_journal(action="ACTION_05", date=d2)
    e3 = _creer_entree_journal(action="ACTION_10", date=d3)

    rep = client_api.get("/api/v1/admins/journal-plateforme/?du=2026-10-05&au=2026-10-10")
    assert rep.status_code == status.HTTP_200_OK
    ids = [r["id"] for r in rep.data["resultats"]]
    assert e2.id in ids
    assert e3.id in ids
    assert len(ids) == 2


@pytest.mark.django_db
def test_filtre_par_agent(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    agent_a = _agent("agent.a@ccd-digital.ci", superviseur=False)
    agent_b = _agent("agent.b@ccd-digital.ci", superviseur=False)

    e_a = _creer_entree_journal(utilisateur_id=agent_a.id, action="ACTION_A")
    _creer_entree_journal(utilisateur_id=agent_b.id, action="ACTION_B")

    rep = client_api.get(f"/api/v1/admins/journal-plateforme/?utilisateur_id={agent_a.id}")
    assert rep.status_code == status.HTTP_200_OK
    assert all(r["utilisateur_id"] == str(agent_a.id) for r in rep.data["resultats"])
    ids = [r["id"] for r in rep.data["resultats"]]
    assert e_a.id in ids


@pytest.mark.django_db
def test_filtre_par_entreprise_et_action(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    ent_1 = uuid.uuid4()
    ent_2 = uuid.uuid4()

    cible = _creer_entree_journal(entreprise_id=ent_1, action="SUSPENSION_CLIENT")
    _creer_entree_journal(entreprise_id=ent_1, action="AUTRE_ACTION")
    _creer_entree_journal(entreprise_id=ent_2, action="SUSPENSION_CLIENT")

    rep = client_api.get(
        f"/api/v1/admins/journal-plateforme/?entreprise_id={ent_1}&action=SUSPENSION_CLIENT"
    )
    assert rep.status_code == status.HTTP_200_OK
    ids = [r["id"] for r in rep.data["resultats"]]
    assert ids == [cible.id]


@pytest.mark.django_db
def test_periode_inversee_refusee(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    rep = client_api.get("/api/v1/admins/journal-plateforme/?du=2026-10-10&au=2026-10-05")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    erreur = rep.data.get("erreur", rep.data)
    details = erreur.get("details", erreur)
    erreur_au = details.get("au")
    if isinstance(erreur_au, list):
        erreur_au = erreur_au[0]
    assert "La date de fin doit être postérieure ou égale à la date de début." in str(erreur_au)


@pytest.mark.django_db
def test_date_illisible_refusee(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    rep = client_api.get("/api/v1/admins/journal-plateforme/?du=14/10/2026")
    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    erreur = rep.data.get("erreur", rep.data)
    details = erreur.get("details", erreur)
    erreur_du = details.get("du")
    if isinstance(erreur_du, list):
        erreur_du = erreur_du[0]
    assert "Date invalide : format attendu AAAA-MM-JJ." in str(erreur_du)


@pytest.mark.django_db
def test_nom_de_l_agent_resolu(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    agent = _agent("awa.kone@ccd-digital.ci", superviseur=False, prenom="Awa", nom="Koné")
    e = _creer_entree_journal(utilisateur_id=agent.id)

    rep = client_api.get(f"/api/v1/admins/journal-plateforme/?utilisateur_id={agent.id}")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data["resultats"][0]["id"] == e.id
    assert rep.data["resultats"][0]["utilisateur_nom"] == "Awa Koné"


@pytest.mark.django_db
def test_nom_d_entreprise_supprimee_lu_dans_le_detail(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    ent_id = uuid.uuid4()
    e = _creer_entree_journal(
        entreprise_id=ent_id,
        detail={"raison_sociale": "Ancienne SARL"},
    )

    rep = client_api.get(f"/api/v1/admins/journal-plateforme/?entreprise_id={ent_id}")
    assert rep.status_code == status.HTTP_200_OK
    assert rep.data["resultats"][0]["id"] == e.id
    assert rep.data["resultats"][0]["entreprise_nom"] == "Ancienne SARL"


@pytest.mark.django_db
def test_ordre_stable_a_horodatage_egal(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    horodatage = timezone.make_aware(datetime(2026, 10, 14, 15, 30))
    e1 = _creer_entree_journal(action="ACTION_MEME_DATE_1", date=horodatage)
    e2 = _creer_entree_journal(action="ACTION_MEME_DATE_2", date=horodatage)

    rep = client_api.get(
        "/api/v1/admins/journal-plateforme/?action=ACTION_MEME_DATE_1"
    )
    assert rep.status_code == status.HTTP_200_OK

    rep = client_api.get("/api/v1/admins/journal-plateforme/?du=2026-10-14&au=2026-10-14")
    assert rep.status_code == status.HTTP_200_OK
    ids = [r["id"] for r in rep.data["resultats"] if r["id"] in (e1.id, e2.id)]
    # e2 a été créé après e1, donc id(e2) > id(e1)
    assert ids == [max(e1.id, e2.id), min(e1.id, e2.id)]


@pytest.mark.django_db
def test_support_lit_le_journal(client_api, agent_support):
    client_api.force_authenticate(user=agent_support)
    _creer_entree_journal()
    rep = client_api.get("/api/v1/admins/journal-plateforme/")
    assert rep.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_liste_des_actions_distinctes_triees(client_api, agent_superviseur):
    client_api.force_authenticate(user=agent_superviseur)
    _creer_entree_journal(action="CHANGEMENT_PLAN")
    _creer_entree_journal(action="ACTIVATION_MODULE")
    _creer_entree_journal(action="CHANGEMENT_PLAN")

    rep = client_api.get("/api/v1/admins/journal-plateforme/actions/")
    assert rep.status_code == status.HTTP_200_OK
    actions = rep.data["actions"]
    assert "ACTIVATION_MODULE" in actions
    assert "CHANGEMENT_PLAN" in actions
    assert actions == sorted(set(actions))


@pytest.mark.django_db
def test_nombre_de_requetes_constant(
    client_api,
    agent_superviseur,
    django_assert_max_num_queries,
):
    client_api.force_authenticate(user=agent_superviseur)
    # Créer 20 agents et 20 lignes
    for i in range(20):
        agent = _agent(f"agent.requetes.{i}@ccd-digital.ci", superviseur=False)
        _creer_entree_journal(utilisateur_id=agent.id)

    # 12 requêtes (dont les SET search_path du middleware tenant), invariant pour 20 agents
    with django_assert_max_num_queries(15):
        rep = client_api.get("/api/v1/admins/journal-plateforme/?taille_page=20")
        assert rep.status_code == status.HTTP_200_OK
        assert len(rep.data["resultats"]) == 20
