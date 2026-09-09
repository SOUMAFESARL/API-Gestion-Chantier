"""Authentification — la règle de gestion, pas la vue.

Le parcours de connexion a cinq issues d'échec, et **une seule réponse**.

    adresse inconnue        ┐
    mot de passe faux       │
    compte bloqué           ├→ 401 identifiants_invalides, details vides
    compte désactivé        │
    compte jamais activé    ┘

    succès                   → 200, jetons + profil

C'est la règle R-01 du contrat d'API. Distinguer les causes revenait à
répondre à une question que personne d'autre qu'un attaquant ne pose :
l'utilisateur qui vient de saisir son mot de passe sait déjà s'il a un compte.

Ce que l'écran affiche — « Tentative 2 sur 5 », puis l'écran de blocage — est
dérivé d'un compteur tenu par le client (contrat §6.3). **Le compteur qui
bloque reste celui du serveur**, en base, dans `utilisateur.tentatives_echouees` :
celui du client ne change que ce qui est écrit à l'écran.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Utilisateur
from apps.core.enums import StatutUtilisateur
from apps.core.exceptions import ErreurMetier

__all__ = [
    "IdentifiantsInvalides",
    "authentifier",
    "duree_acces_en_secondes",
    "emettre_jetons",
    "profil_de_connexion",
]

# Socle Commun §2.2 — le renouvellement dure plus longtemps sur le terrain :
# un chef de chantier ne doit jamais voir un écran de connexion en pleine
# saisie, faute de réseau pour se réauthentifier.
DUREE_RENOUVELLEMENT = {
    "WEB": timedelta(hours=8),
    "MOBILE": timedelta(hours=24),
}


# --------------------------------------------------------------------------
# L'issue — il n'y en a qu'une
# --------------------------------------------------------------------------
class IdentifiantsInvalides(ErreurMetier):
    """La réponse générique du contrat §6.

    Elle ne porte **jamais** de `details` : ni le nombre d'essais restants, ni
    la fin d'un blocage, ni l'adresse. Chacun de ces champs répondait « ce
    compte existe » à qui ne le savait pas.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    code_metier = "identifiants_invalides"
    default_detail = _("Email ou mot de passe incorrect.")


# --------------------------------------------------------------------------
# Authentification
# --------------------------------------------------------------------------
def authentifier(email: str, mot_de_passe: str) -> Utilisateur:
    """Vérifie les identifiants et renvoie l'utilisateur, ou lève.

    ┌──────────────────────────────────────────────────────────────────────┐
    │ L'exception est CONSTRUITE dans la transaction et LEVÉE dehors.      │
    │                                                                      │
    │ Lever depuis l'intérieur annulerait le bloc — et avec lui            │
    │ l'incrément du compteur d'échecs qu'on vient d'écrire. Le compteur   │
    │ resterait à zéro, et aucun compte ne serait jamais bloqué. Le défaut │
    │ ne se voit pas : chaque tentative répond correctement « identifiants │
    │ invalides », la protection contre la force brute est simplement      │
    │ inopérante.                                                          │
    └──────────────────────────────────────────────────────────────────────┘

    `select_for_update` sérialise les tentatives concurrentes sur un même
    compte : sans lui, cinq requêtes simultanées incrémenteraient le compteur
    depuis la même valeur lue, et le blocage n'arriverait jamais non plus.
    """
    email = email.strip().lower()
    echec: ErreurMetier | None = None
    utilisateur = None

    with transaction.atomic():
        utilisateur = Utilisateur.objects.select_for_update().filter(email__iexact=email).first()

        if utilisateur is None:
            # R-02 — égalité temporelle. Le compte n'existe pas, mais on hache
            # quand même : sans cela la réponse revient en une milliseconde au
            # lieu de cent, et le chronomètre suffit à énumérer les adresses.
            Utilisateur().set_password(mot_de_passe)
            echec = IdentifiantsInvalides()

        else:
            # R-02, suite. La vérification est faite **avant** de regarder
            # l'état du compte, et sur tous les chemins : bloqué, désactivé et
            # jamais activé sortaient auparavant sans hachage, ce qui les
            # distinguait au temps de réponse alors que le corps était
            # identique. Une réponse identique qui arrive plus vite n'est pas
            # une réponse identique.
            mot_de_passe_exact = utilisateur.check_password(mot_de_passe)

            refuse = (
                utilisateur.est_bloque
                or utilisateur.statut == StatutUtilisateur.DESACTIVE
                or not utilisateur.is_active
                or utilisateur.statut == StatutUtilisateur.INVITE
            )

            if refuse:
                # Le bon mot de passe ne débloque pas, et ne réactive pas : la
                # sortie d'un compte bloqué est l'email de réinitialisation,
                # celle d'un compte désactivé est l'administrateur.
                echec = IdentifiantsInvalides()

            elif not mot_de_passe_exact:
                utilisateur.enregistrer_echec_connexion()

                # La porte « blocage » du contrat de réinitialisation §1. Le
                # Socle §2.1 est explicite : « Déblocage — par email de
                # réinitialisation uniquement ». Sans cet envoi, un compte
                # bloqué au cinquième essai n'a **aucune sortie** avant les
                # quinze minutes, et l'utilisateur n'en est pas averti.
                #
                # L'envoi est ici et pas dans le modèle : `enregistrer_echec_connexion`
                # décrit un compteur, pas un parcours.
                if utilisateur.est_bloque:
                    from apps.accounts.models import JetonReinitialisation
                    from apps.accounts.services.reinitialisation import demander

                    demander(
                        utilisateur.email,
                        motif=JetonReinitialisation.Motif.BLOCAGE,
                    )

                echec = IdentifiantsInvalides()

            else:
                utilisateur.reinitialiser_echecs()
                Utilisateur.objects.filter(pk=utilisateur.pk).update(last_login=timezone.now())

    if echec is not None:
        raise echec

    return utilisateur


# --------------------------------------------------------------------------
# Jetons et profil
# --------------------------------------------------------------------------
def emettre_jetons(
    utilisateur: Utilisateur, origine: str = "WEB", sid: str | None = None
) -> dict[str, str]:
    """Produit le couple accès / renouvellement.

    L'accès garde la durée globale de 15 minutes ; seul le renouvellement
    dépend de l'origine.

    `sid` identifie la **session** — T-008 §5.1. Il est constant sur toute la
    chaîne de rotation : c'est ce qui permet de révoquer une session entière
    plutôt qu'un jeton isolé, quand l'autre moitié d'une course détient déjà
    la paire suivante. Absent, une session neuve commence.
    """
    refresh = RefreshToken.for_user(utilisateur)
    refresh.set_exp(lifetime=DUREE_RENOUVELLEMENT.get(origine, DUREE_RENOUVELLEMENT["WEB"]))

    refresh["role_global"] = utilisateur.role_global
    refresh["origine"] = origine
    refresh["sid"] = sid or str(uuid.uuid4())

    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def profil_de_connexion(utilisateur: Utilisateur) -> dict[str, object]:
    """Le profil compact joint aux jetons — contrat §4.4.

    Il évite au client un second aller-retour juste pour afficher un nom et
    construire un menu. Sur une liaison de chantier, un aller-retour coûte
    300 à 600 ms : c'est un dixième du budget de 6 s que le Socle §6.1 fixe au
    chargement initial.

    Rien ici n'est sensible : tout est déjà connu de la personne qui vient de
    saisir son mot de passe. Le détail complet reste sur
    `GET /api/v1/utilisateurs/moi/`.

    > `role_global` sert à l'affichage, **jamais** à l'autorisation. Le serveur
    > relit toujours le rôle en base pour décider d'un droit.
    """
    return {
        "id": str(utilisateur.pk),
        "email": utilisateur.email,
        "nom": utilisateur.nom,
        "prenom": utilisateur.prenom,
        "role_global": utilisateur.role_global,
        # **Le libellé vient du serveur, jamais du code de l'écran.** La barre
        # d'application traduisait le code elle-même, par une cascade de six
        # comparaisons — et il y a treize rôles. Un « Responsable Financier »
        # s'y affichait donc « RF », et tout rôle ajouté plus tard s'y
        # afficherait de même. C'est la règle du `CLAUDE.md` sur les
        # énumérations : un libellé se traduit en un seul endroit.
        "role_libelle": utilisateur.get_role_global_display(),
        "is_dg": utilisateur.is_dg,
        "is_owner": utilisateur.is_owner,
        "langue": utilisateur.langue,
        "doit_changer_mot_de_passe": utilisateur.doit_changer_mot_de_passe,
    }


def duree_acces_en_secondes() -> int:
    """Validité du jeton d'accès, en secondes — le `expire_dans` du contrat.

    Le client saurait la déduire en décodant le JWT, mais c'est une opération
    qu'aucun client ne devrait avoir à faire pour une information que le
    serveur connaît.
    """
    return int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
