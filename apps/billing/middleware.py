"""Le passage en lecture seule — évalué à chaque requête, US-016.

**Pourquoi un middleware et non une permission DRF.** Une permission ne
s'applique qu'aux vues qui ne redéfinissent pas `permission_classes` — et la
plupart des vues du produit écrivent `permission_classes = [IsAuthenticated]`,
ce qui **remplace** le réglage global au lieu de s'y ajouter. Le verrou aurait
donc protégé les vues qui ne l'ont pas déclaré, et laissé passer les autres :
exactement l'inverse de ce qu'on veut d'un verrou.

*L'API annonçait cette règle sans l'appliquer.* Le sérialiseur d'abonnement
expose un booléen `lecture_seule` depuis le premier jour, mais rien ne refusait
l'écriture : un client dont l'essai avait expiré continuait de saisir, et seule
son interface le retenait. Une règle que seul le navigateur applique n'est pas
une règle.

**Le contrôle est à la requête, pas à l'heure dite** — parcours de l'essai
gratuit §3.1. Une tâche planifiée qui basculerait les entreprises à 06 h 00 UTC
couperait quelqu'un au milieu d'une saisie. Évalué à la requête, l'effet est
inverse : la personne finit son geste, et c'est **l'action suivante** qui
rencontre le mur.
"""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.utils import timezone
from django_tenants.utils import get_public_schema_name

logger = logging.getLogger(__name__)

METHODES_ECRITURE = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Ce qui reste ouvert en lecture seule — et ce n'est pas une commodité.
#
# **Fermer ces chemins enfermerait le client dehors** : il ne pourrait plus
# souscrire, donc plus rien débloquer. Un mur qui condamne aussi la porte de
# sortie n'est pas un mur, c'est un piège.
CHEMINS_OUVERTS = (
    "/api/v1/abonnement",  # voir son abonnement et souscrire — la sortie
    "/api/v1/auth/",  # se connecter, se déconnecter, changer son mot de passe
    "/api/health",
    "/api/v1/schema",
    "/api/v1/docs",
)


class LectureSeuleAbonnementMiddleware:
    """Refuse l'écriture quand l'abonnement du client ne la permet plus."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._doit_refuser(request):
            return JsonResponse(
                {
                    "erreur": {
                        "code": "abonnement_suspendu",
                        "message": (
                            "Votre essai est terminé. Vous pouvez toujours consulter et "
                            "exporter vos données ; pour reprendre la saisie, choisissez "
                            "un plan."
                        ),
                        "details": {"lecture_seule": True},
                        "trace_id": getattr(request, "identifiant_requete", None),
                    }
                },
                status=403,
            )
        return self.get_response(request)

    def _doit_refuser(self, request) -> bool:
        if request.method not in METHODES_ECRITURE:
            return False
        if not request.path.startswith("/api/"):
            return False
        if request.path.startswith(CHEMINS_OUVERTS):
            return False

        # Une requête sans jeton n'a pas à apprendre l'état de l'abonnement :
        # elle doit recevoir son `401` habituel, pas un `403` qui renseigne.
        if not request.META.get("HTTP_AUTHORIZATION"):
            return False

        tenant = getattr(request, "tenant", None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            # Les endpoints de la plateforme ont leurs propres règles.
            return False

        return self.en_lecture_seule(tenant)

    @staticmethod
    def en_lecture_seule(entreprise) -> bool:
        """Vrai quand l'entreprise ne peut plus écrire.

        Trois causes, et la troisième est celle qui compte : **l'essai peut être
        expiré sans que la tâche de 06 h 00 soit passée.** Se fier au seul statut
        laisserait une journée d'écriture gratuite à qui se connecte tôt.
        """
        from apps.billing.models import Abonnement

        abonnement = (
            Abonnement.objects.filter(entreprise=entreprise).order_by("-date_debut").first()
        )
        if abonnement is None:
            # Pas d'abonnement du tout : on ne bloque pas. Une entreprise sans
            # abonnement est une anomalie de provisionnement, et la sanctionner
            # ici la rendrait inutilisable sans rien expliquer.
            logger.warning("Aucun abonnement pour le schéma %s", entreprise.schema_name)
            return False

        if abonnement.lecture_seule_depuis is not None:
            return True
        if abonnement.statut in (
            Abonnement.Statut.SUSPENDU,
            Abonnement.Statut.RESILIE,
            Abonnement.Statut.IMPAYE,
        ):
            return True
        return (
            abonnement.statut == Abonnement.Statut.ESSAI
            and abonnement.fin_essai is not None
            and abonnement.fin_essai < timezone.localdate()
        )
