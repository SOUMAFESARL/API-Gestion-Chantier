import uuid
from datetime import date

import pytest
from django.urls import resolve
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.authentification import emettre_jetons
from apps.catalogue.models.referentiel import CategorieReferentiel, ReferentielPlateforme
from apps.chantier.services.hors_ligne import listes as listes_hors_ligne
from apps.core.contexte import contexte_entreprise
from apps.core.enums import RoleGlobal, RoleProjet, StatutUtilisateur
from apps.core.exceptions import ErreurConflit
from apps.projets.models import (
    AffectationProjet,
    Element,
    MembreEquipeChantier,
    ModeMesure,
    NiveauProjet,
    PersonneMainOeuvre,
    Projet,
)
from apps.projets.services import equipes as service_equipes
from apps.projets.services import main_oeuvre as service_main_oeuvre
from apps.projets.services.referentiels import (
    ajouter_entree,
    code_fonction_equipe_valide,
    libelle_fonction_equipe,
    table_fonctions_equipe,
)


def _client_pour(utilisateur: Utilisateur) -> APIClient:
    jeton = emettre_jetons(utilisateur)["access"]
    client = APIClient(HTTP_HOST="localhost")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {jeton}")
    return client


@pytest.mark.django_db
def test_fiche_du_collaborateur_et_membres(entreprise_demo):
    user = Utilisateur.objects.create_user(
        email="collab.equipe@demo.ci",
        nom="Kouamé",
        prenom="Adjoua",
        statut=StatutUtilisateur.ACTIF,
        is_active=True,
    )
    user.entreprise = entreprise_demo
    user.save()

    # 1. Création de fiche à la volée
    fiche = service_main_oeuvre.fiche_du_collaborateur(user)
    assert fiche is not None
    assert fiche.utilisateur == user
    assert fiche.nom == "Kouamé"
    assert fiche.prenom == "Adjoua"
    assert fiche.entreprise_partenaire is None  # interne

    # 2. Réappel sans doublon
    fiche2 = service_main_oeuvre.fiche_du_collaborateur(user)
    assert fiche2.pk == fiche.pk
    assert PersonneMainOeuvre.objects.filter(utilisateur=user).count() == 1

    # 3. Création d'un projet et d'une équipe avec ce collaborateur (découplé de CHEF_EQUIPE)
    projet = Projet.objects.create(
        nom="Projet Équipe Test",
        reference="PRJ-EQ-001",
    )

    equipe, _avert = service_equipes.creer_equipe(
        projet,
        nom="Équipe Gros Œuvre",
        membres=[
            {
                "utilisateur_id": user.pk,
                "fonction": "OUVRIER_QUALIFIE",
                "est_chef": True,
            }
        ],
    )
    assert equipe.pk is not None
    assert equipe.membres.count() == 1
    m = equipe.membres.first()
    assert m.personne == fiche
    assert m.est_chef is True
    assert m.fonction == "OUVRIER_QUALIFIE"

    # 4. Tentative d'ajout en doublon
    with pytest.raises(ErreurConflit):
        service_equipes.ajouter_membre(equipe, utilisateur_id=user.pk)


@pytest.mark.django_db
def test_referentiel_fonctions_equipe_et_refus_chef_equipe(entreprise_demo):
    assert ReferentielPlateforme.objects.filter(
        categorie=CategorieReferentiel.FONCTION_EQUIPE, code="MACON"
    ).exists()
    assert not ReferentielPlateforme.objects.filter(
        categorie=CategorieReferentiel.FONCTION_EQUIPE, code="CHEF_EQUIPE"
    ).exists()
    assert code_fonction_equipe_valide("CHEF_EQUIPE") is False
    assert code_fonction_equipe_valide("MACON") is True

    entree = ajouter_entree(
        CategorieReferentiel.FONCTION_EQUIPE,
        "Étanchéiste",
        groupe="Second œuvre & Technique",
    )
    assert entree["code"] == "ETANCHEISTE"
    table = table_fonctions_equipe()
    assert libelle_fonction_equipe("ETANCHEISTE", table) == "Étanchéiste"
    assert code_fonction_equipe_valide("ETANCHEISTE", table) is True

    dg = Utilisateur.objects.create_user(
        email=f"dg-ref-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        nom="Diallo",
        prenom="Moussa",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        statut=StatutUtilisateur.ACTIF,
        is_active=True,
    )
    dg.is_owner = True
    dg.save(update_fields=["is_owner", "modifie_le"])
    client = _client_pour(dg)

    rep_liste = client.get("/api/v1/referentiels/fonctions-equipe/")
    assert rep_liste.status_code == 200
    codes = {e["code"] for e in rep_liste.json()}
    assert {"OUVRIER", "MACON", "ETANCHEISTE"}.issubset(codes)
    assert "CHEF_EQUIPE" not in codes


@pytest.mark.django_db
def test_decouplage_fonction_chef_et_historique_immuable(entreprise_demo):
    projet = Projet.objects.create(nom="Projet Découplage", reference="PRJ-DEC-001")
    equipe, _ = service_equipes.creer_equipe(projet, nom="Équipe Maçons")

    macon = service_main_oeuvre.creer_personne(nom="Koné", prenom="Bakary", metier="Maçon")
    ferrailleur = service_main_oeuvre.creer_personne(
        nom="Bamba", prenom="Seydou", metier="Ferrailleur"
    )
    sans_metier = service_main_oeuvre.creer_personne(nom="Traoré", prenom="Issa", metier="")

    # Refus explicite de CHEF_EQUIPE comme fonction
    with pytest.raises(ValidationError):
        service_equipes.ajouter_membre(equipe, personne=macon, fonction="CHEF_EQUIPE")

    # Déduction automatique de la fonction depuis personne.metier ou repli OUVRIER
    m1, _ = service_equipes.ajouter_membre(
        equipe, personne=macon, est_chef=True, date_arrivee=date(2026, 10, 1)
    )
    m2, _ = service_equipes.ajouter_membre(
        equipe, personne=ferrailleur, date_arrivee=date(2026, 10, 1)
    )
    m3, _ = service_equipes.ajouter_membre(
        equipe, personne=sans_metier, date_arrivee=date(2026, 10, 1)
    )
    assert m1.fonction == "MACON"
    assert m1.est_chef is True
    assert m2.fonction == "FERRAILLEUR"
    assert m3.fonction == "OUVRIER"

    # Remplacement du chef : l'ancien chef garde sa fonction MACON et le nouveau garde FERRAILLEUR
    service_equipes.modifier_membre(m2, donnees={"est_chef": True})
    m1.refresh_from_db()
    m2.refresh_from_db()
    assert m1.est_chef is False
    assert m1.fonction == "MACON"
    assert m2.est_chef is True
    assert m2.fonction == "FERRAILLEUR"

    # Modification indépendante de la fonction du chef actif
    service_equipes.modifier_membre(m2, donnees={"fonction": "COFFREUR"})
    m2.refresh_from_db()
    assert m2.est_chef is True
    assert m2.fonction == "COFFREUR"

    # Retrait daté du chef : l'historique conserve est_chef=True mais libère la place active
    service_equipes.retirer_membre(m2, date_depart=date(2026, 10, 15))
    m2.refresh_from_db()
    assert m2.date_depart == date(2026, 10, 15)
    assert m2.est_chef is True
    assert m2.fonction == "COFFREUR"

    # Un nouveau chef actif peut être nommé sur la même équipe sans conflit DB
    service_equipes.modifier_membre(m3, donnees={"est_chef": True, "fonction": "CARRELEUR"})
    m3.refresh_from_db()
    assert m3.est_chef is True
    assert m3.fonction == "CARRELEUR"
    assert MembreEquipeChantier.objects.filter(equipe=equipe, est_chef=True).count() == 2


@pytest.mark.django_db
def test_planning_expose_code_et_montant_selon_droits(entreprise_demo):
    dg = Utilisateur.objects.create_user(
        email=f"dg-plan-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        nom="Diallo",
        prenom="Moussa",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        statut=StatutUtilisateur.ACTIF,
        is_active=True,
    )
    dg.is_owner = True
    dg.save(update_fields=["is_owner", "modifie_le"])

    role_vi = Role.objects.filter(code=RoleGlobal.VISITEUR).first()
    visiteur = Utilisateur.objects.create_user(
        email=f"vi-plan-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        nom="Koné",
        prenom="Amina",
        role_global=RoleGlobal.VISITEUR,
        role=role_vi,
        statut=StatutUtilisateur.ACTIF,
        is_active=True,
    )

    projet = Projet.objects.create(nom="Projet Planning", reference="PRJ-PLAN-001")
    niv_lot = NiveauProjet.objects.create(projet=projet, ordre=1, libelle="Lot", alerter=True)
    niv_tache = NiveauProjet.objects.create(projet=projet, ordre=2, libelle="Tâche")

    lot = Element.objects.create(
        projet=projet,
        niveau=niv_lot,
        libelle="Gros œuvre",
        code="LOT-01",
        enveloppe=10_000_00,
    )
    tache_a = Element.objects.create(
        projet=projet,
        parent=lot,
        niveau=niv_tache,
        libelle="Fondations",
        code="1.1.A",
        mode_mesure=ModeMesure.POURCENTAGE,
        montant=4_000_00,
    )
    Element.objects.create(
        projet=projet,
        parent=lot,
        niveau=niv_tache,
        libelle="Élévation",
        code="",
        mode_mesure=ModeMesure.POURCENTAGE,
        montant=6_000_00,
    )

    AffectationProjet.objects.create(
        projet=projet,
        utilisateur=visiteur,
        role_projet=RoleProjet.VISITEUR,
        est_actif=True,
    )

    # Avec permission projets.voir_montants (DG) : code et montant sont renseignés
    rep_dg = _client_pour(dg).get(f"/api/v1/projets/{projet.pk}/planning/")
    assert rep_dg.status_code == 200
    cases_dg = rep_dg.json()["cases"]
    assert len(cases_dg) == 1
    lot_dg = cases_dg[0]
    assert lot_dg["code"] == "LOT-01"
    assert lot_dg["montant"] == 10_000_00
    assert lot_dg["enfants"][0]["id"] == str(tache_a.pk)
    assert lot_dg["enfants"][0]["code"] == "1.1.A"
    assert lot_dg["enfants"][0]["montant"] == 4_000_00
    assert lot_dg["enfants"][1]["code"] == ""
    assert lot_dg["enfants"][1]["montant"] == 6_000_00

    # Sans permission projets.voir_montants (Visiteur) : code visible, montant strictement None
    rep_vi = _client_pour(visiteur).get(f"/api/v1/projets/{projet.pk}/planning/")
    assert rep_vi.status_code == 200
    lot_vi = rep_vi.json()["cases"][0]
    assert lot_vi["code"] == "LOT-01"
    assert lot_vi["montant"] is None
    assert lot_vi["enfants"][0]["code"] == "1.1.A"
    assert lot_vi["enfants"][0]["montant"] is None


@pytest.mark.django_db
def test_api_equipes_fonction_libelle_et_hors_ligne(entreprise_demo):
    dg = Utilisateur.objects.create_user(
        email=f"dg-eq-{uuid.uuid4().hex[:6]}@demo.ci",
        password="TestPassword123!",
        nom="Diallo",
        prenom="Moussa",
        role_global=RoleGlobal.DIRECTEUR_GENERAL,
        statut=StatutUtilisateur.ACTIF,
        is_active=True,
    )
    dg.is_owner = True
    dg.save(update_fields=["is_owner", "modifie_le"])
    client = _client_pour(dg)

    projet = Projet.objects.create(nom="Projet API Équipes", reference="PRJ-API-EQ-1")
    macon = service_main_oeuvre.creer_personne(nom="Coulibaly", prenom="Sali", metier="Maçon")
    plombier = service_main_oeuvre.creer_personne(nom="Yao", prenom="Koffi", metier="Plombier")

    # 1. Refus HTTP si fonction == CHEF_EQUIPE
    rep_ko = client.post(
        f"/api/v1/projets/{projet.pk}/equipes/",
        {
            "nom": "Équipe KO",
            "membres": [
                {"personne_id": str(macon.pk), "fonction": "CHEF_EQUIPE", "est_chef": True}
            ],
        },
        format="json",
    )
    assert rep_ko.status_code == 400

    # 2. Création HTTP sans fonction -> déduite du métier + fonction_libelle exposé
    rep_ok = client.post(
        f"/api/v1/projets/{projet.pk}/equipes/",
        {
            "nom": "Équipe Maçonnerie",
            "membres": [{"personne_id": str(macon.pk), "est_chef": True}],
        },
        format="json",
    )
    assert rep_ok.status_code == 201
    data_eq = rep_ok.json()
    assert data_eq["chef"]["fonction"] == "MACON"
    assert data_eq["chef"]["fonction_libelle"] == "Maçon"
    assert data_eq["chef"]["est_chef"] is True

    # 3. Ajout second membre + changement de chef via PATCH sans écraser sa fonction
    rep_add = client.post(
        f"/api/v1/projets/{projet.pk}/equipes/{data_eq['id']}/membres/",
        {"personne_id": str(plombier.pk)},
        format="json",
    )
    assert rep_add.status_code == 201
    m2_id = rep_add.json()["id"]
    assert rep_add.json()["fonction"] == "PLOMBIER"
    assert rep_add.json()["fonction_libelle"] == "Plombier"

    rep_patch = client.patch(
        f"/api/v1/projets/{projet.pk}/equipes/{data_eq['id']}/membres/{m2_id}/",
        {"est_chef": True},
        format="json",
    )
    assert rep_patch.status_code == 200
    assert rep_patch.json()["est_chef"] is True
    assert rep_patch.json()["fonction"] == "PLOMBIER"

    # 4. Départ daté du chef -> conservé dans l'historique (?historique=true)
    rep_del = client.delete(
        f"/api/v1/projets/{projet.pk}/equipes/{data_eq['id']}/membres/{m2_id}/"
    )
    assert rep_del.status_code == 204
    rep_hist = client.get(f"/api/v1/projets/{projet.pk}/equipes/{data_eq['id']}/?historique=true")
    assert rep_hist.status_code == 200
    membres_hist = {m["id"]: m for m in rep_hist.json()["membres"]}
    assert membres_hist[m2_id]["est_chef"] is True
    assert membres_hist[m2_id]["fonction"] == "PLOMBIER"

    # 5. Listes hors ligne & route admin plateforme
    with contexte_entreprise(entreprise_demo):
        hl = listes_hors_ligne()
    assert "MACON" in hl["fonctions_equipe"]
    assert "CHEF_EQUIPE" not in hl["fonctions_equipe"]
    match = resolve("/api/v1/admins/referentiels/fonctions-equipe/")
    assert match.kwargs["categorie"] == "fonctions-equipe"
