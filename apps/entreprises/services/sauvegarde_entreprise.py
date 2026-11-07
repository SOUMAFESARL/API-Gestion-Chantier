"""Sauvegarde d'une entreprise avant sa suppression définitive (D9, lot 5).

Une suppression sans sauvegarde transforme une erreur de clic en perte définitive : elle est
refusée si la sauvegarde n'a pas abouti.

`pg_dump --schema=<slug>` n'a plus de schéma à lire : toutes les entreprises partagent les mêmes
tables. La sauvegarde écrit donc **exactement les lignes que la suppression va emporter** — le même
`perimetre()` — au format `jsonl` des fixtures de Django :

    <slug>_<AAAAMMJJ_HHMMSS>.jsonl         une ligne par enregistrement
    <slug>_<AAAAMMJJ_HHMMSS>.apercu.json   ce que le super admin a confirmé

**Restaurer** : `manage.py loaddata <fichier>.jsonl`, en superutilisateur PostgreSQL (la RLS
refuserait l'insertion de lignes d'entreprise hors contexte). Les fichiers stockés (avatars,
contrats) n'y sont pas : ils restent dans le stockage jusqu'à la suppression.

Les tables de liaison des `ManyToManyField` ne sont pas écrites à part : leurs paires figurent
dans les enregistrements qu'elles relient, et `loaddata` les recrée.
"""

import json
import logging
import re
from pathlib import Path

from django.conf import settings
from django.core import serializers
from django.utils import timezone

from apps.core.contexte import portee_plateforme
from apps.entreprises.services.suppression_definitive import perimetre

logger = logging.getLogger(__name__)

SLUG_SUR = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class SauvegardeImpossible(Exception):  # noqa: N818
    """L'écriture a échoué, ou le fichier produit est vide."""


def sauvegarder_entreprise(entreprise, *, complement: dict) -> Path:
    """Écrit la sauvegarde de `entreprise` et retourne le chemin du `.jsonl`."""
    slug = entreprise.slug
    if not slug or not SLUG_SUR.match(slug):
        # Le slug entre dans un nom de fichier : liste blanche, comme à sa création.
        raise SauvegardeImpossible(f"Slug invalide : {slug!r}")

    dossier = Path(settings.SAUVEGARDES_SUPPRESSION_DIR)
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    chemin = dossier / f"{slug}_{horodatage}.jsonl"
    chemin_apercu = dossier / f"{slug}_{horodatage}.apercu.json"

    plan = perimetre(entreprise, complement.get("adresses"))
    nombre = 0
    try:
        with (
            portee_plateforme(motif="sauvegarde d'une entreprise avant suppression"),
            open(chemin, "w", encoding="utf-8") as flux,
        ):
            # L'entreprise d'abord, ses lignes ensuite : `loaddata` restaure dans l'ordre du
            # fichier, et les clés étrangères différées de PostgreSQL tolèrent le reste.
            serializers.serialize(
                "jsonl", type(entreprise)._base_manager.filter(pk=entreprise.pk), stream=flux
            )
            for modele, queryset in plan.a_supprimer():
                if modele._meta.auto_created:
                    continue
                for objet in queryset.iterator(chunk_size=500):
                    serializers.serialize("jsonl", [objet], stream=flux)
                    nombre += 1
        with open(chemin_apercu, "w", encoding="utf-8") as flux:
            json.dump(
                {
                    "entreprise": {
                        "id": str(entreprise.pk),
                        "slug": slug,
                        "raison_sociale": entreprise.raison_sociale,
                        "statut": str(entreprise.statut),
                    },
                    "complement": complement,
                    "nb_enregistrements": nombre + 1,
                    "sauvegarde_le": timezone.now().isoformat(),
                },
                flux,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
    except Exception as exc:
        chemin.unlink(missing_ok=True)
        chemin_apercu.unlink(missing_ok=True)
        logger.exception("Sauvegarde de l'entreprise %s impossible", slug)
        raise SauvegardeImpossible(f"Sauvegarde de {slug} impossible") from exc

    if chemin.stat().st_size == 0:
        chemin.unlink(missing_ok=True)
        chemin_apercu.unlink(missing_ok=True)
        raise SauvegardeImpossible(f"Sauvegarde vide pour {slug}")
    return chemin
