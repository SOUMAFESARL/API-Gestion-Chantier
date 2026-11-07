"""Le moteur PostgreSQL de Django, qui accorde chaque session au contexte d'entreprise (D9, R-5).

`ENGINE = "apps.core.backends.postgresql"` : c'est le point d'extension prévu par Django pour
modifier le comportement d'une connexion, sans bibliothèque tierce. Il ajoute deux choses au
moteur d'origine :

1. l'*execute wrapper* `apps.core.rls.appliquer_contexte_rls`, posé une fois pour toutes sur la
   connexion : aucune requête ne part sans que la session porte l'entreprise du contexte ;
2. l'oubli de l'état mémorisé dès que la session a pu le perdre. `set_config(..., false)` vaut
   jusqu'à la fin de la session **sauf si sa transaction est annulée** : un `ROLLBACK`, ou un
   `ROLLBACK TO SAVEPOINT`, rétablit l'ancienne valeur côté serveur. Sans cet oubli, la mémoire
   Python dirait « entreprise B » pendant que la session porterait encore « entreprise A ».
"""

from django.db.backends.postgresql import base

from apps.core.rls import appliquer_contexte_rls


class DatabaseWrapper(base.DatabaseWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `(entreprise, rôle)` que porte la session ; `None` : inconnu, à reposer.
        self.etat_rls = None
        # En tête de liste : le plus extérieur, il s'exécute avant tout autre wrapper.
        self.execute_wrappers.insert(0, appliquer_contexte_rls)

    def get_new_connection(self, conn_params):
        self.etat_rls = None
        return super().get_new_connection(conn_params)

    # L'oubli vient **après** l'instruction : `ROLLBACK TO SAVEPOINT` passe lui-même par le
    # wrapper, et un réglage reposé avant lui serait aussitôt annulé.
    def _close(self):
        try:
            return super()._close()
        finally:
            self.etat_rls = None

    def _rollback(self):
        try:
            return super()._rollback()
        finally:
            self.etat_rls = None

    def _savepoint_rollback(self, sid):
        try:
            return super()._savepoint_rollback(sid)
        finally:
            self.etat_rls = None
