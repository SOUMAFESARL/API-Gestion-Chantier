"""Génération de la référence unique séquentielle des projets, par entreprise."""

from django.db import connection, transaction
from django.utils import timezone

from apps.core.contexte import exiger_entreprise
from apps.projets.models import Projet


@transaction.atomic
def generer_reference_projet() -> str:
    """Génère la référence séquentielle `PRJ-{AAAA}-{n}` de l'entreprise active."""
    annee = timezone.now().year
    # Un verrou par entreprise et par année : deux entreprises numérotent en parallèle, deux
    # créations dans la même entreprise se suivent. Il reste détenu jusqu'au commit de la
    # transaction de création.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s), %s)",
            [f"projet-reference:{exiger_entreprise()}", annee],
        )
    prefixe = f"PRJ-{annee}-"
    suffixes = Projet.tous_objets.filter(reference__startswith=prefixe).values_list(
        "reference", flat=True
    )
    numero = (
        max(
            (int(ref[len(prefixe) :]) for ref in suffixes if ref[len(prefixe) :].isdigit()),
            default=0,
        )
        + 1
    )
    return f"{prefixe}{numero:03d}"
