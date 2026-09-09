"""Le franchissement des étapes de configuration — contrat T-024 §5.

**La progression enregistre un fait ; elle ne le produit pas** (R-98).
L'entreprise, le projet et les invitations ont déjà été créés par leurs
endpoints respectifs : ce service note qu'une étape a été franchie, avance le
point de reprise, et bascule à `TERMINEE` quand les trois le sont.

Tout faire ici serait tentant — recevoir le formulaire de l'étape 2, créer le
tiers, le projet, l'affectation, marquer l'étape. Ce serait un service qui
connaît trois modules, et **une seconde façon de créer un projet**, à côté de
`POST /projets/`. Les deux divergeraient à la première règle de gestion ajoutée
d'un seul côté.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.audit.services import journaliser
from apps.core.enums import ActionAudit
from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.onboarding.models import (
    ETAPES,
    ETAPES_FACULTATIVES,
    EtapeConfiguration,
    ProgressionConfiguration,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigurationTerminee",
    "EtapeNonFacultative",
    "EtapePrecedenteNonFranchie",
    "EtapesManquantes",
    "franchir",
    "lire_ou_creer",
    "passer",
    "terminer",
    "valider",
]


# --------------------------------------------------------------------------
# Les quatre refus du contrat — conventions d'API v1.2 §5.1
# --------------------------------------------------------------------------
class EtapePrecedenteNonFranchie(ErreurMetier):
    """R-94 — on ne saute pas une étape en avant."""

    code_metier = "etape_precedente_non_franchie"
    default_detail = "Une étape précédente n'a pas encore été franchie."


class EtapeNonFacultative(ErreurMetier):
    """R-93 — seule `EQUIPE` se passe."""

    code_metier = "etape_non_facultative"
    default_detail = "Cette étape ne peut pas être passée."


class EtapesManquantes(ErreurMetier):
    """`terminer` appelé avant que les trois étapes ne soient franchies."""

    code_metier = "etapes_manquantes"
    default_detail = "La configuration ne peut pas être terminée : des étapes manquent."


class ConfigurationTerminee(ErreurConflit):
    """R-95 — l'état final n'est pas réversible depuis l'API."""

    status_code = status.HTTP_409_CONFLICT
    code_metier = "configuration_terminee"
    default_detail = "La configuration est terminée : elle ne se rouvre pas."


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------
def lire_ou_creer() -> ProgressionConfiguration:
    """La progression du schéma courant, créée si elle n'existe pas — §5.1.

    **`GET` reste sans effet de bord observable** : le client reçoit dans les
    deux cas une progression à 0 %. La création n'est visible que du serveur.

    La course de deux premiers `GET` simultanés est arbitrée par
    `uq_progression_singleton` : le perdant relit la ligne du gagnant plutôt
    que de propager une erreur d'intégrité pour une lecture.
    """
    progression = ProgressionConfiguration.objects.first()
    if progression is not None:
        return progression
    try:
        with transaction.atomic():
            return ProgressionConfiguration.objects.create()
    except IntegrityError:
        return ProgressionConfiguration.objects.get()


# --------------------------------------------------------------------------
# Franchissement
# --------------------------------------------------------------------------
def franchir(
    *, code: str, mode: str, utilisateur, adresse_ip: str | None = None
) -> ProgressionConfiguration:
    """Enregistre le franchissement d'une étape. Idempotent — §5.5.

    Renvoie la progression complète, rafraîchie.
    """
    if code not in ETAPES:
        # `400 validation`, et non 404 : le code est un champ de la requête,
        # pas une ressource. Conventions §5.
        raise ValidationError({"code": ["Étape inconnue."]})

    if mode == EtapeConfiguration.Mode.PASSEE and code not in ETAPES_FACULTATIVES:
        raise EtapeNonFacultative(details={"code": code})

    progression = lire_ou_creer()

    if progression.est_terminee:
        raise ConfigurationTerminee(details={"terminee_le": progression.terminee_le.isoformat()})

    _refuser_le_saut_en_avant(progression, code)

    # **Le rejeu est arbitré par `uq_etape_configuration`, pas par un `if`.**
    # `get_or_create` retente un `get` lorsque l'INSERT heurte l'unicité : deux
    # administrateurs qui valident `PROJET` en même temps produisent une seule
    # ligne, et les deux appels répondent `200` (R-92, test 5).
    #
    # `franchie_le` ne bouge donc jamais au rejeu (R-96) : il date le premier
    # franchissement, qui est ce que mesure l'agrégat « temps de configuration ».
    # Le remettre à jour à chaque correction ferait passer une entreprise de dix
    # minutes à trois semaines parce que quelqu'un a corrigé une faute de frappe
    # dans le RCCM.
    etape, creee = EtapeConfiguration.objects.get_or_create(
        progression=progression,
        code=code,
        defaults={"mode": mode, "franchie_par": utilisateur, "cree_par": utilisateur},
    )

    if creee:
        # **Le vocabulaire du journal est fermé** — `ActionAudit`, huit valeurs.
        # Un code inventé sur place (« ETAPE_FRANCHIE ») dépasse la colonne, et
        # surtout rendrait le journal illisible : ce qui distingue cette entrée
        # d'une autre validation, c'est `type_entite` et `valeur_apres`.
        journaliser(
            action=ActionAudit.VALIDATION,
            type_entite="EtapeConfiguration",
            entite_id=etape.pk,
            utilisateur_id=getattr(utilisateur, "pk", None),
            valeur_apres={"code": code, "mode": mode},
            adresse_ip=adresse_ip,
        )

    _avancer_le_point_de_reprise(progression)
    _terminer_si_tout_est_franchi(progression, utilisateur, adresse_ip)

    progression.refresh_from_db()
    return progression


def valider(*, code: str, utilisateur, adresse_ip: str | None = None) -> ProgressionConfiguration:
    """L'étape a produit des données — §5.2."""
    return franchir(
        code=code,
        mode=EtapeConfiguration.Mode.VALIDEE,
        utilisateur=utilisateur,
        adresse_ip=adresse_ip,
    )


def passer(*, code: str, utilisateur, adresse_ip: str | None = None) -> ProgressionConfiguration:
    """« Passer cette étape » — `EQUIPE` uniquement, §5.3.

    **Passer compte comme franchir** (R-93). Un utilisateur qui décide
    sciemment de ne pas inviter son équipe a terminé sa configuration : le
    contraire laisserait une bannière « Configuration 67 % » sur son tableau de
    bord pour toujours, en réponse à un geste qu'il a fait exprès.

    La distinction est conservée en base malgré tout — elle ne coûte qu'une
    colonne et répond à une question que l'éditeur posera. Un chiffre qu'on n'a
    pas gardé est un chiffre qu'on ne pourra jamais reconstituer.
    """
    return franchir(
        code=code,
        mode=EtapeConfiguration.Mode.PASSEE,
        utilisateur=utilisateur,
        adresse_ip=adresse_ip,
    )


def terminer(*, utilisateur, adresse_ip: str | None = None) -> ProgressionConfiguration:
    """Le bouton « Accéder au tableau de bord » — §5.4.

    **Il ne fait rien de plus que constater.** L'effet 3 du §5.2 a déjà basculé
    le statut au franchissement de la dernière étape ; cet appel existe pour le
    seul cas où l'utilisateur a fermé l'onglet avant l'écran de confirmation.
    """
    progression = lire_ou_creer()

    if progression.est_terminee:
        return progression

    manquantes = _etapes_manquantes(progression)
    if manquantes:
        raise EtapesManquantes(details={"etapes": manquantes})

    _terminer_si_tout_est_franchi(progression, utilisateur, adresse_ip)
    progression.refresh_from_db()
    return progression


# --------------------------------------------------------------------------
# Rouages
# --------------------------------------------------------------------------
def _codes_franchis(progression: ProgressionConfiguration) -> set[str]:
    return set(progression.etapes.values_list("code", flat=True))


def _etapes_manquantes(progression: ProgressionConfiguration) -> list[str]:
    franchies = _codes_franchis(progression)
    return [code for code in ETAPES if code not in franchies]


def _refuser_le_saut_en_avant(progression: ProgressionConfiguration, code: str) -> None:
    """R-94 — un projet ne se crée pas avant que l'entreprise ne soit renseignée.

    La contrainte porte sur le saut **en avant** : revenir sur une étape déjà
    franchie reste permis, et sans effet (§5.5).
    """
    franchies = _codes_franchis(progression)
    absentes = [
        precedente for precedente in ETAPES[: ETAPES.index(code)] if precedente not in franchies
    ]
    if absentes:
        raise EtapePrecedenteNonFranchie(details={"etapes": absentes})


def _avancer_le_point_de_reprise(progression: ProgressionConfiguration) -> None:
    """`etape_courante` est la **première étape non franchie**, recalculée — §6.

    Calculée et non incrémentée : un compteur qui avance de un finirait par
    pointer une étape déjà franchie.
    """
    manquantes = _etapes_manquantes(progression)
    courante = manquantes[0] if manquantes else ETAPES[-1]
    if progression.etape_courante != courante:
        ProgressionConfiguration.objects.filter(pk=progression.pk).update(etape_courante=courante)
        progression.etape_courante = courante


def _terminer_si_tout_est_franchi(progression, utilisateur, adresse_ip) -> None:
    """Bascule à `TERMINEE` — **conditionnellement, en SQL** (R-97).

    Un `if progression.terminee_le is None:` suivi d'un `save()` laisse la
    fenêtre ouverte entre la lecture et l'écriture : deux administrateurs qui
    terminent en même temps écriraient deux horodatages de fin. La condition
    dans le `WHERE` la ferme — le second `UPDATE` ne touche aucune ligne.
    """
    if _etapes_manquantes(progression):
        return

    lignes = ProgressionConfiguration.objects.filter(
        pk=progression.pk, terminee_le__isnull=True
    ).update(
        terminee_le=timezone.now(),
        statut=ProgressionConfiguration.Statut.TERMINEE,
        etape_courante=ETAPES[-1],
    )

    if lignes:
        journaliser(
            action=ActionAudit.VALIDATION,
            type_entite="ProgressionConfiguration",
            entite_id=progression.pk,
            utilisateur_id=getattr(utilisateur, "pk", None),
            valeur_apres={"statut": ProgressionConfiguration.Statut.TERMINEE},
            adresse_ip=adresse_ip,
        )
