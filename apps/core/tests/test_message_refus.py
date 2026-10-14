"""Le motif d'un refus 403 atteint l'utilisateur (conventions d'API §5)."""

from django.core.exceptions import PermissionDenied as RefusDjango
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import MESSAGES, gestionnaire_erreurs

GENERIQUE_403 = MESSAGES[403]


def _erreur(exc):
    contexte = {"request": APIRequestFactory().get("/"), "view": None}
    reponse = gestionnaire_erreurs(exc, contexte)
    return reponse.status_code, reponse.data["erreur"]


def test_un_refus_motive_garde_son_motif():
    statut, erreur = _erreur(
        PermissionDenied("Cette signature exige l'affectation CT sur le chantier.")
    )
    assert statut == 403
    assert erreur["code"] == "acces_refuse"
    assert erreur["message"] == "Cette signature exige l'affectation CT sur le chantier."


def test_un_refus_sans_motif_reste_generique():
    statut, erreur = _erreur(PermissionDenied())
    assert statut == 403
    assert erreur["message"] == GENERIQUE_403


def test_un_refus_django_reste_generique():
    statut, erreur = _erreur(RefusDjango("texte interne"))
    assert statut == 403
    assert erreur["message"] == GENERIQUE_403


def test_un_introuvable_ne_montre_pas_son_texte_interne():
    statut, erreur = _erreur(NotFound("No JournalChantier matches the given query."))
    assert statut == 404
    assert erreur["message"] == MESSAGES[404]
