"""Renouvellement et rotation des jetons — correction du défaut **D-1**.

Le test qui manquait est le premier : **rejouer** un jeton déjà utilisé.
Les réglages étaient corrects, `manage.py check` ne signalait rien, la suite
passait — et la rotation ne révoquait aucun jeton. Une suite verte ne prouve
pas qu'une protection fonctionne ; seul le test qui tente ce qu'elle doit
interdire le prouve.
"""

import time

import pytest
from django.core.cache import cache
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.accounts.services import liste_noire
from apps.accounts.services.renouvellement import FENETRE_GRACE
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"
URL_CONNEXION = "/api/v1/auth/token/"
URL_RENOUVELLEMENT = "/api/v1/auth/token/refresh/"
MOT_DE_PASSE = "MotDePasse1!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture(autouse=True)
def cache_propre():
    """La liste noire est un cache partagé : un test ne doit rien laisser."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def utilisateur(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="rotation@btp.ci").delete()
        yield Utilisateur.objects.create_user(
            email="rotation@btp.ci",
            password=MOT_DE_PASSE,
            nom="Bamba",
            prenom="Kouamé",
            role_global=RoleGlobal.CHEF_PROJET,
            statut=StatutUtilisateur.ACTIF,
        )


def connecter(client, origine="WEB"):
    return client.post(
        URL_CONNEXION,
        {"email": "rotation@btp.ci", "mot_de_passe": MOT_DE_PASSE, "origine": origine},
        format="json",
    ).json()


def renouveler(client, jeton):
    return client.post(URL_RENOUVELLEMENT, {"refresh": jeton}, format="json")


def code(reponse):
    return reponse.json()["erreur"]["code"]


# --------------------------------------------------------------------------
# 1. Le test qui manquait
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_un_jeton_deja_utilise_est_refuse(client, utilisateur):
    """**D-1.** C'est le seul test qui prouve que la rotation révoque.

    Vérifier les réglages ne prouve rien : `ROTATE_REFRESH_TOKENS` et
    `BLACKLIST_AFTER_ROTATION` étaient à `True`, et la rotation ne révoquait
    rien du tout.
    """
    jetons = connecter(client)

    premier = renouveler(client, jetons["refresh"])
    assert premier.status_code == 200

    # Hors de la fenêtre de grâce : c'est un rejeu, pas un réessai.
    liste_noire.revoquer_jeton(
        _jti(jetons["refresh"]), ttl=3600, motif=liste_noire.MOTIF_DECONNEXION
    )
    rejeu = renouveler(client, jetons["refresh"])

    assert rejeu.status_code == 401
    assert code(rejeu) == "jeton_revoque"


@pytest.mark.django_db
def test_la_rotation_emet_un_jeton_de_renouvellement_different(client, utilisateur):
    jetons = connecter(client)
    renouvelle = renouveler(client, jetons["refresh"]).json()

    assert set(renouvelle) == {"access", "refresh"}
    assert renouvelle["refresh"] != jetons["refresh"]


# --------------------------------------------------------------------------
# 2. La fenêtre de grâce — T-008 §4.2
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_un_rejeu_dans_la_minute_est_benin(client, utilisateur):
    """Sur un chantier, le réseau qui tombe pendant un renouvellement est le
    quotidien : le téléphone rejoue. Le Socle §2.2 interdit qu'un chef de
    chantier voie un écran de connexion en pleine saisie."""
    jetons = connecter(client, origine="MOBILE")

    assert renouveler(client, jetons["refresh"]).status_code == 200
    assert renouveler(client, jetons["refresh"]).status_code == 200


@pytest.mark.django_db
def test_la_fenetre_de_grace_ne_glisse_pas(client, utilisateur):
    """Un rejeu bénin ne réécrit pas la clé de révocation.

    La réécrire ancrerait la fenêtre au dernier rejeu, et un jeton rejoué
    toutes les cinquante secondes vivrait indéfiniment.
    """
    jetons = connecter(client)
    jti = _jti(jetons["refresh"])

    renouveler(client, jetons["refresh"])
    _, premier_horodatage = liste_noire.revocation(jti)

    time.sleep(0.05)
    renouveler(client, jetons["refresh"])
    _, second_horodatage = liste_noire.revocation(jti)

    assert second_horodatage == premier_horodatage


@pytest.mark.django_db
def test_un_rejeu_hors_fenetre_revoque_la_session(client, utilisateur):
    jetons = connecter(client)
    sid = _claim(jetons["refresh"], "sid")

    renouvelle = renouveler(client, jetons["refresh"]).json()

    # On vieillit artificiellement la révocation au-delà de la fenêtre.
    liste_noire.revoquer_jeton(_jti(jetons["refresh"]), ttl=3600, motif=liste_noire.MOTIF_ROTATION)
    cle = f"ccd:jwt:revoque:{SCHEMA}:{_jti(jetons['refresh'])}"
    cache.set(cle, f"rotation:{time.time() - FENETRE_GRACE - 1:.3f}", 3600)

    rejeu = renouveler(client, jetons["refresh"])
    assert rejeu.status_code == 401

    # La session entière tombe : le jeton légitime émis par la rotation ne
    # vaut plus rien non plus. Révoquer le seul `jti` présenté laisserait le
    # voleur continuer avec la paire suivante.
    assert liste_noire.session_revoquee(sid)
    assert renouveler(client, renouvelle["refresh"]).status_code == 401


# --------------------------------------------------------------------------
# 3. La session traverse la chaîne de rotation
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_sid_est_constant_sur_la_chaine(client, utilisateur):
    jetons = connecter(client)
    sid = _claim(jetons["refresh"], "sid")

    courant = jetons["refresh"]
    for _ in range(3):
        courant = renouveler(client, courant).json()["refresh"]
        assert _claim(courant, "sid") == sid


@pytest.mark.django_db
def test_l_origine_survit_a_la_rotation(client, utilisateur):
    """Sans cela, un mobile passerait de 24 h à 8 h au premier renouvellement."""
    jetons = connecter(client, origine="MOBILE")
    renouvelle = renouveler(client, jetons["refresh"]).json()

    assert _claim(renouvelle["refresh"], "origine") == "MOBILE"


# --------------------------------------------------------------------------
# 4. Les autres portées de révocation
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_revoquer_l_utilisateur_refuse_tous_ses_jetons(client, utilisateur):
    """Socle §2.2 — « session invalidée immédiatement sur tous les appareils »."""
    web = connecter(client)
    mobile = connecter(client, origine="MOBILE")

    time.sleep(1.1)  # l'époque se compare à `iat`, qui est à la seconde
    with schema_context(SCHEMA):
        liste_noire.revoquer_utilisateur(str(utilisateur.pk), ttl=3600)

    assert renouveler(client, web["refresh"]).status_code == 401
    assert renouveler(client, mobile["refresh"]).status_code == 401


@pytest.mark.django_db
def test_un_compte_desactive_ne_renouvelle_plus(client, utilisateur):
    jetons = connecter(client)

    with schema_context(SCHEMA):
        utilisateur.is_active = False
        utilisateur.save(update_fields=["is_active"])

    assert renouveler(client, jetons["refresh"]).status_code == 401


@pytest.mark.django_db
def test_un_jeton_illisible_est_refuse(client, utilisateur):
    reponse = renouveler(client, "ceci.nest.pas.un.jeton")

    assert reponse.status_code == 401
    assert code(reponse) == "jeton_invalide"


# --------------------------------------------------------------------------
# 5. L'isolation — la clé porte le schéma
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_la_cle_de_revocation_porte_le_schema(client, utilisateur):
    """Redis est partagé par tous les clients : sans le schéma dans la clé, le
    `jti` révoqué d'une entreprise refuserait le jeton d'une autre."""
    jetons = connecter(client)
    renouveler(client, jetons["refresh"])

    with schema_context(SCHEMA):
        assert liste_noire.revocation(_jti(jetons["refresh"])) is not None
    with schema_context("public"):
        assert liste_noire.revocation(_jti(jetons["refresh"])) is None


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------
def _claim(jeton: str, nom: str):
    from rest_framework_simplejwt.tokens import UntypedToken

    return UntypedToken(jeton).payload.get(nom)


def _jti(jeton: str) -> str:
    return _claim(jeton, "jti")
