"""Commande d'administration souveraine : lister et supprimer proprement les entreprises.

Usage :
    # 1. Lister toutes les entreprises, schémas et Directeurs Généraux
    python manage.py gerer_entreprises --lister

    # 2. Supprimer proprement une entreprise par son schéma ou son UUID (avec confirmation)
    python manage.py gerer_entreprises --supprimer test_btp

    # 3. Supprimer sans confirmation interactive (CI / Scripts automatisés)
    python manage.py gerer_entreprises --supprimer test_btp --oui
"""

from django.core.management.base import BaseCommand, CommandError

from apps.tenants.services.nettoyage import (
    SCHEMAS_PROTEGES,
    lister_entreprises_avec_directeurs,
    supprimer_entreprise_proprement,
)


class Command(BaseCommand):
    help = "Gestion et nettoyage propre des entreprises et de leurs schémas multi-tenants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lister",
            action="store_true",
            help="Affiche toutes les entreprises, leurs schémas, Directeurs Généraux et demandes.",
        )
        parser.add_argument(
            "--supprimer",
            type=str,
            help="Nom de schéma (schema_name) ou UUID de l'entreprise à supprimer proprement.",
        )
        parser.add_argument(
            "--oui",
            action="store_true",
            help="Confirme automatiquement la suppression sans demander d'interaction.",
        )

    def handle(self, *args, **options):
        if not options["lister"] and not options["supprimer"]:
            self.stdout.write(
                self.style.WARNING(
                    "Aucune action demandée. Précisez --lister ou --supprimer <schema_ou_uuid>."
                )
            )
            return

        if options["lister"]:
            self._lister()

        if options["supprimer"]:
            self._supprimer(options["supprimer"], options["oui"])

    def _lister(self):
        donnees = lister_entreprises_avec_directeurs()
        entreprises = donnees["entreprises"]
        demandes = donnees["demandes_inscription"]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== ENTREPRISES CLIENTES (TENANTS) ==="))
        if not entreprises:
            self.stdout.write("  (Aucune entreprise cliente enregistrée)")
        for ent in entreprises:
            prot = " [PROTÉGÉ]" if ent["est_protege"] else ""
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n• Entreprise : {ent['raison_sociale']} ({ent['schema_name']}){prot}"
                )
            )
            self.stdout.write(f"  ID UUID   : {ent['id']}")
            self.stdout.write(f"  Statut    : {ent['statut']}")
            self.stdout.write(
                f"  Contact   : {ent['email_contact']} ({ent['telephone_contact'] or 'aucun tél'})"
            )
            self.stdout.write(f"  Domaines  : {', '.join(ent['domaines']) or 'aucun'}")

            dgs = ent["directeurs_generaux"]
            if dgs:
                self.stdout.write("  Directeur(s) Général(aux) :")
                for dg in dgs:
                    if "erreur" in dg:
                        self.stdout.write(self.style.WARNING(f"    - Erreur : {dg['erreur']}"))
                    else:
                        tel = f" | Tél: {dg['telephone']}" if dg["telephone"] else ""
                        nom_complet = f"{dg['nom']} {dg['prenom']}".strip()
                        self.stdout.write(
                            f"    - {nom_complet} <{dg['email']}> [{dg['statut']}]{tel}"
                        )
            else:
                self.stdout.write(self.style.WARNING("  Directeur(s) Général(aux) : Aucun trouvé."))

        self.stdout.write(
            self.style.MIGRATE_HEADING("\n=== DEMANDES D'INSCRIPTION (SCHEMA PUBLIC) ===")
        )
        if not demandes:
            self.stdout.write("  (Aucune demande d'inscription)")
        for dem in demandes:
            self.stdout.write(
                f"• [{dem['statut']}] {dem['raison_sociale']} (slug: {dem['slug_reserve']}) "
                f"-> Contact: {dem['nom']} {dem['prenom']} <{dem['email']}>"
            )
        self.stdout.write("")

    def _supprimer(self, identifiant, confirmation_auto):
        identifiant = identifiant.strip().lower()
        if identifiant in SCHEMAS_PROTEGES:
            raise CommandError(
                f"Interdiction absolue : « {identifiant} » fait partie des schémas "
                f"protégés ({', '.join(SCHEMAS_PROTEGES)})."
            )

        if not confirmation_auto:
            self.stdout.write(
                self.style.WARNING(
                    f"\nATTENTION : Vous allez supprimer l'entreprise « {identifiant} »,\n"
                    "son schéma PostgreSQL et toutes ses données dans le schéma public."
                )
            )
            saisie = input("Pour confirmer la suppression, tapez le nom du schéma : ")
            if saisie.strip().lower() != identifiant:
                self.stdout.write(self.style.ERROR("Annulation : la saisie ne correspond pas."))
                return

        try:
            rapport = supprimer_entreprise_proprement(identifiant)
            self.stdout.write(
                self.style.SUCCESS(f"\n[SUCCÈS] Entreprise « {identifiant} » purgée.")
            )
            schema_s = rapport["schema_supprime"]
            drop_s = rapport.get("schema_drop", False)
            self.stdout.write(f"  Schéma PostgreSQL : {schema_s} (DROP CASCADE : {drop_s})")
            self.stdout.write("  Tables publiques nettoyées :")
            for table, nb in rapport["tables_nettoyees"].items():
                self.stdout.write(f"    - {table} : {nb} ligne(s) supprimée(s)")
            self.stdout.write("")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(f"Erreur inattendue lors de la suppression : {exc}") from exc
