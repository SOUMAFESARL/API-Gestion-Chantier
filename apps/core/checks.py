"""Vérifications système du socle — `manage.py check --database default`.

Elles ne tournent qu'avec `--database` : elles interrogent la base, ce que `check` seul ne fait
pas (et ne doit pas faire, faute de base au moment d'un `collectstatic`, par exemple).
"""

from django.core.checks import Error, Tags, register
from django.db import connections


@register(Tags.database)
def verifier_isolation_rls(app_configs=None, databases=None, **kwargs):
    from apps.core.rls import diagnostic_isolation

    erreurs = []
    for alias in databases or []:
        connexion = connections[alias]
        if connexion.vendor != "postgresql":
            continue
        for defaut in diagnostic_isolation(connexion):
            erreurs.append(Error(defaut, id="core.E101", obj=alias))
    return erreurs
