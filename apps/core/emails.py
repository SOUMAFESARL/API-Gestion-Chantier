"""L'envoi d'emails — un seul chemin, deux formats, jamais d'exception.

**Pourquoi ce module existe.** Les emails du produit vivaient en `f-string`
dans trois services : `tenants/services/inscription.py`,
`accounts/services/invitations.py` et `accounts/services/reinitialisation.py`.
Trois conséquences :

* ils étaient **en texte seul**, donc la règle du parcours d'inscription §11.1
  — « le lien est un bouton, et l'URL est écrite en clair dessous » — était
  intenable : un texte brut n'a pas de bouton ;
* ils n'avaient **pas de relecteur**. C'est le constat de T-018 §12 : *« les
  emails sont la moitié du parcours, et ils n'ont pas d'écran »*. Un texte
  enfermé dans du code n'est relu que par ceux qui lisent du code ;
* rien ne garantissait qu'ils se ressemblent.

Les gabarits sont donc dans `templates/emails/`, deux fichiers par message —
`<nom>.html` et `<nom>.txt` — que l'on peut relire sans ouvrir Python.

**L'envoi n'échoue jamais bruyamment.** C'est une décision, pas une négligence :
une adresse inconnue et une adresse enregistrée doivent produire la même
réponse, sinon l'endpoint devient une machine à énumérer les comptes (contrat
T-014 §4.2). Et un email qui ne part pas ne doit pas annuler l'inscription qui
l'a déclenché — le bouton « Renvoyer » existe pour cela.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context
from django.template.loader import get_template, render_to_string

logger = logging.getLogger(__name__)

__all__ = ["envoyer", "adresse_frontend"]


def adresse_frontend() -> str:
    """L'adresse publique du frontend, sans barre finale — **la seule** que les liens d'e-mail utilisent.

    Des liens écrits `http://localhost:3000` en dur dans trois services faisaient partir des
    invitations et des réinitialisations dont le bouton ne menait nulle part hors du poste du
    développeur. Une valeur locale en production est une panne silencieuse : l'e-mail part, le
    rendu est correct, seul le clic échoue. On la signale donc bruyamment dans le journal.
    """
    adresse = str(getattr(settings, "FRONTEND_URL", "") or "http://localhost:3000").rstrip("/")
    if not settings.DEBUG and ("localhost" in adresse or "127.0.0.1" in adresse):
        logger.error(
            "FRONTEND_URL vaut %r hors développement : les liens des e-mails seront inutilisables. "
            "Renseignez FRONTEND_URL dans le .env du serveur (par exemple https://soumafe.com).",
            adresse,
        )
    return adresse


def _expediteur() -> str | None:
    """L'expéditeur du réglage saisi par le superviseur, sinon `DEFAULT_FROM_EMAIL`."""
    try:
        from apps.platform_admin.services.messagerie import expediteur_actif

        return expediteur_actif()
    except Exception:  # noqa: BLE001
        return getattr(settings, "DEFAULT_FROM_EMAIL", None)


def _contexte_commun() -> dict[str, Any]:
    """Ce que tous les gabarits peuvent lire sans qu'on le leur passe."""
    from apps.billing.models import JOURS_ESSAI

    return {
        "jours_essai": JOURS_ESSAI,
        "email_commercial": getattr(settings, "EMAIL_COMMERCIAL", "commercial@ccd-digital.ci"),
        "telephone_commercial": getattr(settings, "TELEPHONE_COMMERCIAL", ""),
    }


def envoyer(
    gabarit: str,
    sujet: str,
    destinataires: str | Iterable[str],
    contexte: dict[str, Any] | None = None,
) -> bool:
    """Rend `emails/<gabarit>.{txt,html}` et l'envoie. Retourne le succès.

    Le corps texte est le corps principal et la version HTML une *alternative* :
    c'est l'ordre imposé par la norme, et le seul qui donne un message lisible
    dans un client qui refuse le HTML.

    `gabarit` est un nom court — « activation », « espace_pret » —, jamais un
    chemin : les gabarits vivent tous au même endroit.
    """
    if isinstance(destinataires, str):
        destinataires = [destinataires]
    destinataires = [a for a in destinataires if a]
    if not destinataires:
        return False

    donnees = {**_contexte_commun(), **(contexte or {})}

    try:
        # Le corps texte n'est pas du HTML : sans `autoescape=False`, « L'Entreprise » devenait
        # `L&#x27;Entreprise` et une adresse portant `&` devenait `&amp;`, lien cassé compris.
        texte = get_template(f"emails/{gabarit}.txt").template.render(
            Context(donnees, autoescape=False)
        )
        html = render_to_string(f"emails/{gabarit}.html", donnees)
    except Exception:
        # Un gabarit absent ou cassé est un défaut de développement, pas un
        # incident d'exploitation : il doit se voir dans le journal, et ne doit
        # pas faire tomber l'action métier qui envoyait le message.
        logger.exception("Gabarit d'email illisible : %s", gabarit)
        return False

    message = EmailMultiAlternatives(
        subject=sujet,
        body=texte,
        from_email=_expediteur(),
        to=destinataires,
    )
    message.attach_alternative(html, "text/html")

    try:
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Envoi de l'email « %s » impossible", gabarit)
        return False
