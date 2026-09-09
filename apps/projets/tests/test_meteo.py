"""Tests du référentiel des localités et du service météo."""

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import RoleGlobal
from apps.projets.referentiels.villes import (
    LOCALITES,
    lister_villes,
    nom_agglomeration,
    resoudre_coordonnees,
)
from apps.projets.services.meteo import PAYS_METEO, interpreter_code_wmo, obtenir_meteo

# Les neuf pays où une entreprise peut s'inscrire — `PAYS_AUTORISES` du
# serializer d'inscription. Le référentiel doit couvrir **exactement** ceux-là :
# un pays de plus n'est atteignable par personne, un pays de moins laisse un
# client devant une liste de villes vide.
PAYS_INSCRIPTION = {"CI", "SN", "CM", "BF", "ML", "TG", "BJ", "GN", "GA"}

SCHEMA = "demo"
HOTE = "demo.localhost"
URL_METEO = "/api/v1/projets/meteo/"
URL_VILLES = "/api/v1/projets/referentiels/villes/"


@pytest.fixture
def utilisateur(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="test-meteo@demo.ci").delete()
        u = Utilisateur.objects.create_user(
            email="test-meteo@demo.ci",
            password="Secret123!",
            nom="Testeur",
            prenom="Jean",
            role_global=RoleGlobal.ADMIN,
        )
        yield u


@pytest.fixture
def client_auth(utilisateur):
    c = APIClient(headers={"host": HOTE})
    c.force_authenticate(user=utilisateur)
    return c


# ---------------------------------------------------------------------------
# 1. Tests du Référentiel des Villes et Communes de Côte d'Ivoire
# ---------------------------------------------------------------------------


def test_referentiel_villes_ci_complet():
    """Le référentiel contient les communes d'Abidjan et les villes régionales."""
    villes = lister_villes("CI")
    assert len(villes) >= 40

    noms = [v["nom"] for v in villes]
    assert "Cocody" in noms
    assert "Yopougon" in noms
    assert "Plateau" in noms
    assert "Yamoussoukro" in noms
    assert "Bouaké" in noms
    assert "San-Pédro" in noms
    assert "Korhogo" in noms

    for v in villes:
        assert "nom" in v
        assert "latitude" in v
        assert "longitude" in v
        assert -10.0 <= v["longitude"] <= -2.0
        assert 4.0 <= v["latitude"] <= 11.0


def test_le_referentiel_couvre_exactement_les_pays_de_l_inscription():
    """Ni pays orphelin, ni pays d'inscription sans villes.

    C'est la divergence qu'on ne voit pas : ouvrir l'inscription à un pays de
    plus se fait dans un serializer, à l'autre bout du code, et l'entreprise
    créée arrive alors sur un champ « ville » vide sans que rien ne l'ait dit.
    """
    assert set(LOCALITES) == PAYS_INSCRIPTION

    for pays in PAYS_INSCRIPTION:
        localites = lister_villes(pays)
        assert len(localites) >= 15, pays

        # Chaque localité est réellement située : un point à (0, 0) tombe dans
        # le golfe de Guinée, et l'API météo répondrait sans broncher.
        for loc in localites:
            assert loc["nom"].strip()
            assert loc["region"].strip()
            assert loc["latitude"] or loc["longitude"]
            assert -35.0 <= loc["latitude"] <= 40.0
            assert -20.0 <= loc["longitude"] <= 20.0

        # Un nom en double dans un même pays fait deux entrées identiques dans
        # la liste déroulante — impossible de savoir laquelle on a choisie.
        noms = [loc["nom"] for loc in localites]
        assert len(noms) == len(set(noms)), pays

        # Toute localité doit se retrouver par son propre nom, sinon la météo
        # répondra « localité non répertoriée » pour une ville qu'on a proposée.
        for loc in localites:
            assert resoudre_coordonnees(loc["nom"], pays=pays) is not None, (pays, loc["nom"])


def test_le_referentiel_typescript_ne_derive_pas():
    """La liste du frontend est la recopie exacte de celle du serveur.

    Les deux existent parce qu'une liste déroulante ne peut pas attendre le
    réseau pour s'ouvrir. Deux listes que rien ne tient ensemble finissent par
    ne plus dire la même chose, **et personne ne le voit** puisque chacune
    fonctionne : le serveur ne trouve pas la ville que l'écran a proposée, et
    la météo répond « localité non répertoriée » sans autre explication.
    """
    from apps.projets.management.commands.generer_referentiel_villes import (
        CIBLE,
        rendre_typescript,
    )

    assert CIBLE.exists(), CIBLE
    assert CIBLE.read_text(encoding="utf-8") == rendre_typescript(), (
        "Relancer « python manage.py generer_referentiel_villes »."
    )


def test_les_agglomerations_ont_un_groupe_et_un_centre():
    """Là où un groupe « agglomération » existe, il est peuplé et il a un centre."""
    for pays, nom in [("CI", "Abidjan"), ("SN", "Dakar"), ("GN", "Conakry")]:
        assert nom_agglomeration(pays) == nom
        communes = [loc for loc in lister_villes(pays) if loc["agglomeration"]]
        assert len(communes) >= 5, pays

        # Le nom de l'agglomération n'est pas une commune : il doit se résoudre
        # vers son centre, et ce centre doit appartenir au groupe.
        resolution = resoudre_coordonnees(nom, pays=pays)
        assert resolution is not None
        assert resolution[0] in [c["nom"] for c in communes]

    # Les six autres pays présentent une liste simple, sans groupe vide.
    for pays in PAYS_INSCRIPTION - {"CI", "SN", "GN"}:
        assert nom_agglomeration(pays) == ""
        assert not any(loc["agglomeration"] for loc in lister_villes(pays))


def test_resoudre_coordonnees_variations():
    """La résolution gère accents, casse, sous-chaînes et rétrocompatibilité."""
    # Correspondance sous-chaîne sans accent
    res_cocody = resoudre_coordonnees("cocody")
    assert res_cocody is not None
    assert res_cocody[0] == "Cocody"
    assert round(res_cocody[1], 2) == 5.35

    # Rétrocompatibilité : ancienne valeur avec préfixe "Abidjan - Cocody"
    res_legacy = resoudre_coordonnees("Abidjan - Cocody")
    assert res_legacy is not None
    assert res_legacy[0] == "Cocody"

    # Saisie générique "Abidjan" -> redirigé vers Plateau
    res_abidjan = resoudre_coordonnees("Abidjan")
    assert res_abidjan is not None
    assert res_abidjan[0] == "Plateau"

    # Ville régionale avec accent omis
    res_bouake = resoudre_coordonnees("bouake")
    assert res_bouake is not None
    assert res_bouake[0] == "Bouaké"

    # San-Pédro avec espace
    res_sp = resoudre_coordonnees("san pedro")
    assert res_sp is not None
    assert res_sp[0] == "San-Pédro"

    # Nom exact
    res_yam = resoudre_coordonnees("Yamoussoukro")
    assert res_yam is not None
    assert res_yam[0] == "Yamoussoukro"


def test_resoudre_coordonnees_dans_les_neuf_pays():
    """La résolution répond pour les neuf pays, et pour eux seuls.

    Elle répondait `None` dès que le pays n'était pas la Côte d'Ivoire —
    **et c'était la restriction de la météo, pas celle du référentiel.** Les
    deux étaient confondues : impossible de savoir où se trouve Dakar sans
    décider en même temps si on affiche sa température.
    """
    dakar = resoudre_coordonnees("Dakar", pays="SN")
    assert dakar is not None and dakar[0] == "Dakar"

    douala = resoudre_coordonnees("Douala", pays="CM")
    assert douala is not None and round(douala[1], 1) == 4.1

    # Une ville d'un pays, demandée dans un autre, ne se trouve pas : les
    # listes sont cloisonnées par pays, et c'est ce qui empêche un chantier
    # sénégalais de récupérer la météo d'Abidjan.
    assert resoudre_coordonnees("Cocody", pays="SN") is None

    # Un pays hors inscription n'a aucune localité.
    assert resoudre_coordonnees("Cocody", pays="FR") is None
    assert resoudre_coordonnees("Paris", pays="FR") is None


def test_la_meteo_reste_limitee_a_la_cote_d_ivoire():
    """La couverture météo est une décision de produit, et elle est explicite.

    Le référentiel sait résoudre les neuf pays ; ce que la barre affiche
    ailleurs qu'en Côte d'Ivoire n'est pas tranché. Ce test dit lequel des deux
    porte la restriction — le service, pas les données.
    """
    assert frozenset({"CI"}) == PAYS_METEO

    hors_zone = obtenir_meteo(ville="Dakar", pays="SN")
    assert hors_zone["disponible"] is False
    assert hors_zone["raison"] == "PAYS_NON_COUVERT"


# ---------------------------------------------------------------------------
# 2. Tests du Service Météo (Codes WMO, Open-Meteo & Résilience)
# ---------------------------------------------------------------------------


def test_interpreter_code_wmo():
    """L'interprétation WMO associe conditions météo et praticabilité BTP."""
    # 0 -> Ensoleillé, praticable
    desc, praticable, alerte = interpreter_code_wmo(0)
    assert desc == "DEGAGE"
    assert praticable is True
    assert alerte is None

    # 61 -> Pluie modérée, praticable avec vigilance
    desc, praticable, alerte = interpreter_code_wmo(61)
    assert desc == "PLUIE"
    assert praticable is True
    assert alerte == "VIGILANCE_PLUIE"

    # 65 -> Fortes averses, non praticable
    desc, praticable, alerte = interpreter_code_wmo(65)
    assert desc == "AVERSES"
    assert praticable is False
    assert alerte == "INTEMPERIES"

    # 95 -> Orage violent, non praticable
    desc, praticable, alerte = interpreter_code_wmo(95)
    assert desc == "ORAGE"
    assert praticable is False
    assert alerte == "ORAGE"


def test_obtenir_meteo_hors_ci():
    """Un projet hors Côte d'Ivoire renvoie un état indisponible gracieux."""
    resultat = obtenir_meteo("Dakar", pays="SN")
    assert resultat["disponible"] is False
    assert resultat["raison"] == "PAYS_NON_COUVERT"


def test_obtenir_meteo_succes_avec_mock():
    """Succès de récupération de la météo avec calcul de praticabilité."""
    reponse_simulee = {
        "current": {
            "temperature_2m": 30.2,
            "weather_code": 0,
        }
    }
    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value.status = 200
    mock_urlopen.__enter__.return_value.read.return_value = json.dumps(reponse_simulee).encode(
        "utf-8"
    )

    with patch("urllib.request.urlopen", return_value=mock_urlopen):
        resultat = obtenir_meteo("Cocody", pays="CI")

    assert resultat["disponible"] is True
    assert resultat["ville"] == "Cocody"
    assert resultat["temperature"] == 30
    assert resultat["condition"] == "DEGAGE"
    assert resultat["praticable"] is True


def test_obtenir_meteo_panne_reseau_renvoie_temperature_non_disponible():
    """Si l'API météo distante échoue, le système ne crash pas et informe l'utilisateur."""
    with patch("urllib.request.urlopen", side_effect=URLError("Connexion impossible")):
        resultat = obtenir_meteo("Bouaké", pays="CI")

    assert resultat["disponible"] is False
    assert resultat["raison"] == "SERVICE_INDISPONIBLE"
    assert resultat["temperature"] is None


# ---------------------------------------------------------------------------
# 3. Tests des Endpoints API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_api_referentiel_villes(client_auth):
    """Sans paramètre, l'endpoint répond avec le pays de l'entreprise."""
    reponse = client_auth.get(URL_VILLES)
    assert reponse.status_code == 200
    corps = reponse.json()

    assert corps["pays"] == "CI"
    assert corps["agglomeration"] == "Abidjan"
    assert len(corps["localites"]) >= 40
    noms = [v["nom"] for v in corps["localites"]]
    assert "Cocody" in noms
    assert "Yamoussoukro" in noms


@pytest.mark.django_db
def test_api_referentiel_villes_autre_pays(client_auth):
    """Un pays demandé explicitement est servi — une entreprise peut travailler ailleurs."""
    corps = client_auth.get(URL_VILLES, {"pays": "sn"}).json()
    assert corps["pays"] == "SN"
    assert corps["agglomeration"] == "Dakar"
    assert "Ziguinchor" in [v["nom"] for v in corps["localites"]]

    # Un pays sans référentiel répond une liste vide, pas une erreur : l'écran
    # bascule alors sur sa saisie libre.
    vide = client_auth.get(URL_VILLES, {"pays": "FR"}).json()
    assert vide["pays"] == "FR"
    assert vide["localites"] == []
    assert vide["agglomeration"] == ""


@pytest.mark.django_db
def test_api_meteo_projet(client_auth):
    """L'endpoint de météo renvoie un JSON exploitable par la Topbar."""
    reponse_simulee = {
        "current": {
            "temperature_2m": 28.4,
            "weather_code": 2,
        }
    }
    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value.status = 200
    mock_urlopen.__enter__.return_value.read.return_value = json.dumps(reponse_simulee).encode(
        "utf-8"
    )

    with patch("urllib.request.urlopen", return_value=mock_urlopen):
        reponse = client_auth.get(f"{URL_METEO}?ville=San-Pédro&pays=CI")

    assert reponse.status_code == 200
    data = reponse.json()
    assert data["disponible"] is True
    assert data["temperature"] == 28
    assert data["ville"] == "San-Pédro"


@pytest.mark.django_db
def test_api_meteo_directeur_general_recoit_ville_entreprise_uniquement(utilisateur):
    """Le DG voit uniquement la météo de la ville du siège dans la barre, même si projet_id est passé."""
    utilisateur.role_global = RoleGlobal.DIRECTEUR_GENERAL
    utilisateur.save()

    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=utilisateur)

    reponse_simulee = {
        "current": {
            "temperature_2m": 29.0,
            "weather_code": 0,
        }
    }
    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value.status = 200
    mock_urlopen.__enter__.return_value.read.return_value = json.dumps(reponse_simulee).encode("utf-8")

    from apps.tenants.models import Entreprise
    with schema_context("public"):
        Entreprise.objects.filter(schema_name=SCHEMA).update(ville="Abidjan", pays="CI")

    # Même si on passe un projet_id fictif dans la requête de la barre, le DG reste sur le siège
    with patch("urllib.request.urlopen", return_value=mock_urlopen):
        reponse = client.get(f"{URL_METEO}?projet_id=00000000-0000-0000-0000-000000000001")

    assert reponse.status_code == 200
    data = reponse.json()
    assert data["portee"] == "ENTREPRISE"
    # « Abidjan » se résout canoniquement sur son centre « Plateau »
    assert data["ville"] == "Plateau"
