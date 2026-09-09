"""Crée les trois plans — **sans leur prix**.

    python manage.py peupler_plans

**Les tarifs sont laissés à `NULL`, et c'est délibéré.** L'arbitrage A7 est
ouvert : « 49 000 FCFA/mois » n'apparaît que dans la maquette M10, et ce montant
n'a de source ni au CDC, ni au MVP, ni au backlog. Il est né d'un dessin, pas
d'une décision.

*C'est le risque que T-017 §13 décrivait : **un réglage absent se remarque, un
réglage plausible ne se remarque pas.*** Un tarif inventé « en attendant » a de
bonnes chances d'arriver en production sans que personne ne se souvienne qu'il
était un bouche-trou. `NULL` se remarque : l'écran affiche « — » et la
facturation refuse d'émettre.

Idempotente : relancer la commande ne remet aucun prix à zéro, et ne défait pas
un tarif que la Direction aurait tranché.
"""

from django.core.management.base import BaseCommand

from apps.billing.models import Plan

# Les limites viennent du Socle §6.2 pour le MVP — 50 projets par compte, 10 Go
# de documents — et de la maquette M10 pour la répartition entre plans. Elles
# sont, elles, décidées : ce sont des capacités, pas des prix.
PLANS = [
    {
        "code": Plan.Code.STARTER,
        "libelle": "Starter",
        "limite_projets": 3,
        "limite_utilisateurs": 5,
        "limite_stockage_mo": 2_000,
        "acces_ia": False,
    },
    {
        "code": Plan.Code.PRO,
        "libelle": "Pro",
        "limite_projets": 50,
        "limite_utilisateurs": 25,
        "limite_stockage_mo": 10_000,
        "acces_ia": True,
    },
    {
        "code": Plan.Code.ENTERPRISE,
        "libelle": "Enterprise",
        # `None` signifie **illimité**, jamais zéro. Les confondre ferait du
        # plan le plus cher le plus restrictif de tous.
        "limite_projets": None,
        "limite_utilisateurs": None,
        "limite_stockage_mo": None,
        "acces_ia": True,
    },
]


class Command(BaseCommand):
    help = "Crée les trois plans d'abonnement, sans tarif (arbitrage A7 ouvert)."

    def handle(self, *args, **options):
        for definition in PLANS:
            plan, cree = Plan.objects.get_or_create(
                code=definition["code"],
                defaults={k: v for k, v in definition.items() if k != "code"},
            )
            etat = "créé" if cree else "déjà présent"
            self.stdout.write(self.style.SUCCESS(f"Plan {etat} : {plan.libelle}"))

        sans_tarif = Plan.objects.filter(prix_mensuel_montant__isnull=True).count()
        if sans_tarif:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"{sans_tarif} plan(s) sans tarif — arbitrage A7. "
                    "La facturation ne peut pas émettre tant que la Direction n'a "
                    "pas tranché, et l'écran affiche « — »."
                )
            )
