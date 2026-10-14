"""Purge des sauvegardes de schémas supprimés de plus de 30 jours (tâche 2.4)."""

import os
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Purge les sauvegardes de schémas supprimés dont l'âge dépasse le seuil de rétention."

    def add_arguments(self, parser):
        parser.add_argument(
            "--jours",
            type=int,
            default=getattr(settings, "SAUVEGARDES_SUPPRESSION_JOURS", 30),
            help="Nombre de jours de conservation (défaut : %(default)s).",
        )
        parser.add_argument(
            "--appliquer",
            action="store_true",
            default=False,
            help="Supprime réellement les fichiers. Sans ce drapeau, la commande décrit seulement.",
        )

    def handle(self, *args, **options):
        jours = options["jours"]
        appliquer = options["appliquer"]
        dossier = Path(settings.SAUVEGARDES_SUPPRESSION_DIR)

        if not dossier.exists():
            self.stdout.write(self.style.WARNING(f"Dossier introuvable : {dossier}"))
            return

        limite = time.time() - (jours * 86400)
        fichiers_candidats = []

        for motif in ("*.dump", "*.json"):
            for chemin in dossier.glob(motif):
                if chemin.is_file():
                    try:
                        mtime = os.path.getmtime(chemin)
                        if mtime < limite:
                            fichiers_candidats.append(chemin)
                    except OSError:
                        continue

        if not fichiers_candidats:
            self.stdout.write(
                self.style.SUCCESS(f"Aucune sauvegarde de plus de {jours} jours à purger.")
            )
            return

        total = len(fichiers_candidats)
        for fichier in sorted(fichiers_candidats):
            if appliquer:
                try:
                    fichier.unlink(missing_ok=True)
                    self.stdout.write(f"Supprimé : {fichier.name}")
                except OSError as exc:
                    self.stdout.write(
                        self.style.ERROR(f"Erreur suppression {fichier.name} : {exc}")
                    )
            else:
                self.stdout.write(f"[Simulation] À supprimer : {fichier.name}")

        if appliquer:
            self.stdout.write(self.style.SUCCESS(f"{total} fichier(s) purgé(s) avec succès."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"{total} fichier(s) identifié(s) pour la purge. "
                    "Relancez avec --appliquer pour supprimer."
                )
            )
