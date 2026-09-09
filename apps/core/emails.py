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
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

__all__ = ["envoyer"]


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
        texte = render_to_string(f"emails/{gabarit}.txt", donnees)
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
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=destinataires,
    )
    message.attach_alternative(html, "text/html")

    try:
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Envoi de l'email « %s » impossible", gabarit)
        return False
