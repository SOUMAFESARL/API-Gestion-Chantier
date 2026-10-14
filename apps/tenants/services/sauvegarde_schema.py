"""Sauvegarde d'un schéma d'entreprise avant sa suppression définitive.

Une suppression sans sauvegarde transforme une erreur de clic en perte définitive : la
suppression est refusée si la sauvegarde n'a pas abouti.
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.tenants.models import Entreprise

logger = logging.getLogger(__name__)


class SauvegardeImpossible(Exception):  # noqa: N818
    """`pg_dump` a échoué, est introuvable, ou a produit un fichier vide."""


NOM_SCHEMA_SUR = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def sauvegarder_schema(entreprise: Entreprise, *, complement: dict) -> Path:
    """Écrit `<schema>_<AAAAMMJJ_HHMMSS>.dump` (format custom de pg_dump, restaurable par
    pg_restore) et, à côté, `<même nom>.json` : les lignes du schéma public qui la concernent
    et que le dump du schéma ne contient pas. Retourne le chemin du `.dump`."""
    schema = entreprise.schema_name
    if not schema or not NOM_SCHEMA_SUR.match(schema):
        logger.error("Nom de schéma invalide ou dangereux pour la sauvegarde : %r", schema)
        raise SauvegardeImpossible(f"Nom de schéma invalide : {schema!r}")

    dossier = Path(settings.SAUVEGARDES_SUPPRESSION_DIR)
    dossier.mkdir(parents=True, exist_ok=True)

    horodatage = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    chemin = dossier / f"{schema}_{horodatage}.dump"

    base = settings.DATABASES["default"]
    commande = [
        settings.PG_DUMP_CHEMIN,
        "--format=custom",
        "--no-owner",
        f"--schema={schema}",
        f"--file={chemin}",
        f"--host={base.get('HOST', 'localhost')}",
        f"--port={base.get('PORT', '5432')!s}",
        f"--username={base.get('USER', 'postgres')}",
        base["NAME"],
    ]
    env = {**os.environ, "PGPASSWORD": str(base.get("PASSWORD") or "")}

    try:
        subprocess.run(commande, env=env, check=True, capture_output=True, timeout=600)
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        OSError,
    ) as exc:
        if chemin.exists():
            chemin.unlink(missing_ok=True)
        msg_stderr = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            msg_stderr = exc.stderr.decode("utf-8", errors="replace")[:500]
        logger.error("Échec pg_dump pour %s : %s %s", schema, exc, msg_stderr)
        raise SauvegardeImpossible(f"Échec de pg_dump pour {schema}") from exc

    if not chemin.exists() or chemin.stat().st_size == 0:
        if chemin.exists():
            chemin.unlink(missing_ok=True)
        logger.error("Fichier dump absent ou vide après pg_dump pour %s", schema)
        raise SauvegardeImpossible(f"Fichier de sauvegarde vide ou absent pour {schema}")

    # Écriture du JSON compagnon
    chemin_json = chemin.with_suffix(".json")
    try:
        abonnements_data = []
        if hasattr(entreprise, "abonnements"):
            abonnements_data = list(entreprise.abonnements.values())

        raison_sociale = getattr(
            entreprise, "raison_sociale", getattr(entreprise, "nom", "")
        )
        donnees_json = {
            "entreprise": {
                "id": str(entreprise.id),
                "schema_name": entreprise.schema_name,
                "nom": getattr(entreprise, "nom", ""),
                "raison_sociale": raison_sociale,
                "slug": getattr(entreprise, "slug", ""),
                "statut": str(getattr(entreprise, "statut", "")),
                "cree_le": str(getattr(entreprise, "cree_le", "")),
            },
            "abonnements": abonnements_data,
            "complement": complement,
            "sauvegarde_le": timezone.now().isoformat(),
        }
        with open(chemin_json, "w", encoding="utf-8") as f:
            json.dump(donnees_json, f, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        if chemin.exists():
            chemin.unlink(missing_ok=True)
        if chemin_json.exists():
            chemin_json.unlink(missing_ok=True)
        logger.error("Échec écriture JSON compagnon pour %s : %s", schema, exc)
        raise SauvegardeImpossible(f"Échec de l'écriture du JSON pour {schema}") from exc

    return chemin
