"""Renouvellement des jetons — correction du défaut **D-1**.

Ce que ce module remplace, et pourquoi il existe.

`TokenRefreshView` de SimpleJWT rejoue la rotation avec `ROTATE_REFRESH_TOKENS`
et `BLACKLIST_AFTER_ROTATION` à `True` — mais `refresh.blacklist()` n'existe que
si l'application `token_blacklist` est installée, et la bibliothèque **avale
l'`AttributeError`** :

    if api_settings.BLACKLIST_AFTER_ROTATION:
        try:
            refresh.blacklist()
        except AttributeError:
            pass          # ← deux réglages corrects, aucun message, zéro effet

Vérifié le 31/08/2026 sur le code livré : le même jeton de renouvellement
rejoué quatre fois répondait `200` à chaque fois.

L'application `token_blacklist` n'est **pas** la parade — décision **S4** de
T-008 : ses tables portent une clé étrangère vers `utilisateur`, qui existe
dans `public` **et** dans chaque schéma client. La liste noire est dans le
cache (`services/liste_noire.py`), et la rotation est faite ici.

Ce que ce module ne fait pas encore, et qui reste à DEV-1 / DEV-3 :
le claim `sdt` et le plafond absolu de session (T-008 §2.3), le claim `schema`
(§5.2), et la lecture de l'époque par `JWTAuthentication` sur chaque requête
authentifiée (§6.5).
"""

import time

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Utilisateur
from apps.accounts.services import liste_noire
from apps.core.exceptions import ErreurMetier

__all__ = ["FENETRE_GRACE", "JetonInvalide", "JetonRevoque", "renouveler"]

# T-008 §4.2 — la fenêtre de grâce qui rend la règle applicable au terrain.
# Sur un chantier, le réseau qui tombe au milieu d'un renouvellement n'est pas
# un cas limite, c'est le quotidien : le téléphone rejoue. Sans cette fenêtre,
# chaque coupure déconnecterait un chef de chantier en pleine saisie — ce que
# le Socle §2.2 interdit.
FENETRE_GRACE = 60  # secondes


class JetonInvalide(ErreurMetier):
    status_code = status.HTTP_401_UNAUTHORIZED
    code_metier = "jeton_invalide"
    default_detail = _("Session expirée. Reconnectez-vous.")


class JetonRevoque(ErreurMetier):
    status_code = status.HTTP_401_UNAUTHORIZED
    code_metier = "jeton_revoque"
    default_detail = _("Session expirée. Reconnectez-vous.")


def _duree_restante(jeton) -> int:
    """Secondes avant l'expiration naturelle du jeton."""
    return max(0, int(jeton["exp"] - time.time()))


def renouveler(jeton_brut: str) -> dict[str, str]:
    """Échange un jeton de renouvellement contre une paire neuve.

    Les cinq situations du tableau T-008 §4.2 sont traitées ici, et nulle part
    ailleurs : la vue ne décide de rien.
    """
    try:
        ancien = RefreshToken(jeton_brut)
    except TokenError as exc:
        # Signature invalide, jeton expiré, ou charge utile illisible.
        raise JetonInvalide() from exc

    jti = ancien.get("jti")
    sid = ancien.get("sid")
    origine = ancien.get("origine", "WEB")
    identifiant = ancien.get("user_id")
    emis_le = float(ancien.get("iat", 0))

    # --- L'utilisateur entier a-t-il été révoqué ? (Socle §2.2) -------------
    epoque = liste_noire.epoque_utilisateur(identifiant)
    if epoque is not None and emis_le < epoque:
        raise JetonRevoque()

    # --- La session a-t-elle été révoquée ? --------------------------------
    if sid and liste_noire.session_revoquee(sid):
        raise JetonRevoque()

    # --- Ce jeton précis a-t-il déjà servi ? -------------------------------
    deja = liste_noire.revocation(jti) if jti else None
    if deja is not None:
        motif, horodatage = deja
        benin = motif == liste_noire.MOTIF_ROTATION and (time.time() - horodatage) <= FENETRE_GRACE
        if not benin:
            # Rejeu. Le `jti` seul ne suffit pas : l'autre moitié de la course
            # détient déjà la paire suivante. C'est la session qui tombe.
            if sid:
                liste_noire.revoquer_session(
                    sid,
                    ttl=_duree_restante(ancien) or FENETRE_GRACE,
                    motif=liste_noire.MOTIF_REJEU,
                )
            raise JetonRevoque()
        # Rejeu bénin : on émet une paire neuve **sans** réécrire la clé de
        # révocation. La fenêtre reste ancrée à la rotation d'origine ; la
        # réécrire la ferait glisser indéfiniment.

    # --- Le compte est-il toujours en état de se connecter ? ---------------
    utilisateur = Utilisateur.objects.filter(pk=identifiant, is_active=True).first()
    if utilisateur is None:
        raise JetonRevoque()

    # --- Émission de la paire neuve ----------------------------------------
    from apps.accounts.services.authentification import emettre_jetons

    jetons = emettre_jetons(utilisateur, origine=origine, sid=sid)

    # --- Révocation de l'ancien, jusqu'à sa mort naturelle -----------------
    # `deja is None` : un rejeu bénin ne réécrit pas la clé. La réécrire
    # ancrerait la fenêtre de grâce au dernier rejeu, et un jeton représenté
    # toutes les cinquante secondes vivrait indéfiniment — la rotation ne
    # révoquerait plus rien pour qui rejoue assez souvent.
    if jti and deja is None:
        liste_noire.revoquer_jeton(
            jti,
            ttl=_duree_restante(ancien),
            motif=liste_noire.MOTIF_ROTATION,
        )

    return jetons
