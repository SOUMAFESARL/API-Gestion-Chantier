"""Inscription d'une entreprise — contrat T-021, MLD v2.0 §7.5 (D9, R-12).

**Rien n'existe avant l'activation.** Entre le formulaire public et le clic sur
le lien reçu par email, la seule trace est une ligne de `demande_inscription` :
ni compte, ni entreprise. C'est ce que l'écran du lien expiré promet, et c'est
ce qui permet de recommencer avec la même adresse.

**L'activation crée l'espace dans sa propre transaction** : entreprise, compte
du dirigeant, matrice des rôles, abonnement d'essai. Plus de schéma, plus de
tâche de provisionnement, plus de compensation.
"""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from django.utils.formats import localize
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _
from rest_framework import status

from apps.core.contexte import contexte_entreprise
from apps.core.emails import envoyer
from apps.core.enums import StatutEntreprise
from apps.core.exceptions import ErreurMetier
from apps.entreprises.models import (
    DUREE_LIEN_ACTIVATION,
    DemandeInscription,
    Entreprise,
)
from apps.entreprises.services import deriver_slug

logger = logging.getLogger(__name__)

# T-020 §2.3 : dix suffixes, puis on abandonne. Au-delà, ce n'est plus une
# collision de noms, c'est un incident.
SUFFIXES_MAX = 10

# La version des CGU qu'une acceptation engage. §9 du contrat.
VERSION_CGU = "1.0"


class JetonInscriptionExpire(ErreurMetier):
    """Expiré, consommé, inconnu, ou demande abandonnée — §4 et §5.

    Un seul code pour quatre causes, pour la même raison qu'à la
    réinitialisation : distinguer « déjà servi » de « n'existe pas » renseigne
    qui sonde.
    """

    status_code = status.HTTP_410_GONE
    code_metier = "jeton_expire"
    default_detail = _("Ce lien n'est plus valable. Recommencez votre inscription.")


class InscriptionDejaActivee(ErreurMetier):
    """L'entreprise est déjà en essai — §5, idempotence §6."""

    status_code = status.HTTP_409_CONFLICT
    code_metier = "inscription_deja_activee"
    default_detail = _("Cet espace est déjà actif. Connectez-vous.")


class EmailDejaUtilise(ErreurMetier):
    """L'email est déjà associé à une entreprise existante — 409 CONFLICT."""

    status_code = status.HTTP_409_CONFLICT
    code_metier = "email_deja_utilise"
    default_detail = _("Cette adresse email est déjà associée à un compte. Veuillez vous connecter.")


class InscriptionEnCours(ErreurMetier):
    """Une inscription est déjà en attente d'activation pour cet email — 409 CONFLICT."""

    status_code = status.HTTP_409_CONFLICT
    code_metier = "inscription_en_cours"
    default_detail = _(
        "Une inscription est déjà en cours avec cette adresse email. "
        "Veuillez consulter votre boîte de réception pour l'activer."
    )


class SlugIndisponible(ErreurMetier):
    """Dix suffixes essayés sans succès — T-020 §2.3.

    **Incident, pas cas nominal.** Le message reste compréhensible, mais cette
    réponse doit alerter la supervision plutôt que l'utilisateur.
    """

    status_code = status.HTTP_409_CONFLICT
    code_metier = "slug_indisponible"
    default_detail = _("Ce nom d'entreprise n'est pas disponible. Proposez une variante.")


def _slug_libre(base: str) -> str:
    """Le premier slug libre, `base` puis `base_2` … `base_10`.

    Deux tables à interroger, et c'est délibéré : un slug réservé par une
    demande **en attente** vaut autant qu'un schéma déjà créé. Sans cela, deux
    entreprises homonymes qui s'inscrivent à dix minutes d'intervalle se
    disputent le même schéma au moment de l'activation — c'est-à-dire trop
    tard, quand la personne a déjà saisi son mot de passe.
    """
    for tentative in range(1, SUFFIXES_MAX + 1):
        candidat = base if tentative == 1 else f"{base}_{tentative}"[:40]

        pris = (
            Entreprise.objects.filter(slug=candidat).exists()
            or DemandeInscription.objects.filter(
                slug_reserve=candidat,
                statut__in=["EN_ATTENTE", "A_VALIDER", "PROVISIONNEMENT"],
            ).exists()
        )
        if not pris:
            return candidat

    raise SlugIndisponible()


# ---------------------------------------------------------------------------
# §2 — déposer une demande
# ---------------------------------------------------------------------------
def deposer(
    *,
    identifiant: uuid.UUID | None,
    raison_sociale: str,
    pays: str,
    email: str,
    ip: str | None = None,
) -> DemandeInscription:
    """Enregistre la demande et planifie l'email d'activation.

    **La réponse est la même dans les cinq branches du §2.4**, et cette fonction
    ne renvoie donc rien qui les distingue. La vue répond `202` avec l'`id`, le
    statut et la durée — jamais le slug, qui dirait à qui sonde que `sotra_btp`
    était libre, c'est-à-dire que SOTRA BTP n'est pas client.

    **Idempotence par l'identifiant client** (§6). Rejouer la même requête —
    double-clic, retour arrière, réseau capricieux — retrouve la demande
    existante au lieu d'en créer une seconde.
    """
    adresse = email.strip().lower()
    nom_propre = " ".join(raison_sociale.strip().split())
    identifiant = identifiant or uuid.uuid4()
    maintenant = timezone.now()

    existante = DemandeInscription.objects.filter(pk=identifiant).first()
    if existante is not None:
        # Rejeu : ni nouvelle demande, ni nouvel email. Le contrat §6 veut que
        # la seconde requête renvoie le résultat de la première.
        return existante

    slug_base = deriver_slug(nom_propre)

    # Cas 2 — Entreprise déjà existante avec cet email (règle : une entreprise = un email unique)
    entreprise_existante = Entreprise.objects.filter(
        email_contact__iexact=adresse,
    ).first()
    from apps.accounts.selectors import adresse_prise_sur_la_plateforme

    # L'adresse d'un collaborateur, dans n'importe quelle entreprise, compte aussi (R-8) : sans
    # ce test, l'inscription échouerait à l'activation, sur l'unicité du compte.
    if entreprise_existante is not None or adresse_prise_sur_la_plateforme(adresse):
        raise EmailDejaUtilise()

    # Cas 3 — Demande déjà en attente d'activation pour cet email
    if DemandeInscription.objects.filter(email__iexact=adresse, statut="A_VALIDER").exists():
        raise InscriptionEnCours()
    demande_en_attente = DemandeInscription.objects.filter(
        email__iexact=adresse,
        statut=DemandeInscription.Statut.EN_ATTENTE,
    ).first()
    if demande_en_attente is not None:
        if demande_en_attente.expire_le > maintenant:
            raise InscriptionEnCours()
        else:
            # Expirée : libérer la place
            demande_en_attente.statut = DemandeInscription.Statut.ABANDONNEE
            demande_en_attente.save(update_fields=["statut", "modifie_le"])

    # Cas 4 — Demande en cours de provisionnement pour cet email
    demande_prov = DemandeInscription.objects.filter(
        email__iexact=adresse,
        statut=DemandeInscription.Statut.PROVISIONNEMENT,
    ).first()
    if demande_prov is not None:
        raise InscriptionDejaActivee()

    slug = _slug_libre(slug_base)
    jeton = uuid.uuid4()

    demande = DemandeInscription.objects.create(
        id=identifiant,
        raison_sociale=nom_propre,
        pays=pays.upper(),
        email=adresse,
        slug_reserve=slug,
        empreinte=DemandeInscription.empreinte_de(jeton),
        expire_le=maintenant + DUREE_LIEN_ACTIVATION,
        cgu_version=VERSION_CGU,
        cgu_acceptees_le=maintenant,
        cgu_adresse_ip=ip,
    )

    transaction.on_commit(lambda: _envoyer_activation(demande, jeton))
    return demande


def _envoyer_espace_existant(entreprise: Entreprise, destinataire: str) -> None:
    """Branches 3 et 4 du §2.4 — et ce ne sont pas le même message.

    **Une entreprise suspendue recevait « Vous avez déjà un espace »**, avec un
    lien de connexion qui allait la refuser. La branche 4 de T-018 §11 — *« l'état,
    la date, le contact commercial »* — n'avait jamais eu de code : les deux
    branches partageaient un seul email. Le statut les sépare désormais.
    """
    if entreprise.statut in (StatutEntreprise.SUSPENDU, StatutEntreprise.RESILIE):
        # **La date vient de l'abonnement, pas de l'entreprise.**
        #
        # *Elle était lue sur `entreprise.modifie_le` — un champ qui n'existe
        # pas : `Entreprise` n'hérite pas de `ModeleBase`. Le
        # `getattr` de repli évitait l'exception et laissait l'email partir avec
        # **une date vide**, alors que la branche 4 de T-018 §11 exige « l'état,
        # la date, le contact commercial ». Un défaut qu'aucune erreur ne
        # signalait.*
        dernier = entreprise.abonnements.order_by("-date_debut").first()
        effet = getattr(dernier, "lecture_seule_depuis", None) if dernier else None
        conservation = getattr(dernier, "suppression_prevue_le", None) if dernier else None

        envoyer(
            "espace_suspendu",
            f"Votre espace CCD Digital est {entreprise.get_statut_display().lower()}",
            destinataire,
            {
                "raison_sociale": entreprise.raison_sociale,
                "statut_libelle": entreprise.get_statut_display(),
                "date_effet": localize(localtime(effet).date()) if effet else "",
                "conservation_jusqu_au": localize(conservation) if conservation else None,
            },
        )
        return

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")

    envoyer(
        "espace_existant",
        "Vous avez déjà un espace CCD Digital",
        destinataire,
        {
            "raison_sociale": entreprise.raison_sociale,
            "lien_connexion": f"{frontend_url}/connexion",
            "lien_reinitialisation": f"{frontend_url}/mot-de-passe/oublie",
        },
    )


def _envoyer_espace_pret(entreprise: Entreprise, email_admin: str) -> None:
    """Branche 6 — « l'adresse de l'espace, les identifiants, les 14 jours ».

    Aucun mot de passe n'y figure : il a été choisi par la personne elle-même à
    l'activation, et nous ne le connaissons pas.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    adresse_espace = f"{frontend_url}/connexion"
    envoyer(
        "espace_pret",
        f"Votre espace {entreprise.raison_sociale} est prêt",
        email_admin,
        {
            "raison_sociale": entreprise.raison_sociale,
            "adresse_espace": adresse_espace,
            "lien_connexion": f"{frontend_url}/connexion",
            "email_admin": email_admin,
        },
    )


def _envoyer_activation(demande: DemandeInscription, jeton, regenere: bool = False) -> None:
    """L'email d'activation — lien valable 48 h, jeton en fragment.

    `regenere` distingue la branche 2 : une demande était déjà en cours, son
    jeton vient d'être remplacé, et **l'ancien lien ne marche plus**. Le dire
    évite qu'on s'acharne sur le premier message reçu.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    envoyer(
        "activation",
        "Activez votre espace CCD Digital",
        demande.email,
        {
            "raison_sociale": demande.raison_sociale,
            "lien": f"{frontend_url}/activation#jeton={jeton}",
            "regenere": regenere,
        },
    )


def renvoyer(identifiant) -> None:
    """Réémet un lien — §3. **Nouveau jeton, ancien invalidé.**

    L'endpoint prend l'`id` de la demande et **jamais l'adresse** : un endpoint
    public qui accepte une adresse et envoie un message est une machine à
    bombarder une boîte mail. L'`id` est un UUID v4 — 122 bits — connu du seul
    navigateur qui vient de soumettre le formulaire.
    """
    demande = DemandeInscription.objects.filter(
        pk=identifiant, statut=DemandeInscription.Statut.EN_ATTENTE
    ).first()
    if demande is None:
        # Identifiant inconnu : même réponse, aucun email — §3.
        return

    jeton = uuid.uuid4()
    demande.empreinte = DemandeInscription.empreinte_de(jeton)
    demande.expire_le = timezone.now() + DUREE_LIEN_ACTIVATION
    demande.save(update_fields=["empreinte", "expire_le", "modifie_le"])

    transaction.on_commit(lambda: _envoyer_activation(demande, jeton, regenere=True))


# ---------------------------------------------------------------------------
# §4 — vérifier sans consommer
# ---------------------------------------------------------------------------
def verifier(jeton_clair: str) -> DemandeInscription:
    """Lit le jeton **sans le consommer** — R-83.

    Une passerelle de sécurité de messagerie qui pré-visite les liens brûlerait
    l'inscription avant que la personne ne clique.
    """
    demande = DemandeInscription.objects.filter(
        empreinte=DemandeInscription.empreinte_de(jeton_clair)
    ).first()

    if demande is None or not demande.est_utilisable:
        raise JetonInscriptionExpire()

    return demande




# ---------------------------------------------------------------------------
# §5 — activer
# ---------------------------------------------------------------------------
@transaction.atomic
def activer(jeton_clair: str, *, nom: str, prenom: str, mot_de_passe: str) -> DemandeInscription:
    """Consomme le jeton et crée l'espace, **dans la même transaction** (D9, R-12).

    Sous le multi-schéma, l'espace se construisait après coup — un schéma, 193 migrations, puis
    trois transactions et une compensation (T-020). Sans schéma à créer, l'inscription n'est plus
    qu'une suite d'insertions : elle réussit entière, ou ne laisse rien. Un échec annule aussi la
    consommation du jeton : le lien reste valable, et la personne peut réessayer.
    """
    demande = DemandeInscription.objects.select_for_update().filter(
        empreinte=DemandeInscription.empreinte_de(jeton_clair)
    ).first()

    if demande is None:
        raise JetonInscriptionExpire()

    if demande.statut in {
        DemandeInscription.Statut.PROVISIONNEMENT,
        DemandeInscription.Statut.ACTIVEE,
    }:
        # §6 — rejeu d'une activation. L'espace existe déjà.
        raise InscriptionDejaActivee()

    if not demande.est_utilisable:
        raise JetonInscriptionExpire()

    demande.utilise_le = timezone.now()
    demande.nom = nom.strip()
    demande.prenom = prenom.strip()
    # Haché avant toute écriture : la demande le porte jusqu'à la création du compte, quelques
    # lignes plus bas — et `provisionner` le vide dans la même transaction.
    demande.mot_de_passe_transitoire = make_password(mot_de_passe)
    demande.statut = DemandeInscription.Statut.PROVISIONNEMENT
    demande.save(
        update_fields=[
            "utilise_le",
            "nom",
            "prenom",
            "mot_de_passe_transitoire",
            "statut",
            "modifie_le",
        ]
    )

    provisionner(demande)
    return demande


# ---------------------------------------------------------------------------
# Le provisionnement : entreprise, rôles, administrateur, abonnement d'essai
# ---------------------------------------------------------------------------
def provisionner(demande: DemandeInscription) -> Entreprise:
    """Crée l'espace d'une demande au statut `PROVISIONNEMENT` — MLD v2.0 §7.5.

    **Doit tourner dans la transaction de l'appelant** (`activer`, ou la décision du super admin) :
    c'est elle qui garantit le « tout ou rien ». L'e-mail « espace prêt » ne part qu'après sa
    validation.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Le provisionnement doit tourner dans une transaction.")

    from apps.accounts.models import Utilisateur
    from apps.accounts.selectors import adresse_prise_sur_la_plateforme
    from apps.accounts.services.roles import initialiser_roles_par_defaut
    from apps.billing.models import JOURS_ESSAI, Abonnement, Plan
    from apps.core.enums import RoleGlobal, StatutUtilisateur

    # L'adresse est unique sur toute la plateforme (R-8) : déjà prise par un collaborateur d'une
    # autre entreprise, l'insertion du compte échouerait sur la contrainte, plus bas.
    if adresse_prise_sur_la_plateforme(demande.email):
        raise EmailDejaUtilise()

    # Une base sans plans est une base incomplète : `peupler_plans` n'a pas été passée. On le dit
    # avant d'écrire quoi que ce soit, plutôt que de laisser une entreprise sans abonnement.
    plan = (
        Plan.objects.filter(code=Plan.Code.MAITRE_OEUVRE).first()
        or Plan.objects.filter(code=Plan.Code.PRO).first()
    )
    if plan is None:
        raise RuntimeError(
            "Aucun plan d'essai (Maître d'Œuvre / Pro) en base — "
            "passer `manage.py peupler_plans` avant d'activer une inscription."
        )

    entreprise = Entreprise.objects.create(
        slug=demande.slug_reserve,
        raison_sociale=demande.raison_sociale,
        pays=demande.pays,
        email_contact=demande.email,
        statut=StatutEntreprise.ESSAI,
    )

    with contexte_entreprise(entreprise):
        # La matrice des rôles, dès la création de l'entreprise. Semée paresseusement, au premier
        # affichage de l'écran des rôles, elle manquait aux invités du fondateur : refusés
        # partout, sans message (le fondateur, lui, court-circuite la matrice). **Avant** le
        # fondateur : `Utilisateur.save` ne rattache le rôle `DG` que s'il existe déjà — semé
        # après, le fondateur restait sans rôle (`role_id` nul), écart trouvé au lot 7.
        initialiser_roles_par_defaut()

        # D-DEMO-01 / T-S1-01 : le premier inscrit est Directeur Général et propriétaire
        # immuable de l'entreprise. Le mot de passe est déjà haché : `create_user` le hacherait
        # une seconde fois, il est donc posé tel quel.
        administrateur = Utilisateur.objects.create_user(
            email=demande.email,
            password=None,
            nom=demande.nom or demande.email.split("@")[0],
            prenom=demande.prenom,
            role_global=RoleGlobal.DIRECTEUR_GENERAL,
            statut=StatutUtilisateur.ACTIF,
        )
        administrateur.is_owner = True
        administrateur.password = demande.mot_de_passe_transitoire
        administrateur.save(update_fields=["is_owner", "password", "modifie_le"])

    # L'abonnement d'essai — 14 jours. Son tarif reste inconnu tant que l'arbitrage A7 n'est pas
    # rendu, ce qui n'empêche pas d'essayer, seulement de facturer.
    debut = timezone.localdate()
    fin_essai = debut + timedelta(days=JOURS_ESSAI)
    Abonnement.objects.create(
        entreprise=entreprise,
        plan=plan,
        statut=Abonnement.Statut.ESSAI,
        date_debut=debut,
        # L'abonnement d'essai s'arrête avec l'essai : ce qui suit se décide à la souscription.
        date_fin=fin_essai,
        fin_essai=fin_essai,
        renouvellement_auto=False,
    )

    demande.statut = DemandeInscription.Statut.ACTIVEE
    demande.entreprise = entreprise
    demande.mot_de_passe_transitoire = ""
    demande.save(update_fields=["statut", "entreprise", "mot_de_passe_transitoire", "modifie_le"])

    # Branche 6 du §2.4 — l'espace est prêt, et il faut le dire : c'est la seule fois où l'adresse
    # de l'espace est communiquée par écrit (T-018 §11.1). Après validation seulement.
    transaction.on_commit(lambda: _annoncer_espace_pret(entreprise, demande.email))
    return entreprise


def _annoncer_espace_pret(entreprise: Entreprise, email_admin: str) -> None:
    """Un incident SMTP n'annule pas une inscription déjà validée."""
    try:
        _envoyer_espace_pret(entreprise, email_admin)
    except Exception:
        logger.exception("Email « espace prêt » non envoyé — entreprise %s", entreprise.pk)
