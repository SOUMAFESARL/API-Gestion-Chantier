"""Sème les listes et les modèles de découpage de la plateforme (décisions v1.2, §3 et §4).

- **« Phases »** : les grandes étapes d'un chantier.
- **« Lots »** : reprend la catégorie `LOT` du référentiel plateforme, groupes compris (§4.2 :
  « la catégorie LOT du référentiel actuel devient la liste Lots »).
- **Un modèle par type de projet**, désigné modèle par défaut de ce type : c'est lui qui
  pré-remplit le tableau de démarrage. Ouvrage et activité se saisissent librement : leur niveau
  ne puise dans aucune liste. Les lignes types sont des exemples, que l'entreprise modifie.
- Un modèle « Villa » à deux niveaux, Lot et Activité, comme le découpage d'avant la refonte.

Le niveau qui joue le rôle du lot porte « alerter à ce niveau » (§13quater-ter).
"""

from django.db import migrations

PHASES = [
    "Installation de chantier",
    "Études et préparation",
    "Terrassements",
    "Infrastructure",
    "Superstructure",
    "Second œuvre",
    "Finitions",
    "Chaussée",
    "Assainissement et drainage",
    "Signalisation et équipements",
    "VRD et aménagements extérieurs",
    "Réception et levée des réserves",
]

GROS_OEUVRE = "Gros œuvre"
ELECTRICITE = "Électricité courant fort"
PLOMBERIE = "Plomberie sanitaire, ventilation mécanique contrôlée"
PEINTURE = "Peinture"
REVETEMENTS = "Revêtements durs"
FONDATIONS = "Fondations profondes"
METALLERIE = "Menuiserie métallique"
VRD1 = "VRD1 - Terrassements généraux, voirie, parkings, clôture"
VRD3 = "VRD3 - Assainissement eaux pluviales, eaux usées, eaux vannes, station d’épuration"
VRD8 = "VRD8 - Mobilier urbain et signalétique extérieure"

MODELES = [
    {
        "nom": "Bâtiment — Phase, ouvrage, lot, activité",
        "description": "Le découpage d'un immeuble ou d'un bâtiment : chaque phase en "
        "bâtiments, chaque bâtiment en lots, chaque lot en activités.",
        "types": ["BATIMENT_RESIDENTIEL", "BATIMENT_COMMERCIAL"],
        "defaut": ["BATIMENT_RESIDENTIEL", "BATIMENT_COMMERCIAL"],
        "niveaux": [("Phase", "Phases", False), ("Ouvrage", None, False),
                    ("Lot", "Lots", True), ("Activité", None, False)],
        "lignes": [
            ["Installation de chantier", "Site", GROS_OEUVRE, "Clôture et installations de chantier"],
            ["Infrastructure", "Bâtiment A", GROS_OEUVRE, "Fouilles en rigoles"],
            ["Infrastructure", "Bâtiment A", GROS_OEUVRE, "Béton de propreté"],
            ["Infrastructure", "Bâtiment A", GROS_OEUVRE, "Semelles et longrines"],
            ["Superstructure", "Bâtiment A", GROS_OEUVRE, "Élévation des murs"],
            ["Superstructure", "Bâtiment A", GROS_OEUVRE, "Dalle haute"],
            ["Second œuvre", "Bâtiment A", ELECTRICITE, "Gaines et boîtiers"],
            ["Second œuvre", "Bâtiment A", PLOMBERIE, "Réseaux d'alimentation"],
            ["Finitions", "Bâtiment A", REVETEMENTS, "Carrelage"],
            ["Finitions", "Bâtiment A", PEINTURE, "Peinture intérieure"],
        ],
    },
    {
        "nom": "Route — Phase, section, lot, activité",
        "description": "Une route découpée en sections repérées par leurs points "
        "kilométriques (PK).",
        "types": ["TP_ROUTE"],
        "defaut": ["TP_ROUTE"],
        "niveaux": [("Phase", "Phases", False), ("Section", None, False),
                    ("Lot", "Lots", True), ("Activité", None, False)],
        "lignes": [
            ["Installation de chantier", "Base vie", VRD1, "Installation de la base vie"],
            ["Terrassements", "PK 0 – PK 5", VRD1, "Décapage de la terre végétale"],
            ["Terrassements", "PK 0 – PK 5", VRD1, "Déblais et remblais"],
            ["Chaussée", "PK 0 – PK 5", VRD1, "Couche de fondation"],
            ["Chaussée", "PK 0 – PK 5", VRD1, "Revêtement bitumineux"],
            ["Assainissement et drainage", "PK 0 – PK 5", VRD3, "Caniveaux"],
            ["Signalisation et équipements", "PK 0 – PK 5", VRD8, "Signalisation verticale"],
        ],
    },
    {
        "nom": "Génie civil — Partie, élément, lot, activité",
        "description": "Un ouvrage d'art (pont, barrage) découpé en parties puis en éléments, "
        "par exemple les appuis puis la pile n° 2.",
        "types": ["TP_GENIE_CIVIL"],
        "defaut": ["TP_GENIE_CIVIL"],
        "niveaux": [("Partie", None, False), ("Élément", None, False),
                    ("Lot", "Lots", True), ("Activité", None, False)],
        "lignes": [
            ["Appuis", "Culée C0", FONDATIONS, "Forage des pieux"],
            ["Appuis", "Pile n° 2", FONDATIONS, "Forage des pieux"],
            ["Appuis", "Pile n° 2", GROS_OEUVRE, "Ferraillage et coffrage du fût"],
            ["Tablier", "Travée 1", GROS_OEUVRE, "Pose des poutres"],
            ["Tablier", "Travée 1", GROS_OEUVRE, "Hourdis"],
            ["Équipements", "Garde-corps", METALLERIE, "Pose des garde-corps"],
        ],
    },
    {
        "nom": "VRD — Phase, tronçon, lot, activité",
        "description": "Voiries et réseaux divers découpés en tronçons.",
        "types": ["VRD"],
        "defaut": ["VRD"],
        "niveaux": [("Phase", "Phases", False), ("Tronçon", None, False),
                    ("Lot", "Lots", True), ("Activité", None, False)],
        "lignes": [
            ["Terrassements", "Tronçon 1", VRD1, "Décapage"],
            ["Terrassements", "Tronçon 1", VRD1, "Mise en forme de la plateforme"],
            ["Assainissement et drainage", "Tronçon 1", VRD3, "Pose des canalisations"],
            ["Assainissement et drainage", "Tronçon 1", VRD3, "Regards de visite"],
            ["Chaussée", "Tronçon 1", VRD1, "Couche de roulement"],
        ],
    },
    {
        "nom": "Industriel — Phase, installation, lot, activité",
        "description": "Une infrastructure industrielle découpée en installations (hangar, "
        "unité de production, local technique).",
        "types": ["INFRASTRUCTURE_INDUSTRIELLE"],
        "defaut": ["INFRASTRUCTURE_INDUSTRIELLE"],
        "niveaux": [("Phase", "Phases", False), ("Installation", None, False),
                    ("Lot", "Lots", True), ("Activité", None, False)],
        "lignes": [
            ["Infrastructure", "Hangar principal", GROS_OEUVRE, "Massifs des poteaux"],
            ["Infrastructure", "Hangar principal", GROS_OEUVRE, "Dallage industriel"],
            ["Superstructure", "Hangar principal", METALLERIE, "Charpente métallique"],
            ["Superstructure", "Hangar principal", METALLERIE, "Bardage et couverture"],
            ["Second œuvre", "Hangar principal", ELECTRICITE, "Éclairage"],
        ],
    },
    {
        "nom": "Villa — Lot, activité",
        "description": "Deux niveaux, lot et activité : le découpage d'un petit chantier.",
        "types": ["BATIMENT_RESIDENTIEL"],
        "defaut": [],
        "niveaux": [("Lot", "Lots", True), ("Activité", None, False)],
        "lignes": [
            [GROS_OEUVRE, "Fondations"],
            [GROS_OEUVRE, "Élévation des murs"],
            [ELECTRICITE, "Installation électrique"],
            [PLOMBERIE, "Plomberie"],
            [PEINTURE, "Peinture"],
        ],
    },
]


def peupler(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") != "public":
        return
    from apps.catalogue.models.referentiel import cle_comparaison

    Liste = apps.get_model("catalogue", "ListeValeursPlateforme")
    Valeur = apps.get_model("catalogue", "ValeurListePlateforme")
    Modele = apps.get_model("catalogue", "ModeleDecoupagePlateforme")
    Niveau = apps.get_model("catalogue", "NiveauModelePlateforme")
    Ligne = apps.get_model("catalogue", "LigneModelePlateforme")
    Referentiel = apps.get_model("catalogue", "ReferentielPlateforme")

    def valeur(liste, libelle, groupe, ordre):
        Valeur.objects.get_or_create(
            liste=liste,
            cle_comparaison=cle_comparaison(libelle),
            supprime_le__isnull=True,
            defaults={"libelle": libelle, "groupe": groupe, "ordre": ordre},
        )

    phases, _ = Liste.objects.get_or_create(
        libelle="Phases", supprime_le__isnull=True,
        defaults={"description": "Les grandes étapes d'un chantier.", "ordre": 1},
    )
    for ordre, libelle in enumerate(PHASES):
        valeur(phases, libelle, "", ordre)

    lots, _ = Liste.objects.get_or_create(
        libelle="Lots", supprime_le__isnull=True,
        defaults={"description": "Les lots de travaux, par corps d'état.", "ordre": 2},
    )
    entrees = Referentiel.objects.filter(categorie="LOT", supprime_le__isnull=True).order_by(
        "ordre", "libelle"
    )
    for ordre, entree in enumerate(entrees):
        valeur(lots, entree.libelle, entree.groupe, ordre)

    listes = {"Phases": phases, "Lots": lots}
    for definition in MODELES:
        if Modele.objects.filter(nom=definition["nom"], supprime_le__isnull=True).exists():
            continue
        modele = Modele.objects.create(
            nom=definition["nom"],
            description=definition["description"],
            types_projet=definition["types"],
            par_defaut_pour=definition["defaut"],
        )
        for ordre, (libelle, nom_liste, alerter) in enumerate(definition["niveaux"], start=1):
            Niveau.objects.create(
                modele=modele,
                ordre=ordre,
                libelle=libelle,
                liste=listes.get(nom_liste),
                alerter=alerter,
            )
        for ordre, cellules in enumerate(definition["lignes"]):
            Ligne.objects.create(modele=modele, ordre=ordre, valeurs=cellules)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0013_decoupage_listes_modeles"),
    ]

    operations = [
        migrations.RunPython(peupler, migrations.RunPython.noop),
    ]
