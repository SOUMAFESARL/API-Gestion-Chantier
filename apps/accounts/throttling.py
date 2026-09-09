"""Limitation de débit de la connexion.

Deux compteurs, deux menaces différentes :

* **par IP** — `connexion`, 30/min. Protège la plateforme d'un balayage : un
  attaquant qui essaie un mot de passe courant sur des milliers d'adresses ne
  déclenche aucun blocage de compte, puisqu'il ne s'acharne sur aucun.
* **par adresse** — `connexion_email`, 10/min. Protège **un** compte d'un
  essaimage : le même email tenté depuis cent adresses IP passe sous le
  compteur précédent sans le faire sonner.

Le blocage à cinq essais, lui, est encore autre chose : il vit en base et
survit au redémarrage. Ces deux limites-ci vivent dans le cache et ne
remplacent rien — elles écrêtent le débit avant que le compteur en base ne
travaille.
"""

import hashlib

from rest_framework.throttling import SimpleRateThrottle

__all__ = [
    "ThrottleConnexionParEmail",
    "ThrottleDemandeMdpParEmail",
    "ThrottleDemandeMdpRapprochee",
]


class ThrottleConnexionParEmail(SimpleRateThrottle):
    """Compte les tentatives par adresse, indépendamment de l'IP d'origine."""

    scope = "connexion_email"

    def get_cache_key(self, request, view) -> str | None:
        email = (request.data or {}).get("email")
        if not isinstance(email, str) or not email.strip():
            # Requête sans adresse : c'est un `400`, pas une tentative. Le
            # compteur des cinq essais ne bouge pas non plus (contrat §5).
            return None

        # L'adresse est hachée avant d'entrer dans la clé de cache : une clé
        # se lit dans Redis, s'exporte avec un dump et traîne dans les outils
        # de supervision. Le compteur n'a pas besoin de l'adresse en clair.
        empreinte = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": empreinte}


class ThrottleDemandeMdpParEmail(SimpleRateThrottle):
    """3 demandes de réinitialisation par heure, **par adresse** — contrat §3.4.

    **Cette limite ne protège pas le système, elle protège une personne.** Sans
    elle, n'importe qui peut faire pleuvoir des emails « réinitialisez votre mot
    de passe » dans la boîte d'un directeur, en boucle, sans compte et sans
    trace. Le produit devient l'instrument du harcèlement, et c'est le nom de
    domaine de l'éditeur qui finit signalé comme expéditeur indésirable.
    """

    scope = "mdp_demande_email"

    def get_cache_key(self, request, view) -> str | None:
        email = (request.data or {}).get("email")
        if not isinstance(email, str) or not email.strip():
            return None
        empreinte = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": empreinte}


class ThrottleDemandeMdpRapprochee(ThrottleDemandeMdpParEmail):
    """Une demande par cinq minutes et par adresse — contrat §3.4.

    C'est le délai que le bouton « Renvoyer l'email » de M6 doit respecter à
    l'écran. Le désactiver pendant le décompte vaut mieux que laisser
    l'utilisateur récolter un `429` qu'il ne comprend pas.

    Le taux n'est pas déclaré dans les réglages : DRF ne sait exprimer que des
    périodes d'une seconde, une minute, une heure ou un jour. Cinq minutes se
    posent donc à la main.
    """

    scope = "mdp_demande_rapprochee"

    def parse_rate(self, rate):
        """Apprend à DRF l'unité qui lui manque, au lieu de la contourner.

        `SimpleRateThrottle` ne connaît que la seconde, la minute, l'heure et
        le jour. Une première version renvoyait `(1, 300)` sans regarder le
        réglage — et **ignorait donc le `None` par lequel les tests désactivent
        les compteurs**, ce qui faisait échouer dix-neuf tests sur une limite
        qu'ils ne testaient pas.
        """
        if rate is None:
            return (None, None)

        nombre, periode = rate.split("/")
        if periode.endswith("min"):
            minutes = int(periode[:-3] or 1)
            return (int(nombre), 60 * minutes)

        return super().parse_rate(rate)
