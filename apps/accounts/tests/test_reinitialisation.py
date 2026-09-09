"""Réinitialisation du mot de passe — contrat §3, §5 et §5bis.

**Chaque test tente ce que la protection doit interdire**, plutôt que de
vérifier qu'elle est configurée. C'est la leçon de la rotation des jetons : les
deux réglages étaient corrects, `manage.py check` ne signalait rien, la suite
passait — et aucun jeton n'était révoqué, parce qu'aucun test ne **rejouait**
un jeton déjà utilisé.

Le jeton en clair n'existe que dans l'email. Les tests le lisent donc là où
l'utilisateur le lirait, dans `mail.outbox` : c'est aussi ce qui vérifie, au
passage, que le lien part et qu'il porte un fragment.
"""

import re

import pytest
from django.core import mail
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from apps.accounts.models import TENTATIVES_MAX, JetonReinitialisation, Utilisateur
from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, RoleGlobal, StatutUtilisateur

SCHEMA = "demo"
HOTE = "demo.localhost"

DEMANDE = "/api/v1/auth/mot-de-passe/demande/"
VERIFIER = "/api/v1/auth/mot-de-passe/verifier/"
REINITIALISER = "/api/v1/auth/mot-de-passe/reinitialiser/"
REGLES = "/api/v1/referentiels/regles-mot-de-passe/"
CONNEXION = "/api/v1/auth/token/"

ANCIEN = "MotDePasse1!"
NOUVEAU = "Chantier2026!"


@pytest.fixture
def client():
    return APIClient(headers={"host": HOTE})


@pytest.fixture(autouse=True)
def cache_vide():
    """Les compteurs de débit vivent dans le cache et survivent aux tests.

    Sans ce nettoyage, le sixième test de la session récolte un `429` hérité du
    cinquième — un échec qui n'accuse pas le bon coupable.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def utilisateur(db):
    with schema_context(SCHEMA):
        Utilisateur.tous_objets.filter(email="oubli@btp.ci").delete()
        yield Utilisateur.objects.create_user(
            email="oubli@btp.ci",
            password=ANCIEN,
            nom="Bamba",
            prenom="Awa",
            role_global=RoleGlobal.CHEF_CHANTIER,
            statut=StatutUtilisateur.ACTIF,
        )


def _jeton_du_dernier_email() -> str:
    """Le jeton, lu là où l'utilisateur le lirait — et jamais ailleurs."""
    trouve = re.search(r"#jeton=([0-9a-f-]{36})", mail.outbox[-1].body)
    assert trouve, "aucun lien de réinitialisation dans l'email"
    return trouve.group(1)


@pytest.fixture
def poster(client, django_capture_on_commit_callbacks):
    """Poste une demande **et exécute les rappels de `on_commit`**.

    *Sans cela, dix-sept tests échouaient sur un `mail.outbox` vide.* Le service
    planifie l'email par `transaction.on_commit`, précisément pour qu'un message
    ne parte pas sur un changement annulé — et pytest-django enveloppe chaque
    test dans une transaction qu'il **annule** à la fin. Les rappels ne sont
    donc jamais exécutés, et l'email n'existe pas.

    Le symptôme accuse le service ; la cause est la mécanique du test. C'est le
    même piège que les tâches Celery mises en file dans une transaction.
    """

    def _appel(email: str):
        with django_capture_on_commit_callbacks(execute=True):
            return client.post(DEMANDE, {"email": email}, format="json")

    return _appel


@pytest.fixture
def demander(poster):
    """Une demande aboutie, et le jeton qu'elle a envoyé."""

    def _appel(email: str) -> str:
        reponse = poster(email)
        assert reponse.status_code == 202
        return _jeton_du_dernier_email()

    return _appel


# ---------------------------------------------------------------------------
# §3 — la demande ne dit jamais si le compte existe
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_adresse_inconnue_repond_202_et_n_envoie_rien(poster):
    """Le `202` est identique ; c'est l'email qui fait la différence.

    Répondre autrement ferait de ce formulaire public un annuaire des clients.
    """
    with schema_context(SCHEMA):
        reponse = poster("personne@nulle-part.ci")

    assert reponse.status_code == 202
    assert mail.outbox == []


@pytest.mark.django_db
def test_adresse_connue_repond_le_meme_202(poster, utilisateur):
    with schema_context(SCHEMA):
        reponse = poster(utilisateur.email)

    assert reponse.status_code == 202
    assert reponse.data["expire_dans"] == 3600
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_le_jeton_n_est_jamais_stocke_en_clair(client, utilisateur, demander):
    """Un jeton vaut un mot de passe pendant une heure — décision J2."""
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)

        assert not JetonReinitialisation.objects.filter(empreinte=jeton).exists()
        assert JetonReinitialisation.objects.filter(
            empreinte=JetonReinitialisation.empreinte_de(jeton)
        ).exists()


@pytest.mark.django_db
def test_une_demande_plus_recente_invalide_la_precedente(client, utilisateur, demander):
    """Sinon deux liens vivants circulent après « Renvoyer l'email »."""
    with schema_context(SCHEMA):
        premier = demander(utilisateur.email)
        # Le compteur d'une demande par cinq minutes ne doit pas masquer la
        # règle qu'on teste ici.
        from django.core.cache import cache

        cache.clear()
        demander(utilisateur.email)

        reponse = client.post(VERIFIER, {"jeton": premier}, format="json")

    assert reponse.status_code == 410
    assert reponse.data["erreur"]["code"] == "jeton_expire"


# ---------------------------------------------------------------------------
# §5bis — la vérification ne consomme pas
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_verifier_ne_consomme_pas_le_jeton(client, utilisateur, demander):
    """Règle R-32.

    Une passerelle antivirus qui suit les liens d'un email brûlerait un jeton
    consommé à la vérification, **avant** que son destinataire ne clique. Le
    défaut serait invisible en recette et systématique chez le client équipé.
    """
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)

        for _ in range(3):
            reponse = client.post(VERIFIER, {"jeton": jeton}, format="json")
            assert reponse.status_code == 200

        assert reponse.data["email"] == utilisateur.email
        assert reponse.data["motif"] == JetonReinitialisation.Motif.OUBLI

        # Et il sert encore après trois vérifications.
        enregistrement = client.post(
            REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json"
        )
        assert enregistrement.status_code == 200


@pytest.mark.django_db
def test_jeton_inexistant_repond_410_et_pas_404(client, utilisateur):
    """Un seul code pour quatre causes — §5.3.

    Distinguer « déjà servi » de « n'existe pas » dirait à qui balaie des
    jetons lesquels ont existé.
    """
    with schema_context(SCHEMA):
        reponse = client.post(VERIFIER, {"jeton": "0" * 36}, format="json")

    assert reponse.status_code == 410
    assert reponse.data["erreur"]["code"] == "jeton_expire"


@pytest.mark.django_db
def test_jeton_expire_est_refuse(client, utilisateur, demander):
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)
        JetonReinitialisation.objects.filter(
            empreinte=JetonReinitialisation.empreinte_de(jeton)
        ).update(expire_le=timezone.now() - timezone.timedelta(seconds=1))

        reponse = client.post(VERIFIER, {"jeton": jeton}, format="json")

    assert reponse.status_code == 410


# ---------------------------------------------------------------------------
# §5 — l'enregistrement, et ce qu'il interdit
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_un_jeton_ne_sert_qu_une_fois(client, utilisateur, demander):
    """Décision J4. Un lien qui reste actif après usage traîne dans une boîte mail."""
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)

        premier = client.post(
            REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json"
        )
        rejeu = client.post(
            REINITIALISER, {"jeton": jeton, "mot_de_passe": "AutreChose9!"}, format="json"
        )

    assert premier.status_code == 200
    assert rejeu.status_code == 410
    assert rejeu.data["erreur"]["code"] == "jeton_expire"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "faible",
    [
        pytest.param("chantier", id="sans majuscule, chiffre ni special"),
        pytest.param("abidjan2026", id="sans majuscule ni special"),
        pytest.param("soumafe!!", id="sans majuscule ni chiffre"),
        pytest.param("Court1!", id="moins de 8 caracteres"),
    ],
)
def test_les_mots_de_passe_du_defaut_d4_sont_refuses(client, utilisateur, demander, faible):
    """**Défaut D-4.** Ces trois-là étaient acceptés le 27 août 2026.

    La maquette M6 affichait quatre coches quand le serveur n'en contrôlait
    qu'une : trois règles à l'écran ne correspondaient à aucun contrôle.
    """
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)
        reponse = client.post(
            REINITIALISER, {"jeton": jeton, "mot_de_passe": faible}, format="json"
        )

    assert reponse.status_code == 400
    assert reponse.data["erreur"]["code"] == "validation"


@pytest.mark.django_db
def test_une_majuscule_accentuee_compte(client, utilisateur, demander):
    """`É` est une majuscule. `[A-Z]` ne le saurait pas — Socle §1.1."""
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)
        reponse = client.post(
            REINITIALISER, {"jeton": jeton, "mot_de_passe": "Éburnéa2026!"}, format="json"
        )

    assert reponse.status_code == 200


@pytest.mark.django_db
def test_le_nouveau_mot_de_passe_ouvre_la_session_et_l_ancien_non(client, utilisateur, demander):
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)
        client.post(REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json")

        avec_ancien = client.post(
            CONNEXION, {"email": utilisateur.email, "mot_de_passe": ANCIEN}, format="json"
        )
        avec_nouveau = client.post(
            CONNEXION, {"email": utilisateur.email, "mot_de_passe": NOUVEAU}, format="json"
        )

    assert avec_ancien.status_code == 401
    assert avec_nouveau.status_code == 200


@pytest.mark.django_db
def test_la_reinitialisation_leve_le_blocage(client, utilisateur, demander):
    """« Le blocage se lève ici, et nulle part ailleurs » — §5.2, effet 2."""
    with schema_context(SCHEMA):
        utilisateur.tentatives_echouees = TENTATIVES_MAX
        utilisateur.bloque_le = timezone.now()
        utilisateur.save(update_fields=["tentatives_echouees", "bloque_le"])

        mail.outbox.clear()
        jeton = demander(utilisateur.email)
        client.post(REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json")

        rafraichi = Utilisateur.objects.get(pk=utilisateur.pk)

    assert rafraichi.tentatives_echouees == 0
    assert rafraichi.bloque_le is None


@pytest.mark.django_db
def test_un_compte_desactive_ne_se_reactive_pas(client, utilisateur, demander):
    """§5.2, effet 3 — le détail d'ordre qui coûte cher si on l'inverse.

    Un salarié parti, dont l'administrateur a fermé le compte, rouvrirait
    l'accès en cliquant sur un vieux lien de réinitialisation.
    """
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)

        Utilisateur.objects.filter(pk=utilisateur.pk).update(statut=StatutUtilisateur.DESACTIVE)

        reponse = client.post(
            REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json"
        )
        rafraichi = Utilisateur.objects.get(pk=utilisateur.pk)

    assert reponse.status_code == 200
    assert rafraichi.statut == StatutUtilisateur.DESACTIVE


@pytest.mark.django_db
def test_la_reinitialisation_laisse_une_entree_d_audit(client, utilisateur, demander):
    """Socle §2.4 — effet 6. Et **sans jamais y écrire le jeton**."""
    with schema_context(SCHEMA):
        jeton = demander(utilisateur.email)
        client.post(REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json")

        entree = JournalAudit.objects.filter(
            type_entite="utilisateur", entite_id=utilisateur.pk
        ).first()

        assert entree is not None
        assert entree.action == ActionAudit.MODIFICATION
        trace = f"{entree.valeur_avant}{entree.valeur_apres}"

    assert jeton not in trace
    assert NOUVEAU not in trace


# ---------------------------------------------------------------------------
# §3.4 — les limites de débit
# ---------------------------------------------------------------------------
def _activer_limites(monkeypatch, **taux) -> None:
    """Réactive les compteurs pour un test, et pour lui seul.

    `THROTTLE_RATES` est un attribut de **classe**, lu à l'import : passer par
    `settings.REST_FRAMEWORK` ne le changerait pas. On corrige la classe, comme
    le font déjà les tests de la connexion.
    """
    from rest_framework.throttling import SimpleRateThrottle

    base = {
        "anon": None,
        "user": None,
        "connexion": None,
        "connexion_email": None,
        "mdp_demande": None,
        "mdp_demande_email": None,
        "mdp_demande_rapprochee": None,
        "mdp_reinitialiser": None,
        "mdp_verifier": None,
    }
    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {**base, **taux})


@pytest.mark.django_db
def test_deux_demandes_rapprochees_sont_refusees(poster, utilisateur, monkeypatch):
    """Une par cinq minutes et par adresse — la limite qui protège une personne.

    Sans elle, n'importe qui fait pleuvoir des emails « réinitialisez votre mot
    de passe » dans la boîte d'un directeur, sans compte et sans trace.
    """
    _activer_limites(monkeypatch, mdp_demande_rapprochee="1/5min")

    with schema_context(SCHEMA):
        premiere = poster(utilisateur.email)
        seconde = poster(utilisateur.email)

    assert premiere.status_code == 202
    assert seconde.status_code == 429


@pytest.mark.django_db
def test_la_limite_par_adresse_vaut_aussi_pour_une_adresse_inconnue(poster, monkeypatch):
    """Une limite qui ne se déclencherait que sur les comptes réels serait un
    oracle d'énumération de plus — §3.4."""
    _activer_limites(monkeypatch, mdp_demande_rapprochee="1/5min")
    inconnue = "fantome@nulle-part.ci"

    with schema_context(SCHEMA):
        premiere = poster(inconnue)
        seconde = poster(inconnue)

    assert premiere.status_code == 202
    assert seconde.status_code == 429


@pytest.mark.django_db
def test_trois_demandes_par_heure_et_par_adresse(poster, utilisateur, monkeypatch):
    """La seconde dimension du §3.4, indépendante de l'IP."""
    _activer_limites(monkeypatch, mdp_demande_email="3/hour")

    with schema_context(SCHEMA):
        codes = [poster(utilisateur.email).status_code for _ in range(4)]

    assert codes == [202, 202, 202, 429]


# ---------------------------------------------------------------------------
# §6.3 — le référentiel des règles
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_referentiel_sert_les_quatre_regles(client):
    with schema_context(SCHEMA):
        reponse = client.get(REGLES)

    assert reponse.status_code == 200
    codes = [r["code"] for r in reponse.data["regles"]]
    assert codes == ["LONGUEUR", "MAJUSCULE", "CHIFFRE", "SPECIAL"]


@pytest.mark.django_db
def test_les_motifs_du_referentiel_acceptent_les_accents(client):
    """`\\p{Lu}` et non `[A-Z]` : sinon l'écran refuserait ce que le serveur accepte."""
    with schema_context(SCHEMA):
        reponse = client.get(REGLES)

    motifs = {r["code"]: r["motif"] for r in reponse.data["regles"]}
    assert motifs["MAJUSCULE"] == r"\p{Lu}"
    assert motifs["CHIFFRE"] == r"\p{Nd}"


# ---------------------------------------------------------------------------
# §1 — la porte « blocage »
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_le_cinquieme_echec_envoie_le_lien_de_deblocage(
    client, utilisateur, django_capture_on_commit_callbacks
):
    """Socle §2.1 : « Déblocage — par email de réinitialisation uniquement ».

    Sans cet envoi, un compte bloqué au cinquième essai n'a **aucune sortie**
    avant quinze minutes, et son titulaire n'en est pas averti. La deuxième des
    trois portes du contrat §1 — même jeton, même écran, même effet que
    l'oubli ; seul l'email diffère.
    """
    with schema_context(SCHEMA):
        with django_capture_on_commit_callbacks(execute=True):
            for _ in range(TENTATIVES_MAX):
                client.post(
                    CONNEXION,
                    {"email": utilisateur.email, "mot_de_passe": "faux"},
                    format="json",
                )

        rafraichi = Utilisateur.objects.get(pk=utilisateur.pk)
        assert rafraichi.est_bloque

        assert len(mail.outbox) == 1
        assert "bloqué" in mail.outbox[-1].subject

        # Et le lien reçu ouvre bien la porte : c'est le même couloir.
        jeton = _jeton_du_dernier_email()
        verification = client.post(VERIFIER, {"jeton": jeton}, format="json")
        assert verification.status_code == 200
        assert verification.data["motif"] == JetonReinitialisation.Motif.BLOCAGE


@pytest.mark.django_db
def test_les_quatre_premiers_echecs_n_envoient_rien(
    client, utilisateur, django_capture_on_commit_callbacks
):
    """L'email part **au** blocage, pas à chaque erreur de frappe."""
    with schema_context(SCHEMA), django_capture_on_commit_callbacks(execute=True):
        for _ in range(TENTATIVES_MAX - 1):
            client.post(
                CONNEXION,
                {"email": utilisateur.email, "mot_de_passe": "faux"},
                format="json",
            )

    assert mail.outbox == []


# ---------------------------------------------------------------------------
# Multi-tenant cross-schema
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_demande_depuis_schema_public_trouve_utilisateur_tenant(
    utilisateur, django_capture_on_commit_callbacks
):
    """Depuis le domaine racine (public), un utilisateur d'un tenant peut demander
    la réinitialisation. Le jeton est créé dans son schéma de tenant et l'email
    contient le lien avec le sous-domaine de son entreprise.
    """
    client_public = APIClient(headers={"host": "localhost"})

    with django_capture_on_commit_callbacks(execute=True):
        reponse = client_public.post(DEMANDE, {"email": utilisateur.email}, format="json")

    assert reponse.status_code == 202
    assert len(mail.outbox) == 1
    # Le lien dans l'email pointe vers le sous-domaine du tenant (demo.localhost)
    assert HOTE in mail.outbox[-1].body

    jeton = _jeton_du_dernier_email()

    # Vérification depuis le domaine public : doit fonctionner et renvoyer le domaine du tenant
    reponse_verif = client_public.post(VERIFIER, {"jeton": jeton}, format="json")
    assert reponse_verif.status_code == 200
    assert reponse_verif.data["email"] == utilisateur.email
    assert reponse_verif.data["domaine"] == HOTE
    assert HOTE in reponse_verif.data["url_connexion"]

    # Réinitialisation depuis le domaine public : doit mettre à jour le mot de passe dans le tenant
    reponse_reinit = client_public.post(
        REINITIALISER, {"jeton": jeton, "mot_de_passe": NOUVEAU}, format="json"
    )
    assert reponse_reinit.status_code == 200

    # Connexion sur le tenant avec le nouveau mot de passe
    client_tenant = APIClient(headers={"host": HOTE})
    avec_nouveau = client_tenant.post(
        CONNEXION, {"email": utilisateur.email, "mot_de_passe": NOUVEAU}, format="json"
    )
    assert avec_nouveau.status_code == 200
