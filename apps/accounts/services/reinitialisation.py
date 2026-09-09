"""Réinitialisation du mot de passe — contrat §3, §5 et §5bis.

**Trois portes, un seul couloir** (§1). L'oubli et le blocage après cinq échecs
partagent le même jeton, le même endpoint de validation et les mêmes effets ;
ils ne diffèrent que par ce qui les déclenche et par le gabarit d'email. Écrire
deux parcours parallèles aurait doublé la surface à tester pour une différence
qui tient en un texte.
"""

import logging
import uuid

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ValidationDjango
from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import status

from apps.accounts.models import (
    DUREE_JETON_REINITIALISATION,
    JetonReinitialisation,
    Utilisateur,
)
from apps.accounts.services.liste_noire import revoquer_utilisateur
from apps.audit.services import journaliser
from apps.core.emails import envoyer
from apps.core.enums import ActionAudit, StatutUtilisateur
from apps.core.exceptions import ErreurMetier
from apps.tenants.models import Entreprise

logger = logging.getLogger(__name__)

# Durée de révocation des sessions : au moins celle du jeton de renouvellement,
# sans quoi une session ouverte avant le changement survivrait à sa révocation.
TTL_REVOCATION = 24 * 3600


class JetonExpire(ErreurMetier):
    """**Un seul code pour quatre causes** — contrat §5.3.

    Expiré, consommé, invalidé par une demande plus récente, ou inexistant.
    Distinguer « ce jeton a déjà servi » de « ce jeton n'existe pas » dirait à
    qui teste des jetons au hasard lesquels ont existé. Et la conduite à tenir
    est la même dans les quatre cas : redemander un lien.

    `410 Gone` et non `404` : la ressource a existé et n'existe plus. C'est
    exactement ce que `410` signifie, et cela évite d'ajouter un cinquième sens
    au `404`, qui sert déjà aux ressources hors périmètre.
    """

    status_code = status.HTTP_410_GONE
    code_metier = "jeton_expire"
    default_detail = _("Ce lien n'est plus valable. Demandez-en un nouveau.")


# ---------------------------------------------------------------------------
# §3 — la demande
# ---------------------------------------------------------------------------
def demander(
    email: str,
    *,
    ip: str | None = None,
    motif: str = JetonReinitialisation.Motif.OUBLI,
) -> None:
    """Crée un lien et planifie l'email — **sans jamais dire si le compte existe**.

    La fonction ne renvoie rien et ne lève rien sur une adresse inconnue : la
    vue répond `202` dans tous les cas (§3.2). Ce qui change, c'est l'email —
    qui ne part pas.

    Les cas qui ne produisent aucun effet, contrat §3.3 :

      · adresse inconnue ;
      · compte supprimé logiquement — le manager les exclut déjà ;
      · compte `INVITE`, jamais activé : sa porte est le lien d'invitation.

    **Le compte bloqué est explicitement inclus** : c'est précisément la
    situation que ce parcours doit dénouer.
    """
    adresse = (email or "").strip().lower()
    schema_courant = getattr(connection, "schema_name", "public")
    public_schema = get_public_schema_name()

    cible_schema = schema_courant
    cible_utilisateur = Utilisateur.objects.filter(email__iexact=adresse).first()
    cible_entreprise: Entreprise | None = None

    # Si l'utilisateur n'est pas dans le schéma courant (ex. requête sur public),
    # rechercher parmi les schémas des entreprises clientes actives.
    if cible_utilisateur is None and schema_courant == public_schema:
        for entreprise in Entreprise.objects.exclude(schema_name=public_schema):
            with schema_context(entreprise.schema_name):
                candidat = Utilisateur.objects.filter(email__iexact=adresse).first()
                if candidat is not None:
                    cible_schema = entreprise.schema_name
                    cible_utilisateur = candidat
                    cible_entreprise = entreprise
                    break
    elif cible_schema != public_schema:
        cible_entreprise = Entreprise.objects.filter(schema_name=cible_schema).first()

    if cible_utilisateur is None or cible_utilisateur.statut == StatutUtilisateur.INVITE:
        return

    if cible_utilisateur.statut == StatutUtilisateur.DESACTIVE or not cible_utilisateur.is_active:
        return

    jeton = uuid.uuid4()

    with schema_context(cible_schema):
        with transaction.atomic():
            # Une demande plus récente invalide les précédentes : sans cela, deux
            # liens vivants circulent après un clic sur « Renvoyer l'email ».
            JetonReinitialisation.objects.filter(
                utilisateur=cible_utilisateur, utilise_le__isnull=True, invalide_le__isnull=True
            ).update(invalide_le=timezone.now())

            JetonReinitialisation.objects.create(
                utilisateur=cible_utilisateur,
                empreinte=JetonReinitialisation.empreinte_de(jeton),
                motif=motif,
                expire_le=timezone.now() + DUREE_JETON_REINITIALISATION,
                ip_demande=ip,
            )

        # Hors transaction : un email ne se rejoue pas, et en planifier un dans une
        # transaction ferait partir le message même en cas d'annulation.
        transaction.on_commit(
            lambda: _envoyer_lien(cible_utilisateur, jeton, motif, entreprise=cible_entreprise)
        )


def _envoyer_lien(
    utilisateur: Utilisateur,
    jeton,
    motif: str,
    *,
    entreprise: Entreprise | None = None,
) -> None:
    """Compose et envoie E1 ou E2 — contrat §4.

    Le jeton voyage en **fragment**. Un fragment n'est pas transmis au serveur :
    il n'atteint ni les journaux Nginx, ni l'en-tête `Referer` d'une page
    ouverte depuis le lien.
    """
    schema_courant = getattr(connection, "schema_name", "public")
    public_schema = get_public_schema_name()

    if entreprise is None and schema_courant != public_schema:
        entreprise = Entreprise.objects.filter(schema_name=schema_courant).first()

    if entreprise is not None:
        domaine = entreprise.domains.filter(is_primary=True).first()
        hote = domaine.domain if domaine else entreprise.schema_name
        protocole = "https" if not settings.DEBUG else "http"
        port = ":3000" if settings.DEBUG else ""
        base_frontend = f"{protocole}://{hote}{port}"
    else:
        base_frontend = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

    lien = f"{base_frontend}/mot-de-passe/definir#jeton={jeton}"
    bloque = motif == JetonReinitialisation.Motif.BLOCAGE

    sujet = (
        "Votre compte CCD Digital a été bloqué"
        if bloque
        else "Réinitialisation de votre mot de passe CCD Digital"
    )
    # Un email ne contient jamais le mot de passe, ni l'indication qu'un compte
    # existe pour une autre adresse que la sienne — contrat §4.2.
    #
    # `envoyer` journalise et n'échoue jamais : le jeton reste valable, la
    # personne peut redemander un lien, et faire remonter l'échec révélerait au
    # passage que l'adresse existe.
    envoyer(
        "reinitialisation",
        sujet,
        utilisateur.email,
        {"motif": "blocage" if bloque else "oubli", "lien": lien},
    )


# ---------------------------------------------------------------------------
# §5bis — la vérification, qui ne consomme pas
# ---------------------------------------------------------------------------
def verifier(jeton_clair: str) -> JetonReinitialisation:
    """Lit le jeton **sans le consommer** — règle R-32.

    Certaines passerelles de sécurité de messagerie suivent les URL d'un email
    pour les analyser avant de le remettre. Un jeton marqué « utilisé » à la
    vérification serait **brûlé par l'antivirus avant que son destinataire ne
    clique** — un défaut invisible en recette interne, systématique chez un
    client qui en est équipé.
    """
    empreinte = JetonReinitialisation.empreinte_de(jeton_clair)
    jeton = (
        JetonReinitialisation.objects.select_related("utilisateur")
        .filter(empreinte=empreinte)
        .first()
    )
    schema_trouve = getattr(connection, "schema_name", "public")
    public_schema = get_public_schema_name()

    if (jeton is None or not jeton.est_utilisable) and schema_trouve == public_schema:
        # Recherche multi-tenant si la requête a atteint le domaine public
        for entreprise in Entreprise.objects.exclude(schema_name=public_schema):
            with schema_context(entreprise.schema_name):
                candidat = (
                    JetonReinitialisation.objects.select_related("utilisateur")
                    .filter(empreinte=empreinte)
                    .first()
                )
                if candidat is not None and candidat.est_utilisable:
                    jeton = candidat
                    schema_trouve = entreprise.schema_name
                    break

    if jeton is None or not jeton.est_utilisable:
        raise JetonExpire()

    jeton._schema_name = schema_trouve
    return jeton


# ---------------------------------------------------------------------------
# §5 — l'enregistrement
# ---------------------------------------------------------------------------
def reinitialiser(
    jeton_clair: str,
    mot_de_passe: str,
    *,
    ip: str | None = None,
    appareil: str = "",
) -> Utilisateur:
    """Enregistre le nouveau mot de passe et ferme toutes les sessions.

    Les effets, **dans cet ordre** (§5.2) — et deux détails d'ordre coûtent cher
    si on les inverse :

      3. Le statut ne repasse à `ACTIF` que depuis `INVITE`. **Jamais depuis
         `DESACTIVE`** : un salarié parti dont l'administrateur a fermé le
         compte rouvrirait l'accès en cliquant sur un vieux lien.
      7. L'email de confirmation sort de la transaction. À l'intérieur, un
         « votre mot de passe a été modifié » partirait même en cas
         d'annulation — un message alarmant pour un changement qui n'a pas eu
         lieu.
    """
    jeton = verifier(jeton_clair)
    schema_cible = getattr(jeton, "_schema_name", getattr(connection, "schema_name", "public"))

    with schema_context(schema_cible):
        utilisateur = jeton.utilisateur

        # Le serveur reste seul juge de la complexité — les coches de l'écran sont
        # un confort (§6.3). `validate_password` porte les trois validateurs du
        # défaut D-4, en plus de ceux de Django.
        try:
            validate_password(mot_de_passe, utilisateur)
        except ValidationDjango as erreur:
            raise erreur

        etait_bloque = utilisateur.est_bloque

        with transaction.atomic():
            utilisateur.set_password(mot_de_passe)

            champs = ["password", "tentatives_echouees", "bloque_le", "modifie_le"]
            # Le blocage se lève ici, et nulle part ailleurs.
            utilisateur.tentatives_echouees = 0
            utilisateur.bloque_le = None

            if utilisateur.statut == StatutUtilisateur.INVITE:
                utilisateur.statut = StatutUtilisateur.ACTIF
                champs.append("statut")

            # Le mot de passe est désormais celui de son titulaire : plus rien à
            # imposer au prochain écran de connexion.
            if utilisateur.doit_changer_mot_de_passe:
                utilisateur.doit_changer_mot_de_passe = False
                champs.append("doit_changer_mot_de_passe")

            utilisateur.save(update_fields=champs)

            jeton.utilise_le = timezone.now()
            jeton.save(update_fields=["utilise_le", "modifie_le"])

            # Révocation totale des sessions — c'est ce que M6 promet à l'écran 4 :
            # « toutes vos sessions actives ont été invalidées sur tous vos appareils ».
            revoquer_utilisateur(utilisateur.pk, ttl=TTL_REVOCATION)

            # Effet 6 — Socle §2.4. **Ni le mot de passe, ni le jeton, ni son
            # empreinte** n'entrent dans le journal : il se consulte et s'exporte.
            # Ce qui compte ici est qu'un changement a eu lieu, par quelle porte,
            # et depuis où.
            journaliser(
                action=ActionAudit.MODIFICATION,
                type_entite="utilisateur",
                entite_id=utilisateur.pk,
                utilisateur_id=utilisateur.pk,
                valeur_avant={"motif": jeton.motif, "etait_bloque": etait_bloque},
                valeur_apres={"mot_de_passe": "modifie", "sessions": "revoquees"},
                adresse_ip=ip,
                appareil=appareil,
            )

        transaction.on_commit(lambda: _confirmer(utilisateur))
        return utilisateur


def _confirmer(utilisateur: Utilisateur) -> None:
    """E3 — la confirmation. Elle prévient d'un changement qu'on n'a pas fait."""
    envoyer(
        "mot_de_passe_modifie",
        "Votre mot de passe CCD Digital a été modifié",
        utilisateur.email,
    )
