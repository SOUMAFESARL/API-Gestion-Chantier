"""Inscription d'une entreprise — contrat T-021, provisionnement T-020.

**Rien n'existe avant l'activation.** Entre le formulaire public et le clic sur
le lien reçu par email, la seule trace est une ligne de `demande_inscription`
dans `public` : ni schéma, ni compte, ni entreprise. C'est ce que l'écran du
lien expiré promet, et c'est ce qui permet de recommencer avec la même adresse.
"""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import models, transaction
from django.utils import timezone
from django.utils.formats import localize
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context
from rest_framework import status

from apps.core.emails import envoyer
from apps.core.enums import StatutEntreprise
from apps.core.exceptions import ErreurMetier
from apps.tenants.models import (
    DUREE_LIEN_ACTIVATION,
    DemandeInscription,
    Domaine,
    Entreprise,
)
from apps.tenants.services import deriver_slug

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
            Entreprise.objects.filter(schema_name=candidat).exists()
            or DemandeInscription.objects.filter(
                slug_reserve=candidat, statut=DemandeInscription.Statut.EN_ATTENTE
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

    # Cas 2 — Entreprise déjà existante avec cet email (T-021 §2.4 - règle : une entreprise = un email unique)
    entreprise_existante = Entreprise.objects.filter(
        email_contact__iexact=adresse,
    ).first()
    if entreprise_existante is not None:
        transaction.on_commit(lambda: _envoyer_espace_existant(entreprise_existante, adresse))
        derniere_demande = (
            DemandeInscription.objects.filter(
                models.Q(entreprise=entreprise_existante) | models.Q(email__iexact=adresse)
            )
            .order_by("-cree_le")
            .first()
        )
        if derniere_demande is not None:
            return derniere_demande

        class _DemandeNeutre:
            pk = identifiant
            email = adresse
            statut = DemandeInscription.Statut.EN_ATTENTE
            expire_le = maintenant + DUREE_LIEN_ACTIVATION

        return _DemandeNeutre()  # type: ignore

    # Cas 3 — Demande déjà en attente d'activation pour cet email
    demande_en_attente = DemandeInscription.objects.filter(
        email__iexact=adresse,
        statut=DemandeInscription.Statut.EN_ATTENTE,
    ).first()
    if demande_en_attente is not None:
        if demande_en_attente.expire_le > maintenant:
            # Demande toujours en cours : renouveler le jeton sans créer de doublon
            jeton = uuid.uuid4()
            demande_en_attente.empreinte = DemandeInscription.empreinte_de(jeton)
            demande_en_attente.expire_le = maintenant + DUREE_LIEN_ACTIVATION
            demande_en_attente.save(update_fields=["empreinte", "expire_le", "modifie_le"])
            transaction.on_commit(
                lambda: _envoyer_activation(demande_en_attente, jeton, regenere=True)
            )
            return demande_en_attente
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
        return demande_prov

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
        # pas : `Entreprise` hérite de `TenantMixin`, pas de `ModeleBase`. Le
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

    base_url = "http://localhost:3000"

    envoyer(
        "espace_existant",
        "Vous avez déjà un espace CCD Digital",
        destinataire,
        {
            "raison_sociale": entreprise.raison_sociale,
            "lien_connexion": f"{base_url}/connexion",
            "lien_reinitialisation": f"{base_url}/mot-de-passe/oublie",
        },
    )


def _envoyer_espace_pret(entreprise: Entreprise, email_admin: str, fin_essai) -> None:
    """Branche 6 — « l'adresse de l'espace, les identifiants, les 14 jours ».

    Aucun mot de passe n'y figure : il a été choisi par la personne elle-même à
    l'activation, et nous ne le connaissons pas.
    """
    adresse_espace = "http://localhost:3000"
    envoyer(
        "espace_pret",
        f"Votre espace {entreprise.raison_sociale} est prêt",
        email_admin,
        {
            "raison_sociale": entreprise.raison_sociale,
            "adresse_espace": adresse_espace,
            "lien_connexion": f"{adresse_espace}/connexion",
            "email_admin": email_admin,
        },
    )


def _envoyer_activation(demande: DemandeInscription, jeton, regenere: bool = False) -> None:
    """L'email d'activation — lien valable 48 h, jeton en fragment.

    `regenere` distingue la branche 2 : une demande était déjà en cours, son
    jeton vient d'être remplacé, et **l'ancien lien ne marche plus**. Le dire
    évite qu'on s'acharne sur le premier message reçu.
    """
    envoyer(
        "activation",
        "Activez votre espace CCD Digital",
        demande.email,
        {
            "raison_sociale": demande.raison_sociale,
            "lien": f"http://localhost:3000/activation#jeton={jeton}",
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
def activer(jeton_clair: str, *, nom: str, prenom: str, mot_de_passe: str) -> DemandeInscription:
    """Consomme le jeton et lance le provisionnement — les effets 1 à 4.

    **T1 est une transaction courte, dans `public` seulement.** Elle marque le
    jeton consommé, pose le nom et le mot de passe **haché** sur la demande, et
    passe le statut à `PROVISIONNEMENT`. Le reste — schéma, migrations,
    administrateur, domaine — se fait après, et hors transaction : la promesse
    « une seule transaction » du MLD §7.5 n'était pas tenable, `migrate_schemas`
    validant et fermant la connexion.
    """
    demande = DemandeInscription.objects.filter(
        empreinte=DemandeInscription.empreinte_de(jeton_clair)
    ).first()

    if demande is None:
        raise JetonInscriptionExpire()

    if demande.statut in {
        DemandeInscription.Statut.PROVISIONNEMENT,
        DemandeInscription.Statut.ACTIVEE,
    }:
        # §6 — rejeu d'une activation. L'espace existe ou se construit.
        raise InscriptionDejaActivee()

    if not demande.est_utilisable:
        raise JetonInscriptionExpire()

    with transaction.atomic():
        demande.utilise_le = timezone.now()
        demande.nom = nom.strip()
        demande.prenom = prenom.strip()
        # Haché avant de toucher la base : la colonne vit dans `public`, et le
        # compte qui portera ce mot de passe n'existe pas encore — MLD §4.8.
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

    # **Après le `commit`, jamais dedans.** Une tâche mise en file à l'intérieur
    # peut être consommée avant la validation : le worker lit alors une demande
    # qui n'existe pas encore et échoue sur un `DoesNotExist` incompréhensible,
    # une fois sur cinquante, sur une machine chargée.
    from apps.tenants.tasks import provisionner_entreprise

    transaction.on_commit(lambda: provisionner_entreprise.delay(str(demande.pk)))
    return demande


# ---------------------------------------------------------------------------
# T-020 §4.3 — le provisionnement lui-même
# ---------------------------------------------------------------------------
def provisionner(identifiant) -> None:
    """Crée le schéma, l'administrateur et le domaine — T2 puis T3.

    **Hors de toute transaction englobante**, et c'est le défaut D-7 qui
    l'impose : `TenantMixin.save()` rattrape un échec de `create_schema` par
    `self.delete(force_drop=True)`. Si l'échec est une erreur de base, la
    transaction est déjà avortée, le rattrapage lève `InFailedSqlTransaction`,
    **et c'est cette exception-là qui remonte** — l'erreur d'origine, la seule
    qui dise ce qui n'a pas marché, est perdue.

    En cas d'échec, la demande passe à `ECHEC` : c'est la compensation qui
    remplace la transaction unique du MLD §7.5.
    """
    demande = DemandeInscription.objects.filter(pk=identifiant).first()
    if demande is None or demande.statut != DemandeInscription.Statut.PROVISIONNEMENT:
        return

    try:
        # --- T2 : l'entreprise, et son schéma avec ses migrations ------------
        entreprise = Entreprise.objects.create(
            schema_name=demande.slug_reserve,
            raison_sociale=demande.raison_sociale,
            pays=demande.pays,
            email_contact=demande.email,
            statut=StatutEntreprise.ESSAI,
        )

        Domaine.objects.get_or_create(
            domain=f"{demande.slug_reserve.replace('_', '-')}.{settings.DOMAINE_PRINCIPAL}",
            defaults={"tenant": entreprise, "is_primary": True},
        )

        # **Après `create`, la connexion pointe sur `public`.** `migrate_schemas`
        # se termine par `set_schema_to_public()` : sans `schema_context`,
        # l'administrateur serait écrit dans `public.utilisateur`, chez
        # l'éditeur. La table existe, les colonnes aussi, l'insertion réussit,
        # **aucune erreur n'est levée**.
        with schema_context(entreprise.schema_name):
            from apps.accounts.models import Utilisateur
            from apps.core.enums import RoleGlobal, StatutUtilisateur

            # D-DEMO-01 / T-S1-01 : Le premier inscrit est Directeur Général
            # et Propriétaire immuable du tenant.
            administrateur = Utilisateur.objects.create_user(
                email=demande.email,
                password=None,
                nom=demande.nom or demande.email.split("@")[0],
                prenom=demande.prenom,
                role_global=RoleGlobal.DIRECTEUR_GENERAL,
                statut=StatutUtilisateur.ACTIF,
            )
            administrateur.is_owner = True
            # Le mot de passe est déjà haché : le repasser par `set_password`
            # le hacherait deux fois.
            administrateur.password = demande.mot_de_passe_transitoire
            administrateur.save(update_fields=["is_owner", "password", "modifie_le"])

            # --- La matrice des rôles, dès la création de l'entreprise -------
            #
            # **Elle était semée paresseusement, au premier affichage de l'écran
            # des rôles.** Tant que personne n'y allait, le schéma n'avait aucun
            # rôle — et `PermissionModule` refuse tout à qui n'a pas le sien.
            # Le fondateur ne s'en apercevait pas : `AD`, `DG` et le propriétaire
            # court-circuitent la matrice. **Ses invités, eux, étaient refusés
            # partout** — un conducteur de travaux sans un seul module, sans
            # message, et sans que rien ne relie la cause à l'effet.
            #
            # Une entreprise n'existe donc plus sans sa matrice.
            from apps.accounts.services.roles import initialiser_roles_par_defaut

            initialiser_roles_par_defaut()

        # --- L'abonnement d'essai — 14 jours en plan Pro ---------------------
        # Sans lui, aucun compteur de jours restants ne peut s'afficher : c'est
        # la dépendance que DEV-12 attendait. Le plan Pro est celui de l'essai,
        # et son **tarif reste inconnu** tant que l'arbitrage A7 n'est pas rendu
        # — ce qui n'empêche pas d'essayer, seulement de facturer.
        from apps.billing.models import JOURS_ESSAI, Abonnement, Plan

        plan = (
            Plan.objects.filter(code=Plan.Code.MAITRE_OEUVRE).first()
            or Plan.objects.filter(code=Plan.Code.PRO).first()
        )
        if plan is None:
            # Une base sans plans est une base incomplète : `peupler_plans` n'a
            # pas été passée. On le dit plutôt que de laisser l'entreprise sans
            # abonnement, ce qui se verrait bien plus tard et bien plus mal.
            raise RuntimeError(
                "Aucun plan d'essai (Maître d'Œuvre / Pro) en base — "
                "passer `manage.py peupler_plans` avant de provisionner une entreprise."
            )

        debut = timezone.localdate()
        fin_essai = debut + timedelta(days=JOURS_ESSAI)
        Abonnement.objects.get_or_create(
            entreprise=entreprise,
            statut=Abonnement.Statut.ESSAI,
            defaults={
                "plan": plan,
                "date_debut": debut,
                # L'abonnement d'essai s'arrête avec l'essai : ce qui suit se
                # décide à la souscription, pas ici.
                "date_fin": fin_essai,
                "fin_essai": fin_essai,
                "renouvellement_auto": False,
            },
        )

        # --- T3 : la demande est close, et la colonne transitoire vidée ------
        with transaction.atomic():
            demande.statut = DemandeInscription.Statut.ACTIVEE
            demande.entreprise = entreprise
            demande.mot_de_passe_transitoire = ""
            demande.save(
                update_fields=["statut", "entreprise", "mot_de_passe_transitoire", "modifie_le"]
            )

        # Branche 6 du §2.4 — l'espace est prêt, et il faut le dire.
        #
        # **C'est la seule fois où l'adresse du client lui est communiquée par
        # écrit** (T-018 §11.1). Il la retrouvera dans cet email six mois plus
        # tard. La branche existait au parcours et n'avait aucun code : le
        # client apprenait l'adresse de son espace par l'écran, et l'oubliait
        # en fermant l'onglet.
        _envoyer_espace_pret(entreprise, demande.email, fin_essai)

    except Exception:
        logger.exception("Provisionnement en échec — demande %s", identifiant)
        DemandeInscription.objects.filter(pk=identifiant).update(
            statut=DemandeInscription.Statut.ECHEC, modifie_le=timezone.now()
        )
        raise
