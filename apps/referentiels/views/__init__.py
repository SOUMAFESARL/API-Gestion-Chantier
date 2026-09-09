"""Vues du module « referentiels ».

Référentiels partagés par tous les tenants.
"""

import inspect

from django.db.models import Choices, TextChoices
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import enums

__all__ = ["EnumerationsView"]


def _libelles() -> dict[str, list[dict[str, str]]]:
    """Toutes les énumérations du produit, sous forme code / libellé.

    Construit par introspection de `apps.core.enums` : ajouter une
    énumération là suffit, il n'y a rien à recopier ici.
    """
    resultat: dict[str, list[dict[str, str]]] = {}
    for nom, objet in inspect.getmembers(enums, inspect.isclass):
        if not issubclass(objet, Choices) or objet in (Choices, TextChoices):
            continue
        cle = _en_snake_case(nom)
        resultat[cle] = [{"code": code, "libelle": str(libelle)} for code, libelle in objet.choices]
    return resultat


def _en_snake_case(nom: str) -> str:
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in nom).lstrip("_")


class EnumerationsView(APIView):
    """Dictionnaire des libellés d'énumération.

    L'API renvoie partout ailleurs le **code** (`"EN_COURS"`), jamais le
    libellé : le libellé est affaire d'affichage. Le client charge cette
    table une fois au démarrage et la met en cache. C'est aussi le seul
    endroit à traduire le jour où l'interface passe en anglais (H5).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Libellés des énumérations",
        description="Codes et libellés de toutes les énumérations du produit.",
        responses={200: dict},
    )
    def get(self, request):
        return Response(_libelles())


class ReglesMotDePasseView(APIView):
    r"""`GET /api/v1/referentiels/regles-mot-de-passe/` — contrat §6.3.

    **Les règles sont servies, pas recopiées.** L'écran de saisie doit allumer
    ses coches à la frappe : un aller-retour par caractère est exclu sur une
    liaison 3G. Mais deux implémentations d'une même règle divergent toujours,
    et c'est déjà arrivé — la maquette M6 affichait quatre coches quand le
    serveur n'en contrôlait qu'une (défaut D-4).

    Le client allume ses coches à partir de cette liste ; **le serveur reste
    seul juge** au moment d'enregistrer. Un mot de passe faible envoyé
    directement à l'API est refusé par `AUTH_PASSWORD_VALIDATORS`, que l'écran
    ait allumé ses coches ou non.

    Les motifs sont donnés en syntaxe **ECMAScript avec le drapeau `u`** : c'est
    le client qui les exécute. `\p{Lu}` plutôt que `[A-Z]` — `É` est une
    majuscule, et le Socle §1.1 range les accents parmi les caractères pris en
    charge.

    Les libellés passent par la traduction côté client, comme les énumérations :
    la liste porte des **codes**, l'écran porte les phrases.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Règles de complexité du mot de passe",
        description="Un seul endroit à modifier le jour où la politique change.",
        responses={200: None},
    )
    def get(self, request):
        return Response(
            {
                "regles": [
                    {"code": "LONGUEUR", "motif": r"^.{8,}$"},
                    {"code": "MAJUSCULE", "motif": r"\p{Lu}"},
                    {"code": "CHIFFRE", "motif": r"\p{Nd}"},
                    {"code": "SPECIAL", "motif": r"[^\p{L}\p{N}]"},
                ]
            }
        )
