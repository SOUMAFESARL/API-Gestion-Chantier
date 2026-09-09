"""Débloque un compte bloqué après cinq tentatives échouées.

    python manage.py debloquer_compte chef@btp.ci
    python manage.py debloquer_compte chef@btp.ci --schema demo
    python manage.py debloquer_compte chef@btp.ci --simulation

Sans `--schema`, la commande cherche l'adresse dans **tous** les schémas
clients : c'est le cas d'usage du support, qui reçoit un appel et ne sait
pas toujours de quelle entreprise vient la personne.

Cette commande ne réactive **pas** un compte désactivé par un
administrateur : ce sont deux états distincts, aux sorties différentes.
Un compte désactivé se réactive depuis l'administration (workflow T5).
"""

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context

from apps.core.enums import StatutUtilisateur


# La console Windows est en cp1252 : une flèche « → » ou un emoji y fait
# planter la commande sur un UnicodeEncodeError. Sortie en ASCII pour les
# symboles ; les lettres accentuées, elles, passent sans problème.
class Command(BaseCommand):
    help = "Débloque un compte verrouillé par cinq tentatives de connexion échouées."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Adresse email du compte.")
        parser.add_argument(
            "--schema",
            help="Schéma de l'entreprise cliente. Omis, la recherche porte sur tous.",
        )
        parser.add_argument(
            "--simulation",
            action="store_true",
            help="Affiche l'état du compte sans rien modifier.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        schemas = [options["schema"]] if options["schema"] else self._schemas_clients()

        if not schemas:
            raise CommandError("Aucune entreprise cliente enregistrée.")

        trouve = False
        for code_schema in schemas:
            if self._traiter(code_schema, email, simulation=options["simulation"]):
                trouve = True

        if not trouve:
            raise CommandError(f"Aucun compte « {email} » dans {self._enumerer(schemas)}.")

    # ----------------------------------------------------------------------

    def _schemas_clients(self) -> list[str]:
        from apps.tenants.models import Entreprise

        with schema_context(get_public_schema_name()):
            return list(
                Entreprise.objects.exclude(schema_name=get_public_schema_name())
                .order_by("schema_name")
                .values_list("schema_name", flat=True)
            )

    def _traiter(self, code_schema: str, email: str, *, simulation: bool) -> bool:
        with schema_context(code_schema):
            from apps.accounts.models import Utilisateur

            utilisateur = Utilisateur.objects.filter(email__iexact=email).first()
            if utilisateur is None:
                return False

            self.stdout.write(self.style.MIGRATE_HEADING(f"\nSchéma « {code_schema} »"))
            self.stdout.write(f"  compte             : {utilisateur.email}")
            self.stdout.write(f"  statut             : {utilisateur.statut}")
            self.stdout.write(f"  tentatives échouées: {utilisateur.tentatives_echouees}")
            etat = "oui" if utilisateur.est_bloque else "non"
            self.stdout.write(f"  bloqué             : {etat}")

            if utilisateur.bloque_le:
                # Aucune échéance à annoncer : un blocage ne s'éteint plus seul
                # (T-008 §6.3). On dit depuis quand, et par où il se lève.
                self.stdout.write(
                    f"  bloqué depuis      : {utilisateur.bloque_le:%d/%m/%Y à %H:%M}"
                )
                self.stdout.write(
                    "  sortie             : email de réinitialisation, ou cette commande"
                )

            if utilisateur.statut == StatutUtilisateur.DESACTIVE:
                self.stdout.write(
                    self.style.WARNING(
                        "  -> Ce compte est DÉSACTIVÉ, pas bloqué. Un blocage se lève par "
                        "désactivation attend un administrateur (workflow T5). Cette "
                        "commande n'y touche pas."
                    )
                )
                return True

            if not utilisateur.est_bloque and utilisateur.tentatives_echouees == 0:
                self.stdout.write(
                    self.style.SUCCESS("  -> Rien à faire, le compte est utilisable.")
                )
                return True

            if simulation:
                self.stdout.write(self.style.WARNING("  -> Simulation : aucune modification."))
                return True

            utilisateur.bloque_le = None
            utilisateur.tentatives_echouees = 0
            utilisateur.save(update_fields=["bloque_le", "tentatives_echouees", "modifie_le"])

            self.stdout.write(self.style.SUCCESS("  -> Débloqué. Le compte peut se reconnecter."))
            return True

    @staticmethod
    def _enumerer(schemas: list[str]) -> str:
        if len(schemas) == 1:
            return f"le schéma « {schemas[0]} »"
        return f"les {len(schemas)} schémas clients"
