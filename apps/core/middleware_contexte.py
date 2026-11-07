"""Remet le contexte d'entreprise à zéro au début et à la fin de chaque requête.

Un serveur WSGI réutilise ses fils d'exécution d'une requête à l'autre. L'authentification active
l'entreprise sans bloc à refermer (`activer_entreprise`) : sans ce middleware, la requête suivante
servie par le même fil hériterait de l'entreprise de la précédente.
"""

from apps.core.contexte import reinitialiser_contexte


class ContexteEntrepriseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        reinitialiser_contexte()
        try:
            return self.get_response(request)
        finally:
            reinitialiser_contexte()
