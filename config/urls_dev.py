"""Routes de développement — **NON VERSIONNÉ, jamais en production.**

Ce fichier est écarté par `.git/info/exclude` : il n'existe que sur un poste de
développement, et `urls_public.py` l'importe dans un `suppress(ImportError)`.
Sur un dépôt cloné, il n'y a rien à monter.

**Ce qu'il expose est destructeur**, et mérite donc trois verrous plutôt qu'un :

  1. le fichier n'existe pas ailleurs ;
  2. `urls_public.py` ne le monte que si `DEBUG` ;
  3. la vue elle-même exige `OUTILS_TEST=1` dans l'environnement.

Un seul verrou finit toujours par sauter — celui qu'on désarme « cinq minutes
pour essayer un truc » et qu'on oublie de remettre.
"""

import os

from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

__all__ = ["urlpatterns"]


def _autorise() -> bool:
    return settings.DEBUG and os.environ.get("OUTILS_TEST") == "1"


@csrf_exempt
def reinitialiser_base(request):
    """Efface les entreprises d'essai, leurs schémas et leurs demandes.

    C'est ce que le bouton « Repartir de zéro » appelle. Il effaçait jusqu'ici
    le seul état du navigateur, ce qui suffisait tant que l'inscription était
    simulée — depuis qu'elle écrit vraiment en base, cela ne suffit plus.

    **`public` et `demo` sont préservés.** Le premier rend `localhost`
    résolvable : le supprimer ferait répondre 404 à toute requête, y compris à
    la page d'inscription qui porte ce bouton. Le second est l'espace de
    démonstration, avec les comptes qui servent à se connecter.
    """
    if not _autorise():
        return JsonResponse(
            {"erreur": {"code": "acces_refuse", "message": "Outil indisponible.", "details": {}}},
            status=403,
        )
    if request.method != "POST":
        return JsonResponse({"erreur": {"code": "methode", "details": {}}}, status=405)

    from apps.tenants.models import DemandeInscription, Entreprise

    avant = {
        "entreprises": Entreprise.objects.exclude(schema_name__in=["public", "demo"]).count(),
        "demandes": DemandeInscription.tous_objets.count(),
    }

    call_command("vider_inscription_test", tout=True, pour_de_vrai=True, verbosity=0)

    return JsonResponse(
        {
            "efface": avant,
            "conserves": ["public", "demo"],
        }
    )


urlpatterns = [
    path("api/v1/dev/reinitialiser/", reinitialiser_base, name="dev-reinitialiser"),
]
