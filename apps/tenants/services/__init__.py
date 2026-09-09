"""Services du schéma `public` — dérivation du nom de schéma d'un tenant.

**Règle R-60 de T-020 : le slug est dérivé côté serveur, jamais reçu du client.**
Le formulaire d'inscription est public ; ce qu'il envoie est une raison sociale
saisie par un inconnu.
"""

import unicodedata

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.tenants.services.images import traiter_logo_entreprise

__all__ = ["LONGUEUR_MAX_SLUG", "deriver_slug", "traiter_logo_entreprise"]

# 40 et non 63. PostgreSQL tronque un identifiant au-delà de 63 **octets**,
# avec un avis et non une erreur — et `.{1,63}` du validateur de django-tenants
# compte des *caractères*. Soixante-trois « é » valent cent vingt-six octets :
# deux raisons sociales longues et accentuées pouvaient devenir **le même
# schéma**. La translittération ASCII ci-dessous supprime la cause ; le
# plafond à 40 laisse de la marge quoi qu'il arrive.
LONGUEUR_MAX_SLUG = 40

# Noms que PostgreSQL ou django-tenants se réservent. Un tenant qui s'appellerait
# `public` écraserait le schéma de la plateforme.
SLUGS_INTERDITS = frozenset({"public", "information_schema", "template0", "template1", "postgres"})


def deriver_slug(raison_sociale: str) -> str:
    """Le nom de schéma d'une entreprise, construit par **liste blanche**.

    **C'est la barrière, et il n'y en a pas d'autre qui vaille.** Le validateur
    de django-tenants n'interdit que le préfixe `pg_` :

        PGSQL_VALID_SCHEMA_NAME = re.compile(r'^(?!pg_).{1,63}$')

    Espaces, guillemets, points-virgules, `public` — tout passe. Et
    `create_schema()` interpole le résultat dans du SQL :

        cursor.execute('CREATE SCHEMA "%s"' % self.schema_name)

    *Vérifié le 31/08/2026 sur la bibliothèque installée, 3.14.0 :*
    ``a"; DROP SCHEMA public CASCADE; --`` *est accepté par le validateur.*
    Comme le slug est dérivé d'une **raison sociale saisie sur un formulaire
    public**, c'est une injection à un formulaire de distance.

    D'où une liste blanche `[a-z0-9]` — jamais une liste noire. Une liste noire
    oublie toujours un caractère ; une liste blanche ne laisse passer que ce
    qu'on a nommé.

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

    # Un schéma ne commence jamais par un chiffre : PostgreSQL l'accepte entre
    # guillemets, mais tout ce qui l'oublie ensuite casse.
    if slug[0].isdigit():
        slug = f"e_{slug}"[:LONGUEUR_MAX_SLUG]

    if slug in SLUGS_INTERDITS or slug.startswith("pg_"):
        slug = f"e_{slug}"[:LONGUEUR_MAX_SLUG]

    return slug
