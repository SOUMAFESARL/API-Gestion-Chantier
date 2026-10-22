"""Tests pour la mise à jour manuelle de l'avancement d'une activité (F3, L3).

Couvre :
- PATCH /api/v1/activites/{id}/avancement/ :
  - CT et CP affectés autorisés (200)
  - CC affecté refusé (403 avec motif)
  - CT non affecté au projet refusé (403 avec motif)
  - Commentaire court < 10 caractères refusé (400)
  - Quantité inférieure à la quantité actuelle refusée (422 ErreurMetier)
  - Recalcul complet en chaîne de l'activité, du lot et du projet
  - Création de MiseAJourInline et entrée dans JournalAudit (RG-F3-06)
- GET /api/v1/activites/{id}/avancement/historique/ :
  - Liste ordonnée de la plus récente à la plus ancienne avec auteur
    en clair, date, valeurs avant/après, commentaire
- RG-F3-01 :
  - PATCH ordinaire sur /api/v1/activites/{id}/ refusant quantite_realisee et avancement (403)
  - POST de création d'activité autorisant quantite_realisee et avancement à 0,
    et refusant une valeur > 0 (403)
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import (
    ActionAudit,
    RoleGlobal,
    RoleProjet,
    StatutProjet,
    StatutUtilisateur,
)
from apps.projets.models import Activite, AffectationProjet, Lot, MiseAJourInline, Projet


@pytest.fixture
def donnees_test(schema_demo):
    """Initialise un projet, un lot, deux activités et quatre profils d'utilisateurs."""
    role_cp = Role.objects.filter(code=RoleGlobal.CHEF_PROJET).first()
    role_ct = Role.objects.filter(code=RoleGlobal.CONDUCTEUR_TRAVAUX).first()
    role_cc = Role.objects.filter(code=RoleGlobal.CHEF_CHANTIER).first()

    if not (role_cp and role_ct and role_cc):
        from apps.accounts.services.roles import initialiser_roles_par_defaut

        initialiser_roles_par_defaut()
        role_cp = Role.objects.filter(code=RoleGlobal.CHEF_PROJET).first()
        role_ct = Role.objects.filter(code=RoleGlobal.CONDUCTEUR_TRAVAUX).first()
        role_cc = Role.objects.filter(code=RoleGlobal.CHEF_CHANTIER).first()

    # Utilisateurs
    user_cp = Utilisateur.objects.create_user(
        email="cp_f3@demo.ci",
        password="Password123!",
        nom="Kouame",
        prenom="Adama",
        role=role_cp,
        role_global=RoleGlobal.CHEF_PROJET,
        statut=StatutUtilisateur.ACTIF,
    )
    user_ct = Utilisateur.objects.create_user(
        email="ct_f3@demo.ci",
        password="Password123!",
        nom="Bakayoko",
        prenom="Ibrahim",
        role=role_ct,
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
        statut=StatutUtilisateur.ACTIF,
    )
    user_cc = Utilisateur.objects.create_user(
        email="cc_f3@demo.ci",
        password="Password123!",
        nom="Toure",
        prenom="Moussa",
        role=role_cc,
        role_global=RoleGlobal.CHEF_CHANTIER,
        statut=StatutUtilisateur.ACTIF,
    )
    user_ct_autre = Utilisateur.objects.create_user(
        email="ct_autre_f3@demo.ci",
        password="Password123!",
        nom="Diallo",
        prenom="Amara",
        role=role_ct,
        role_global=RoleGlobal.CONDUCTEUR_TRAVAUX,
        statut=StatutUtilisateur.ACTIF,
    )

    # Projet
    projet = Projet.objects.create(
        reference="PRJ-F3-TEST",
        nom="Chantier F3 Avancement Manuel",
        ville="Abidjan",
        maitre_ouvrage="Maître d'Ouvrage Test",
        statut=StatutProjet.EN_COURS,
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 12, 31),
        chef_projet=user_cp,
        conducteur_travaux=user_ct,
    )

    # Affectations
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=user_cp,
        role_projet=RoleProjet.CHEF_PROJET,
        est_actif=True,
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=user_ct,
        role_projet=RoleProjet.CONDUCTEUR_TRAVAUX,
        est_actif=True,
    )
    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=user_cc,
        role_projet=RoleProjet.CHEF_CHANTIER,
        est_actif=True,
    )

    # Lot
    lot = Lot.objects.create(
        projet=projet,
        code="LOT-01",
        libelle="Gros Œuvre",
        budget_initial_montant=Decimal("1000000"),
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 6, 30),
    )

    # Activités
    activite1 = Activite.objects.create(
        lot=lot,
        libelle="Fondations profondes",
        quantite_prevue=Decimal("10.000"),
        quantite_realisee=Decimal("0.000"),
        avancement=Decimal("0.00"),
        poids=Decimal("10.000"),
        date_debut_prevue=date(2026, 1, 1),
        date_fin_prevue=date(2026, 3, 31),
    )
    activite2 = Activite.objects.create(
        lot=lot,
        libelle="Élévation des murs",
        quantite_prevue=Decimal("10.000"),
        quantite_realisee=Decimal("0.000"),
        avancement=Decimal("0.00"),
        poids=Decimal("10.000"),
        date_debut_prevue=date(2026, 4, 1),
        date_fin_prevue=date(2026, 6, 30),
    )

    return {
        "projet": projet,
        "lot": lot,
        "activite1": activite1,
        "activite2": activite2,
        "user_cp": user_cp,
        "user_ct": user_ct,
        "user_cc": user_cc,
        "user_ct_autre": user_ct_autre,
    }


@pytest.fixture
def client_api():
    client = APIClient()
    client.defaults["HTTP_HOST"] = "demo.localhost"
    return client


@pytest.mark.django_db
def test_ct_affecte_peut_mettre_a_jour_avancement(donnees_test, client_api):
    """Le Conducteur de Travaux affecté au projet peut mettre à jour l'avancement (200)."""
    user_ct = donnees_test["user_ct"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_ct)

    url = f"/api/v1/activites/{activite.id}/avancement/"
    payload = {
        "quantite_realisee": "4.000",
        "commentaire": "Constat métrique contradictoire sur chantier",
    }
    rep = client_api.patch(url, payload, format="json")

    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert Decimal(str(data["quantite_realisee"])) == Decimal("4.000")
    assert Decimal(str(data["avancement"])) == Decimal("40.00")

    activite.refresh_from_db()
    assert activite.quantite_realisee == Decimal("4.000")
    assert activite.avancement == Decimal("40.00")


@pytest.mark.django_db
def test_cp_affecte_peut_mettre_a_jour_avancement(donnees_test, client_api):
    """Le Chef de Projet affecté au projet peut mettre à jour l'avancement (200)."""
    user_cp = donnees_test["user_cp"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_cp)

    url = f"/api/v1/activites/{activite.id}/avancement/"
    payload = {
        "quantite_realisee": "3.500",
        "commentaire": "Ajustement validé suite à la réunion de chantier",
    }
    rep = client_api.patch(url, payload, format="json")

    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()
    assert Decimal(str(data["quantite_realisee"])) == Decimal("3.500")
    assert Decimal(str(data["avancement"])) == Decimal("35.00")


@pytest.mark.django_db
def test_cc_affecte_refuse_403(donnees_test, client_api):
    """Un Chef de Chantier (CC) affecté au projet est refusé en 403 avec un motif explicite."""
    user_cc = donnees_test["user_cc"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_cc)

    url = f"/api/v1/activites/{activite.id}/avancement/"
    payload = {
        "quantite_realisee": "3.000",
        "commentaire": "Tentative de mise à jour par le chef de chantier",
    }
    rep = client_api.patch(url, payload, format="json")

    assert rep.status_code == status.HTTP_403_FORBIDDEN
    erreur = rep.json()["erreur"]
    assert "Conducteur de Travaux" in erreur["message"]
    assert "Chef de Projet" in erreur["message"]


@pytest.mark.django_db
def test_ct_non_affecte_refuse_403(donnees_test, client_api):
    """Un Conducteur de Travaux (CT) non affecté à ce projet est refusé en 403 avec motif."""
    user_ct_autre = donnees_test["user_ct_autre"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_ct_autre)

    url = f"/api/v1/activites/{activite.id}/avancement/"
    payload = {
        "quantite_realisee": "3.000",
        "commentaire": "Tentative de saisie par un tiers non affecté",
    }
    rep = client_api.patch(url, payload, format="json")

    assert rep.status_code == status.HTTP_403_FORBIDDEN
    erreur = rep.json()["erreur"]
    assert "Conducteur de Travaux" in erreur["message"]
    assert "Chef de Projet" in erreur["message"]


@pytest.mark.django_db
def test_commentaire_court_refuse_400(donnees_test, client_api):
    """Un commentaire de moins de 10 caractères est refusé en 400."""
    user_ct = donnees_test["user_ct"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_ct)

    url = f"/api/v1/activites/{activite.id}/avancement/"
    payload = {
        "quantite_realisee": "4.000",
        "commentaire": "Court",  # 5 caractères < 10
    }
    rep = client_api.patch(url, payload, format="json")

    assert rep.status_code == status.HTTP_400_BAD_REQUEST
    erreur = rep.json()["erreur"]
    assert "commentaire" in erreur["details"]


@pytest.mark.django_db
def test_quantite_en_baisse_refusee_422(donnees_test, client_api):
    """RG-F3-02 : Une quantité inférieure au réalisé actuel est refusée en 422."""
    user_ct = donnees_test["user_ct"]
    activite = donnees_test["activite1"]
    activite.quantite_realisee = Decimal("5.000")
    activite.avancement = Decimal("50.00")
    activite.save(update_fields=["quantite_realisee", "avancement"])

    client_api.force_authenticate(user=user_ct)
    url = f"/api/v1/activites/{activite.id}/avancement/"
    payload = {
        "quantite_realisee": "4.500",  # 4.5 < 5.0
        "commentaire": "Tentative de baisse de la quantité réalisée",
    }
    rep = client_api.patch(url, payload, format="json")

    assert rep.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    erreur = rep.json()["erreur"]
    assert erreur["message"] == "L'avancement d'une activité ne peut pas diminuer."


@pytest.mark.django_db
def test_recalcul_lot_et_projet(donnees_test, client_api):
    """La mise à jour manuelle recalcule l'avancement du lot et du projet."""
    user_ct = donnees_test["user_ct"]
    activite1 = donnees_test["activite1"]
    lot = donnees_test["lot"]
    projet = donnees_test["projet"]

    # Initialement à 0%
    assert lot.avancement == Decimal("0.00")
    assert projet.avancement_reel == Decimal("0.00")

    client_api.force_authenticate(user=user_ct)
    url = f"/api/v1/activites/{activite1.id}/avancement/"
    payload = {
        # 5 / 10 = 50% sur activite1 (poids 10 sur 20 du lot -> 25% du lot)
        "quantite_realisee": "5.000",
        "commentaire": "Avancement de 50% sur l'activité 1",
    }
    rep = client_api.patch(url, payload, format="json")
    assert rep.status_code == status.HTTP_200_OK

    lot.refresh_from_db()
    projet.refresh_from_db()

    assert lot.avancement == Decimal("25.00")
    assert projet.avancement_reel == Decimal("25.00")


@pytest.mark.django_db
def test_creation_mise_a_jour_inline_et_audit(donnees_test, client_api):
    """Une MiseAJourInline est enregistrée et l'action est tracée dans l'audit."""
    user_ct = donnees_test["user_ct"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_ct)

    url = f"/api/v1/activites/{activite.id}/avancement/"
    commentaire = "Avancement validé contradictoirement sur chantier"
    payload = {
        "quantite_realisee": "6.000",
        "commentaire": commentaire,
    }
    rep = client_api.patch(
        url,
        payload,
        format="json",
        HTTP_USER_AGENT="Mozilla/5.0 TestBrowser",
    )
    assert rep.status_code == status.HTTP_200_OK

    # Vérification MiseAJourInline
    maj = MiseAJourInline.objects.filter(activite=activite).first()
    assert maj is not None
    assert maj.auteur == user_ct
    assert maj.quantite_avant == Decimal("0.000")
    assert maj.quantite_apres == Decimal("6.000")
    assert maj.avancement_avant == Decimal("0.00")
    assert maj.avancement_apres == Decimal("60.00")
    assert maj.commentaire == commentaire
    assert maj.source == "F3_INLINE"

    # Vérification JournalAudit (RG-F3-06)
    entree_audit = JournalAudit.objects.filter(
        action=ActionAudit.MODIFICATION,
        type_entite="activite",
        entite_id=activite.pk,
    ).first()
    assert entree_audit is not None
    assert entree_audit.utilisateur_id == user_ct.pk
    assert entree_audit.valeur_avant["quantite_realisee"] == "0.000"
    assert entree_audit.valeur_apres["quantite_realisee"] == "6.000"
    assert entree_audit.valeur_apres["commentaire"] == commentaire
    assert entree_audit.appareil == "Mozilla/5.0 TestBrowser"
    assert entree_audit.adresse_ip is not None


@pytest.mark.django_db
def test_historique_ordonne_du_plus_recent_au_plus_ancien(donnees_test, client_api):
    """GET .../avancement/historique/ rend les entrées par date décroissante."""
    user_ct = donnees_test["user_ct"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_ct)

    url_patch = f"/api/v1/activites/{activite.id}/avancement/"
    # Première saisie
    client_api.patch(
        url_patch,
        {"quantite_realisee": "3.000", "commentaire": "Première mise à jour inline"},
        format="json",
    )
    # Deuxième saisie
    client_api.patch(
        url_patch,
        {"quantite_realisee": "7.000", "commentaire": "Deuxième mise à jour inline"},
        format="json",
    )

    url_hist = f"/api/v1/activites/{activite.id}/avancement/historique/"
    rep = client_api.get(url_hist)
    assert rep.status_code == status.HTTP_200_OK
    data = rep.json()

    assert len(data) == 2
    # Du plus récent au plus ancien
    assert Decimal(str(data[0]["quantite_apres"])) == Decimal("7.000")
    assert data[0]["commentaire"] == "Deuxième mise à jour inline"
    assert Decimal(str(data[1]["quantite_apres"])) == Decimal("3.000")
    assert data[1]["commentaire"] == "Première mise à jour inline"

    # Auteur en clair et date
    assert user_ct.nom in data[0]["auteur"] or user_ct.email in data[0]["auteur"]
    assert "date" in data[0]
    assert "cree_le" not in data[0]
    assert "auteur_nom" not in data[0]
    assert "avant" in data[0] and "apres" in data[0]


@pytest.mark.django_db
def test_patch_ordinaire_refuse_quantite_realisee_et_avancement(donnees_test, client_api):
    """RG-F3-01 : PATCH ordinaire refuse quantite_realisee et avancement en 403."""
    user_ct = donnees_test["user_ct"]
    activite = donnees_test["activite1"]
    client_api.force_authenticate(user=user_ct)

    url = f"/api/v1/activites/{activite.id}/"
    message_attendu = (
        "L'avancement se met à jour par un rapport approuvé ou par la mise à jour manuelle."
    )

    # 1. Envoi de quantite_realisee
    rep1 = client_api.patch(url, {"quantite_realisee": "5.000"}, format="json")
    assert rep1.status_code == status.HTTP_403_FORBIDDEN
    assert rep1.json()["erreur"]["message"] == message_attendu

    # 2. Envoi de avancement
    rep2 = client_api.patch(url, {"avancement": "50.00"}, format="json")
    assert rep2.status_code == status.HTTP_403_FORBIDDEN
    assert rep2.json()["erreur"]["message"] == message_attendu


@pytest.mark.django_db
def test_post_creation_autorise_a_zero_et_refuse_superieur_a_zero(donnees_test, client_api):
    """RG-F3-01 : À la création, avancement à 0 autorisé ; > 0 refusé en 403."""
    user_ct = donnees_test["user_ct"]
    lot = donnees_test["lot"]
    client_api.force_authenticate(user=user_ct)

    url = f"/api/v1/lots/{lot.id}/activites/"
    message_attendu = (
        "L'avancement se met à jour par un rapport approuvé ou par la mise à jour manuelle."
    )

    # 1. Création avec quantite_realisee=0 et avancement=0 : autorisé
    payload_valide = {
        "libelle": "Activité neuve valide à zéro",
        "quantite_prevue": "15.000",
        "quantite_realisee": 0,
        "avancement": 0,
    }
    rep_valide = client_api.post(url, payload_valide, format="json")
    assert rep_valide.status_code == status.HTTP_201_CREATED
    assert Decimal(str(rep_valide.json()["quantite_realisee"])) == Decimal("0.000")
    assert Decimal(str(rep_valide.json()["avancement"])) == Decimal("0.00")

    # 2. Création avec quantite_realisee > 0 : refusé en 403
    payload_invalide = {
        "libelle": "Activité neuve avec avancement déjà positif",
        "quantite_prevue": "15.000",
        "quantite_realisee": "5.000",
    }
    rep_invalide = client_api.post(url, payload_invalide, format="json")
    assert rep_invalide.status_code == status.HTTP_403_FORBIDDEN
    assert rep_invalide.json()["erreur"]["message"] == message_attendu
