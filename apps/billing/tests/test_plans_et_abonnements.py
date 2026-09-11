"""Plans et abonnements — MLD §4.3 et §4.4, parcours d'essai T-025.

**Le test qui compte le plus ici n'est pas technique.** C'est celui qui vérifie
qu'aucun tarif n'a été inventé : l'arbitrage A7 est ouvert, et un montant
plausible posé « en attendant » arriverait en production sans que personne ne se
souvienne qu'il était un bouche-trou.
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.billing.models import JOURS_ESSAI, Abonnement, Plan
from apps.core.enums import StatutEntreprise
from apps.tenants.models import Entreprise


@pytest.fixture
def plans(db):
    from django.core.management import call_command

    call_command("peupler_plans", verbosity=0)
    return Plan.objects.all()


@pytest.fixture
def entreprise(db):
    """Une entreprise **sans son schéma**.

    Deux pièges, tous deux invisibles à la lecture :

    · `auto_create_schema` est un attribut de **classe** de `TenantMixin`, pas
      un champ. Le passer à `create()` lève un `TypeError` ;
    · **`schema_context` est indispensable**, même si cette table vit dans
      `public`. `TenantMixin.save()` refuse : « Can't create tenant outside the
      public schema ». *Ces cinq tests passaient isolément et échouaient dans la
      suite complète* — un test précédent laisse la connexion positionnée sur
      `demo`, et rien ne la remet en place. L'échec accuse alors la fixture, pas
      le test qui a déplacé la connexion.
    """
    with schema_context(get_public_schema_name()):
        entreprise = Entreprise(
            schema_name="essai_billing",
            raison_sociale="Essai Billing",
            email_contact="dg@essai-billing.ci",
            statut=StatutEntreprise.ESSAI,
        )
        entreprise.auto_create_schema = False
        entreprise.save()
        yield entreprise


# ---------------------------------------------------------------------------
# Forfaits BTP — Tarifs et Quotas
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_tarifs_plans_btp_configures(plans):
    """Les 3 forfaits BTP portent leurs tarifs configurés (en centimes de FCFA)."""
    assert plans.filter(est_actif=True).count() == 3
    for plan in plans.filter(est_actif=True):
        assert plan.prix_mensuel_montant is not None, plan.libelle
        assert plan.prix_annuel_montant is not None, plan.libelle
        assert plan.tarif_connu is True


@pytest.mark.django_db
def test_peupler_les_plans_est_idempotent(plans):
    """Relancer la commande ne crée pas de doublons."""
    from django.core.management import call_command

    call_command("peupler_plans", verbosity=0)

    assert Plan.objects.filter(est_actif=True).count() == 3
    assert Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE).prix_mensuel_montant == 4_900_000


@pytest.mark.django_db
def test_illimite_se_dit_null_et_jamais_zero(plans):
    """Confondre les deux ferait du plan le plus cher le plus restrictif."""
    promoteur = Plan.objects.get(code=Plan.Code.PROMOTEUR)
    batisseur = Plan.objects.get(code=Plan.Code.BATISSEUR)

    assert promoteur.limite_projets is None
    assert promoteur.limite_utilisateurs is None
    assert batisseur.limite_projets == 3


@pytest.mark.django_db
def test_un_prix_negatif_est_refuse_en_base(plans):
    """La contrainte vit en base, pas seulement dans un service."""
    mo = Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE)

    with pytest.raises(IntegrityError), transaction.atomic():
        Plan.objects.filter(pk=mo.pk).update(prix_mensuel_montant=-1)


# ---------------------------------------------------------------------------
# L'abonnement d'essai
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_compteur_de_jours_se_calcule_et_ne_se_stocke_pas(plans, entreprise):
    """Une valeur figée en base serait fausse dès le lendemain, et personne ne
    la verrait vieillir."""
    debut = timezone.localdate()
    abonnement = Abonnement.objects.create(
        entreprise=entreprise,
        plan=Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE),
        date_debut=debut,
        date_fin=debut + timedelta(days=JOURS_ESSAI),
        fin_essai=debut + timedelta(days=JOURS_ESSAI),
    )

    assert abonnement.jours_essai_restants == JOURS_ESSAI

    abonnement.fin_essai = debut - timedelta(days=1)
    # Jamais négatif : « -3 jours restants » n'est pas une information.
    assert abonnement.jours_essai_restants == 0

    abonnement.statut = Abonnement.Statut.ACTIF
    assert abonnement.jours_essai_restants is None


@pytest.mark.django_db
def test_une_seule_entreprise_ne_peut_avoir_deux_abonnements_vivants(plans, entreprise):
    """Deux essais simultanés donneraient deux compteurs, et deux réponses à
    « quand expire mon accès ? »."""
    debut = timezone.localdate()
    commun = {
        "entreprise": entreprise,
        "plan": Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE),
        "date_debut": debut,
        "date_fin": debut + timedelta(days=30),
    }
    Abonnement.objects.create(statut=Abonnement.Statut.ESSAI, **commun)

    with pytest.raises(IntegrityError), transaction.atomic():
        Abonnement.objects.create(statut=Abonnement.Statut.ACTIF, **commun)


@pytest.mark.django_db
def test_un_abonnement_resilie_libere_la_place(plans, entreprise):
    """La contrainte ne vaut que pour `ESSAI` et `ACTIF` : un client qui revient
    ne doit pas buter sur son ancien abonnement."""
    debut = timezone.localdate()
    commun = {
        "entreprise": entreprise,
        "plan": Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE),
        "date_debut": debut,
        "date_fin": debut + timedelta(days=30),
    }
    Abonnement.objects.create(statut=Abonnement.Statut.RESILIE, **commun)
    Abonnement.objects.create(statut=Abonnement.Statut.ESSAI, **commun)

    assert Abonnement.objects.filter(entreprise=entreprise).count() == 2


@pytest.mark.django_db
def test_une_date_de_suppression_sans_annonce_est_refusee(plans, entreprise):
    """**Aucune date de suppression ne peut exister sans l'annonce qui l'a
    précédée** — MLD §4.4.

    La règle vivrait sinon dans un service, qu'une commande d'administration
    contournerait sans le savoir.
    """
    debut = timezone.localdate()
    abonnement = Abonnement.objects.create(
        entreprise=entreprise,
        plan=Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE),
        date_debut=debut,
        date_fin=debut + timedelta(days=30),
        statut=Abonnement.Statut.RESILIE,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Abonnement.objects.filter(pk=abonnement.pk).update(
            suppression_prevue_le=debut + timedelta(days=90)
        )


@pytest.mark.django_db
def test_une_fin_anterieure_au_debut_est_refusee(plans, entreprise):
    debut = timezone.localdate()

    with pytest.raises(IntegrityError), transaction.atomic():
        Abonnement.objects.create(
            entreprise=entreprise,
            plan=Plan.objects.get(code=Plan.Code.MAITRE_OEUVRE),
            date_debut=debut,
            date_fin=debut - timedelta(days=1),
        )
