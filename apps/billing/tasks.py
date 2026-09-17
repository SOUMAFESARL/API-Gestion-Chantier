"""Tâches Celery de la facturation. Elles appellent un service, jamais l'inverse."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# Les quatre seuils du parcours de l'essai gratuit §2.1, dans l'ordre où ils
# tombent. J+0 clôt la série : c'est le jour où l'essai est fini.
SEUILS = (7, 3, 1, 0)


@shared_task
def relancer_essais() -> int:
    """Les quatre relances de l'essai — parcours §2, US-016.

    **Elle tourne dans `public`** : c'est là que vivent les abonnements. Puis
    elle **entre dans le schéma de chaque client** pour compter ce qui y a été
    construit. Sans cette bascule, elle compterait les projets de `public` —
    c'est-à-dire aucun — et annoncerait à chaque client qu'il n'a rien fait.
    *La tâche ne lèverait aucune erreur : elle trouve zéro, et zéro est un
    nombre valide.* C'est la règle 3 du `CLAUDE.md`, et c'est ici qu'elle se paie.

    **Elle ne décide de rien.** Le passage en lecture seule est évalué à la
    requête, pas ici : une tâche qui coupe l'accès à 06 h 00 UTC couperait
    quelqu'un en train de saisir. À J+0 elle pose le statut et envoie le
    message — elle rend l'état visible (§3.1).
    """
    from apps.billing.models import Abonnement, RelanceEssai
    from apps.billing.services.relances import bilan_du_schema, destinataires_relance
    from apps.core.emails import envoyer

    envoyees = 0
    aujourdhui = timezone.localdate()

    for seuil in SEUILS:
        # Une date **exacte**, pas un intervalle : c'est ce qui rend la tâche
        # rejouable sans rattraper des jours passés.
        cible = aujourdhui + timedelta(days=seuil)
        abonnements = Abonnement.objects.filter(
            statut=Abonnement.Statut.ESSAI, fin_essai=cible
        ).select_related("entreprise")

        for abonnement in abonnements:
            schema = abonnement.entreprise.schema_name

            try:
                with schema_context(schema):
                    bilan = bilan_du_schema()
                    adresses = destinataires_relance()
            except Exception:
                # Un schéma illisible ne doit pas arrêter la tournée des autres.
                logger.exception("Relance impossible pour le schéma %s", schema)
                continue

            if not adresses:
                # Un espace sans administrateur actif : personne à qui écrire.
                logger.warning("Aucun destinataire de relance dans le schéma %s", schema)
                continue

            # La trace **avant** l'envoi : si la contrainte refuse la ligne, la
            # relance a déjà été faite et le message ne doit pas repartir.
            _, cree = RelanceEssai.objects.get_or_create(
                abonnement=abonnement,
                seuil=seuil,
                defaults={"destinataires": len(adresses)},
            )
            if not cree:
                continue

            envoyer(
                "essai_relance",
                _sujet(seuil, abonnement.entreprise.raison_sociale),
                adresses,
                {
                    "raison_sociale": abonnement.entreprise.raison_sociale,
                    "jours_restants": seuil,
                    "bilan": bilan,
                    "lien_abonnement": _lien_abonnement(abonnement.entreprise),
                },
            )
            envoyees += 1

            if seuil == 0:
                _clore_essai(abonnement)

    return envoyees


def _sujet(seuil: int, raison_sociale: str) -> str:
    if seuil == 0:
        return f"L'essai de {raison_sociale} est terminé"
    if seuil == 1:
        return f"Dernier jour d'essai pour {raison_sociale}"
    return f"Il reste {seuil} jours d'essai à {raison_sociale}"


def _lien_abonnement(entreprise) -> str:
    from django.conf import settings

    base_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    if not base_url:
        protocole = "http" if settings.DEBUG else "https"
        port = ":3000" if settings.DEBUG else ""
        domaine = getattr(settings, "DOMAINE_PRINCIPAL", "localhost")
        base_url = f"{protocole}://{domaine}{port}"

    return f"{base_url}/parametres/abonnement"


def _clore_essai(abonnement) -> None:
    """J+0 — le statut suit ce que l'email vient d'annoncer.

    `lecture_seule_depuis` est posé ici, mais **ce n'est pas lui qui coupe
    l'accès** : la permission l'évalue à chaque requête, de sorte que la
    personne finit son geste et rencontre le mur à l'action suivante (§3.1).
    """
    from django.utils import timezone as tz

    abonnement.statut = abonnement.Statut.SUSPENDU
    abonnement.lecture_seule_depuis = abonnement.lecture_seule_depuis or tz.now()
    abonnement.save(update_fields=["statut", "lecture_seule_depuis", "modifie_le"])


@shared_task
def reconcilier_paiements_recents() -> dict:
    """Réconciliation rapide des paiements Mobile Money récents (entre 2 et 30 min).

    Tourne à haute fréquence (toutes les 2 minutes) pour débloquer sans délai les utilisateurs
    dont le push USSD/Mobile Money a tardé (> 3 min) ou dont l'IPN CinetPay a été retardé.
    """
    from apps.billing.services.paiement import PaiementAbonnementService

    logger.info("Démarrage réconciliation CinetPay (transactions récentes 2-30 min)...")
    return PaiementAbonnementService.verifier_paiements_en_attente(
        delai_min_minutes=2,
        delai_max_minutes=30,
        timeout_heures=None,
    )


@shared_task
def reconcilier_paiements_anciens() -> dict:
    """Réconciliation périodique des paiements en attente plus anciens (entre 30 min et 24h).

    Tourne toutes les 15 minutes. Marque également comme `EXPIRE` les transactions
    qui ont dépassé le délai de 24h sans confirmation opérateur.
    """
    from apps.billing.services.paiement import PaiementAbonnementService

    logger.info("Démarrage réconciliation CinetPay (transactions anciennes 30 min - 24h)...")
    return PaiementAbonnementService.verifier_paiements_en_attente(
        delai_min_minutes=30,
        delai_max_minutes=1440,
        timeout_heures=24,
    )


@shared_task
def verifier_paiements_en_attente() -> dict:
    """Tâche générique de réconciliation de l'ensemble des paiements CinetPay en attente.

    Tourne dans le schéma `public` (tables billing) sur un intervalle régulier.
    """
    from apps.billing.services.paiement import PaiementAbonnementService

    logger.info("Démarrage de la tâche Celery globale de réconciliation des paiements CinetPay...")
    resultat = PaiementAbonnementService.verifier_paiements_en_attente(
        delai_min_minutes=2,
        timeout_heures=24,
    )
    logger.info(
        f"Fin de la réconciliation CinetPay : {resultat.get('confirmes')} confirmés, "
        f"{resultat.get('echoues')} échoués/expirés, {resultat.get('en_attente')} en attente."
    )
    return resultat
