"""Alertes calculees et rappels des abonnements payants."""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.accounts.models import Utilisateur
from apps.billing.models import Abonnement, RappelExpiration
from apps.core.emails import envoyer
from apps.core.enums import RoleGlobal, StatutUtilisateur

logger = logging.getLogger(__name__)
SEUILS_EXPIRATION = (7, 3, 1, 0)
ROLES_FACTURATION = (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL, RoleGlobal.DIRECTEUR_FINANCIER)


def alerte_expiration(abonnement, aujourd_hui=None):
    aujourd_hui = aujourd_hui or timezone.localdate()
    jours = (abonnement.date_fin - aujourd_hui).days
    if (
        abonnement.statut
        not in (
            Abonnement.Statut.ACTIF,
            Abonnement.Statut.IMPAYE,
            Abonnement.Statut.SUSPENDU,
        )
        or jours > 7
    ):
        return None
    seuil = next(seuil for seuil in sorted(SEUILS_EXPIRATION) if jours <= seuil)
    if jours < 0:
        message = "Votre abonnement a expire. Renouvelez-le pour continuer a utiliser le service."
    elif jours == 0:
        message = "Votre abonnement arrive a expiration aujourd'hui. Pensez a le renouveler."
    else:
        message = (
            f"Votre abonnement arrive a expiration dans {jours} jour(s). Pensez a le renouveler."
        )
    return {
        "id": f"{abonnement.pk}:{abonnement.date_fin.isoformat()}:{seuil}",
        "type": "ABONNEMENT_EXPIRE" if jours < 0 else "ABONNEMENT_EXPIRATION",
        "abonnement_id": abonnement.pk,
        "entreprise_id": abonnement.entreprise_id,
        "date_expiration": abonnement.date_fin,
        "jours_restants": max(0, jours),
        "seuil": seuil,
        "niveau": "URGENT" if jours <= 1 else "AVERTISSEMENT",
        "message": message,
        "lien_renouvellement": settings.FRONTEND_URL.rstrip("/") + "/parametres/abonnement",
    }


def notifications_expiration(entreprise):
    with schema_context(get_public_schema_name()):
        abonnement = (
            Abonnement.objects.filter(entreprise=entreprise)
            .order_by("-date_debut", "-cree_le", "-pk")
            .first()
        )
        alerte = alerte_expiration(abonnement) if abonnement else None
        return [alerte] if alerte else []


def envoyer_rappels_expiration():
    """Rejouable le meme jour ; les echecs SMTP restent eligibles a une reprise."""
    aujourd_hui = timezone.localdate()
    envoyes = 0
    with schema_context(get_public_schema_name()):
        candidats = list(
            Abonnement.objects.filter(
                statut=Abonnement.Statut.ACTIF,
                date_fin__in=[aujourd_hui + timedelta(days=j) for j in SEUILS_EXPIRATION],
            )
            .exclude(entreprise__schema_name=get_public_schema_name())
            .values_list("pk", flat=True)
        )
        for abonnement_id in candidats:
            try:
                # Serialise les executions concurrentes et les renouvellements de cette ligne.
                with transaction.atomic():
                    abonnement = (
                        Abonnement.objects.select_for_update()
                        .select_related("entreprise")
                        .get(pk=abonnement_id)
                    )
                    seuil = (abonnement.date_fin - aujourd_hui).days
                    if (
                        abonnement.statut != Abonnement.Statut.ACTIF
                        or seuil not in SEUILS_EXPIRATION
                    ):
                        continue
                    with schema_context(abonnement.entreprise.schema_name):
                        destinataires = list(
                            Utilisateur.objects.filter(
                                role_global__in=ROLES_FACTURATION,
                                statut=StatutUtilisateur.ACTIF,
                                is_active=True,
                            )
                            .values_list("email", flat=True)
                            .distinct()
                        )
                    alerte = alerte_expiration(abonnement, aujourd_hui)
                    for email in destinataires:
                        rappel, _ = RappelExpiration.objects.get_or_create(
                            abonnement=abonnement,
                            date_echeance=abonnement.date_fin,
                            seuil=seuil,
                            destinataire=email,
                        )
                        if rappel.envoye_le:
                            continue
                        if envoyer(
                            "abonnement_expiration",
                            "Votre abonnement arrive a expiration",
                            email,
                            {**alerte, "raison_sociale": abonnement.entreprise.raison_sociale},
                        ):
                            rappel.envoye_le = timezone.now()
                            rappel.save(update_fields=["envoye_le", "modifie_le"])
                            envoyes += 1
            except Exception:
                logger.exception("Echec du rappel d'abonnement %s", abonnement_id)
    return envoyes
