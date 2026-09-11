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

# Forfaits personnalisés BTP — Capacités et tarifs (en centimes de FCFA)
PLANS = [
    {
        "code": Plan.Code.BATISSEUR,
        "libelle": "Bâtisseur",
        "limite_projets": 3,
        "limite_utilisateurs": 5,
        "limite_stockage_mo": 2_000,
        "acces_ia": False,
        "prix_mensuel_montant": 19_000_00,  # 19 000 FCFA
        "prix_annuel_montant": 190_000_00,  # 190 000 FCFA
    },
    {
        "code": Plan.Code.MAITRE_OEUVRE,
        "libelle": "Maître d'Œuvre",
        "limite_projets": 50,
        "limite_utilisateurs": 25,
        "limite_stockage_mo": 10_000,
        "acces_ia": True,
        "prix_mensuel_montant": 49_000_00,  # 49 000 FCFA
        "prix_annuel_montant": 490_000_00,  # 490 000 FCFA
    },
    {
        "code": Plan.Code.PROMOTEUR,
        "libelle": "Promoteur",
        "limite_projets": None,
        "limite_utilisateurs": None,
        "limite_stockage_mo": None,
        "acces_ia": True,
        "prix_mensuel_montant": 119_000_00,  # 119 000 FCFA
        "prix_annuel_montant": 1_190_000_00,  # 1 190 000 FCFA
    },
]


class Command(BaseCommand):
    help = "Crée ou met à jour les trois forfaits BTP (Bâtisseur, Maître d'Œuvre, Promoteur)."

    def handle(self, *args, **options):
        for definition in PLANS:
            code = definition["code"]
            defaults = {k: v for k, v in definition.items() if k != "code"}
            plan, cree = Plan.objects.update_or_create(
                code=code,
                defaults=defaults,
            )
            etat = "créé" if cree else "mis à jour"
            tarif_desc = (
                f"{plan.prix_mensuel_montant / 100:,.0f} FCFA/mois"
                if plan.prix_mensuel_montant
                else "sans tarif"
            )
            self.stdout.write(self.style.SUCCESS(f"Plan {etat} : {plan.libelle} ({tarif_desc})"))

        # Désactiver les anciens codes génériques pour qu'ils ne soient plus proposés
        Plan.objects.filter(code__in=["STARTER", "PRO", "ENTERPRISE"]).update(est_actif=False)
