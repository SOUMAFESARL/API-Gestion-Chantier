"""Sélecteurs pour le domaine des notifications et des préférences."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.droits import a_permission
from apps.core.enums import StatutUtilisateur
from apps.projets.models import AffectationProjet, Projet
from apps.projets.services.perimetres import perimetre_de

if TYPE_CHECKING:
    from apps.notifications.models import Notification, PreferenceNotification

logger = logging.getLogger(__name__)

__all__ = [
    "compter_notifications_non_lues",
    "lister_notifications_utilisateur",
    "obtenir_destinataires_projet_par_permission",
    "obtenir_preferences_utilisateur",
    "peut_recevoir_email",
    "peut_recevoir_in_app",
]


def lister_notifications_utilisateur(
    utilisateur: Utilisateur,
    *,
    non_lues_seulement: bool = False,
    projet: Projet | None = None,
    limite: int | None = 50,
) -> QuerySet[Notification]:
    """Retourne les notifications adressées à un collaborateur, ordonnées par récence.

    Optimisé pour exploiter l'index partiel `idx_notif_non_lues` quand `non_lues_seulement=True`.
    """
    from apps.notifications.models import Notification

    qs = (
        Notification.objects.filter(
            destinataire=utilisateur,
            supprime_le__isnull=True,
        )
        .select_related("projet", "destinataire")
        .order_by("-cree_le")
    )

    if non_lues_seulement:
        qs = qs.filter(est_lue=False)

    if projet is not None:
        qs = qs.filter(projet=projet)

    if limite is not None and limite > 0:
        qs = qs[:limite]

    return qs


def compter_notifications_non_lues(
    utilisateur: Utilisateur,
    *,
    projet: Projet | None = None,
) -> int:
    """Compte les notifications non lues pour le badge de la cloche."""
    from apps.notifications.models import Notification

    qs = Notification.objects.filter(
        destinataire=utilisateur,
        est_lue=False,
        supprime_le__isnull=True,
    )
    if projet is not None:
        qs = qs.filter(projet=projet)
    return qs.count()


def obtenir_preferences_utilisateur(
    utilisateur: Utilisateur,
) -> QuerySet[PreferenceNotification]:
    """Retourne l'ensemble des réglages de préférences d'un utilisateur."""
    from apps.notifications.models import PreferenceNotification

    return PreferenceNotification.objects.filter(
        utilisateur=utilisateur,
        supprime_le__isnull=True,
    )


def peut_recevoir_in_app(utilisateur: Utilisateur, type_evenement: str) -> bool:
    """Détermine si l'utilisateur accepte la notification in-app pour ce type d'événement.

    Par défaut (aucune préférence enregistrée), la notification in-app est activée (True).
    """
    from apps.notifications.models import PreferenceNotification

    pref = (
        PreferenceNotification.objects.filter(
            utilisateur=utilisateur,
            type_evenement=str(type_evenement),
            supprime_le__isnull=True,
        )
        .only("in_app")
        .first()
    )
    if pref is not None:
        return bool(pref.in_app)
    return True


def peut_recevoir_email(utilisateur: Utilisateur, type_evenement: str) -> bool:
    """Détermine si l'utilisateur accepte la notification par e-mail pour cet événement.

    Exige une adresse e-mail valide. Par défaut (sans préférence), l'e-mail est activé (True).
    """
    adresse = getattr(utilisateur, "email", "") or ""
    if not adresse.strip():
        return False

    from apps.notifications.models import PreferenceNotification

    pref = (
        PreferenceNotification.objects.filter(
            utilisateur=utilisateur,
            type_evenement=str(type_evenement),
            supprime_le__isnull=True,
        )
        .only("email")
        .first()
    )
    if pref is not None:
        return bool(pref.email)
    return True


def obtenir_destinataires_projet_par_permission(
    projet: Projet,
    permission_requise: str,
    *,
    auteur: Any | None = None,
) -> list[Utilisateur]:
    """Identifie les membres actifs du projet habilités par la permission requise.

    Règles :
    1. Sélectionne les affectations actives au chantier (en cours à date du jour).
    2. Inclut également le chef de projet et le conducteur de travaux rattachés au projet.
    3. Exclut impérativement l'auteur de l'action pour éviter l'auto-notification.
    4. Vérifie que le collaborateur détient la permission requise (soit via son rôle
       sur la plateforme ou portée entreprise, soit via son rôle affecté au projet).
    5. Cloisonnement strict à l'entreprise du chantier (D9).
    """
    jour = timezone.localdate()
    affectations = (
        AffectationProjet.objects.filter(
            projet=projet,
            est_actif=True,
            supprime_le__isnull=True,
            utilisateur__supprime_le__isnull=True,
            utilisateur__statut=StatutUtilisateur.ACTIF,
            utilisateur__is_active=True,
        )
        .filter(Q(date_debut__isnull=True) | Q(date_debut__lte=jour))
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        .select_related("utilisateur", "utilisateur__role", "utilisateur__role_personnalise")
        .prefetch_related("perimetres")
    )

    candidats: dict[Any, Utilisateur] = {}
    for aff in affectations:
        if aff.utilisateur_id:
            candidats[aff.utilisateur_id] = aff.utilisateur

    if (
        projet.chef_projet_id
        and projet.chef_projet
        and getattr(projet.chef_projet, "statut", None) == StatutUtilisateur.ACTIF
        and getattr(projet.chef_projet, "is_active", True)
        and projet.chef_projet.supprime_le is None
    ):
        candidats[projet.chef_projet_id] = projet.chef_projet

    if (
        projet.conducteur_travaux_id
        and projet.conducteur_travaux
        and getattr(projet.conducteur_travaux, "statut", None) == StatutUtilisateur.ACTIF
        and getattr(projet.conducteur_travaux, "is_active", True)
        and projet.conducteur_travaux.supprime_le is None
    ):
        candidats[projet.conducteur_travaux_id] = projet.conducteur_travaux

    # Exclusion de l'auteur de l'action
    if auteur is not None:
        auteur_id = getattr(auteur, "pk", getattr(auteur, "id", auteur))
        candidats.pop(auteur_id, None)

    perm_code = getattr(permission_requise, "value", str(permission_requise)).lower()

    destinataires: list[Utilisateur] = []
    for user in candidats.values():
        # Contrôle des habilitations : permissions effectives plateforme OU périmètre projet
        has_perm = a_permission(user, perm_code, entreprise=projet.entreprise) or perimetre_de(
            user, projet
        ).peut_quelque_part(perm_code)

        if has_perm:
            destinataires.append(user)

    return destinataires
