"""Les relances de l'essai — parcours de l'essai gratuit §2, US-016.

Ces tests **tentent ce que la tâche doit interdire** plutôt que de vérifier
qu'elle est configurée : c'est la leçon de la rotation des jetons, dont les deux
réglages étaient corrects et qui ne révoquait rien.

Trois promesses sont éprouvées ici, et chacune échouerait en silence :

* une relance ne part **qu'une fois**, même si la tâche est rejouée le même jour ;
* seuls les `AD` actifs et le `DG` la reçoivent ;
* le bilan est compté **dans le schéma du client**, jamais dans `public` — et
  c'est le piège qui ne lève aucune erreur, puisque zéro est un nombre valide.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, Plan, RelanceEssai
from apps.billing.tasks import relancer_essais
from apps.core.enums import RoleGlobal, StatutUtilisateur
from apps.projets.models import Projet
from apps.tenants.models import Entreprise

SCHEMA = "demo"


@pytest.fixture
def essai_a_trois_jours(db):
    """Un abonnement d'essai qui se termine dans trois jours, et son entreprise."""
    entreprise = Entreprise.objects.get(schema_name=SCHEMA)
    plan = Plan.objects.filter(code=Plan.Code.PRO).first()
    if plan is None:
        plan = Plan.objects.create(code=Plan.Code.PRO, libelle="Pro")

    Abonnement.objects.filter(entreprise=entreprise).delete()
    RelanceEssai.objects.all().delete()

    aujourdhui = timezone.localdate()
    abonnement = Abonnement.objects.create(
        entreprise=entreprise,
        plan=plan,
        date_debut=aujourdhui - timedelta(days=11),
        date_fin=aujourdhui + timedelta(days=3),
        fin_essai=aujourdhui + timedelta(days=3),
        statut=Abonnement.Statut.ESSAI,
        renouvellement_auto=False,
    )
    yield abonnement


@pytest.fixture
def equipe(db):
    """Un administrateur, un directeur général, et un chef de chantier."""
    with schema_context(SCHEMA):
        for adresse in ("ad.relance@demo.ci", "dg.relance@demo.ci", "cc.relance@demo.ci"):
            Utilisateur.tous_objets.filter(email=adresse).delete()
        Utilisateur.objects.create_user(
            email="ad.relance@demo.ci",
            password="MotDePasse1!",
            nom="Kone",
            prenom="Ad",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        Utilisateur.objects.create_user(
            email="dg.relance@demo.ci",
            password="MotDePasse1!",
            nom="Soro",
            prenom="Dg",
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        Utilisateur.objects.create_user(
            email="cc.relance@demo.ci",
            password="MotDePasse1!",
            nom="Diallo",
            prenom="Cc",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )
        yield


@pytest.mark.django_db
def test_une_relance_ne_part_qu_une_fois(essai_a_trois_jours, equipe):
    """**Le test qui compte** : rejouer la tâche ne doit pas réécrire au client.

    La sélection porte sur une date exacte, donc rien n'empêche la tâche de
    tourner deux fois le même jour — une reprise, un *worker* redémarré. Sans la
    trace en base, le client reçoit deux fois « il vous reste 3 jours », et il
    n'y voit pas un incident technique : il y voit un produit qui insiste.
    """
    mail.outbox.clear()
    assert relancer_essais() == 1
    assert len(mail.outbox) == 1

    # Deuxième passage, le même jour, sans rien changer.
    assert relancer_essais() == 0
    assert len(mail.outbox) == 1, "la relance est repartie une seconde fois"

    assert RelanceEssai.objects.filter(abonnement=essai_a_trois_jours, seuil=3).count() == 1


@pytest.mark.django_db
def test_seuls_l_administrateur_et_le_directeur_general_recoivent(essai_a_trois_jours, equipe):
    """Un chef de chantier n'a rien à faire d'un email de facturation — §2.2."""
    mail.outbox.clear()
    relancer_essais()

    assert len(mail.outbox) == 1
    destinataires = set(mail.outbox[0].to)
    assert "ad.relance@demo.ci" in destinataires
    assert "dg.relance@demo.ci" in destinataires
    assert "cc.relance@demo.ci" not in destinataires, "le chef de chantier a été sollicité"


@pytest.mark.django_db
def test_le_bilan_est_compte_dans_le_schema_du_client(essai_a_trois_jours, equipe):
    """Le piège de la règle 3, et il ne lève aucune erreur.

    Sans `schema_context`, la tâche compte les projets de `public` — c'est-à-dire
    aucun — et annonce au client qu'il n'a rien construit. **Zéro est un nombre
    valide** : rien ne signale la faute.
    """
    with schema_context(SCHEMA):
        nb_projets = Projet.objects.count()

    mail.outbox.clear()
    relancer_essais()

    corps = mail.outbox[0].body
    assert f"{nb_projets} projet" in corps, corps
    # Trois comptes sont annoncés, et aucun ne doit être celui de `public`.
    assert "3 collaborateurs" in corps, corps


@pytest.mark.django_db
def test_les_deux_formats_partent_ensemble(essai_a_trois_jours, equipe):
    """Un client qui refuse le HTML doit lire le message quand même."""
    mail.outbox.clear()
    relancer_essais()

    message = mail.outbox[0]
    assert message.body, "le corps texte est vide"
    formats = [type_ for _, type_ in message.alternatives]
    assert "text/html" in formats, "aucune version HTML"

    html = next(contenu for contenu, type_ in message.alternatives if type_ == "text/html")
    # La règle §11.1 : le lien est un bouton, **et** l'URL est écrite en clair.
    assert html.count("/parametres/abonnement") >= 2, "l'URL n'est pas visible sous le bouton"


@pytest.mark.django_db
def test_a_j_plus_zero_l_essai_passe_en_lecture_seule(essai_a_trois_jours, equipe):
    """J+0 pose le statut et l'horodatage — il ne coupe pas l'accès lui-même."""
    aujourdhui = timezone.localdate()
    essai_a_trois_jours.fin_essai = aujourdhui
    essai_a_trois_jours.save(update_fields=["fin_essai", "modifie_le"])

    mail.outbox.clear()
    relancer_essais()

    essai_a_trois_jours.refresh_from_db()
    assert essai_a_trois_jours.statut == Abonnement.Statut.SUSPENDU
    assert essai_a_trois_jours.lecture_seule_depuis is not None
    assert "lecture seule" in mail.outbox[0].body
