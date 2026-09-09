"""Les seize tests d'acceptation du wizard — contrat T-024 §12.

**Deux d'entre eux ne tomberont jamais par accident**, et ce sont les deux qui
comptent.

Le test 5 — deux administrateurs franchissent la même étape — porte sur une
mise à jour perdue : elle ne lève rien, ne ralentit rien, et laisse une base
parfaitement cohérente, avec une étape en moins. Un test séquentiel passerait
quel que soit le modèle choisi, JSONB compris ; celui d'ici **force
l'entrelacement** en insérant la ligne concurrente entre la lecture et
l'écriture du service, ce qui exerce vraiment la branche d'unicité.

Le test 11 — une quatrième étape livrée après coup — ne coûte rien à écrire
aujourd'hui, n'échouera jamais tant qu'il n'y a que trois étapes, et il est le
seul obstacle entre cette quatrième étape et un wizard qui rouvre chez tous les
clients existants le jour de la livraison.
"""

import pytest
from django.db import IntegrityError, connection
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.enums import CodeEtape, ModeEtape, RoleGlobal, StatutUtilisateur
from apps.onboarding import services
from apps.onboarding.models import ETAPES, EtapeConfiguration, ProgressionConfiguration

SCHEMA = "demo"
HOTE = "demo.localhost"
URL = "/api/v1/configuration/"
URL_TERMINER = "/api/v1/configuration/terminer/"


def url_valider(code: str) -> str:
    return f"/api/v1/configuration/etapes/{code}/valider/"


def url_passer(code: str) -> str:
    return f"/api/v1/configuration/etapes/{code}/passer/"


# --------------------------------------------------------------------------
# Décor
# --------------------------------------------------------------------------
@pytest.fixture
def table_vide(db):
    """Une progression par schéma : chaque test repart de zéro.

    `supprimer_definitivement` et non `delete` — Socle §3.1 détourne la
    suppression vers une suppression logique, et une ligne « supprimée »
    heurterait encore `uq_progression_singleton`.
    """
    with schema_context(SCHEMA):
        for etape in EtapeConfiguration.tous_objets.all():
            etape.supprimer_definitivement()
        for progression in ProgressionConfiguration.tous_objets.all():
            progression.supprimer_definitivement()
        yield


def _creer(email: str, role: str) -> Utilisateur:
    Utilisateur.tous_objets.filter(email=email).delete()
    return Utilisateur.objects.create_user(
        email=email,
        password="MotDePasse1!",
        nom="Kouassi",
        prenom="Ange",
        role_global=role,
        statut=StatutUtilisateur.ACTIF,
    )


@pytest.fixture
def administrateur(table_vide):
    with schema_context(SCHEMA):
        yield _creer("ad@demo.ci", RoleGlobal.ADMIN)


@pytest.fixture
def chef_de_projet(table_vide):
    with schema_context(SCHEMA):
        yield _creer("cp@demo.ci", RoleGlobal.CHEF_PROJET)


@pytest.fixture
def directeur_general(table_vide):
    with schema_context(SCHEMA):
        yield _creer("dg@demo.ci", RoleGlobal.DIRECTEUR_GENERAL)


@pytest.fixture
def client(administrateur):
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=administrateur)
    return client


def code_erreur(reponse) -> str:
    return reponse.json()["erreur"]["code"]


def franchir_dans_le_schema(code: str, utilisateur, mode=ModeEtape.VALIDEE):
    with schema_context(SCHEMA):
        return services.franchir(code=code, mode=mode, utilisateur=utilisateur)


# --------------------------------------------------------------------------
# 1 — R-91 : une seule progression par schéma
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_une_seconde_progression_leve_une_erreur_dintegrite(table_vide):
    """La garantie est **en base**, pas dans un service.

    Un contrôle applicatif serait contourné par la première commande
    d'administration écrite un soir de mise en production.
    """
    with schema_context(SCHEMA):
        ProgressionConfiguration.objects.create()
        with pytest.raises(IntegrityError):
            ProgressionConfiguration.objects.create()


# --------------------------------------------------------------------------
# 2, 3, 8 — le pourcentage
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_aucune_etape_franchie_donne_zero_pour_cent(table_vide):
    """**0 %, et non 33 %.** M9 affichait la position, pas l'avancement."""
    with schema_context(SCHEMA):
        assert services.lire_ou_creer().pourcentage == 0


@pytest.mark.django_db
def test_deux_etapes_sur_trois_donnent_soixante_sept(administrateur):
    """67, entier. Un pourcentage de configuration n'a pas de décimale."""
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)
    progression = franchir_dans_le_schema(CodeEtape.PROJET, administrateur)
    assert progression.pourcentage == 67


@pytest.mark.django_db
def test_passer_equipe_mene_a_cent_pour_cent(administrateur):
    """R-93 — passer franchit.

    Le contraire laisserait une bannière « Configuration 67 % » pour toujours,
    en réponse à un geste que l'utilisateur a fait exprès.
    """
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)
    franchir_dans_le_schema(CodeEtape.PROJET, administrateur)
    with schema_context(SCHEMA):
        progression = services.passer(code=CodeEtape.EQUIPE, utilisateur=administrateur)
        assert progression.pourcentage == 100
        assert progression.statut == ProgressionConfiguration.Statut.TERMINEE
        assert progression.terminee_le is not None


# --------------------------------------------------------------------------
# 4 — R-90 : le pourcentage ne s'écrit pas
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_pourcentage_nest_pas_accepte_en_ecriture(client):
    """**La ressource n'expose aucune écriture directe.**

    Le contrat §12 formule ce test comme « un `PATCH` contenant `pourcentage`
    répond 400 ». Il n'y a pas de `PATCH` : la progression ne se modifie que
    par les trois actions du §5.2 à §5.4, et la méthode est donc refusée en
    amont — `405`, ce qui est un refus plus net qu'un `400`.

    Ce que la règle protège est vérifié des deux côtés : la méthode est
    refusée, et le champ est en lecture seule dans le sérialiseur.
    """
    from apps.onboarding.serializers import ProgressionSerializer

    reponse = client.patch(URL, {"pourcentage": 100}, format="json")
    assert reponse.status_code == 405
    assert ProgressionSerializer().fields["pourcentage"].read_only is True


# --------------------------------------------------------------------------
# 5 — R-92 : deux administrateurs, une seule ligne
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_deux_franchissements_concurrents_produisent_une_seule_ligne(administrateur, monkeypatch):
    """**L'entrelacement est forcé**, sinon le test ne prouve rien.

    Un second `franchir` appelé après le premier passerait avec un tableau
    JSONB comme avec une table fille. Ici, la ligne concurrente est insérée
    **pendant** le premier appel, juste avant son écriture : c'est l'unicité de
    la base qui doit trancher, et le service doit traiter le heurt comme un
    rejeu — `200`, pas `409`.
    """
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)

    original = services._refuser_le_saut_en_avant
    concurrent = {"fait": False}

    def inserer_la_ligne_de_lautre_administrateur(progression, code):
        original(progression, code)
        if not concurrent["fait"]:
            concurrent["fait"] = True
            EtapeConfiguration.objects.create(
                progression=progression,
                code=code,
                mode=ModeEtape.VALIDEE,
                franchie_par=administrateur,
            )

    monkeypatch.setattr(
        services, "_refuser_le_saut_en_avant", inserer_la_ligne_de_lautre_administrateur
    )

    progression = franchir_dans_le_schema(CodeEtape.PROJET, administrateur)

    with schema_context(SCHEMA):
        assert EtapeConfiguration.objects.filter(code=CodeEtape.PROJET).count() == 1
        assert progression.pourcentage == 67


# --------------------------------------------------------------------------
# 6, 7 — R-94 et R-93 : l'ordre et le caractère facultatif
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_valider_projet_sans_entreprise_est_refuse(client):
    """R-94 — un projet ne se crée pas avant que l'entreprise ne soit renseignée."""
    reponse = client.post(url_valider(CodeEtape.PROJET), {}, format="json")
    assert reponse.status_code == 422
    assert code_erreur(reponse) == "etape_precedente_non_franchie"
    assert reponse.json()["erreur"]["details"]["etapes"] == [CodeEtape.ENTREPRISE]


@pytest.mark.django_db
def test_passer_entreprise_est_refuse(client):
    """`ENTREPRISE` reste obligatoire : un espace sans entreprise n'a rien à montrer."""
    reponse = client.post(url_passer(CodeEtape.ENTREPRISE), {}, format="json")
    assert reponse.status_code == 422
    assert code_erreur(reponse) == "etape_non_facultative"


@pytest.mark.django_db
def test_passer_projet_est_accepte(client, administrateur):
    """Refonte Sprint 1 : `PROJET` est facultatif et peut être passé."""
    # L'étape 1 doit d'abord être franchie
    rep_ent = client.post(url_valider(CodeEtape.ENTREPRISE), {}, format="json")
    assert rep_ent.status_code == 200

    reponse = client.post(url_passer(CodeEtape.PROJET), {}, format="json")
    assert reponse.status_code == 200
    assert reponse.json()["pourcentage"] == 67
    assert reponse.json()["etape_courante"] == CodeEtape.EQUIPE


@pytest.mark.django_db
def test_un_code_detape_inconnu_repond_400(client):
    """`400 validation`, et non `404` : le code est un champ, pas une ressource."""
    reponse = client.post(url_valider("PARAMETRES"), {}, format="json")
    assert reponse.status_code == 400
    assert code_erreur(reponse) == "validation"


# --------------------------------------------------------------------------
# 9 — R-96 : le rejeu ne redate rien
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_revalider_une_etape_ne_bouge_pas_franchie_le(administrateur):
    """`franchie_le` date le **premier** franchissement.

    Le remettre à jour à chaque correction ferait passer une entreprise de dix
    minutes à trois semaines parce que quelqu'un a corrigé une faute de frappe
    dans le RCCM — et c'est cet horodatage que mesure l'agrégat « temps de
    configuration ».
    """
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)
    with schema_context(SCHEMA):
        premier = EtapeConfiguration.objects.get(code=CodeEtape.ENTREPRISE).franchie_le

    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)
    with schema_context(SCHEMA):
        assert EtapeConfiguration.objects.get(code=CodeEtape.ENTREPRISE).franchie_le == premier
        assert EtapeConfiguration.objects.filter(code=CodeEtape.ENTREPRISE).count() == 1


# --------------------------------------------------------------------------
# 10 — R-95 : l'état final n'est pas réversible
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_valider_apres_la_fin_repond_409(client, administrateur):
    """Le wizard est un chemin d'entrée, pas un mode d'édition."""
    for code in ETAPES:
        franchir_dans_le_schema(code, administrateur)

    reponse = client.post(url_valider(CodeEtape.ENTREPRISE), {}, format="json")
    assert reponse.status_code == 409
    assert code_erreur(reponse) == "configuration_terminee"


# --------------------------------------------------------------------------
# 11 — la quatrième étape
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_une_quatrieme_etape_ne_fait_pas_redescendre_une_configuration_terminee(
    administrateur, monkeypatch
):
    """**Le test qui n'échouera jamais tant qu'il n'y a que trois étapes.**

    Il est le seul obstacle entre la livraison d'une quatrième étape et un
    wizard qui rouvre, un lundi matin, chez tous les clients existants — une
    régression qu'aucun test ne trouve, parce qu'elle n'apparaît que sur des
    données antérieures à la migration.
    """
    for code in ETAPES:
        franchir_dans_le_schema(code, administrateur)

    from apps.onboarding import models

    monkeypatch.setattr(models, "ETAPES", (*ETAPES, "PARAMETRES"))

    with schema_context(SCHEMA):
        progression = ProgressionConfiguration.objects.get()
        assert progression.est_terminee
        assert progression.pourcentage == 100


# --------------------------------------------------------------------------
# 12 — R-97 : un seul horodatage de fin
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_deux_appels_a_terminer_ecrivent_un_seul_horodatage(client, administrateur):
    """La condition est dans le `WHERE`, pas dans un `if`.

    Un `if terminee_le is None:` suivi d'un `save()` laisse la fenêtre ouverte
    entre la lecture et l'écriture.
    """
    for code in ETAPES:
        franchir_dans_le_schema(code, administrateur)

    with schema_context(SCHEMA):
        horodatage = ProgressionConfiguration.objects.get().terminee_le

    premier = client.post(URL_TERMINER, {}, format="json")
    second = client.post(URL_TERMINER, {}, format="json")

    assert premier.status_code == second.status_code == 200
    with schema_context(SCHEMA):
        assert ProgressionConfiguration.objects.get().terminee_le == horodatage


@pytest.mark.django_db
def test_terminer_avant_les_trois_etapes_nomme_les_manquantes(client, administrateur):
    """`details` nomme ce qui manque : un refus sans la liste oblige à deviner."""
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)

    reponse = client.post(URL_TERMINER, {}, format="json")
    assert reponse.status_code == 422
    assert code_erreur(reponse) == "etapes_manquantes"
    assert reponse.json()["erreur"]["details"]["etapes"] == [
        CodeEtape.PROJET,
        CodeEtape.EQUIPE,
    ]


# --------------------------------------------------------------------------
# 13 — la porte : `AD` seulement
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_un_chef_de_projet_ne_peut_pas_franchir_une_etape(chef_de_projet):
    """Le rôle est vérifié côté serveur, pas seulement à l'écran."""
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=chef_de_projet)

    reponse = client.post(url_valider(CodeEtape.ENTREPRISE), {}, format="json")
    assert reponse.status_code == 403
    assert code_erreur(reponse) == "acces_refuse"


@pytest.mark.django_db
def test_un_directeur_general_peut_lire_et_franchir_la_configuration(directeur_general):
    """T-S1-01 / D-DEMO-01 : Le DG (créateur du tenant) a accès à la configuration."""
    client = APIClient(headers={"host": HOTE})
    client.force_authenticate(user=directeur_general)

    reponse_get = client.get(URL)
    assert reponse_get.status_code == 200

    reponse_val = client.post(url_valider(CodeEtape.ENTREPRISE), {}, format="json")
    assert reponse_val.status_code == 200


@pytest.mark.django_db
def test_un_anonyme_ne_lit_pas_la_progression(table_vide):
    reponse = APIClient(headers={"host": HOTE}).get(URL)
    assert reponse.status_code == 401


# --------------------------------------------------------------------------
# 14 — la lecture crée la ressource
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_premier_get_cree_la_progression_a_zero(client):
    """`GET` reste sans effet de bord **observable** — §5.1.

    Le client reçoit dans les deux cas une progression à 0 % : il n'a donc pas
    à connaître l'ordre entre sa première lecture et sa première écriture.
    """
    with schema_context(SCHEMA):
        assert not ProgressionConfiguration.objects.exists()

    reponse = client.get(URL)
    corps = reponse.json()

    assert reponse.status_code == 200
    assert corps["pourcentage"] == 0
    assert corps["statut"] == "EN_COURS"
    assert corps["etape_courante"] == CodeEtape.ENTREPRISE
    assert corps["terminee_le"] is None

    # Les trois étapes sont là, dans l'ordre, même non franchies.
    assert [etape["code"] for etape in corps["etapes"]] == list(ETAPES)
    assert all(etape["mode"] is None for etape in corps["etapes"])

    with schema_context(SCHEMA):
        assert ProgressionConfiguration.objects.count() == 1


@pytest.mark.django_db
def test_le_point_de_reprise_est_la_premiere_etape_non_franchie(client, administrateur):
    """§6 — `etape_courante` est **calculée**, jamais incrémentée.

    Un compteur qui avance de un finirait par pointer une étape déjà franchie.
    """
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)
    assert client.get(URL).json()["etape_courante"] == CodeEtape.PROJET


# --------------------------------------------------------------------------
# 15, 16 — la forme de la table
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_aucune_colonne_de_brouillon(table_vide):
    """R-99 — la saisie en cours vit dans le navigateur.

    Une colonne `donnees_brouillon` créerait un état que chaque liste, chaque
    compteur et chaque export devrait apprendre à ignorer — et il s'en
    trouverait toujours un pour l'oublier.
    """
    colonnes = {champ.name for champ in ProgressionConfiguration._meta.get_fields()}
    assert not {colonne for colonne in colonnes if "brouillon" in colonne}


@pytest.mark.django_db
def test_les_tables_sont_dans_le_schema_tenant_et_absentes_de_public(table_vide):
    """§1.1 — la progression est lue à chaque affichage du tableau de bord.

    Dans `public`, elle ferait de la table de l'éditeur une dépendance de
    chaque page de chaque client.
    """
    with connection.cursor() as curseur:
        curseur.execute(
            "select table_schema from information_schema.tables "
            "where table_name = 'progression_configuration'"
        )
        schemas = {ligne[0] for ligne in curseur.fetchall()}

    assert SCHEMA in schemas
    assert "public" not in schemas


# --------------------------------------------------------------------------
# Le mode est conservé — la question que l'éditeur posera
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_mode_distingue_validee_de_passee(client, administrateur):
    """« Combien de nouveaux clients invitent au moins un collaborateur ? »

    La distinction ne coûte qu'une colonne, et un chiffre qu'on n'a pas gardé
    ne se reconstitue jamais.
    """
    franchir_dans_le_schema(CodeEtape.ENTREPRISE, administrateur)
    franchir_dans_le_schema(CodeEtape.PROJET, administrateur)
    client.post(url_passer(CodeEtape.EQUIPE), {}, format="json")

    modes = {etape["code"]: etape["mode"] for etape in client.get(URL).json()["etapes"]}
    assert modes == {
        CodeEtape.ENTREPRISE: ModeEtape.VALIDEE,
        CodeEtape.PROJET: ModeEtape.VALIDEE,
        CodeEtape.EQUIPE: ModeEtape.PASSEE,
    }
