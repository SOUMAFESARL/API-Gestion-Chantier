"""Les deux règles que l'API annonçait sans les appliquer — US-013 et US-016.

**Ces tests tentent ce que les règles doivent interdire.** C'est la seule forme
qui prouve quelque chose : les réglages de rotation des jetons étaient corrects,
la suite passait, et la rotation ne révoquait rien — parce qu'aucun test ne
**rejouait** un jeton.

Ici : on écrit avec un essai expiré, et on invite au-delà du plan.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Utilisateur
from apps.billing.models import Abonnement, Plan
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.core.exceptions import QuotaPlanAtteint
from apps.tenants.models import Entreprise

SCHEMA = "demo"
HOTE = "demo.localhost"


@pytest.fixture
def plan_starter(db):
    """Un plan à trois sièges — assez petit pour être atteint dans un test."""
    plan, _ = Plan.objects.update_or_create(
        code=Plan.Code.STARTER,
        defaults={"libelle": "Starter", "limite_utilisateurs": 3},
    )
    return plan


@pytest.fixture
def abonnement_demo(db, plan_starter):
    entreprise = Entreprise.objects.get(schema_name=SCHEMA)
    Abonnement.objects.filter(entreprise=entreprise).delete()
    aujourdhui = timezone.localdate()
    return Abonnement.objects.create(
        entreprise=entreprise,
        plan=plan_starter,
        date_debut=aujourdhui - timedelta(days=5),
        date_fin=aujourdhui + timedelta(days=9),
        fin_essai=aujourdhui + timedelta(days=9),
        statut=Abonnement.Statut.ESSAI,
        renouvellement_auto=False,
    )


@pytest.fixture
def admin_demo(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="admin.regles@demo.ci").delete()
        yield Utilisateur.objects.create_user(
            email="admin.regles@demo.ci",
            password="MotDePasse1!",
            nom="Kone",
            prenom="Awa",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )


# ---------------------------------------------------------------------------
# US-016 — la lecture seule
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_l_ecriture_est_refusee_quand_l_essai_est_expire(abonnement_demo, admin_demo):
    """**Le test qui compte.** Avant, l'API répondait `200` et enregistrait.

    Le sérialiseur exposait bien `lecture_seule: true` — mais seul le navigateur
    s'en servait. Un client hors interface écrivait sans obstacle.
    """
    abonnement_demo.fin_essai = timezone.localdate() - timedelta(days=1)
    abonnement_demo.save(update_fields=["fin_essai", "modifie_le"])

    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=admin_demo)
    # `force_authenticate` ne pose pas d'en-tête `Authorization` : le verrou
    # n'agit que sur une requête qui en porte une, pour ne pas transformer un
    # `401` anonyme en `403` bavard. On la pose donc explicitement.
    reponse = client.post(
        "/api/v1/tiers/",
        {"type_tiers": "ENTREPRISE", "raison_sociale": "Essai bloque"},
        format="json",
        HTTP_AUTHORIZATION="Bearer test",
    )

    # Le refus vient d'un middleware : c'est une réponse Django simple, pas une
    # réponse DRF — elle se lit par `.json()`, et elle porte quand même
    # l'enveloppe d'erreur des conventions d'API §5.1.
    assert reponse.status_code == status.HTTP_403_FORBIDDEN, reponse.content
    corps = reponse.json()
    assert corps["erreur"]["code"] == "abonnement_suspendu"
    assert corps["erreur"]["details"]["lecture_seule"] is True


@pytest.mark.django_db
def test_la_lecture_reste_ouverte_quand_l_essai_est_expire(abonnement_demo, admin_demo):
    """« Vous pouvez toujours consulter et exporter vos données. »"""
    abonnement_demo.fin_essai = timezone.localdate() - timedelta(days=1)
    abonnement_demo.save(update_fields=["fin_essai", "modifie_le"])

    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=admin_demo)
    reponse = client.get("/api/v1/tiers/", HTTP_AUTHORIZATION="Bearer test")

    assert reponse.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_l_abonnement_reste_modifiable_pour_pouvoir_souscrire(abonnement_demo, admin_demo):
    """**La porte de sortie ne se ferme pas.**

    Un mur qui condamne aussi l'endroit où l'on souscrit n'est pas un mur, c'est
    un piège : le client ne peut plus rien débloquer.
    """
    abonnement_demo.fin_essai = timezone.localdate() - timedelta(days=1)
    abonnement_demo.save(update_fields=["fin_essai", "modifie_le"])

    from apps.billing.middleware import LectureSeuleAbonnementMiddleware

    entreprise = Entreprise.objects.get(schema_name=SCHEMA)
    assert LectureSeuleAbonnementMiddleware.en_lecture_seule(entreprise) is True

    verrou = LectureSeuleAbonnementMiddleware(lambda r: None)
    for chemin in ("/api/v1/abonnement/", "/api/v1/auth/deconnexion/"):
        fausse = type(
            "R",
            (),
            {
                "method": "POST",
                "path": chemin,
                "META": {"HTTP_AUTHORIZATION": "Bearer x"},
                "tenant": entreprise,
            },
        )()
        assert verrou._doit_refuser(fausse) is False, chemin


@pytest.mark.django_db
def test_un_essai_en_cours_n_empeche_rien(abonnement_demo, admin_demo):
    """Le verrou ne doit pas se déclencher pendant l'essai."""
    from apps.billing.middleware import LectureSeuleAbonnementMiddleware

    entreprise = Entreprise.objects.get(schema_name=SCHEMA)
    assert LectureSeuleAbonnementMiddleware.en_lecture_seule(entreprise) is False


# ---------------------------------------------------------------------------
# US-013 — la limite d'utilisateurs du plan
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_l_invitation_est_refusee_au_dela_du_plan(abonnement_demo, admin_demo):
    """Trois sièges, trois occupants : la quatrième invitation est refusée.

    *`QuotaPlanAtteint` existait depuis le socle et n'était levée nulle part.*
    """
    from apps.accounts.services.invitations import creer_invitation

    with schema_context(SCHEMA):
        Invitation.objects.all().delete()
        Utilisateur.tous_objets.exclude(email="admin.regles@demo.ci").delete()

        # Un compte actif, puis deux invitations : trois sièges sur trois.
        creer_invitation("un@demo.ci", RoleGlobal.CHEF_CHANTIER)
        creer_invitation("deux@demo.ci", RoleGlobal.CHEF_CHANTIER)

        with pytest.raises(QuotaPlanAtteint) as refus:
            creer_invitation("trois@demo.ci", RoleGlobal.CHEF_CHANTIER)

    assert refus.value.details["limite"] == 3
    assert refus.value.details["sieges_occupes"] >= 3
    with schema_context(SCHEMA):
        assert not Invitation.objects.filter(email="trois@demo.ci").exists(), (
            "une invitation refusée a laissé une ligne en base"
        )


@pytest.mark.django_db
def test_une_invitation_en_attente_occupe_un_siege(abonnement_demo, admin_demo):
    """Sinon une entreprise envoie trente invitations puis dépasse à l'activation.

    Le dépassement se produirait alors compte par compte, sans personne à qui
    le dire — l'invitant est parti depuis longtemps.
    """
    from apps.billing.services.quota import sieges_occupes

    with schema_context(SCHEMA):
        Invitation.objects.all().delete()
        Utilisateur.tous_objets.exclude(email="admin.regles@demo.ci").delete()
        avant = sieges_occupes()

        from apps.accounts.services.invitations import creer_invitation

        creer_invitation("attente@demo.ci", RoleGlobal.CHEF_CHANTIER)
        assert sieges_occupes() == avant + 1


@pytest.mark.django_db
def test_un_plan_sans_limite_n_en_impose_aucune(abonnement_demo, admin_demo):
    """`NULL` signifie **illimité**, jamais « zéro »."""
    from apps.billing.services.quota import limite_du_plan, verifier_quota_avant_invitation

    abonnement_demo.plan.limite_utilisateurs = None
    abonnement_demo.plan.save(update_fields=["limite_utilisateurs", "modifie_le"])

    entreprise = Entreprise.objects.get(schema_name=SCHEMA)
    assert limite_du_plan(entreprise) is None
    with schema_context(SCHEMA):
        verifier_quota_avant_invitation(entreprise)  # ne doit rien lever
