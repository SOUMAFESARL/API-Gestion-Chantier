"""Service de gestion du référentiel d'articles et initialisation du catalogue."""

import json
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from django.db import transaction

from apps.core.contexte import contexte_entreprise
from apps.stock.models import ArticleCatalogue

if TYPE_CHECKING:
    from apps.entreprises.models import Entreprise


def initialiser_articles_base_entreprise(
    entreprise: "Entreprise",
) -> list[ArticleCatalogue]:
    """Initialise le catalogue d'articles de base pour une entreprise donnée à partir de la fixture.

    Idempotent : ne recrée pas les articles dont le code existe déjà pour cette entreprise.
    """
    fixture_path = (
        Path(__file__).resolve().parent.parent / "fixtures" / "articles_base.json"
    )
    if not fixture_path.exists():
        return []

    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    articles_crees: list[ArticleCatalogue] = []
    with contexte_entreprise(entreprise), transaction.atomic():
        codes_existants = set(
            ArticleCatalogue.tous_objets.filter(entreprise=entreprise).values_list(
                "code", flat=True
            )
        )

        for item in data:
            fields = item.get("fields", {})
            code = fields.get("code")
            if not code or code in codes_existants:
                continue

            article = ArticleCatalogue(
                entreprise=entreprise,
                code=code,
                designation=fields.get("designation", ""),
                categorie=fields.get("categorie", "MATERIAU"),
                famille=fields.get("famille", ""),
                unite_mesure=fields.get("unite_mesure", "U"),
                seuil_alerte_defaut=Decimal(
                    str(fields.get("seuil_alerte_defaut", "0"))
                ),
                description=fields.get("description", ""),
                est_actif=fields.get("est_actif", True),
            )
            article.save()
            articles_crees.append(article)
            codes_existants.add(code)

    return articles_crees
