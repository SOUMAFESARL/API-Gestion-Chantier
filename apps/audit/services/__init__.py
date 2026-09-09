"""Écriture du journal d'audit — Socle Commun §2.4.

Une seule porte d'entrée, `journaliser`. Les appelants ne construisent pas
d'objet `JournalAudit` eux-mêmes : le jour où la table se partitionne par mois
(MLD §5.3, dès deux millions de lignes), c'est ici que ça se règle, et nulle
part ailleurs.
"""

import logging

from django.db import DatabaseError, transaction

from apps.audit.models import JournalAudit

logger = logging.getLogger(__name__)

__all__ = ["journaliser"]


def journaliser(
    *,
    action: str,
    type_entite: str,
    entite_id=None,
    utilisateur_id=None,
    valeur_avant: dict | None = None,
    valeur_apres: dict | None = None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> JournalAudit | None:
    """Écrit une entrée, et ne fait jamais échouer l'action qu'elle décrit.

    **Ce compromis mérite d'être écrit, parce qu'il se discute.** Le Socle §2.4
    dit « sans exception », ce qui plaide pour laisser l'erreur remonter. Mais
    une écriture d'audit qui échoue ferait alors échouer la réinitialisation
    d'un mot de passe déjà enregistré : l'utilisateur verrait une erreur pour
    une opération réussie, et recommencerait sur un jeton désormais consommé.

    L'échec est donc **journalisé au niveau `error`** plutôt qu'avalé : il
    remonte à la supervision, qui est l'endroit où l'on peut y répondre.

    **Un cas connu, et c'est l'écart E1.** `apps.audit` vit dans `TENANT_APPS`
    seul, parce que la table référence `utilisateur`. Or `apps.accounts` est
    dans les deux listes : une action du personnel de l'éditeur, dans le schéma
    `public`, ne trouve pas de table où écrire. La même asymétrie avait écarté
    les tables de liste noire de SimpleJWT. Elle reste ouverte.

    **Ne jamais passer de mot de passe, de jeton ou d'empreinte** dans
    `valeur_avant` ou `valeur_apres` : le journal se consulte et s'exporte.
    """
    try:
        # **Le point de sauvegarde n'est pas une précaution, c'est la
        # condition de la promesse ci-dessus.** Attraper `DatabaseError` ne
        # suffit pas : sous PostgreSQL, une instruction en échec avorte la
        # transaction entière, et l'appelant meurt sur sa requête suivante avec
        # un `TransactionManagementError` — loin d'ici, et sans rapport visible
        # avec le journal.
        #
        # *Découvert le 03/09/2026 en branchant le wizard : un `action` de 28
        # caractères sur une colonne de 20 a fait échouer le franchissement
        # d'étape, alors que ce service est écrit pour ne jamais faire échouer
        # l'action qu'il décrit.* L'`atomic` imbriqué ouvre un `SAVEPOINT` et
        # n'annule que l'écriture d'audit.
        with transaction.atomic():
            return JournalAudit.objects.create(
                action=action,
                type_entite=type_entite,
                entite_id=entite_id,
                utilisateur_id=utilisateur_id,
                valeur_avant=valeur_avant,
                valeur_apres=valeur_apres,
                adresse_ip=adresse_ip,
                appareil=appareil or "",
            )
    except DatabaseError:
        logger.exception("Journal d'audit non écrit — action=%s entite=%s", action, type_entite)
        return None
