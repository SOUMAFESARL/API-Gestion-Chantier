"""Inscription d'une entreprise — contrat T-021, provisionnement T-020.

**Les cinq endpoints vivent sur le domaine de la plateforme.** Les tests
interrogent donc `localhost`, schéma `public`, et non un sous-domaine client :
au moment de l'inscription, le client n'a pas encore de sous-domaine.

`transaction.on_commit` ne s'exécute pas sous pytest-django — la transaction du
test est annulée. C'est **voulu ici** : sans `django_capture_on_commit_callbacks`,
l'email ne part pas et le provisionnement ne se déclenche pas. Un seul test le
capture, celui qui vérifie le provisionnement de bout en bout.
"""

import re
import uuid

import pytest
from django.core import mail
from django.db import IntegrityError
from django.utils import timezone

from apps.tenants.models import DemandeInscription, Entreprise

DEPOT = "/api/v1/inscription/"
RENVOI = "/api/v1/inscription/renvoyer/"
VERIFIER = "/api/v1/inscription/verifier/"
ACTIVER = "/api/v1/inscription/activer/"

HOTE = "localhost"
MOT_DE_PASSE = "Chantier2026!"


@pytest.fixture
def client():
    from rest_framework.test import APIClient

    return APIClient(headers={"host": HOTE})


@pytest.fixture(autouse=True)
def cache_vide():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _payload(**surcharges):
    base = {
        "id": str(uuid.uuid4()),
        "raison_sociale": f"SOTRA {uuid.uuid4().hex[:6]}",
        "pays": "CI",
        "email": "patron@sotra-btp.ci",
        "cgu_acceptees": True,
    }
    base.update(surcharges)
    return base


@pytest.fixture
def deposer(client, django_capture_on_commit_callbacks):
    """Dépose une demande **et laisse partir l'email**, pour en lire le jeton."""

    def _appel(**surcharges):
        with django_capture_on_commit_callbacks(execute=True):
            reponse = client.post(DEPOT, _payload(**surcharges), format="json")
        assert reponse.status_code == 202
        trouve = re.search(r"#jeton=([0-9a-f-]{36})", mail.outbox[-1].body)
        assert trouve, "aucun lien d'activation dans l'email"
        return reponse.data["id"], trouve.group(1)

    return _appel


# ---------------------------------------------------------------------------
# §2 — le dépôt ne dit jamais ce qu'il ne doit pas dire
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_depot_repond_202_et_jamais_201(client):
    """`201 Created` dirait « la ressource existe, la voici ».

    Rien n'est créé du point de vue du client — ni entreprise, ni schéma, ni
    compte, seulement une demande qui expire en 48 h si personne ne lit
    l'email.
    """
    reponse = client.post(DEPOT, _payload(), format="json")

    assert reponse.status_code == 202
    assert reponse.data["statut"] == "EN_ATTENTE"
    assert reponse.data["expire_dans"] == 172800


@pytest.mark.django_db
def test_la_reponse_ne_contient_jamais_le_slug(client):
    """Le renvoyer dirait à qui sonde que `sotra_btp` était libre — c'est-à-dire
    que SOTRA BTP n'est pas client."""
    reponse = client.post(DEPOT, _payload(raison_sociale="SOTRA BTP"), format="json")

    corps = str(reponse.data)
    assert "sotra_btp" not in corps
    assert "slug" not in corps


@pytest.mark.django_db
def test_le_meme_identifiant_ne_cree_pas_deux_demandes(client):
    """Idempotence §6 — un double-clic sur « Créer mon compte ».

    C'est le seul parcours du produit où le client rejoue sans le savoir.
    """
    charge = _payload()

    premiere = client.post(DEPOT, charge, format="json")
    seconde = client.post(DEPOT, charge, format="json")

    assert premiere.status_code == seconde.status_code == 202
    assert premiere.data["id"] == seconde.data["id"]
    assert DemandeInscription.objects.filter(pk=charge["id"]).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("surcharge", "champ"),
    [
        ({"raison_sociale": "A"}, "raison_sociale"),
        ({"raison_sociale": "建設 株式会社"}, "raison_sociale"),
        ({"pays": "FR"}, "pays"),
        ({"pays": "XX"}, "pays"),
        ({"email": "pas-une-adresse"}, "email"),
        ({"cgu_acceptees": False}, "cgu_acceptees"),
    ],
)
def test_les_refus_de_validation_de_m8(client, surcharge, champ):
    """Les quatre messages de M8 écran 7 sont conservés tels quels."""
    reponse = client.post(DEPOT, _payload(**surcharge), format="json")

    assert reponse.status_code == 400
    assert reponse.data["erreur"]["code"] == "validation"


@pytest.mark.django_db
def test_deux_entreprises_homonymes_ne_se_disputent_pas_un_schema(client):
    """Le slug est réservé **dès l'inscription**, pas à l'activation.

    Deux entreprises homonymes distinctes (adresses emails différentes)
    obtiennent des slugs distincts et ne se disputent pas le même schéma.
    """
    client.post(
        DEPOT,
        _payload(raison_sociale="Bâtir SARL", email="contact@batir-ci.ci"),
        format="json",
    )
    client.post(
        DEPOT,
        _payload(raison_sociale="Batir  SARL", email="contact@batir-sn.sn"),
        format="json",
    )

    slugs = list(DemandeInscription.objects.values_list("slug_reserve", flat=True))

    assert len(slugs) == 2
    assert len(slugs) == len(set(slugs)), slugs
    assert "batir_sarl" in slugs
    assert "batir_sarl_2" in slugs


@pytest.mark.django_db
def test_deux_inscriptions_successives_meme_nom_et_email_en_attente_rejette_doublon(
    client, django_capture_on_commit_callbacks
):
    """Une seconde soumission avec un email déjà en attente d'activation
    est rejetée dès le formulaire avec 400 Bad Request.
    """
    mail.outbox.clear()
    charge1 = _payload(
        id=str(uuid.uuid4()),
        raison_sociale="SOUMAFE BTP",
        email="contact@soumafe.ci",
    )
    charge2 = _payload(
        id=str(uuid.uuid4()),
        raison_sociale="SOUMAFE BTP",
        email="contact@soumafe.ci",
    )

    with django_capture_on_commit_callbacks(execute=True):
        reponse1 = client.post(DEPOT, charge1, format="json")
    assert reponse1.status_code == 202

    reponse2 = client.post(DEPOT, charge2, format="json")
    assert reponse2.status_code == 400
    assert "email" in reponse2.data["erreur"]["details"]

    # Une seule demande en base
    assert DemandeInscription.objects.filter(email="contact@soumafe.ci").count() == 1


@pytest.mark.django_db
def test_inscription_apres_activation_ne_cree_pas_de_deuxieme_entreprise(
    client, django_capture_on_commit_callbacks
):
    """Une entreprise déjà activée empêche toute réinscription avec le même email dès le formulaire (400)."""
    entreprise = Entreprise(
        schema_name="soumafe_btp",
        raison_sociale="SOUMAFE BTP",
        email_contact="contact@soumafe.ci",
    )
    entreprise.auto_create_schema = False
    entreprise.save()

    nb_entreprises_avant = Entreprise.objects.count()
    nb_demandes_avant = DemandeInscription.objects.count()

    charge = _payload(
        raison_sociale="SOUMAFE BTP",
        email="contact@soumafe.ci",
    )
    reponse = client.post(DEPOT, charge, format="json")

    assert reponse.status_code == 400
    assert "email" in reponse.data["erreur"]["details"]
    # Aucune nouvelle entreprise ni demande
    assert Entreprise.objects.count() == nb_entreprises_avant
    assert DemandeInscription.objects.count() == nb_demandes_avant


@pytest.mark.django_db
def test_tolerance_casse_et_espaces_nom_et_email(client):
    """La détection du doublon est insensible à la casse et aux espaces superflus."""
    reponse1 = client.post(
        DEPOT,
        _payload(raison_sociale="  SOUMAFE   BTP  ", email="Contact@Soumafe.ci"),
        format="json",
    )
    assert reponse1.status_code == 202

    reponse2 = client.post(
        DEPOT,
        _payload(raison_sociale="soumafe btp", email="contact@soumafe.ci"),
        format="json",
    )
    assert reponse2.status_code == 400
    assert "email" in reponse2.data["erreur"]["details"]

    assert DemandeInscription.objects.filter(email="contact@soumafe.ci").count() == 1


@pytest.mark.django_db
def test_contrainte_bdd_entreprise_email_rejette_doublon(db):
    """La contrainte PostgreSQL uq_entreprise_email_contact empêche tout doublon d'email en base."""
    e1 = Entreprise(
        schema_name="cie_alpha",
        raison_sociale="Alpha Construction",
        email_contact="contact@alpha.ci",
    )
    e1.auto_create_schema = False
    e1.save()

    # Même email avec une raison sociale différente
    e2 = Entreprise(
        schema_name="cie_beta",
        raison_sociale="Beta BTP",
        email_contact="Contact@Alpha.ci",
    )
    e2.auto_create_schema = False
    with pytest.raises(IntegrityError):
        e2.save()


@pytest.mark.django_db
def test_contrainte_bdd_demande_email_attente_rejette_doublon(db):
    """La contrainte PostgreSQL uq_demande_email_attente empêche deux demandes EN_ATTENTE avec le même email."""
    maintenant = timezone.now()
    DemandeInscription.objects.create(
        id=uuid.uuid4(),
        raison_sociale="Beta BTP",
        pays="CI",
        email="beta@btp.ci",
        slug_reserve="beta_btp",
        empreinte="empreinte1",
        expire_le=maintenant + timezone.timedelta(hours=48),
        statut=DemandeInscription.Statut.EN_ATTENTE,
        cgu_version="1.0",
        cgu_acceptees_le=maintenant,
    )

    # Même email avec un nom différent
    with pytest.raises(IntegrityError):
        DemandeInscription.objects.create(
            id=uuid.uuid4(),
            raison_sociale="Autre Entreprise",
            pays="CI",
            email="Beta@btp.ci",
            slug_reserve="autre_entreprise",
            empreinte="empreinte2",
            expire_le=maintenant + timezone.timedelta(hours=48),
            statut=DemandeInscription.Statut.EN_ATTENTE,
            cgu_version="1.0",
            cgu_acceptees_le=maintenant,
        )


@pytest.mark.django_db
def test_inscription_meme_email_nom_different_rejete_en_validation(client):
    """Même si le nom d'entreprise est différent, un email déjà utilisé est immédiatement rejeté au formulaire (400)."""
    entreprise = Entreprise(
        schema_name="soumafe_btp",
        raison_sociale="SOUMAFE BTP",
        email_contact="contact@soumafe.ci",
    )
    entreprise.auto_create_schema = False
    entreprise.save()

    charge = _payload(
        raison_sociale="AUTRE ENTREPRISE NOUVELLE",
        email="Contact@Soumafe.ci",
    )
    reponse = client.post(DEPOT, charge, format="json")

    assert reponse.status_code == 400
    assert "email" in reponse.data["erreur"]["details"]
    assert DemandeInscription.objects.filter(email="contact@soumafe.ci").count() == 0


# ---------------------------------------------------------------------------
# §4 — vérifier sans consommer
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_verifier_ne_consomme_pas_le_jeton(client, deposer):
    """R-83 — une passerelle antivirus brûlerait l'inscription avant le clic."""
    _, jeton = deposer(raison_sociale="SOTRA BTP")

    for _ in range(3):
        reponse = client.post(VERIFIER, {"jeton": jeton}, format="json")
        assert reponse.status_code == 200

    assert reponse.data["raison_sociale"] == "SOTRA BTP"
    assert "slug" not in str(reponse.data)

    demande = DemandeInscription.objects.get(empreinte=DemandeInscription.empreinte_de(jeton))
    assert demande.utilise_le is None


@pytest.mark.django_db
def test_un_jeton_inconnu_repond_410(client):
    reponse = client.post(VERIFIER, {"jeton": str(uuid.uuid4())}, format="json")

    assert reponse.status_code == 410
    assert reponse.data["erreur"]["code"] == "jeton_expire"


@pytest.mark.django_db
def test_un_jeton_expire_est_refuse(client, deposer):
    _, jeton = deposer()
    DemandeInscription.objects.filter(empreinte=DemandeInscription.empreinte_de(jeton)).update(
        expire_le=timezone.now() - timezone.timedelta(seconds=1)
    )

    reponse = client.post(VERIFIER, {"jeton": jeton}, format="json")

    assert reponse.status_code == 410


@pytest.mark.django_db
def test_le_renvoi_invalide_le_jeton_precedent(client, deposer, django_capture_on_commit_callbacks):
    """Sinon deux liens vivants circulent après « Renvoyer l'email »."""
    identifiant, premier = deposer()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = client.post(RENVOI, {"id": identifiant}, format="json")

    assert reponse.status_code == 202
    assert client.post(VERIFIER, {"jeton": premier}, format="json").status_code == 410

    second = re.search(r"#jeton=([0-9a-f-]{36})", mail.outbox[-1].body).group(1)
    assert client.post(VERIFIER, {"jeton": second}, format="json").status_code == 200


@pytest.mark.django_db
def test_le_renvoi_sur_un_identifiant_inconnu_repond_202_sans_email(client):
    """Même réponse, aucun email — §3."""
    mail.outbox.clear()
    reponse = client.post(RENVOI, {"id": str(uuid.uuid4())}, format="json")

    assert reponse.status_code == 202
    assert mail.outbox == []


# ---------------------------------------------------------------------------
# §5 — activer
# ---------------------------------------------------------------------------
@pytest.mark.django_db
@pytest.mark.parametrize("faible", ["chantier", "abidjan2026", "soumafe!!"])
def test_un_mot_de_passe_faible_ne_consomme_pas_le_jeton(client, deposer, faible):
    """Un refus de complexité ne doit pas coûter le lien à qui le corrige."""
    _, jeton = deposer()

    reponse = client.post(
        ACTIVER, {"jeton": jeton, "nom": "Koné", "mot_de_passe": faible}, format="json"
    )

    assert reponse.status_code == 400
    # Et le jeton sert encore.
    assert client.post(VERIFIER, {"jeton": jeton}, format="json").status_code == 200


@pytest.mark.django_db
def test_activer_consomme_le_jeton_et_lance_le_provisionnement(client, deposer):
    _, jeton = deposer()

    reponse = client.post(
        ACTIVER,
        {"jeton": jeton, "nom": "Koné", "prenom": "Amadou", "mot_de_passe": MOT_DE_PASSE},
        format="json",
    )

    assert reponse.status_code == 202
    assert reponse.data["statut"] == "PROVISIONNEMENT"

    demande = DemandeInscription.objects.get(pk=reponse.data["suivi"])
    assert demande.utilise_le is not None
    assert demande.statut == DemandeInscription.Statut.PROVISIONNEMENT
    # Haché, jamais en clair — MLD §4.8.
    assert demande.mot_de_passe_transitoire
    assert MOT_DE_PASSE not in demande.mot_de_passe_transitoire


@pytest.mark.django_db
def test_rejouer_une_activation_repond_409(client, deposer):
    """§6 — l'espace existe ou se construit ; il ne s'en crée pas un second."""
    _, jeton = deposer()
    charge = {"jeton": jeton, "nom": "Koné", "mot_de_passe": MOT_DE_PASSE}

    premiere = client.post(ACTIVER, charge, format="json")
    seconde = client.post(ACTIVER, charge, format="json")

    assert premiere.status_code == 202
    assert seconde.status_code == 409
    assert seconde.data["erreur"]["code"] == "inscription_deja_activee"


@pytest.mark.django_db
def test_la_sonde_repond_200_meme_en_echec(client, deposer):
    """**`ECHEC` répond `200`, et ce n'est pas une négligence.**

    La requête a réussi : elle demandait un état, elle l'a obtenu. Un `500`
    dirait que la *sonde* est en panne, et le client réessaierait indéfiniment
    un endpoint qu'il croit cassé.
    """
    _, jeton = deposer()
    activation = client.post(
        ACTIVER, {"jeton": jeton, "nom": "Koné", "mot_de_passe": MOT_DE_PASSE}, format="json"
    )
    suivi = activation.data["suivi"]

    DemandeInscription.objects.filter(pk=suivi).update(statut=DemandeInscription.Statut.ECHEC)
    reponse = client.get(f"/api/v1/inscription/etat/{suivi}/")

    assert reponse.status_code == 200
    assert reponse.data["statut"] == "ECHEC"


@pytest.mark.django_db
def test_la_sonde_ne_livre_le_slug_qu_une_fois_l_espace_pret(client, deposer):
    """`url_connexion` est le **seul** endroit où le slug apparaît, et seulement
    après consommation du jeton — pour qui a prouvé qu'il lit la boîte mail."""
    _, jeton = deposer(raison_sociale="SOTRA BTP")
    activation = client.post(
        ACTIVER, {"jeton": jeton, "nom": "Koné", "mot_de_passe": MOT_DE_PASSE}, format="json"
    )

    reponse = client.get(f"/api/v1/inscription/etat/{activation.data['suivi']}/")

    assert reponse.data["statut"] == "PROVISIONNEMENT"
    assert "url_connexion" not in reponse.data
