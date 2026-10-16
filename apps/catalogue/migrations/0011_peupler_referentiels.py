"""Peuple les référentiels de la plateforme (arbitrage du 16/10/2026).

- Types de projet : les six codes de l'ancienne énumération `TypeProjet`, pour que les
  projets existants gardent leur libellé.
- Noms de lot : la liste indicative par corps d'état que le formulaire de lot proposait
  en dur (`features/referentiels/lots.ts` du frontend).
"""

from django.db import migrations

TYPES_PROJET = [
    ("BATIMENT_RESIDENTIEL", "Bâtiment — Résidentiel"),
    ("BATIMENT_COMMERCIAL", "Bâtiment — Commercial"),
    ("TP_ROUTE", "TP — Route"),
    ("TP_GENIE_CIVIL", "TP — Génie civil"),
    ("VRD", "VRD"),
    ("INFRASTRUCTURE_INDUSTRIELLE", "Infrastructure industrielle"),
]

LOTS = [
    (
        "Voiries et réseaux divers",
        [
            "VRD1 - Terrassements généraux, voirie, parkings, clôture",
            "VRD2 - Drainage général, murs de soutènement, traitement des déchets",
            "VRD3 - Assainissement eaux pluviales, eaux usées, eaux vannes, station d’épuration",
            "VRD4 - Alimentation en eau potable, arrosage, bâches à eau (sanitaire et sécurité incendie)",
            "VRD5 - Alimentation électricité, locaux transfo, groupes électrogènes, éclairage public",
            "VRD6 - Alimentation télécommunications",
            "VRD7 - Jardins, plantations d’arbres, d’arbustes et engazonnement",
            "VRD8 - Mobilier urbain et signalétique extérieure",
            "VRD9 - Terrains de sports",
        ],
    ),
    (
        "Lots architecturaux",
        [
            "Fondations profondes",
            "Gros œuvre",
            "Étanchéité des toitures terrasses et autres",
            "Menuiserie intérieure en bois",
            "Menuiserie aluminium",
            "Vitrerie",
            "Menuiserie métallique",
            "Revêtements durs décoratifs",
            "Revêtements durs",
            "Revêtements souples",
            "Faux plafonds (staff, acoustique ou diffusant)",
            "Peinture",
            "Teintures, rideaux, stores",
            "Signalétique",
        ],
    ),
    (
        "Lots techniques",
        [
            "Plomberie sanitaire, ventilation mécanique contrôlée",
            "Climatisation",
            "Électricité courant fort",
            "Distribution du courant régulé",
            "Détection, extinction, report d’alarmes techniques",
            "Sonorisation des salles de langue, conférence, projection",
            "Ascenseurs",
            "Portes coupe-feu",
            "Sécurité incendie",
            "Nacelle de nettoyage des façades",
            "Paratonnerre",
        ],
    ),
    (
        "Télécommunication et informatique",
        [
            "Réseau informatique",
            "Téléphonie, interphonie",
            "Installation TV",
        ],
    ),
    (
        "Sécurité d’accès",
        [
            "Système de sécurité d’accès par lecteur biométrique, digicode",
            "Système de caméras de surveillance",
            "Anti-intrusion",
            "GTB/GTC",
        ],
    ),
    (
        "Décoration",
        [
            "Décoration habillage muraux (salle de conférence, bibliothèque)",
            "Décoration mobilier salle de conférence (sièges)",
            "Décoration plafond salle de conférence",
            "Rideaux décoratifs salle de conférence",
        ],
    ),
    (
        "Mobilier",
        [
            "MOB.1 Mobilier bureaux, académique",
            "MOB.2 Mobilier logement étudiants et enseignants, logements de fonction et astreintes",
            "MOB.3 Mobilier restauration et centre médical",
            "MOB.4 Mobilier urbain de jardin",
            "MOB.5 Mobilier bibliothèque",
        ],
    ),
    (
        "Équipements",
        [
            "EQU.1 Équipements scientifiques de laboratoires spécialisés et ateliers",
            "EQU.2 Équipements de laboratoires de langue et multimédia",
            "EQU.3 Équipements de cuisine et vaissellerie",
            "EQU.4 Équipements informatiques pour l’administration",
            "EQU.5 Équipements de reprographie centrale et photocopie en bureaux",
            "EQU.6 Équipements didactiques divers (tableaux)",
            "EQU.7 Équipements sportifs",
            "EQU.8 Équipements médicaux",
            "EQU.9 Équipements téléenseignement, visioconférence",
        ],
    ),
]


def peupler(apps, schema_editor):
    from apps.catalogue.models.referentiel import code_depuis_libelle

    Referentiel = apps.get_model("catalogue", "ReferentielPlateforme")
    for ordre, (code, libelle) in enumerate(TYPES_PROJET):
        Referentiel.objects.get_or_create(
            categorie="TYPE_PROJET",
            code=code,
            supprime_le__isnull=True,
            defaults={"libelle": libelle, "ordre": ordre},
        )
    ordre = 0
    for famille, noms in LOTS:
        for nom in noms:
            Referentiel.objects.get_or_create(
                categorie="LOT",
                code=code_depuis_libelle(nom),
                supprime_le__isnull=True,
                defaults={"libelle": nom, "groupe": famille, "ordre": ordre},
            )
            ordre += 1


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0010_referentiel_plateforme")]

    operations = [migrations.RunPython(peupler, migrations.RunPython.noop)]
