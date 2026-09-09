"""Génération de la référence unique séquentielle par projet et par schéma."""

from django.utils import timezone

from apps.projets.models import Projet


def generer_reference_projet() -> str:
    """Génère la référence séquentielle `PRJ-{AAAA}-{n}` pour le schéma courant."""
    annee = timezone.now().year
    prefixe = f"PRJ-{annee}-"
    dernier = Projet.objects.filter(reference__startswith=prefixe).order_by("-cree_le").first()
    if not dernier:
        return f"{prefixe}001"

    try:
        numero = int(dernier.reference.split("-")[-1]) + 1
    except (ValueError, IndexError):
        numero = 1

    return f"{prefixe}{numero:03d}"
