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


def _purger_tout_zanf(stdout=None, style=None):
    """Purge intégrale de tous les schémas et références 'zanf' pour tests en production.
    
    1. Schémas PostgreSQL (DROP SCHEMA ... CASCADE)
    2. Dépendances et entreprises dans public.entreprise_cliente
    3. public.demande_inscription
    4. public.utilisateur et toutes ses clés étrangères
    """
    import sys
    from django.conf import settings
    # Ne jamais exécuter pendant les tests unitaires
    if getattr(settings, "TESTING", False) or "pytest" in sys.modules or "test" in sys.argv:
        return

    from django.db import connection

    def _log(msg, niveau="success"):
        if stdout and style:
            fn = getattr(style, niveau.upper(), style.SUCCESS)
            stdout.write(fn(msg))

    try:
        # ── 1. Identifier les entreprises 'zanf' et leurs schémas ────────
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, schema_name 
                FROM public.entreprise_cliente 
                WHERE schema_name ILIKE '%zanf%' 
                   OR raison_sociale ILIKE '%zanf%' 
                   OR email_contact ILIKE '%zanf%'
                   OR id IN (
                       SELECT entreprise_id FROM public.demande_inscription 
                       WHERE email ILIKE '%zanf%' 
                          OR nom ILIKE '%zanf%' 
                          OR prenom ILIKE '%zanf%' 
                          OR raison_sociale ILIKE '%zanf%'
                   );
            """)
            entreprises = cursor.fetchall()

        # ── 2. Identifier et supprimer les schémas PostgreSQL ────────────
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name ILIKE '%zanf%' 
                  AND schema_name NOT IN ('public', 'demo');
            """)
            schemas_directs = [row[0] for row in cursor.fetchall()]

        schemas_from_ent = [e[1] for e in entreprises if e[1] not in ("public", "demo")]
        tous_schemas = set(schemas_directs + schemas_from_ent)

        for schema_nom in tous_schemas:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_nom}" CASCADE;')
                _log(f"[PURGE] Schéma PostgreSQL « {schema_nom} » supprimé.")
            except Exception as e:
                _log(f"[PURGE] Avertissement suppression schéma {schema_nom} : {e}", "warning")

        # ── 3. Supprimer les entreprises 'zanf' et leurs dépendances ──────
        if entreprises:
            ent_ids = [e[0] for e in entreprises]
            with connection.cursor() as cursor:
                # catalogue_entreprise_module
                cursor.execute(
                    "DELETE FROM public.catalogue_entreprise_module WHERE entreprise_id = ANY(%s);",
                    [ent_ids],
                )
                # factures & paiements
                cursor.execute("""
                    DELETE FROM public.paiement_abonnement 
                    WHERE facture_id IN (
                        SELECT id FROM public.facture WHERE entreprise_id = ANY(%s)
                    );
                """, [ent_ids])
                cursor.execute("DELETE FROM public.facture WHERE entreprise_id = ANY(%s);", [ent_ids])
                # abonnements & rappels / relances
                cursor.execute("""
                    DELETE FROM public.rappel_expiration_abonnement 
                    WHERE abonnement_id IN (
                        SELECT id FROM public.abonnement WHERE entreprise_id = ANY(%s)
                    );
                """, [ent_ids])
                cursor.execute("""
                    DELETE FROM public.relance_essai 
                    WHERE abonnement_id IN (
                        SELECT id FROM public.abonnement WHERE entreprise_id = ANY(%s)
                    );
                """, [ent_ids])
                cursor.execute("DELETE FROM public.abonnement WHERE entreprise_id = ANY(%s);", [ent_ids])
                # Détacher demandes_inscription
                cursor.execute(
                    "UPDATE public.demande_inscription SET entreprise_id = NULL WHERE entreprise_id = ANY(%s);",
                    [ent_ids],
                )
                # domaines
                cursor.execute("DELETE FROM public.domaine WHERE tenant_id = ANY(%s);", [ent_ids])
                # entreprises
                cursor.execute("DELETE FROM public.entreprise_cliente WHERE id = ANY(%s);", [ent_ids])

            _log(f"[PURGE] {len(entreprises)} entreprise(s) purgée(s) de public.entreprise_cliente.")

        # ── 4. Supprimer les demandes d'inscription 'zanf' ────────────────
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM public.demande_inscription 
                WHERE email ILIKE '%zanf%' 
                   OR slug_reserve ILIKE '%zanf%' 
                   OR raison_sociale ILIKE '%zanf%' 
                   OR nom ILIKE '%zanf%' 
                   OR prenom ILIKE '%zanf%';
            """)
            nb_demandes = cursor.rowcount
            if nb_demandes > 0:
                _log(f"[PURGE] {nb_demandes} demande(s) d'inscription purgée(s).")

        # ── 5. Supprimer les utilisateurs 'zanf' dans public.utilisateur ──
        with connection.cursor() as cursor:
            # Tables dépendantes directes
            cursor.execute("""
                DELETE FROM public.utilisateur_groups 
                WHERE utilisateur_id IN (
                    SELECT id FROM public.utilisateur 
                    WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                );
            """)
            cursor.execute("""
                DELETE FROM public.utilisateur_user_permissions 
                WHERE utilisateur_id IN (
                    SELECT id FROM public.utilisateur 
                    WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                );
            """)
            cursor.execute("""
                DELETE FROM public.jeton_reinitialisation 
                WHERE utilisateur_id IN (
                    SELECT id FROM public.utilisateur 
                    WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                );
            """)
            cursor.execute("""
                DELETE FROM public.appareil 
                WHERE utilisateur_id IN (
                    SELECT id FROM public.utilisateur 
                    WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                );
            """)
            cursor.execute("""
                DELETE FROM public.django_admin_log 
                WHERE user_id IN (
                    SELECT id FROM public.utilisateur 
                    WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                );
            """)
            cursor.execute("""
                DELETE FROM public.invitation 
                WHERE emetteur_id IN (
                    SELECT id FROM public.utilisateur 
                    WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                );
            """)

            # Neutraliser les FKs cree_par_id / supprime_par_id
            cursor.execute("""
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
            """)
            fks = cursor.fetchall()
            for table, col in fks:
                try:
                    cursor.execute(f"""
                        UPDATE public."{table}"
                        SET "{col}" = NULL
                        WHERE "{col}" IN (
                            SELECT id FROM public.utilisateur 
                            WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%'
                        );
                    """)
                except Exception:
                    pass

            # Supprimer de public.utilisateur
            cursor.execute("""
                DELETE FROM public.utilisateur 
                WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%';
            """)
            connection.commit()
            # ── 6. Rapport d'état final ──────────────────────────────────────
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name ILIKE '%zanf%' AND schema_name NOT IN ('public', 'demo');")
            rest_schemas = [r[0] for r in cursor.fetchall()]
            cursor.execute("SELECT schema_name FROM public.entreprise_cliente WHERE schema_name ILIKE '%zanf%' OR raison_sociale ILIKE '%zanf%' OR email_contact ILIKE '%zanf%';")
            rest_ent = [r[0] for r in cursor.fetchall()]
            cursor.execute("SELECT email, slug_reserve FROM public.demande_inscription WHERE email ILIKE '%zanf%' OR slug_reserve ILIKE '%zanf%' OR raison_sociale ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%';")
            rest_dem = [f"{r[0]} ({r[1]})" for r in cursor.fetchall()]
            cursor.execute("SELECT email FROM public.utilisateur WHERE email ILIKE '%zanf%' OR nom ILIKE '%zanf%' OR prenom ILIKE '%zanf%';")
            rest_usr = [r[0] for r in cursor.fetchall()]

            _log(f"[RAPPORT] Purge terminée avec succès.")
            _log(f"  - Schémas PostgreSQL zanf restants : {len(rest_schemas)} {rest_schemas}")
            _log(f"  - Entreprises zanf restantes : {len(rest_ent)} {rest_ent}")
            _log(f"  - Demandes d'inscription zanf restantes : {len(rest_dem)} {rest_dem}")
            _log(f"  - Utilisateurs zanf restants dans public : {len(rest_usr)} {rest_usr}")

    except Exception as exc:
        _log(f"[PURGE] Erreur globale lors de la purge zanf : {exc}", "error")


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
