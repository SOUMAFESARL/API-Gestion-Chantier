"""Passerelle : l'ancien vocabulaire des schémas, traduit vers le contexte d'entreprise (D9).

**Transitoire — disparaît au lot 8** de la sortie du multi-schéma. Le code écrit pour
django-tenants parlait de schémas ; il parle désormais d'entreprises. Cette passerelle fait la
traduction en un seul endroit, pour que la bascule ne réécrive pas 90 fichiers d'un coup et que
chaque usage restant se retrouve par `grep passerelle_schema`.

| Avant (django-tenants) | Maintenant |
|---|---|
| `schema_context("public")` | **aucun effet** : les tables de plateforme se lisent sans contexte, et l'entreprise active, s'il y en a une, le reste |
| `schema_context("demo")` | `contexte_entreprise(<l'entreprise dont le slug est demo>)` |
| `connection.schema_name` | `schema_courant()` : le slug de l'entreprise active, ou `"public"` |
| `request.tenant`, `connection.tenant` | `entreprise_courante()` |
| `get_public_schema_name()` | `schema_public()` |

**Ce que la traduction ne couvre pas** : sous django-tenants, se placer dans `public` cachait les
tables d'entreprise ; ici, une requête sur une table d'entreprise dans `contexte_schema("public")`
reste soumise au contexte en cours — cloisonnée s'il y a une entreprise active, refusée sinon. C'est
le comportement voulu (D9, R-4), mais un code qui comptait sur `public` pour **ne voir que le
personnel de l'éditeur** dans `utilisateur` doit le dire (`entreprise__isnull=True`).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager, nullcontext
from functools import lru_cache

from apps.core.contexte import contexte_entreprise, entreprise_courante_id

__all__ = [
    "SCHEMA_PUBLIC",
    "contexte_schema",
    "entreprise_courante",
    "entreprise_du_schema",
    "schema_courant",
    "schema_public",
]

SCHEMA_PUBLIC = "public"


def schema_public() -> str:
    return SCHEMA_PUBLIC


@lru_cache(maxsize=1024)
def _slug_de(entreprise_id: uuid.UUID) -> str:
    from apps.tenants.models import Entreprise

    slug = Entreprise.objects.filter(pk=entreprise_id).values_list("schema_name", flat=True).first()
    return slug or SCHEMA_PUBLIC


def schema_courant() -> str:
    """Le slug de l'entreprise active, ou `"public"` sans entreprise active."""
    identifiant = entreprise_courante_id()
    return _slug_de(identifiant) if identifiant else SCHEMA_PUBLIC


def entreprise_courante():
    """L'entreprise active, ou `None`."""
    from apps.tenants.models import Entreprise

    identifiant = entreprise_courante_id()
    return Entreprise.objects.filter(pk=identifiant).first() if identifiant else None


def entreprise_du_schema(nom: str):
    """L'entreprise dont le slug est `nom` ; `ValueError` si elle n'existe pas."""
    from apps.tenants.models import Entreprise

    entreprise = Entreprise.objects.filter(schema_name=nom).first()
    if entreprise is None:
        raise ValueError(f"Aucune entreprise « {nom} ».")
    return entreprise


@contextmanager
def contexte_schema(nom: str | None):
    """`schema_context(nom)` d'hier : l'entreprise du slug, ou rien pour `public`."""
    if not nom or nom == SCHEMA_PUBLIC:
        with nullcontext():
            yield
        return
    with contexte_entreprise(entreprise_du_schema(nom)):
        yield
