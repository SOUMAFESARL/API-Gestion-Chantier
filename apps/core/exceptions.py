"""Format d'erreur unique de l'API — conventions T-005 §5.

Une API qui répond tantôt `{"detail": …}`, tantôt `{"champ": [...]}`,
tantôt du HTML oblige le client à écrire un cas par endpoint. Un seul
format, partout :

    {
      "erreur": {
        "code": "rapport_deja_existant",
        "message": "Un rapport existe déjà pour ce lot à cette date.",
        "details": {},
        "trace_id": "01J8XQ2M4K7N9P0R"
      }
    }

`code` est un contrat machine : c'est sur lui que le client branche son
comportement. `message` est fait pour l'œil humain et changera.
"""

import logging

from django.core.exceptions import ValidationError as ValidationDjango
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.core.middleware import identifiant_requete_courant

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Codes techniques — dérivés du statut HTTP
# --------------------------------------------------------------------------
CODES = {
    status.HTTP_400_BAD_REQUEST: "validation",
    status.HTTP_401_UNAUTHORIZED: "non_authentifie",
    status.HTTP_403_FORBIDDEN: "acces_refuse",
    status.HTTP_404_NOT_FOUND: "introuvable",
    status.HTTP_405_METHOD_NOT_ALLOWED: "methode_non_autorisee",
    status.HTTP_409_CONFLICT: "conflit",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "fichier_trop_volumineux",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "regle_metier",
    status.HTTP_429_TOO_MANY_REQUESTS: "trop_de_requetes",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_indisponible",
}

MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "Certains champs sont invalides.",
    status.HTTP_401_UNAUTHORIZED: "Vous devez être connecté pour effectuer cette action.",
    status.HTTP_403_FORBIDDEN: "Vous n'avez pas les droits nécessaires pour cette action.",
    status.HTTP_404_NOT_FOUND: "La ressource demandée est introuvable.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Cette méthode n'est pas autorisée ici.",
    status.HTTP_409_CONFLICT: "Cette opération entre en conflit avec une donnée existante.",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "Le fichier dépasse la taille maximale autorisée.",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "Cette opération est refusée par une règle de gestion.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Trop de requêtes. Réessayez dans un instant.",
    status.HTTP_503_SERVICE_UNAVAILABLE: (
        "Service momentanément indisponible. Réessayez dans un instant."
    ),
}


# --------------------------------------------------------------------------
# Erreurs métier — codes stables, catalogue des conventions §5.1
# --------------------------------------------------------------------------
class ErreurMetier(APIException):
    """Une règle de gestion refuse l'opération.

    À distinguer d'une erreur de validation : les champs sont corrects,
    c'est l'opération qui est interdite dans l'état courant. Le client
    l'affiche comme un message d'ensemble, pas sous un champ de formulaire.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code_metier = "regle_metier"
    default_detail = "Cette opération est refusée par une règle de gestion."

    def __init__(self, detail=None, details=None):
        super().__init__(detail or self.default_detail)
        self.details = details or {}


class ErreurConflit(ErreurMetier):
    """L'opération entre en conflit avec une donnée déjà présente."""

    status_code = status.HTTP_409_CONFLICT
    code_metier = "conflit"


class RapportDejaExistant(ErreurConflit):
    code_metier = "rapport_deja_existant"
    default_detail = "Un rapport existe déjà pour ce lot à cette date."


class ModeExecutionVerrouille(ErreurMetier):
    code_metier = "mode_execution_verrouille"
    default_detail = (
        "Le mode d'exécution ne peut plus être modifié : un rapport a déjà été soumis sur ce lot."
    )


class BordereauVerrouille(ErreurMetier):
    code_metier = "bordereau_verrouille"
    default_detail = "Le bordereau ne peut plus être modifié : un bon de paiement a déjà été émis."


class RapportNonModifiable(ErreurMetier):
    code_metier = "rapport_non_modifiable"
    default_detail = "Un rapport approuvé ne peut plus être modifié, seulement annoté."


class QuantitesNonValidees(ErreurMetier):
    code_metier = "quantites_non_validees"
    default_detail = (
        "Un bon de paiement ne peut porter que des quantités validées par le Conducteur de Travaux."
    )


class SignatureNiveauInsuffisant(ErreurMetier):
    code_metier = "signature_niveau_insuffisant"
    default_detail = "Le montant de ce bon exige un niveau de signature supérieur."


class QuotaPlanAtteint(ErreurMetier):
    status_code = status.HTTP_403_FORBIDDEN
    code_metier = "quota_plan_atteint"
    default_detail = "La limite de votre abonnement est atteinte."


class AbonnementSuspendu(ErreurMetier):
    status_code = status.HTTP_403_FORBIDDEN
    code_metier = "abonnement_suspendu"
    default_detail = "Votre abonnement est suspendu. Régularisez pour retrouver l'accès."


class PhotosMaxAtteint(ErreurMetier):
    code_metier = "photos_max_atteint"
    default_detail = "Un rapport ne peut pas porter plus de cinq photos."


class ActionInterditeDelegue(ErreurMetier):
    status_code = status.HTTP_403_FORBIDDEN
    code_metier = "action_interdite_delegue"
    default_detail = "Seul le Directeur Général peut inviter ou nommer un administrateur."


class ActionReserveeDg(ErreurMetier):
    status_code = status.HTTP_403_FORBIDDEN
    code_metier = "action_reservee_dg"
    default_detail = "Seul le Directeur Général a autorité pour modifier ou supprimer des rôles."


class DgNonAssignableCommeCp(ErreurMetier):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code_metier = "dg_non_assignable_comme_cp"
    default_detail = "Le Directeur Général ne peut pas s'auto-désigner comme Chef de projet."


class ChefProjetRequis(ErreurMetier):
    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "chef_projet_requis"
    default_detail = "L'assignation d'un Chef de Projet est obligatoire (existant ou invité)."


class RoleSubstitutionObligatoire(ErreurMetier):
    status_code = status.HTTP_400_BAD_REQUEST
    code_metier = "substitution_obligatoire"
    default_detail = (
        "Vous devez obligatoirement sélectionner un rôle de substitution "
        "pour réaffecter les utilisateurs associés."
    )


# --------------------------------------------------------------------------
# Gestionnaire
# --------------------------------------------------------------------------
def gestionnaire_erreurs(exc, context):
    """Gestionnaire d'exceptions DRF — réponse au format unique."""
    if isinstance(exc, ValidationDjango):
        exc = _convertir_validation_django(exc)

    reponse = exception_handler(exc, context)
    trace_id = identifiant_requete_courant()

    if reponse is None:
        logger.exception("Erreur non gérée", exc_info=exc, extra={"trace_id": trace_id})
        return Response(
            _enveloppe(
                "erreur_interne",
                "Une erreur interne est survenue. L'équipe technique a été informée.",
                {},
                trace_id,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code_http = reponse.status_code

    if isinstance(exc, ErreurMetier):
        reponse.data = _enveloppe(exc.code_metier, str(exc.detail), exc.details, trace_id)
        return reponse

    details = reponse.data if isinstance(reponse.data, dict) else {"detail": reponse.data}
    reponse.data = _enveloppe(
        CODES.get(code_http, "erreur"),
        MESSAGES.get(code_http, "La requête n'a pas pu être traitée."),
        details,
        trace_id,
    )
    return reponse


def _enveloppe(code: str, message: str, details: dict, trace_id: str | None) -> dict:
    return {
        "erreur": {
            "code": code,
            "message": message,
            "details": details,
            "trace_id": trace_id,
        }
    }


def _convertir_validation_django(exc: ValidationDjango):
    """Traduit une ValidationError Django en son équivalent DRF."""
    from rest_framework.exceptions import ValidationError as ValidationDrf

    if hasattr(exc, "message_dict"):
        return ValidationDrf(exc.message_dict)
    return ValidationDrf(exc.messages)
