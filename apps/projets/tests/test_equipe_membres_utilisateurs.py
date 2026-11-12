import pytest

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur
from apps.core.exceptions import ErreurConflit
from apps.projets.models import PersonneMainOeuvre, Projet
from apps.projets.services import equipes as service_equipes
from apps.projets.services import main_oeuvre as service_main_oeuvre


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

    # 3. Création d'un projet et d'une équipe avec ce collaborateur
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
                "fonction": "CHEF_EQUIPE",
                "est_chef": True,
            }
        ],
    )
    assert equipe.pk is not None
    assert equipe.membres.count() == 1
    m = equipe.membres.first()
    assert m.personne == fiche
    assert m.est_chef is True

    # 4. Tentative d'ajout en doublon
    with pytest.raises(ErreurConflit):
        service_equipes.ajouter_membre(equipe, utilisateur_id=user.pk)
