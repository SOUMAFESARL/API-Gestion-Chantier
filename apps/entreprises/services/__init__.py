"""Services de l'application « entreprises » — dérivation du slug d'une entreprise.

**Règle R-60 de T-020 : le slug est dérivé côté serveur, jamais reçu du client.**
Le formulaire d'inscription est public ; ce qu'il envoie est une raison sociale
saisie par un inconnu.
"""

import unicodedata

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.entreprises.services.images import traiter_logo_entreprise

__all__ = ["LONGUEUR_MAX_SLUG", "deriver_slug", "traiter_logo_entreprise"]

# 40 caractères ASCII : le slug préfixe les clés de fichiers et se lit dans les commandes. La
# translittération ci-dessous garantit qu'un caractère vaut un octet.
LONGUEUR_MAX_SLUG = 40

# Noms réservés : ils désignent la plateforme ou PostgreSQL dans les journaux et les chemins.
SLUGS_INTERDITS = frozenset({"public", "information_schema", "template0", "template1", "postgres"})


def deriver_slug(raison_sociale: str) -> str:
    """Le slug d'une entreprise, construit par **liste blanche** (D9, R-13).

    Le slug ne nomme plus de schéma, mais il entre dans des clés de fichiers et des journaux, et
    il vient d'une **raison sociale saisie sur un formulaire public**. D'où une liste blanche
    `[a-z0-9_]` — jamais une liste noire : une liste noire oublie toujours un caractère ; une liste
    blanche ne laisse passer que ce qu'on a nommé.

    Lève `ValidationError` quand rien d'utilisable ne subsiste — §2.5 du contrat
    d'inscription : « SARL 建設 » ne donne aucune adresse, et l'écran doit le
    dire plutôt que d'inventer un nom.
    """
    # Translittération : « é » devient « e », et non deux octets de plus.
    sans_accent = unicodedata.normalize("NFKD", raison_sociale or "")
    ascii_seul = sans_accent.encode("ascii", "ignore").decode("ascii").lower()

    # Liste blanche : tout ce qui n'est pas [a-z0-9] devient une séparation.
    morceaux = []
    courant = []
    for caractere in ascii_seul:
        if caractere.isalnum():
            courant.append(caractere)
        elif courant:
            morceaux.append("".join(courant))
            courant = []
    if courant:
        morceaux.append("".join(courant))

    slug = "_".join(morceaux)[:LONGUEUR_MAX_SLUG].strip("_")

    if not slug:
        raise ValidationError(
            _(
                "Ce nom ne permet pas de créer une adresse. "
                "Proposez une variante en lettres latines."
            ),
            code="slug_vide",
        )

    # Règle héritée et conservée : un slug ne commence pas par un chiffre, et les slugs déjà
    # attribués restent ainsi stables.
    if slug[0].isdigit():
        slug = f"e_{slug}"[:LONGUEUR_MAX_SLUG]

    if slug in SLUGS_INTERDITS or slug.startswith("pg_"):
        slug = f"e_{slug}"[:LONGUEUR_MAX_SLUG]

    return slug
