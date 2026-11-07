"""Débloque un compte bloqué après cinq tentatives échouées.

    python manage.py debloquer_compte chef@btp.ci
    python manage.py debloquer_compte chef@btp.ci --simulation

L'adresse est unique sur la plateforme (D9, R-8) : la commande la cherche dans toutes les
entreprises, en portée plateforme. C'est le cas d'usage du support, qui reçoit un appel et ne sait
pas toujours de quelle entreprise vient la personne.

Cette commande ne réactive **pas** un compte désactivé par un
administrateur : ce sont deux états distincts, aux sorties différentes.
Un compte désactivé se réactive depuis l'administration (workflow T5).
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core.contexte import portee_plateforme
from apps.core.enums import StatutUtilisateur


# La console Windows est en cp1252 : une flèche « → » ou un emoji y fait
# planter la commande sur un UnicodeEncodeError. Sortie en ASCII pour les
# symboles ; les lettres accentuées, elles, passent sans problème.
class Command(BaseCommand):
    help = "Débloque un compte verrouillé par cinq tentatives de connexion échouées."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Adresse email du compte.")
        parser.add_argument(
            "--simulation",
            action="store_true",
            help="Affiche l'état du compte sans rien modifier.",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import Utilisateur

        email = options["email"].strip().lower()
        with portee_plateforme(motif="commande debloquer_compte"):
            utilisateur = (
                Utilisateur.objects.filter(email__iexact=email).select_related("entreprise").first()
            )
            if utilisateur is None:
                raise CommandError(f"Aucun compte « {email} » sur la plateforme.")
            self._traiter(utilisateur, simulation=options["simulation"])

    # ----------------------------------------------------------------------

    def _traiter(self, utilisateur, *, simulation: bool) -> None:
        entreprise = utilisateur.entreprise
        portee = entreprise.slug if entreprise else "personnel de l'éditeur"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\nEntreprise « {portee} »"))
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
            return

        if not utilisateur.est_bloque and utilisateur.tentatives_echouees == 0:
            self.stdout.write(
                self.style.SUCCESS("  -> Rien à faire, le compte est utilisable.")
            )
            return

        if simulation:
            self.stdout.write(self.style.WARNING("  -> Simulation : aucune modification."))
            return

        utilisateur.bloque_le = None
        utilisateur.tentatives_echouees = 0
        utilisateur.save(update_fields=["bloque_le", "tentatives_echouees", "modifie_le"])

        self.stdout.write(self.style.SUCCESS("  -> Débloqué. Le compte peut se reconnecter."))
        return
