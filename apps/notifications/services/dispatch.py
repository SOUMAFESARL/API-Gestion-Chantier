"""Service de diffusion et d'orchestration des notifications de chantier."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from apps.accounts.models import Utilisateur
from apps.notifications.selectors.notifications import (
    obtenir_destinataires_projet_par_permission,
    peut_recevoir_email,
    peut_recevoir_in_app,
)
from apps.notifications.tasks import envoyer_email_notification_async
from apps.projets.models import Projet

if TYPE_CHECKING:
    from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

__all__ = ["notifier_projet_par_permission"]


def notifier_projet_par_permission(
    projet: Projet | str,
    evenement: str | Any,
    permission_requise: str | Any,
    *,
    auteur: Any | None = None,
    objet: Any | None = None,
    titre: str,
    message: str,
    lien: str,
    regroupement: str | None = None,
) -> list[Notification]:
    """Diffuse une notification ciblée aux membres actifs d'un projet selon leurs permissions.

    Exemple d'appel d'une ligne :
    >>> notifier_projet_par_permission(p, "DOC", "ged.voir", titre="Plan", message="Ok", lien="/d")

    Fonctionnement :
    1. Résout le projet et ses membres actifs habilités par `permission_requise`.
    2. Exclut systématiquement `auteur` pour éviter l'auto-notification de l'émetteur.
    3. Respecte les réglages de `PreferenceNotification` de chaque utilisateur (in-app, e-mail).
    4. Crée la notification in-app pour la cloche.
    5. Applique l'anti-saturation si regroupement fourni (1 rapport + 10 photos = 1 notification).
    6. Déclenche l'envoi d'e-mail asynchrone via Celery avec lien d'action directe.
    """
    from apps.notifications.models import Notification

    # 1. Résolution de l'instance Projet
    if not isinstance(projet, Projet):
        projet_instance = Projet.objects.select_related("entreprise").filter(pk=projet).first()
        if not projet_instance:
            logger.warning("Notification annulée : projet %s introuvable", projet)
            return []
        projet = projet_instance

    evenement_code = str(getattr(evenement, "value", evenement))
    perm_code = str(getattr(permission_requise, "value", permission_requise))

    # 2. Résolution des métadonnées de l'objet cible (clic / lien)
    type_objet = ""
    objet_id = None
    if objet is not None:
        type_objet = str(getattr(objet, "type_objet", objet.__class__.__name__.upper()))
        raw_id = getattr(objet, "id", getattr(objet, "pk", None))
        if raw_id is not None:
            objet_id = raw_id

    # 3. Sélection des collaborateurs actifs habilités (auteur exclu)
    destinataires = obtenir_destinataires_projet_par_permission(
        projet=projet,
        permission_requise=perm_code,
        auteur=auteur,
    )

    if not destinataires:
        logger.debug(
            "Aucun destinataire habilité pour l'événement %s sur le projet %s",
            evenement_code,
            projet.reference,
        )
        return []

    notifications_traitees: list[Notification] = []

    # 4. Traitement par destinataire
    for destinataire in destinataires:
        autorise_in_app = peut_recevoir_in_app(destinataire, evenement_code)
        autorise_email = peut_recevoir_email(destinataire, evenement_code)

        if not autorise_in_app and not autorise_email:
            continue

        notification: Notification | None = None
        doit_envoyer_email = autorise_email

        # 4.1. In-App avec regroupement anti-saturation
        if autorise_in_app:
            if regroupement:
                notification = Notification.objects.filter(
                    destinataire=destinataire,
                    projet=projet,
                    cle_groupe=str(regroupement),
                    est_lue=False,
                    supprime_le__isnull=True,
                ).first()

                if notification is not None:
                    # Incrémentation du regroupement existant
                    if hasattr(notification, "incrementer_regroupement"):
                        notification.incrementer_regroupement(delta=1)
                    else:
                        notification.compteur = (notification.compteur or 1) + 1
                        notification.titre = titre
                        notification.corps = message
                        notification.url_action = lien
                        notification.save(
                            update_fields=[
                                "compteur",
                                "titre",
                                "corps",
                                "url_action",
                                "modifie_le",
                            ]
                        )
                    # Anti-saturation : un seul e-mail pour l'ensemble du lot
                    doit_envoyer_email = False
                    notifications_traitees.append(notification)

            if notification is None:
                canaux = {"in_app": True, "email": autorise_email}
                cree_par_user = auteur if isinstance(auteur, Utilisateur) else None
                notification = Notification.objects.create(
                    entreprise=projet.entreprise,
                    destinataire=destinataire,
                    projet=projet,
                    type_evenement=evenement_code,
                    titre=titre,
                    corps=message,
                    type_objet=type_objet,
                    objet_id=objet_id,
                    url_action=lien,
                    canal="IN_APP",
                    canaux_envoyes=canaux,
                    cle_groupe=str(regroupement or ""),
                    compteur=1,
                    cree_par=cree_par_user,
                )
                notifications_traitees.append(notification)

        # 4.2. E-mail avec bouton d'action directe (asynchrone Celery)
        if doit_envoyer_email and getattr(destinataire, "email", None):
            try:
                envoyer_email_notification_async.delay(
                    email=destinataire.email,
                    sujet=titre,
                    message=message,
                    lien_action=lien,
                    libelle_action="Accéder au projet",
                    prenom=getattr(destinataire, "prenom", ""),
                    details={"Chantier": projet.nom},
                    entreprise_id=str(projet.entreprise_id) if projet.entreprise_id else None,
                )
            except Exception:
                logger.warning(
                    "Échec d'envoi asynchrone Celery pour %s, bascule synchrone",
                    destinataire.email,
                    exc_info=True,
                )
                from apps.core.emails import envoyer_email_notification

                envoyer_email_notification(
                    destinataire=destinataire.email,
                    sujet=titre,
                    message=message,
                    lien_action=lien,
                    libelle_action="Accéder au projet",
                    prenom=getattr(destinataire, "prenom", ""),
                    details={"Chantier": projet.nom},
                )

    return notifications_traitees
