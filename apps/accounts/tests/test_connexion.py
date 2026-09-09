"""Les issues du parcours de connexion — maquette M1, contrat d'API §14.

**Cinq causes d'échec, une seule réponse.** Ce fichier a changé de nature avec
DEV-1.3 : il vérifiait auparavant que chaque cause avait son code et son écran,
il vérifie maintenant qu'aucune ne se distingue de l'extérieur.

Les tests qui portaient sur `tentatives_restantes`, `compte_bloque`,
`compte_desactive` et `compte_non_active` ne sont pas supprimés : ils sont
retournés. Ce que le serveur ne dit plus, la base doit continuer de le savoir —
c'est elle qui bloque, et le test le lit maintenant en base.
"""

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import TENTATIVES_MAX, Utilisateur
from apps.core.enums import RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"
URL = "/api/v1/auth/token/"
MOT_DE_PASSE = "MotDePasse1!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture
def utilisateur(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="essai@btp.ci").delete()
        yield Utilisateur.objects.create_user(
            email="essai@btp.ci",
            password=MOT_DE_PASSE,
            nom="Kouassi",
            prenom="Ange",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )


def connecter(client, mot_de_passe, email="essai@btp.ci", **extra):
    return client.post(URL, {"email": email, "mot_de_passe": mot_de_passe, **extra}, format="json")


def code(reponse):
    return reponse.json()["erreur"]["code"]


def sans_trace(reponse):
    """Le corps d'erreur, `trace_id` retiré — ce qui doit être identique."""
    erreur = dict(reponse.json()["erreur"])
    erreur.pop("trace_id", None)
    return erreur


def relire(utilisateur):
    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        return utilisateur


# --------------------------------------------------------------------------
# 1. Succès — jetons, profil, en-têtes
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_succes_renvoie_les_jetons_le_profil_et_la_duree(client, utilisateur):
    reponse = connecter(client, MOT_DE_PASSE)

    assert reponse.status_code == 200
    corps = reponse.json()
    assert set(corps) == {"access", "refresh", "expire_dans", "utilisateur"}
    assert corps["access"]
    # Contrat §4.2 — 15 minutes. Le client n'a pas à décoder le JWT pour une
    # information que le serveur connaît.
    assert corps["expire_dans"] == 900


@pytest.mark.django_db
def test_le_profil_evite_un_second_aller_retour(client, utilisateur):
    """Contrat §4.4 — le client doit pouvoir afficher un nom sans rappeler."""
    profil = connecter(client, MOT_DE_PASSE).json()["utilisateur"]

    assert profil["email"] == "essai@btp.ci"
    assert profil["nom"] == "Kouassi"
    assert profil["prenom"] == "Ange"
    assert profil["role_global"] == RoleGlobal.CHEF_CHANTIER
    assert profil["langue"] == "fr"
    assert profil["id"]
    assert profil["doit_changer_mot_de_passe"] is False


@pytest.mark.django_db
def test_le_profil_signale_un_mot_de_passe_a_changer(client, utilisateur):
    """Vrai quand le mot de passe courant a été posé par quelqu'un d'autre que
    son titulaire. Le client impose alors le changement avant d'ouvrir
    l'application."""
    with schema_context(SCHEMA):
        utilisateur.doit_changer_mot_de_passe = True
        utilisateur.save(update_fields=["doit_changer_mot_de_passe"])

    profil = connecter(client, MOT_DE_PASSE).json()["utilisateur"]

    assert profil["doit_changer_mot_de_passe"] is True


@pytest.mark.django_db
def test_la_reponse_porteuse_de_jetons_ne_se_met_pas_en_cache(client, utilisateur):
    """R-05. C'est la seule réponse de l'API dont la mise en cache remettrait
    un jeton en circulation après une déconnexion — bouton « Précédent »
    compris."""
    assert connecter(client, MOT_DE_PASSE)["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_succes_remet_le_compteur_a_zero(client, utilisateur):
    connecter(client, "faux")
    connecter(client, MOT_DE_PASSE)

    assert relire(utilisateur).tentatives_echouees == 0


@pytest.mark.django_db
def test_email_insensible_a_la_casse_et_aux_espaces(client, utilisateur):
    reponse = connecter(client, MOT_DE_PASSE, email="  Essai@BTP.ci  ")
    assert reponse.status_code == 200


# --------------------------------------------------------------------------
# 2. R-01 — les cinq causes ne se distinguent pas
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_les_cinq_causes_produisent_la_meme_reponse(client, utilisateur, db):
    """Comparées **entre elles**, jamais à une forme attendue.

    C'est la formulation du test 1 du §16 du contrat, et elle est délibérée :
    un test qui compare chaque réponse à une constante passerait encore le
    jour où les cinq divergent ensemble.
    """
    reponses = {}

    # a. adresse inconnue dans ce schéma
    reponses["inconnue"] = connecter(client, "peu importe", email="inconnu@btp.ci")

    # b. mot de passe faux
    reponses["mot_de_passe"] = connecter(client, "faux")

    # c. compte désactivé par l'administrateur
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="desactive@btp.ci").delete()
        Utilisateur.objects.create_user(
            email="desactive@btp.ci",
            password=MOT_DE_PASSE,
            nom="Bamba",
            statut=StatutUtilisateur.DESACTIVE,
        )
    reponses["desactive"] = connecter(client, MOT_DE_PASSE, email="desactive@btp.ci")

    # d. compte invité, jamais activé
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="invite@btp.ci").delete()
        Utilisateur.objects.create_user(
            email="invite@btp.ci",
            password=MOT_DE_PASSE,
            nom="Diallo",
            statut=StatutUtilisateur.INVITE,
        )
    reponses["invite"] = connecter(client, MOT_DE_PASSE, email="invite@btp.ci")

    # e. compte bloqué par cinq échecs
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="bloque@btp.ci").delete()
        bloque = Utilisateur.objects.create_user(
            email="bloque@btp.ci",
            password=MOT_DE_PASSE,
            nom="Touré",
            statut=StatutUtilisateur.ACTIF,
        )
        bloque.bloque_le = timezone.now()
        bloque.save(update_fields=["bloque_le"])
    reponses["bloque"] = connecter(client, MOT_DE_PASSE, email="bloque@btp.ci")

    statuts = {nom: r.status_code for nom, r in reponses.items()}
    assert set(statuts.values()) == {401}, statuts

    corps = {nom: sans_trace(r) for nom, r in reponses.items()}
    reference = corps["inconnue"]
    for nom, valeur in corps.items():
        assert valeur == reference, f"la cause « {nom} » se distingue : {valeur}"

    # Aucun en-tête ne les distingue non plus.
    entetes = {r.get("WWW-Authenticate") for r in reponses.values()}
    assert entetes == {None}
    assert {r.get("Retry-After") for r in reponses.values()} == {None}


@pytest.mark.django_db
def test_aucune_reponse_ne_porte_le_compteur(client, utilisateur):
    """R-09. `tentatives_restantes` et `bloque_jusqu_a` répondaient « ce compte
    existe » à qui ne le savait pas."""
    for _ in range(TENTATIVES_MAX + 1):
        details = connecter(client, "faux").json()["erreur"]["details"]
        assert details == {}


# --------------------------------------------------------------------------
# 3. Ce que le serveur ne dit plus, la base le sait toujours
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_compteur_du_serveur_augmente_a_chaque_essai(client, utilisateur):
    """Le compteur qui bloque est celui-ci, en base. Celui de l'écran est tenu
    par le client et n'a aucun effet sur la sécurité."""
    releves = []
    for _ in range(3):
        connecter(client, "faux")
        releves.append(relire(utilisateur).tentatives_echouees)

    assert releves == [1, 2, 3]


@pytest.mark.django_db
def test_cinq_echecs_bloquent_le_compte(client, utilisateur):
    for _ in range(TENTATIVES_MAX):
        connecter(client, "faux")

    assert relire(utilisateur).est_bloque


@pytest.mark.django_db
def test_le_bon_mot_de_passe_ne_debloque_pas(client, utilisateur):
    for _ in range(TENTATIVES_MAX):
        connecter(client, "faux")

    reponse = connecter(client, MOT_DE_PASSE)

    assert reponse.status_code == 401
    assert code(reponse) == "identifiants_invalides"
    assert relire(utilisateur).est_bloque


@pytest.mark.django_db
def test_le_blocage_ne_desactive_pas_le_compte(client, utilisateur):
    """Blocage et désactivation sont deux états distincts, aux sorties
    différentes : l'un expire, l'autre attend un administrateur."""
    for _ in range(TENTATIVES_MAX):
        connecter(client, "faux")

    apres = relire(utilisateur)
    assert apres.est_bloque
    assert apres.statut == StatutUtilisateur.ACTIF


@pytest.mark.django_db
def test_le_blocage_n_expire_pas(client, utilisateur):
    """**Un blocage ne s'éteint plus seul** — arbitrage Q1 de T-008 §6.3.

    Le code portait une expiration à quinze minutes : une *seconde sortie* que
    le Socle §2.1 ne prévoit pas, lui qui dit « déblocage par email de
    réinitialisation **uniquement** ». Attendre suffisait donc à ressayer cinq
    mots de passe de plus, indéfiniment — l'email n'était qu'une politesse.

    Le test avance l'horloge d'un jour : le bon mot de passe reste refusé.
    """
    for _ in range(TENTATIVES_MAX):
        connecter(client, "faux")

    with schema_context(SCHEMA):
        utilisateur.refresh_from_db()
        assert utilisateur.est_bloque
        # Le blocage est daté d'hier : rien n'a d'échéance à franchir.
        utilisateur.bloque_le = timezone.now() - timezone.timedelta(days=1)
        utilisateur.save(update_fields=["bloque_le"])
        utilisateur.refresh_from_db()
        assert utilisateur.est_bloque, "le blocage s'est éteint tout seul"

    assert connecter(client, MOT_DE_PASSE).status_code == 401


@pytest.mark.django_db
def test_un_compte_refuse_ne_voit_pas_son_compteur_bouger(client, utilisateur):
    """Un compte désactivé n'est pas une tentative de force brute : le
    compteur des cinq essais ne le concerne pas."""
    with schema_context(SCHEMA):
        utilisateur.statut = StatutUtilisateur.DESACTIVE
        utilisateur.save(update_fields=["statut"])

    connecter(client, "faux")

    assert relire(utilisateur).tentatives_echouees == 0


# --------------------------------------------------------------------------
# 4. Validation de la requête
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_champs_manquants(client, db):
    reponse = client.post(URL, {}, format="json")

    assert reponse.status_code == 400
    assert code(reponse) == "validation"
    assert "email" in reponse.json()["erreur"]["details"]


@pytest.mark.django_db
def test_mot_de_passe_trop_long(client, utilisateur):
    """Sans borne, une chaîne d'un mégaoctet fait travailler bcrypt pendant
    tout ce temps : un déni de service à coût nul pour l'appelant."""
    reponse = connecter(client, "a" * 129)

    assert reponse.status_code == 400
    assert "mot_de_passe" in reponse.json()["erreur"]["details"]
    # Le mot de passe n'a pas été vérifié : ce n'est pas une tentative.
    assert relire(utilisateur).tentatives_echouees == 0


@pytest.mark.django_db
def test_un_400_n_est_jamais_une_tentative(client, utilisateur):
    """R-07. Sinon un client web bogué verrouille le compte de son
    utilisateur en envoyant trois formulaires incomplets."""
    for _ in range(3):
        client.post(URL, {"email": "essai@btp.ci"}, format="json")

    assert relire(utilisateur).tentatives_echouees == 0


@pytest.mark.django_db
def test_seul_le_json_est_accepte(client, utilisateur):
    """R-04. Un formulaire HTML ne sait émettre que du `form-encoded` : sans
    cette règle, un site tiers poste ce formulaire depuis le navigateur de la
    victime, la connecte sur *son* compte à lui, et récolte ensuite ce qu'elle
    y saisit."""
    reponse = client.post(
        URL,
        "email=essai@btp.ci&mot_de_passe=" + MOT_DE_PASSE,
        content_type="application/x-www-form-urlencoded",
    )

    assert reponse.status_code == 415
    assert "access" not in reponse.json()


@pytest.mark.django_db
def test_toute_erreur_porte_le_format_commun(client, utilisateur):
    erreur = connecter(client, "faux").json()["erreur"]

    assert set(erreur) == {"code", "message", "details", "trace_id"}
    assert erreur["trace_id"]


# --------------------------------------------------------------------------
# 5. Durée du renouvellement selon l'origine — Socle §2.2
# --------------------------------------------------------------------------
@pytest.mark.django_db
@pytest.mark.parametrize(("origine", "heures"), [("WEB", 8), ("MOBILE", 24)])
def test_duree_du_jeton_selon_l_origine(client, utilisateur, origine, heures):
    from rest_framework_simplejwt.tokens import RefreshToken

    reponse = connecter(client, MOT_DE_PASSE, origine=origine)
    jeton = RefreshToken(reponse.json()["refresh"])

    duree = jeton.payload["exp"] - jeton.payload["iat"]
    assert abs(duree - heures * 3600) < 60


# --------------------------------------------------------------------------
# 6. Limitation de débit — deux compteurs, deux menaces
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_limitation_par_adresse_ip(client, utilisateur, monkeypatch):
    """Protège la plateforme d'un balayage : un mot de passe courant essayé
    sur des milliers d'adresses ne bloque aucun compte, puisqu'il ne s'acharne
    sur aucun.

    La limitation est neutralisée par défaut en test — son état est partagé
    par le cache — et ce test la réactive pour lui seul.

    `THROTTLE_RATES` est un attribut de CLASSE, lu à l'import : passer par
    `settings.REST_FRAMEWORK` ne le changerait pas. On corrige la classe.
    """
    from rest_framework.throttling import SimpleRateThrottle

    monkeypatch.setattr(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {"anon": None, "user": None, "connexion": "3/min", "connexion_email": None},
    )

    codes = [connecter(client, "faux", email=f"inconnu{i}@btp.ci").status_code for i in range(4)]

    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


@pytest.mark.django_db
def test_limitation_par_adresse_email(client, utilisateur, monkeypatch):
    """Protège **un** compte d'un essaimage : le même email tenté depuis cent
    IP passe sous le compteur précédent sans le faire sonner."""
    from rest_framework.throttling import SimpleRateThrottle

    monkeypatch.setattr(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {"anon": None, "user": None, "connexion": None, "connexion_email": "3/min"},
    )

    codes = [connecter(client, "faux").status_code for _ in range(4)]

    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429

    # Une autre adresse n'est pas touchée : le compteur est bien par email.
    assert connecter(client, "faux", email="autre@btp.ci").status_code == 401
