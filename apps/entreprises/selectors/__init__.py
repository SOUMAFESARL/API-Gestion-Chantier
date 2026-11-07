"""Lectures de l'application « entreprises ».

`entreprise_courante()` et `slug_courant()` donnent l'objet et l'identifiant lisible de
l'entreprise active (`apps.core.contexte`). Ce sont les seules lectures de
l'entreprise active hors de l'ORM (D9).
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from apps.core.contexte import entreprise_courante_id

__all__ = ["entreprise_courante", "slug_courant", "url_logo"]


def entreprise_courante():
    """L'entreprise active, ou `None` sans entreprise active."""
    from apps.entreprises.models import Entreprise

    identifiant = entreprise_courante_id()
    return Entreprise.objects.filter(pk=identifiant).first() if identifiant else None


@lru_cache(maxsize=1024)
def _slug_de(entreprise_id: uuid.UUID) -> str | None:
    from apps.entreprises.models import Entreprise

    return Entreprise.objects.filter(pk=entreprise_id).values_list("slug", flat=True).first()


def slug_courant() -> str | None:
    """Le slug de l'entreprise active, ou `None` sans entreprise active.

    Le slug ne change pas après l'inscription : il se met en cache par identifiant.
    """
    identifiant = entreprise_courante_id()
    return _slug_de(identifiant) if identifiant else None


def url_logo(entreprise, request=None) -> str | None:
    """L'URL du logo de l'entreprise, absolue quand la requête est connue ; `None` sans logo.

    `Entreprise.logo` est une **clé de stockage**, pas un fichier : l'URL se calcule à la lecture
    (une URL S3 signée périme), comme dans `EntrepriseSerializer`.
    """
    from django.core.files.storage import default_storage

    cle = getattr(entreprise, "logo", "") or ""
    if not cle:
        return None
    url = default_storage.url(cle)
    return request.build_absolute_uri(url) if request is not None else url
