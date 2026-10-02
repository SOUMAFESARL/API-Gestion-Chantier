"""Commande de provisionnement des entreprises en attente — robuste pour cPanel.

Exécute le provisionnement des schémas PostgreSQL et des comptes administrateurs
pour les demandes d'inscription au statut PROVISIONNEMENT.

Peut être lancée :
1. De façon ponctuelle avec `--demande-id <UUID>` (déclenchée dès l'activation web).
2. De façon périodique via un Cron Job cPanel (filet de sécurité toutes les 2 minutes).
"""

import logging

from django.core.management.base import BaseCommand

from apps.tenants.models import DemandeInscription
from apps.tenants.services.inscription import provisionner

logger = logging.getLogger(__name__)


def _purger_utilisateurs_test_public(stdout, style):
    """Purge les comptes de test résiduels spécifiques du schéma public."""
    from django.db import connection

    cibles_sql = "'duzanf@gmail.com', 'duzanf2@gmail.com'"
    try:
        with connection.cursor() as cursor:
            # 1. Neutraliser les contraintes FK pointant vers public.utilisateur
            cursor.execute(
                f"""
                SELECT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                  AND ccu.table_name = 'utilisateur'
                """
            )
            fks = cursor.fetchall()
            for table, col in fks:
                try:
                    cursor.execute(
                        f"""
                        UPDATE public."{table}"
                        SET "{col}" = NULL
                        WHERE "{col}" IN (
                            SELECT id FROM public.utilisateur WHERE LOWER(email) IN ({cibles_sql})
                        )
                        """
                    )
                except Exception:
                    pass

            # 2. Supprimer les comptes résiduels du schéma public
            cursor.execute(
                f"""
                DELETE FROM public.utilisateur
                WHERE LOWER(email) IN ({cibles_sql})
                """
            )
            count = cursor.rowcount
            if count > 0 and stdout and style:
                stdout.write(style.SUCCESS(f"[PURGE] {count} compte(s) purgé(s) du schéma public."))
    except Exception as exc:
        if stdout and style:
            stdout.write(style.WARNING(f"[PURGE] Avertissement purge public : {exc}"))


class Command(BaseCommand):
    help = "Provisionne les schémas PostgreSQL des demandes d'inscription en attente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demande-id",
            type=str,
            default=None,
            help="UUID de la demande d'inscription spécifique à provisionner.",
        )

    def handle(self, *args, **options):
        _purger_utilisateurs_test_public(self.stdout, self.style)
        demande_id = options.get("demande_id")

        if demande_id:
            demandes = DemandeInscription.objects.filter(
                pk=demande_id,
                statut=DemandeInscription.Statut.PROVISIONNEMENT,
            )
            if not demandes.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Aucune demande en statut PROVISIONNEMENT trouvée pour l'ID : {demande_id}"
                    )
                )
                return
        else:
            demandes = DemandeInscription.objects.filter(
                statut=DemandeInscription.Statut.PROVISIONNEMENT
            ).order_by("cree_le")

        total = demandes.count()
        if total == 0:
            self.stdout.write("Aucune demande d'inscription en attente de provisionnement.")
            return

        self.stdout.write(f"Démarrage du provisionnement pour {total} demande(s)...")

        for demande in demandes:
            self.stdout.write(
                f"Traitement de la demande {demande.pk} (Entreprise : {demande.raison_sociale}, Schéma : {demande.slug_reserve})..."
            )
            try:
                provisionner(demande.pk)
                demande.refresh_from_db()
                if demande.statut == DemandeInscription.Statut.ACTIVEE:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Succès : Espace {demande.raison_sociale} provisionné avec succès."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Échec : La demande {demande.pk} s'est terminée avec le statut {demande.statut}."
                        )
                    )
            except Exception as exc:
                logger.exception("Erreur lors du provisionnement de la demande %s", demande.pk)
                self.stdout.write(
                    self.style.ERROR(
                        f"Erreur critique lors du provisionnement de {demande.pk} : {exc}"
                    )
                )
