"""Peuple une entreprise de développement avec un jeu de données de test réaliste.

    python manage.py peupler_donnees_test                     # entreprise `demo`
    python manage.py peupler_donnees_test --entreprise demo

**Développement uniquement.** Le jeu couvre les situations qu'on veut pouvoir tester sans les
fabriquer à la main : un chantier à l'heure, un en retard, un suspendu par un arrêt, un
réceptionné, un pas encore démarré, un découpage à périmètres (deux rédacteurs sur la même
route), des journaux approuvés, soumis, rejetés et en brouillon, des blocages à chaque étape.

Ce que la commande crée, dans l'entreprise choisie :

- une quinzaine de collaborateurs (mot de passe commun, `--motdepasse`) ;
- une vingtaine de tiers : maîtres d'ouvrage, bureaux d'études, tâcherons, sous-traitants,
  fournisseurs ;
- un registre d'une centaine de personnes de main-d'œuvre ;
- huit chantiers `TEST-2026-0xx`, chacun avec son arbre, ses affectations, ses équipes, et
  l'historique de son avancement.

**L'avancement passe par les calculs de l'application**, jamais par une valeur écrite à la
main : les quantités des feuilles avancent par semaine jusqu'à l'ouverture du chantier sur la
plateforme (la reprise), puis jour après jour par des journaux approuvés, synchronisés comme le
fait `synchroniser_rapport_approuve`. Chaque étape recalcule l'arbre et enregistre son relevé,
ce qui donne une vraie courbe en S. Le statut, l'indice de santé et les alertes sont évalués une
seule fois, à la fin, par rapport à aujourd'hui — les évaluer en cours de route les jugerait
contre la mauvaise date et laisserait des alertes fausses.

Idempotent : un chantier dont la référence existe déjà est laissé tel quel. Pour tout régénérer,
`--reinitialiser` supprime d'abord **physiquement** les chantiers `TEST-2026-*` et ce qui en
dépend — et eux seuls : collaborateurs, tiers et registre sont réutilisés. C'est l'exception de
maintenance que `ModeleBase.supprimer_definitivement` prévoit ; la règle du Socle §3.1 vaut pour
les données de l'application, pas pour un jeu de test qu'on rejoue.
"""

# Les tables de données (gabarits, chantiers, tiers) restent sur une ligne par entrée.
# ruff: noqa: E501

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

FUSEAU = timezone.get_fixed_timezone(0)  # Abidjan : UTC+0, sans heure d'été.
GRAINE = 20261106

# ---------------------------------------------------------------------------
# Les gabarits de découpage : (niveau 1, niveau 2, feuille, unité, quantité, prix unitaire
# en FCFA, début et fin en fraction de la durée du chantier).
# ---------------------------------------------------------------------------
BATIMENT = [
    ("Installation de chantier", "Installation", "Clôture et baraquements", "FORFAIT", 1, 3_500_000, 0.00, 0.04),
    ("Installation de chantier", "Installation", "Implantation et piquetage", "FORFAIT", 1, 800_000, 0.02, 0.05),
    ("Gros œuvre", "Terrassements", "Fouilles en rigole", "M3", 180, 6_500, 0.04, 0.10),
    ("Gros œuvre", "Fondations", "Béton de propreté", "M3", 15, 85_000, 0.08, 0.12),
    ("Gros œuvre", "Fondations", "Semelles filantes en béton armé", "M3", 45, 185_000, 0.10, 0.18),
    ("Gros œuvre", "Élévation", "Maçonnerie en agglos de 15", "M2", 950, 9_500, 0.18, 0.45),
    ("Gros œuvre", "Élévation", "Poteaux et chaînages", "M3", 38, 210_000, 0.18, 0.45),
    ("Gros œuvre", "Planchers", "Dalle haute du rez-de-chaussée", "M2", 320, 28_000, 0.28, 0.38),
    ("Gros œuvre", "Planchers", "Dalle haute de l'étage", "M2", 320, 28_000, 0.40, 0.50),
    ("Gros œuvre", "Toiture", "Charpente et couverture", "M2", 340, 22_000, 0.50, 0.60),
    ("Second œuvre", "Électricité", "Gaines et tirage des câbles", "ML", 2400, 1_800, 0.50, 0.70),
    ("Second œuvre", "Électricité", "Appareillage et tableau", "U", 140, 15_000, 0.75, 0.88),
    ("Second œuvre", "Plomberie", "Réseaux d'alimentation et d'évacuation", "ML", 650, 6_500, 0.50, 0.68),
    ("Second œuvre", "Plomberie", "Appareils sanitaires", "U", 36, 95_000, 0.78, 0.90),
    ("Second œuvre", "Menuiseries", "Portes intérieures en bois", "U", 42, 85_000, 0.72, 0.85),
    ("Second œuvre", "Menuiseries", "Fenêtres en aluminium", "U", 48, 120_000, 0.70, 0.84),
    ("Finitions", "Revêtements", "Enduits intérieurs et extérieurs", "M2", 2600, 3_500, 0.55, 0.75),
    ("Finitions", "Revêtements", "Carrelage sol et faïence", "M2", 780, 14_000, 0.72, 0.90),
    ("Finitions", "Peinture", "Peinture intérieure", "M2", 2200, 2_800, 0.85, 0.97),
    ("Finitions", "Peinture", "Peinture extérieure", "M2", 900, 3_200, 0.88, 0.98),
    ("VRD", "Assainissement", "Fosse septique et puisard", "U", 2, 1_200_000, 0.30, 0.45),
    ("VRD", "Aménagements extérieurs", "Pavage de la cour", "M2", 400, 12_000, 0.90, 1.00),
]


def _route() -> list[tuple]:
    lignes = [
        ("Installation et études", "Installation", "Amenée et repli du matériel", "FORFAIT", 1, 25_000_000, 0.00, 0.06),
        ("Installation et études", "Études", "Études d'exécution", "FORFAIT", 1, 18_000_000, 0.00, 0.10),
    ]
    for section, decalage in (("Section 1 — PK 0 à PK 4", 0.0), ("Section 2 — PK 4 à PK 8", 0.25)):
        etendue = 0.70
        for lot, tache, unite, qte, pu, d, f in (
            ("Terrassements", "Décapage de la terre végétale", "M2", 36_000, 450, 0.08, 0.25),
            ("Terrassements", "Déblais", "M3", 14_000, 2_800, 0.12, 0.35),
            ("Terrassements", "Remblais compactés", "M3", 11_000, 4_200, 0.18, 0.42),
            ("Chaussée", "Couche de fondation", "M3", 7_200, 14_500, 0.35, 0.60),
            ("Chaussée", "Couche de base en graveleux latéritique", "M3", 6_000, 19_000, 0.45, 0.70),
            ("Chaussée", "Imprégnation", "M2", 30_000, 1_200, 0.62, 0.75),
            ("Chaussée", "Revêtement en enrobé", "M2", 28_000, 9_500, 0.68, 0.90),
            ("Assainissement", "Caniveaux maçonnés", "ML", 5_200, 38_000, 0.30, 0.80),
            ("Assainissement", "Dalots", "U", 6, 9_500_000, 0.25, 0.65),
            ("Signalisation", "Marquage au sol", "ML", 8_000, 1_500, 0.88, 0.98),
            ("Signalisation", "Panneaux de signalisation", "U", 40, 180_000, 0.88, 1.00),
        ):
            lignes.append(
                (section, lot, tache, unite, qte, pu,
                 round(decalage + d * etendue, 3), round(min(1.0, decalage + f * etendue), 3))
            )
    return lignes


ROUTE = _route()

VRD = [
    ("Installation", "Installation", "Installation de chantier", "FORFAIT", 1, 6_000_000, 0.00, 0.05),
    ("Voirie", "Chaussées", "Terrassement des chaussées", "M3", 9_500, 3_200, 0.04, 0.30),
    ("Voirie", "Chaussées", "Couche de base", "M3", 3_800, 17_500, 0.25, 0.55),
    ("Voirie", "Chaussées", "Revêtement bicouche", "M2", 19_000, 4_800, 0.55, 0.80),
    ("Voirie", "Bordures", "Bordures T2", "ML", 6_400, 7_500, 0.45, 0.75),
    ("Assainissement", "Eaux usées", "Collecteur des eaux usées", "ML", 3_100, 28_000, 0.10, 0.45),
    ("Assainissement", "Eaux usées", "Regards de visite", "U", 85, 350_000, 0.15, 0.50),
    ("Assainissement", "Eaux pluviales", "Caniveaux des eaux pluviales", "ML", 4_200, 35_000, 0.20, 0.60),
    ("Réseaux divers", "Eau potable", "Adduction d'eau potable", "ML", 3_600, 14_000, 0.35, 0.70),
    ("Réseaux divers", "Électricité", "Réseau basse tension", "ML", 3_800, 16_000, 0.40, 0.80),
    ("Réseaux divers", "Électricité", "Candélabres d'éclairage public", "U", 120, 650_000, 0.70, 0.92),
    ("Espaces verts", "Plantations", "Engazonnement", "M2", 6_000, 1_800, 0.85, 0.98),
    ("Espaces verts", "Plantations", "Plantation d'arbres d'alignement", "U", 300, 25_000, 0.88, 1.00),
]

ENTREPOT = [
    ("Terrassements", "Plateforme", "Décapage et nivellement", "M2", 12_000, 1_500, 0.00, 0.10),
    ("Terrassements", "Plateforme", "Couche de forme compactée", "M3", 4_800, 9_000, 0.06, 0.18),
    ("Fondations", "Massifs", "Massifs en béton armé", "M3", 320, 195_000, 0.15, 0.28),
    ("Charpente métallique", "Structure", "Fabrication en atelier", "KG", 180_000, 1_350, 0.10, 0.40),
    ("Charpente métallique", "Structure", "Montage sur site", "KG", 180_000, 450, 0.35, 0.55),
    ("Couverture et bardage", "Enveloppe", "Couverture en bac acier", "M2", 8_500, 11_000, 0.52, 0.70),
    ("Couverture et bardage", "Enveloppe", "Bardage double peau", "M2", 4_200, 14_500, 0.55, 0.75),
    ("Dallage", "Dallage industriel", "Dallage fibré de 20 cm", "M2", 8_000, 21_000, 0.60, 0.85),
    ("Équipements", "Quais", "Niveleurs de quai", "U", 8, 6_500_000, 0.80, 0.95),
    ("Équipements", "Électricité", "Éclairage et distribution", "FORFAIT", 1, 85_000_000, 0.70, 0.97),
    ("Équipements", "Sécurité incendie", "Réseau de sprinklers", "FORFAIT", 1, 120_000_000, 0.72, 1.00),
]

GABARITS = {
    "BATIMENT": (["Phase", "Ouvrage", "Tâche"], BATIMENT),
    "ROUTE": (["Section", "Lot", "Tâche"], ROUTE),
    "VRD": (["Lot", "Ouvrage", "Tâche"], VRD),
    "ENTREPOT": (["Lot", "Ouvrage", "Tâche"], ENTREPOT),
}

# Les équipes de chaque gabarit : (nom, corps d'état, partenaire ou None, effectif, cases).
# L'équipe est posée sur chaque case qui porte l'un de ces intitulés, à n'importe quel niveau.
EQUIPES = {
    "BATIMENT": [
        ("Équipe gros œuvre", "Maçonnerie et béton armé", None, 7,
         ["Installation de chantier", "Gros œuvre", "VRD"]),
        ("Équipe électricité", "Électricité", "Diallo Électricité & Plomberie", 4, ["Électricité"]),
        ("Équipe plomberie", "Plomberie sanitaire", "Diallo Électricité & Plomberie", 3, ["Plomberie"]),
        ("Équipe finitions", "Revêtements et peinture", "Kouamé Bâtiment SARL", 6,
         ["Finitions", "Menuiseries"]),
    ],
    "ROUTE": [
        ("Équipe terrassement", "Terrassement", None, 6, ["Installation et études", "Terrassements"]),
        ("Équipe chaussée", "Chaussée", "Génie Routier du Centre", 7, ["Chaussée", "Signalisation"]),
        ("Équipe assainissement", "Ouvrages hydrauliques", "Bâtir Plus Sous-traitance", 5,
         ["Assainissement"]),
    ],
    "VRD": [
        ("Équipe voirie", "Voirie", None, 6, ["Installation", "Voirie", "Espaces verts"]),
        ("Équipe réseaux", "Réseaux humides et secs", "Bâtir Plus Sous-traitance", 6,
         ["Assainissement", "Réseaux divers"]),
    ],
    "ENTREPOT": [],
}

MATERIAUX = {
    "BATIMENT": [("Ciment CPJ 45", "t"), ("Sable", "m3"), ("Gravier 15/25", "m3"),
                 ("Fer à béton HA 10", "kg"), ("Agglos de 15", "u")],
    "ROUTE": [("Graveleux latéritique", "m3"), ("Gasoil", "l"), ("Bitume 80/100", "t"),
              ("Ciment CPJ 45", "t")],
    "VRD": [("Tuyaux PVC 200", "ml"), ("Ciment CPJ 45", "t"), ("Sable", "m3"),
            ("Câble 4x25 mm²", "ml")],
    "ENTREPOT": [],
}

PRENOMS = [
    "Koffi", "Yao", "Kouadio", "Konan", "Amani", "N'Guessan", "Ibrahim", "Moussa", "Seydou",
    "Adama", "Lassina", "Bakary", "Didier", "Hervé", "Serge", "Jean-Marc", "Rodrigue", "Patrice",
    "Aya", "Affoué", "Adjoua", "Mariam", "Fatou", "Awa", "Salimata", "Rokia", "Christelle",
    "Bintou", "Ange", "Emmanuel",
]
NOMS = [
    "Kouassi", "Kouamé", "Koné", "Traoré", "Coulibaly", "Ouattara", "Bamba", "Diabaté", "Touré",
    "Yao", "Konaté", "Diallo", "Sanogo", "Doumbia", "Gnamien", "Aka", "Tanoh", "Brou", "Kacou",
    "Assi", "Dosso", "Fofana", "Cissé", "Soro", "Silué", "Yeo", "Tra", "Zadi", "Gbagbo", "Béhi",
]
METIERS = {
    None: ["Maçon", "Ferrailleur", "Coffreur", "Manœuvre", "Conducteur d'engin", "Chauffeur",
           "Topographe", "Soudeur"],
    "Diallo Électricité & Plomberie": ["Électricien", "Plombier", "Aide électricien"],
    "Kouamé Bâtiment SARL": ["Carreleur", "Peintre", "Menuisier", "Enduiseur"],
    "Bâtir Plus Sous-traitance": ["Maçon", "Poseur de canalisations", "Manœuvre"],
    "Génie Routier du Centre": ["Conducteur d'engin", "Régleur", "Manœuvre", "Chauffeur"],
}


# ---------------------------------------------------------------------------
# Les chantiers : décalages en jours par rapport à aujourd'hui.
# ---------------------------------------------------------------------------
@dataclass
class Chantier:
    reference: str
    nom: str
    description: str
    type_projet: str
    gabarit: str
    client: str
    ville: str
    quartier: str
    debut: int
    fin: int
    echelle: float
    # Rythme réel rapporté au rythme prévu : 0,7 en retard. Un chantier « à l'heure » est un
    # peu en avance (1,1 et plus) : l'application juge en jours ouvrés et case par case, et une
    # seule feuille à plus de 5 points de retard fait passer le chantier EN_RETARD.
    rythme: float
    chef_projet: str
    conducteur: str
    redacteurs: list = field(default_factory=list)  # (email, rôle, intitulé du périmètre ou None)
    autres: list = field(default_factory=list)  # (email, rôle, fonction)
    maitre_oeuvre: str = ""
    arret_depuis: int | None = None  # chantier arrêté depuis N jours
    receptionne: bool = False
    jours_manquants: int = 0  # journaux non rédigés dans la fenêtre


CHANTIERS = [
    Chantier(
        "TEST-2026-001", "Villa duplex R+1 — Bingerville",
        "Construction d'une villa duplex de 6 pièces avec piscine et dépendances.",
        "BATIMENT_RESIDENTIEL", "BATIMENT", "SCI Les Palmiers", "Bingerville", "Cité Feh Kessé",
        -120, 90, 0.35, 1.15, "cp.kone@demo.ci", "ct.yao@demo.ci",
        redacteurs=[("cc.coulibaly@demo.ci", "CC", None)],
        autres=[("moa.palmiers@demo.ci", "MOA", ""), ("df.aka@demo.ci", "VI", "FINANCIER")],
        maitre_oeuvre="Cabinet Archi Concept",
    ),
    Chantier(
        "TEST-2026-002", "Immeuble R+4 — Marcory Zone 4",
        "Immeuble d'habitation de 16 appartements, R+4 sur sous-sol.",
        "BATIMENT_RESIDENTIEL", "BATIMENT", "Groupe Immobilier Ivoire", "Abidjan", "Marcory Zone 4",
        -200, 60, 1.6, 0.68, "cp.kone@demo.ci", "ct.ouattara@demo.ci",
        redacteurs=[("cc.traore@demo.ci", "CC", None)],
        autres=[("moe.kacou@demo.ci", "MOE", ""), ("qse.konan@demo.ci", "VI", "QHSE")],
        maitre_oeuvre="BET Ivoire Ingénierie", jours_manquants=3,
    ),
    Chantier(
        "TEST-2026-003", "Réhabilitation de la route Yamoussoukro - Attiégouakro (8 km)",
        "Reprise de la chaussée, des fossés et de la signalisation sur 8 km.",
        "TP_ROUTE", "ROUTE", "Ageroute — Direction régionale du Centre", "Yamoussoukro",
        "Axe Yamoussoukro - Attiégouakro",
        -90, 180, 1.0, 0.93, "cp.bamba@demo.ci", "ct.nguessan@demo.ci",
        redacteurs=[("cc.kouassi@demo.ci", "CC", "Section 1 — PK 0 à PK 4"),
                    ("it.soro@demo.ci", "IT", "Section 2 — PK 4 à PK 8")],
        autres=[("moe.kacou@demo.ci", "MOE", ""), ("df.aka@demo.ci", "VI", "FINANCIER")],
        maitre_oeuvre="BET Ivoire Ingénierie",
    ),
    Chantier(
        "TEST-2026-004", "Entrepôt logistique — Vridi",
        "Entrepôt de stockage de 8 000 m² à charpente métallique, avec 8 quais de chargement.",
        "INFRASTRUCTURE_INDUSTRIELLE", "ENTREPOT", "Port Logistique Services", "Abidjan",
        "Zone industrielle de Vridi",
        25, 300, 1.0, 0.0, "cp.bamba@demo.ci", "ct.yao@demo.ci",
        redacteurs=[("cc.diabate@demo.ci", "CC", None)],
    ),
    Chantier(
        "TEST-2026-005", "Groupe scolaire de 6 classes — Bouaké",
        "Bâtiment de 6 classes, bloc administratif et latrines.",
        "BATIMENT_COMMERCIAL", "BATIMENT", "Mairie de Bouaké", "Bouaké", "Quartier Air France 2",
        -240, 20, 0.6, 1.12, "cp.bamba@demo.ci", "ct.ouattara@demo.ci",
        redacteurs=[("cc.gnamien@demo.ci", "CC", None)],
        autres=[("vi.audit@demo.ci", "VI", "")],
    ),
    Chantier(
        "TEST-2026-006", "Clinique médicale — Cocody Riviera 3",
        "Clinique de 20 lits avec bloc opératoire, R+2.",
        "BATIMENT_COMMERCIAL", "BATIMENT", "Polyclinique Sainte Grâce", "Abidjan",
        "Cocody Riviera 3",
        -150, 120, 1.2, 0.9, "cp.kone@demo.ci", "ct.nguessan@demo.ci",
        redacteurs=[("cc.diabate@demo.ci", "CC", None)],
        maitre_oeuvre="Cabinet Archi Concept", arret_depuis=12,
    ),
    Chantier(
        "TEST-2026-007", "Résidence balnéaire — Assinie",
        "Quatre bungalows et un espace de restauration en bord de lagune.",
        "BATIMENT_RESIDENTIEL", "BATIMENT", "SCI Les Palmiers", "Assinie-Mafia", "Bord de lagune",
        -400, -60, 0.5, 1.05, "cp.kone@demo.ci", "ct.yao@demo.ci",
        redacteurs=[("cc.coulibaly@demo.ci", "CC", None)], receptionne=True,
    ),
    Chantier(
        "TEST-2026-008", "VRD du lotissement Les Cocotiers — Grand-Bassam",
        "Voirie, assainissement et réseaux d'un lotissement de 240 lots.",
        "VRD", "VRD", "Société Foncière du Littoral", "Grand-Bassam", "Mondoukou",
        -60, 120, 0.8, 0.75, "cp.bamba@demo.ci", "ct.nguessan@demo.ci",
        redacteurs=[("cc.traore@demo.ci", "CC", None)],
        autres=[("qse.konan@demo.ci", "VI", "QHSE")], jours_manquants=2,
    ),
]

COLLABORATEURS = [
    # (email, prénom, nom, code du rôle, téléphone)
    ("cp.kone@demo.ci", "Ibrahim", "Koné", "CP", "+2250701020301"),
    ("cp.bamba@demo.ci", "Mariam", "Bamba", "CP", "+2250701020302"),
    ("ct.yao@demo.ci", "Serge", "Yao", "CT", "+2250701020303"),
    ("ct.ouattara@demo.ci", "Aminata", "Ouattara", "CT", "+2250701020304"),
    ("ct.nguessan@demo.ci", "Paul", "N'Guessan", "CT", "+2250701020305"),
    ("cc.coulibaly@demo.ci", "Moussa", "Coulibaly", "CC", "+2250701020306"),
    ("cc.traore@demo.ci", "Fatou", "Traoré", "CC", "+2250701020307"),
    ("cc.kouassi@demo.ci", "Jean-Marc", "Kouassi", "CC", "+2250701020308"),
    ("cc.diabate@demo.ci", "Adama", "Diabaté", "CC", "+2250701020309"),
    ("cc.gnamien@demo.ci", "Hervé", "Gnamien", "CC", "+2250701020310"),
    ("it.soro@demo.ci", "Lassina", "Soro", "IT", "+2250701020311"),
    ("df.aka@demo.ci", "Christelle", "Aka", "DF", "+2250701020312"),
    ("qse.konan@demo.ci", "Rodrigue", "Konan", "QSE", "+2250701020313"),
    ("moe.kacou@demo.ci", "Ange", "Kacou", "MOE", "+2250701020314"),
    ("moa.palmiers@demo.ci", "Didier", "Assi", "MOA", "+2250701020315"),
    ("vi.audit@demo.ci", "Patrice", "Tanoh", "VI", "+2250701020316"),
]

TIERS = [
    # (raison sociale, rôles, ville, téléphone, email)
    ("SCI Les Palmiers", ["CLIENT_MOA"], "Abidjan", "+22527220001", "contact@palmiers-ci.com"),
    ("Groupe Immobilier Ivoire", ["CLIENT_MOA"], "Abidjan", "+22527220002", "direction@immo-ivoire.ci"),
    ("Ageroute — Direction régionale du Centre", ["CLIENT_MOA", "ADMINISTRATION"], "Yamoussoukro",
     "+22530640003", "centre@ageroute.ci"),
    ("Port Logistique Services", ["CLIENT_MOA"], "Abidjan", "+22521250004", "projets@pls.ci"),
    ("Mairie de Bouaké", ["CLIENT_MOA", "ADMINISTRATION"], "Bouaké", "+22531630005",
     "services.techniques@bouake.ci"),
    ("Polyclinique Sainte Grâce", ["CLIENT_MOA"], "Abidjan", "+22527220006", "direction@saintegrace.ci"),
    ("Société Foncière du Littoral", ["CLIENT_MOA"], "Grand-Bassam", "+22521300007", "contact@sfl.ci"),
    ("Cabinet Archi Concept", ["MAITRE_OEUVRE"], "Abidjan", "+22527220008", "agence@archiconcept.ci"),
    ("BET Ivoire Ingénierie", ["MAITRE_OEUVRE"], "Abidjan", "+22527220009", "bet@ivoire-ing.ci"),
    ("Bureau Veritas Côte d'Ivoire", ["BUREAU_CONTROLE"], "Abidjan", "+22527220010", "abidjan@bureauveritas.ci"),
    ("Diallo Électricité & Plomberie", ["TACHERON"], "Abidjan", "+2250500000020", "diallo.ep@gmail.com"),
    ("Kouamé Bâtiment SARL", ["TACHERON"], "Abidjan", "+2250500000010", "kouame.bat@gmail.com"),
    ("Bâtir Plus Sous-traitance", ["SOUS_TRAITANT"], "Abidjan", "+2250500000030", "contact@batirplus.ci"),
    ("Génie Routier du Centre", ["SOUS_TRAITANT"], "Yamoussoukro", "+2250500000040", "grc@grc-tp.ci"),
    ("Sococim Ciments CI", ["FOURNISSEUR"], "Abidjan", "+22521000030", "ventes@sococim.ci"),
    ("SOTICI Tuyaux & Aciers", ["FOURNISSEUR"], "Abidjan", "+22521000040", "commandes@sotici.ci"),
    ("Carrière du Banco", ["FOURNISSEUR"], "Abidjan", "+22521000050", "ventes@carrierebanco.ci"),
    ("Alu Fenêtres CI", ["FOURNISSEUR"], "Abidjan", "+22521000060", "devis@alufenetres.ci"),
    ("Locamat Engins", ["PRESTATAIRE"], "Abidjan", "+22521000070", "location@locamat.ci"),
]

BLOCAGES = [
    # (référence, titre, description, sévérité, intitulé de la case, suite donnée)
    ("TEST-2026-002", "Rupture de ciment chez le fournisseur",
     "Sococim annonce dix jours de délai sur le CPJ 45 ; le coulage de la dalle du R+3 est reporté.",
     "MAJEUR", "Planchers", "OUVERT"),
    ("TEST-2026-002", "Plans d'exécution de l'étage non visés",
     "Le BET n'a pas visé les plans de ferraillage de la dalle du R+4.",
     "CRITIQUE", "Dalle haute de l'étage", "PRIS_EN_CHARGE"),
    ("TEST-2026-001", "Retard de livraison des fenêtres",
     "Alu Fenêtres CI a livré 30 fenêtres sur 48.", "MINEUR", "Fenêtres en aluminium", "RESOLU"),
    ("TEST-2026-008", "Conflit foncier sur l'emprise de la voie 3",
     "Un riverain conteste l'emprise ; les travaux de la voie 3 sont à l'arrêt.",
     "CRITIQUE", "Chaussées", "OUVERT"),
    ("TEST-2026-008", "Réseau CIE non dévoyé",
     "La ligne aérienne traverse le tracé du collecteur ; dévoiement demandé à la CIE.",
     "MAJEUR", "Eaux usées", "PRIS_EN_CHARGE"),
    ("TEST-2026-003", "Panne du compacteur",
     "Le compacteur vibrant est immobilisé ; un engin de remplacement est attendu chez Locamat.",
     "MINEUR", "Terrassements", "RESOLU"),
]

FENETRE_JOURNAUX = 15  # jours ouvrés couverts par des journaux, jusqu'à aujourd'hui


# Rôles personnalisés dont le jeu a besoin. Ils existaient à la main dans l'ancienne base `demo` ;
# une base neuve ne les a pas, et le jeu doit se monter seul. Droits **effectifs** relevés le
# 07/11/2026 (`permissions_du_role`, lot 6) : `IT` rédige et valide ; `MOE` et `MOA` n'en avaient
# aucun. Leur donner ceux d'`IT` (lot 3) les faisait rédiger un journal par jour — deux fois plus
# de journaux que l'ancien modèle. Ils reçoivent la lecture seule : ils suivent, ne rédigent pas.
_PERMISSIONS_IT = {
    "chantier": ["chantier.lire", "chantier.rediger", "chantier.valider"],
    "pilotage": ["pilotage.lire", "pilotage.voir_montants"],
    "projets": [
        "projets.affecter_membres", "projets.changer_statut", "projets.creer", "projets.ecrire",
        "projets.gerer_equipes", "projets.lire", "projets.resilier_archiver",
        "projets.voir_montants",
    ],
    "tiers": ["tiers.ecrire", "tiers.lire"],
}
_PERMISSIONS_LECTURE = {
    "chantier": ["chantier.lire"],
    "pilotage": ["pilotage.lire"],
    "projets": ["projets.lire"],
}
ROLES_PERSONNALISES = {
    "IT": ("Ingénieur / Technicien", "Contrôle qualité, suivi des non-conformités et vérification des documents techniques", _PERMISSIONS_IT),
    "MOE": ("Maître d'Œuvre", "Supervision technique, coordination architecturale et validation des avancements", _PERMISSIONS_LECTURE),
    "MOA": ("Maître d'Ouvrage (Client)", "Suivi de l'avancement global du chantier et consultation des rapports d'activité", _PERMISSIONS_LECTURE),
}


def _dt(jour: date, heure: int, minute: int = 0) -> datetime:
    return datetime.combine(jour, time(heure, minute), tzinfo=FUSEAU)


def _quantite_montant(unite, qte, pu, echelle) -> tuple[int, int]:
    """Quantité de la feuille et montant en FCFA, mis à l'échelle du chantier."""
    if unite == "FORFAIT":
        return 1, round(pu * echelle)
    quantite = max(1, round(qte * echelle))
    return quantite, quantite * pu


def adresse_entreprise(email: str, slug: str) -> str:
    """`cp.kone@demo.ci` dans l'entreprise `beta` : `cp.kone@beta.ci`."""
    return f"{email.split('@', 1)[0]}@{slug}.ci"


def _q(valeur) -> Decimal:
    return Decimal(str(valeur)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = "Peuple une entreprise de développement avec huit chantiers de test et leur historique."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entreprise", dest="entreprise", default="demo",
            help="Slug de l'entreprise.",
        )
        parser.add_argument("--motdepasse", default="Demo1234!")
        parser.add_argument(
            "--reinitialiser",
            action="store_true",
            help="Supprime physiquement les chantiers TEST-2026-* avant de les recréer.",
        )
        parser.add_argument(
            "--chantiers",
            nargs="+",
            metavar="REFERENCE",
            help="Ne crée que ces chantiers (TEST-2026-002…) — la suite d'étanchéité n'a pas "
            "besoin des huit.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG:
            raise CommandError("Commande de développement : refusée quand DEBUG est faux.")

        from apps.core.contexte import contexte_entreprise
        from apps.entreprises.models import Entreprise

        slug = options["entreprise"]
        entreprise = Entreprise.objects.filter(slug=slug).first()
        if entreprise is None:
            raise CommandError(
                f"Aucune entreprise « {slug} ». Lancez d'abord `creer_entreprise_demo`."
            )

        self.slug = slug
        self.alea = random.Random(GRAINE)
        self.aujourdhui = timezone.localdate()
        with contexte_entreprise(entreprise):
            from apps.accounts.services.roles import initialiser_roles_par_defaut

            initialiser_roles_par_defaut()
            if options["reinitialiser"]:
                self._reinitialiser()
            self._roles_personnalises()
            self.utilisateurs = self._collaborateurs(options["motdepasse"])
            self.tiers = self._tiers()
            self.registre = self._registre()
            retenus = options.get("chantiers")
            inconnus = set(retenus or []) - {c.reference for c in CHANTIERS}
            if inconnus:
                raise CommandError(f"Chantiers inconnus : {', '.join(sorted(inconnus))}")
            for chantier in CHANTIERS:
                if retenus is None or chantier.reference in retenus:
                    self._chantier(chantier)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Jeu de test prêt."))
        self.stdout.write(
            f"  Connexion : http://localhost:3000 — comptes *@{slug}.ci, mot de passe "
            f"« {options['motdepasse']} » (cp.kone, ct.yao, cc.coulibaly…)"
        )

    def _reinitialiser(self) -> None:
        """Supprime les chantiers de test, enfants d'abord : leurs clés sont restrictives."""
        from apps.chantier.models import AlerteJournal, Blocage, JournalChantier, RapportJournalier
        from apps.chantier.models.relance import RelanceJournal
        from apps.chantier.models.synthese import SynthesePeriodique
        from apps.projets.models import (
            AffectationEquipeElement,
            AffectationProjet,
            AlerteRetard,
            ArretChantier,
            Element,
            EquipeChantier,
            MembreEquipeChantier,
            MiseAJourInline,
            NiveauProjet,
            PointAvancement,
            Projet,
            SanteProjetSnapshot,
        )

        projets = list(Projet.tous_objets.filter(reference__startswith="TEST-2026-"))
        if not projets:
            return
        with transaction.atomic():
            for modele, chemin in (
                (AlerteJournal, "journal__rapport__projet"),
                (JournalChantier, "rapport__projet"),
                (RelanceJournal, "projet"),
                (SynthesePeriodique, "projet"),
                (RapportJournalier, "projet"),
                (Blocage, "projet"),
                (AffectationEquipeElement, "equipe__projet"),
                (MembreEquipeChantier, "equipe__projet"),
                (EquipeChantier, "projet"),
                (MiseAJourInline, "element__projet"),
                (AlerteRetard, "projet"),
                (ArretChantier, "projet"),
                (PointAvancement, "projet"),
                (SanteProjetSnapshot, "projet"),
                (AffectationProjet, "projet"),
            ):
                if any(f.name == chemin.split("__")[0] for f in modele._meta.get_fields()):
                    modele.tous_objets.filter(**{f"{chemin}__in": projets}).delete()
            for projet in projets:
                profondeurs = Element.tous_objets.filter(projet=projet).values_list(
                    "profondeur", flat=True
                )
                for profondeur in sorted(set(profondeurs), reverse=True):
                    Element.tous_objets.filter(projet=projet, profondeur=profondeur).delete()
                NiveauProjet.tous_objets.filter(projet=projet).delete()
            Projet.tous_objets.filter(pk__in=[p.pk for p in projets]).delete()
        self.stdout.write(self.style.WARNING(f"  {len(projets)} chantiers de test supprimés"))

    # ------------------------------------------------------------------ référentiels
    def _roles_personnalises(self) -> None:
        from apps.accounts.models import Role
        from apps.accounts.services.roles import creer_role

        for code, (libelle, description, permissions) in ROLES_PERSONNALISES.items():
            if Role.objects.filter(code=code, supprime_le__isnull=True).exists():
                continue
            creer_role(
                code=code,
                libelle=libelle,
                description=description,
                permissions_modules=permissions,
                portee="ENTREPRISE",
            )
            self.stdout.write(f"  Rôle personnalisé créé : {code}")

    def _collaborateurs(self, mot_de_passe) -> dict:
        from apps.accounts.models import Role, Utilisateur
        from apps.core.enums import StatutUtilisateur

        resultat = {}
        for cle, prenom, nom, code, telephone in COLLABORATEURS:
            # L'adresse est unique sur toute la plateforme (D9) : chaque entreprise peuplée a son
            # domaine, `@demo.ci` pour `demo`, `@beta.ci` pour `beta`. Les gabarits gardent
            # `@demo.ci` comme clé.
            email = adresse_entreprise(cle, self.slug)
            utilisateur = Utilisateur.objects.filter(email=email).first()
            if utilisateur is None:
                role = Role.objects.filter(code=code, supprime_le__isnull=True).first()
                if role is None:
                    raise CommandError(f"Rôle « {code} » absent de l'entreprise.")
                utilisateur = Utilisateur.objects.create_user(
                    email=email,
                    password=mot_de_passe,
                    nom=nom,
                    prenom=prenom,
                    telephone=telephone,
                    role=role,
                    role_global=code,
                    statut=StatutUtilisateur.ACTIF,
                )
                self.stdout.write(f"  Collaborateur créé : {email} ({code})")
            resultat[cle] = utilisateur
        self.dg = Utilisateur.objects.filter(is_owner=True).first() or resultat["cp.kone@demo.ci"]
        return resultat

    def _tiers(self) -> dict:
        from apps.core.enums import TypeTiers
        from apps.tiers.models import RoleTiers, Tiers

        resultat = {}
        for raison, roles, ville, telephone, email in TIERS:
            tiers = Tiers.objects.filter(raison_sociale=raison).first()
            if tiers is None:
                tiers = Tiers.objects.create(
                    raison_sociale=raison,
                    type_tiers=TypeTiers.ENTREPRISE,
                    telephone=telephone,
                    email=email,
                    ville=ville,
                )
            for role in roles:
                RoleTiers.objects.get_or_create(tiers=tiers, role=role)
            resultat[raison] = tiers
        self.stdout.write(f"  Tiers : {len(resultat)}")
        return resultat

    def _registre(self) -> dict:
        """Le registre de main-d'œuvre, par entreprise (None : la nôtre)."""
        from apps.projets.models import PersonneMainOeuvre
        from apps.projets.services.main_oeuvre import creer_personne

        effectifs = {None: 45, "Diallo Électricité & Plomberie": 14, "Kouamé Bâtiment SARL": 16,
                     "Bâtir Plus Sous-traitance": 18, "Génie Routier du Centre": 14}
        alea = random.Random(GRAINE + 1)
        paires = [(p, n) for p in PRENOMS for n in NOMS]
        alea.shuffle(paires)
        registre: dict = {}
        crees = 0
        for partenaire_nom, effectif in effectifs.items():
            partenaire = self.tiers[partenaire_nom] if partenaire_nom else None
            # Ordre de création : relancé sur un registre existant, le jeu recompose les mêmes
            # équipes qu'à la première passe. Sans ordre, PostgreSQL rend les lignes dans
            # l'ordre qu'il veut, et les journaux changent (lot 6, TEST-2026-006).
            existantes = list(
                PersonneMainOeuvre.objects.filter(
                    entreprise_partenaire=partenaire, utilisateur__isnull=True, est_actif=True
                ).order_by("cree_le", "id")
            )
            while len(existantes) < effectif:
                prenom, nom = paires.pop()
                if PersonneMainOeuvre.objects.filter(
                    nom=nom, prenom=prenom, entreprise_partenaire=partenaire
                ).exists():
                    continue
                existantes.append(
                    creer_personne(
                        nom=nom,
                        prenom=prenom,
                        telephone=f"+22507{alea.randint(10_000_000, 99_999_999)}",
                        entreprise_partenaire=partenaire,
                        metier=alea.choice(METIERS[partenaire_nom]),
                        createur=self.dg,
                    )
                )
                crees += 1
            registre[partenaire_nom] = existantes
        self.curseurs = dict.fromkeys(registre, 0)
        self.stdout.write(f"  Registre de main-d'œuvre : {crees} personnes créées")
        return registre

    def _personnes(self, partenaire_nom, nombre) -> list:
        """Les suivantes du registre d'une entreprise, en tournant quand il est épuisé."""
        pool = self.registre[partenaire_nom]
        choisies = []
        for _ in range(min(nombre, len(pool))):
            choisies.append(pool[self.curseurs[partenaire_nom] % len(pool)])
            self.curseurs[partenaire_nom] += 1
        return choisies

    # ------------------------------------------------------------------ un chantier
    def _chantier(self, c: Chantier) -> None:
        from apps.projets.models import Projet

        if Projet.objects.filter(reference=c.reference).exists():
            self.stdout.write(f"  {c.reference} déjà présent — laissé tel quel")
            return
        self.stdout.write(self.style.MIGRATE_HEADING(f"  {c.reference} — {c.nom}"))
        # Un chantier entier dans une transaction : un échec ne laisse rien à moitié créé.
        with transaction.atomic():
            self._creer_chantier(c)

    def _creer_chantier(self, c: Chantier) -> None:
        from apps.core.enums import StatutProjet
        from apps.projets.models import Projet

        debut = self.aujourdhui + timedelta(days=c.debut)
        fin = self.aujourdhui + timedelta(days=c.fin)
        niveaux, lignes = GABARITS[c.gabarit]
        montant_total = sum(
            _quantite_montant(unite, q, pu, c.echelle)[1] for _a, _b, _c, unite, q, pu, _d, _f in lignes
        )

        projet = Projet.objects.create(
            reference=c.reference,
            nom=c.nom,
            description=c.description,
            type_projet=c.type_projet,
            client=self.tiers[c.client],
            maitre_ouvrage=c.client,
            maitre_oeuvre=c.maitre_oeuvre,
            ville=c.ville,
            quartier=c.quartier,
            budget_initial_montant=int(montant_total * 1.08) * 100,
            date_debut_prevue=debut,
            date_fin_prevue=fin,
            date_debut_reelle=debut if c.debut <= 0 else None,
            chef_projet=self.utilisateurs[c.chef_projet],
            conducteur_travaux=self.utilisateurs[c.conducteur],
            statut=StatutProjet.EN_COURS if c.debut <= 0 else StatutProjet.EN_ATTENTE,
            cree_par=self.dg,
        )
        self._arbre(projet, c, niveaux, lignes, debut, fin)
        self._affectations(projet, c, debut)
        equipes = self._equipes(projet, c, debut)

        # Le chantier a été ouvert sur la plateforme peu avant la fenêtre des journaux : ce qui
        # précède est repris d'un coup (la reprise), ce qui suit est saisi au jour le jour.
        jours = self._jours_ouvres_fenetre()
        ouverture = max(debut, jours[0] - timedelta(days=3))
        if c.debut > 0:
            ouverture = self.aujourdhui - timedelta(days=5)
        if c.receptionne:
            ouverture = debut - timedelta(days=7)
        Projet.objects.filter(pk=projet.pk).update(cree_le=_dt(ouverture, 9))
        projet.refresh_from_db()

        if c.debut <= 0:
            self._simuler(projet, c, debut, fin, jours, equipes)
        self._finaliser(projet, c, debut, fin)

    def _arbre(self, projet, c: Chantier, niveaux, lignes, debut, fin) -> None:
        from apps.projets.services.tableau_demarrage import appliquer_tableau

        duree = (fin - debut).days
        tableau = []
        for n1, n2, feuille, unite, qte, pu, f_debut, f_fin in lignes:
            quantite, montant = _quantite_montant(unite, qte, pu, c.echelle)
            tableau.append(
                {
                    "cellules": [n1, n2, feuille],
                    "unite": unite,
                    "quantite": str(quantite),
                    "montant": str(montant * 100),
                    "date_debut": (debut + timedelta(days=round(f_debut * duree))).isoformat(),
                    "date_fin": (debut + timedelta(days=max(1, round(f_fin * duree)))).isoformat(),
                }
            )
        appliquer_tableau(
            projet,
            niveaux=[{"libelle": libelle} for libelle in niveaux],
            lignes=tableau,
            confirmer_avertissements=True,
            auteur=self.utilisateurs[c.chef_projet],
        )
        # Les ouvrages sous-traités ont leur titulaire.
        from apps.projets.models import Element

        for _nom, _corps, partenaire, _n, cases in EQUIPES[c.gabarit]:
            if partenaire:
                Element.objects.filter(projet=projet, libelle__in=cases).update(
                    titulaire=self.tiers[partenaire]
                )
        self.stdout.write(f"    arbre : {Element.objects.filter(projet=projet).count()} cases")

    def _affectations(self, projet, c: Chantier, debut) -> None:
        from apps.projets.models import Element
        from apps.projets.services.affectations import affecter_collaborateur_projet

        depuis = min(debut, self.aujourdhui) - timedelta(days=10)
        affecter = [(c.chef_projet, "CP", None, ""), (c.conducteur, "CT", None, "")]
        affecter += [(email, role, perimetre, "") for email, role, perimetre in c.redacteurs]
        affecter += [(email, role, None, fonction) for email, role, fonction in c.autres]
        for email, role, perimetre, fonction in affecter:
            ids = None
            if perimetre:
                ids = [str(Element.objects.get(projet=projet, libelle=perimetre).pk)]
            affecter_collaborateur_projet(
                projet=projet,
                utilisateur=self.utilisateurs[email],
                role_projet=role,
                date_debut=depuis,
                fonction_membre=fonction,
                perimetres_ids=ids,
                modifie_par=self.utilisateurs[c.chef_projet],
            )

    def _equipes(self, projet, c: Chantier, debut) -> dict:
        """Crée les équipes ; rend, par identifiant de case, l'équipe qui y travaille."""
        from apps.projets.models import Element
        from apps.projets.services.equipes import affecter_equipe, creer_equipe

        arrivee = max(debut, self.aujourdhui - timedelta(days=400))
        depart = (debut + timedelta(days=(c.fin - c.debut))) if c.receptionne else None
        par_case = {}
        for nom, corps, partenaire, effectif, cases in EQUIPES[c.gabarit]:
            personnes = self._personnes(partenaire, effectif)
            membres = [
                {
                    "personne": p,
                    "fonction": "CHEF_EQUIPE" if i == 0 else self.alea.choice(
                        ["OUVRIER_QUALIFIE", "OUVRIER", "OUVRIER", "MANOEUVRE", "APPRENTI"]
                    ),
                    "est_chef": i == 0,
                    "date_arrivee": arrivee,
                    # Le chef reste jusqu'au bout : un chef d'équipe n'a pas de date de départ.
                    "date_depart": None if i == 0 else depart,
                }
                for i, p in enumerate(personnes)
            ]
            equipe, _ = creer_equipe(
                projet,
                nom=nom,
                corps_etat=corps,
                entreprise_partenaire=self.tiers[partenaire] if partenaire else None,
                membres=membres,
                createur=self.utilisateurs[c.conducteur],
            )
            for element in Element.objects.filter(projet=projet, libelle__in=cases):
                affecter_equipe(equipe, element, createur=self.utilisateurs[c.conducteur])
                par_case[element.pk] = equipe
        return par_case

    # ------------------------------------------------------------------ l'historique
    def _jours_ouvres_fenetre(self) -> list[date]:
        from apps.chantier.services.journal import jours_saisissables_ouvres

        return jours_saisissables_ouvres(self.aujourdhui, nb=FENETRE_JOURNAUX)

    def _fraction(self, feuille, jour: date, c: Chantier, debut: date) -> float:
        """Part réalisée d'une feuille à `jour` : le planning, parcouru au rythme du chantier."""
        if c.arret_depuis is not None:
            jour = min(jour, self.aujourdhui - timedelta(days=c.arret_depuis))
        effectif = debut + timedelta(days=(jour - debut).days * c.rythme)
        d, f = feuille.date_debut_prevue, feuille.date_fin_prevue
        if effectif <= d:
            return 0.0
        if effectif >= f:
            return 1.0
        return (effectif - d).days / max(1, (f - d).days)

    def _simuler(self, projet, c: Chantier, debut, fin, jours, equipes) -> None:
        from apps.projets.selectors.arbre import charger_arbre

        arbre = charger_arbre(projet)
        feuilles = [e for e in arbre.elements if arbre.est_feuille(e)]
        parents = {e.pk: e for e in arbre.elements}

        # 1. La reprise, semaine par semaine, jusqu'à l'ouverture des journaux.
        bascule = jours[0] if not c.receptionne else self.aujourdhui + timedelta(days=1)
        semaine = debut + timedelta(days=7)
        while semaine < bascule:
            self._poser_quantites(feuilles, semaine, c, debut)
            self._releve(projet, semaine)
            semaine += timedelta(days=7)
        self._poser_quantites(feuilles, bascule - timedelta(days=1), c, debut)
        self._releve(projet, bascule - timedelta(days=1))
        if c.receptionne:
            return

        # 2. Les journaux, jour ouvré après jour ouvré.
        manquants = set(self.alea.sample(jours[:-4], c.jours_manquants)) if c.jours_manquants else set()
        rejete = jours[-6] if c.reference == "TEST-2026-002" else None
        for jour in jours:
            if c.arret_depuis is not None and jour >= self.aujourdhui - timedelta(days=c.arret_depuis):
                break
            if jour in manquants:
                continue
            rang = len(jours) - 1 - jours.index(jour)  # 0 : aujourd'hui
            statut = "APPROUVE"
            if rang == 0:
                statut = "BROUILLON"
            elif rang == 1:
                statut = "SOUMIS"
            if jour == rejete:
                statut = "REJETE"
            for titulaire in self._redacteurs(projet):
                self._journal(projet, c, jour, statut, titulaire, feuilles, parents, equipes, debut)
            self._releve(projet, jour)
        self.stdout.write(f"    avancement réel : {projet.avancement_reel} %")

    def _poser_quantites(self, feuilles, jour, c: Chantier, debut) -> None:
        """La reprise : la quantité réalisée de chaque feuille, d'après le planning."""
        from apps.projets.models import Element

        a_jour = []
        for f in feuilles:
            fraction = self._fraction(f, jour, c, debut)
            quantite = _q(Decimal(str(f.quantite_prevue)) * Decimal(str(fraction)))
            if quantite != f.quantite_realisee:
                f.quantite_realisee = quantite
                if quantite > 0 and f.date_debut_reelle is None:
                    f.date_debut_reelle = min(jour, f.date_debut_prevue + timedelta(days=3))
                if fraction >= 1.0 and f.date_fin_reelle is None:
                    f.date_fin_reelle = jour
                    f.cloture = True
                    f.cloture_le = _dt(jour, 17)
                a_jour.append(f)
        Element.objects.bulk_update(
            a_jour,
            ["quantite_realisee", "date_debut_reelle", "date_fin_reelle", "cloture", "cloture_le"],
        )

    def _releve(self, projet, jour) -> None:
        from apps.projets.services.avancement import recalculer_avancements_projet
        from apps.projets.services.courbe import enregistrer_releve

        recalculer_avancements_projet(projet)
        enregistrer_releve(projet, jour=jour)

    def _redacteurs(self, projet):
        from apps.chantier.services.fonctions import REDIGER, titulaires

        return titulaires(projet, REDIGER)

    def _journal(self, projet, c, jour, statut, titulaire, feuilles, parents, equipes, debut):
        from apps.chantier.models import JournalChantier, RapportJournalier
        from apps.chantier.selectors.journal import contexte_projet
        from apps.chantier.services import signatures

        auteur = titulaire.utilisateur
        chemins = titulaire.chemins

        def dans_perimetre(f):
            return not chemins or any(f.chemin.startswith(ch) for ch in chemins)

        meteo = self.alea.choices(
            ["ENSOLEILLE", "NUAGEUX", "PLUIE", "ORAGE"], weights=[55, 25, 15, 5]
        )[0]
        apres_midi = meteo if self.alea.random() < 0.6 else self.alea.choice(["ENSOLEILLE", "NUAGEUX"])
        conditions = {"ENSOLEILLE": "FAVORABLES", "NUAGEUX": "FAVORABLES",
                      "PLUIE": "DIFFICILES", "ORAGE": "DIFFICILES"}[meteo]
        rendement = {"ENSOLEILLE": 1.0, "NUAGEUX": 1.0, "PLUIE": 0.6, "ORAGE": 0.3}[meteo]
        veille = jour - timedelta(days=1)

        activites, lots, equipes_jour = [], {}, {}
        for f in feuilles:
            if not dans_perimetre(f):
                continue
            cible = Decimal(str(f.quantite_prevue)) * Decimal(str(self._fraction(f, jour, c, debut)))
            avant = Decimal(str(self._fraction(f, veille, c, debut))) * Decimal(str(f.quantite_prevue))
            # Le retard pris les jours précédents (pluie, absence) se rattrape en partie.
            ecart = max(Decimal("0"), avant - Decimal(str(f.quantite_realisee or 0)))
            quantite = _q((cible - avant) * Decimal(str(rendement)) + ecart * Decimal("0.8"))
            reste = Decimal(str(f.quantite_prevue)) - Decimal(str(f.quantite_realisee or 0))
            quantite = min(quantite, _q(max(Decimal("0"), reste)))
            if quantite <= 0:
                continue
            equipe = self._equipe_de(f, parents, equipes)
            activites.append(
                {
                    "activite_id": str(f.pk),
                    "equipe_ids": [str(equipe.pk)] if equipe else [],
                    "quantite_jour": float(quantite),
                    "pourcentage_jour": None,
                    "jalon_atteint": False,
                    "localisation": "",
                    "observation": "",
                }
            )
            if f.parent_id:
                lots[str(f.parent_id)] = {"lot_id": str(f.parent_id), "observation": ""}
            if equipe:
                equipes_jour[equipe.pk] = equipe

        equipes_saisie = []
        for equipe in equipes_jour.values():
            membres = [m.personne_id for m in equipe.membres.filter(date_depart__isnull=True)]
            presents = [str(p) for p in membres if self.alea.random() < 0.9]
            equipes_saisie.append(
                {"equipe_id": str(equipe.pk), "presents": presents, "heures": 8.0,
                 "qualite": "", "retards": [], "observation": ""}
            )
        materiaux = [
            {"designation": nom, "unite": unite,
             "quantite_consommee": float(self.alea.choice([2, 5, 8, 10, 15, 20, 40]))}
            for nom, unite in self.alea.sample(MATERIAUX[c.gabarit], k=min(2, len(MATERIAUX[c.gabarit])))
        ] if activites else []
        note = self.alea.choice([
            "Travaux conformes au planning de la semaine.",
            "Rien à signaler.",
            "Réception des matériaux en matinée, contrôle de conformité effectué.",
            "Visite du maître d'œuvre ; observations notées sur le cahier de chantier.",
            "Réunion de chantier hebdomadaire tenue à 10 h.",
        ])
        if meteo in ("PLUIE", "ORAGE"):
            note = "Pluie en cours de journée : production réduite, coulages reportés."
        saisie = {
            "date": jour.isoformat(),
            "projet_id": str(projet.pk),
            "arret": None,
            "meteo": {"matin": meteo, "apres_midi": apres_midi, "conditions": conditions},
            "heure_debut": "07:30",
            "heure_fin": "17:00",
            "equipes": equipes_saisie,
            "activites": activites,
            "lots_travailles": list(lots.values()),
            "materiaux": materiaux,
            "livraisons": [],
            "equipements": [],
            "blocages": [],
            "incidents": [],
            "besoins": [],
            "previsions": [],
            "photos": [],
            "pieces_jointes": [],
            "note_redacteur": note,
        }
        effectif = sum(len(e["presents"]) for e in equipes_saisie)

        rapport = RapportJournalier.objects.create(
            projet=projet,
            date_rapport=jour,
            auteur=auteur,
            cree_par=auteur,
            statut="BROUILLON",
            meteo=meteo,
            effectif_present=effectif,
            observations=note,
            blocages_critiques=0,
        )
        journal = JournalChantier.objects.create(
            rapport=rapport, saisie=saisie, perimetre_ids=list(titulaire.perimetre_ids),
            cree_par=auteur,
        )
        RapportJournalier.objects.filter(pk=rapport.pk).update(cree_le=_dt(jour, 16, 30))
        if statut == "BROUILLON":
            return

        journal.photographie = contexte_projet(projet, jour, chemins=chemins, auteur=auteur)
        signatures.figer_signataires(journal)
        soumis_le = _dt(jour, 17, 30)
        champs_rapport = {"statut": "SOUMIS", "soumis_le": soumis_le}
        if statut in ("APPROUVE", "REJETE"):
            from apps.accounts.models import Utilisateur

            attendus = journal.signataires_attendus or {}
            valideurs = list(Utilisateur.objects.filter(pk__in=attendus.get("VALIDATION", [])))
            approbateurs = list(Utilisateur.objects.filter(pk__in=attendus.get("APPROBATION", [])))
            signe_ct = _dt(jour + timedelta(days=1), 9)
            signe_cp = _dt(jour + timedelta(days=1), 11)
            journal.signatures = [
                {"etape": "VALIDATION", "utilisateur_id": str(u.pk), "nom": f"{u.prenom} {u.nom}",
                 "signe_le": signe_ct.isoformat(), "commentaire": ""}
                for u in valideurs
            ]
            journal.valide_ct_par = valideurs[-1] if valideurs else None
            journal.valide_ct_le = signe_ct
            if statut == "APPROUVE" and approbateurs:
                journal.signatures += [
                    {"etape": "APPROBATION", "utilisateur_id": str(u.pk),
                     "nom": f"{u.prenom} {u.nom}", "signe_le": signe_cp.isoformat(),
                     "commentaire": ""}
                    for u in approbateurs
                ]
                champs_rapport.update(statut="APPROUVE", valide_par=approbateurs[-1], valide_le=signe_cp)
            elif statut == "REJETE":
                champs_rapport.update(
                    statut="REJETE",
                    valide_par=approbateurs[-1] if approbateurs else None,
                    valide_le=signe_cp,
                    commentaire_validation=(
                        "Les quantités de maçonnerie déclarées dépassent ce qui a été constaté "
                        "sur place : merci de les reprendre après métré contradictoire."
                    ),
                )
        journal.save()
        RapportJournalier.objects.filter(pk=rapport.pk).update(**champs_rapport)

        if champs_rapport["statut"] == "APPROUVE":
            self._synchroniser(rapport.pk, activites, jour, {f.pk: f for f in feuilles})

    def _equipe_de(self, feuille, parents, equipes):
        element = feuille
        while element is not None:
            if element.pk in equipes:
                return equipes[element.pk]
            element = parents.get(element.parent_id)
        return None

    def _synchroniser(self, rapport_id, activites, jour, feuilles) -> None:
        """Ce que fait `synchroniser_rapport_approuve`, sans évaluer statut et santé en cours
        de route — ils le sont à la fin, par rapport à aujourd'hui."""
        from uuid import UUID

        from apps.chantier.models import RapportJournalier

        for ligne in activites:
            feuille = feuilles[UUID(ligne["activite_id"])]
            feuille.quantite_realisee = (feuille.quantite_realisee or Decimal("0")) + _q(
                ligne["quantite_jour"]
            )
            champs = ["quantite_realisee", "modifie_le"]
            if feuille.date_debut_reelle is None:
                feuille.date_debut_reelle = jour
                champs.append("date_debut_reelle")
            feuille.save(update_fields=champs)
        RapportJournalier.objects.filter(pk=rapport_id).update(f3_sync_done=True)

    # ------------------------------------------------------------------ la fin
    def _finaliser(self, projet, c: Chantier, debut, fin) -> None:
        from apps.core.enums import StatutProjet
        from apps.projets.models import Projet
        from apps.projets.services.arret_chantier import declarer_arret_chantier
        from apps.projets.services.avancement import recalculer_apres_quantites

        self._blocages(projet)
        if c.arret_depuis is not None:
            declarer_arret_chantier(
                projet=projet,
                date_debut=self.aujourdhui - timedelta(days=c.arret_depuis),
                motif="Suspension demandée par le maître d'ouvrage dans l'attente du permis "
                "de construire modificatif.",
                auteur=self.utilisateurs[c.chef_projet],
            )
        recalculer_apres_quantites([], projet=projet, declencheur_type="JEU_DE_TEST")
        if c.arret_depuis is not None:
            Projet.objects.filter(pk=projet.pk).update(statut=StatutProjet.SUSPENDU)
        if c.receptionne:
            Projet.objects.filter(pk=projet.pk).update(
                statut=StatutProjet.RECEPTIONNE, date_fin_reelle=fin - timedelta(days=4)
            )
        projet.refresh_from_db()
        self.stdout.write(
            f"    statut : {projet.statut} — avancement {projet.avancement_reel} % — "
            f"santé {projet.indice_sante if projet.indice_sante is not None else '—'}"
        )

    def _blocages(self, projet) -> None:
        from apps.chantier.models import Blocage
        from apps.chantier.services.blocage import (
            creer_blocage,
            prendre_en_charge_blocage,
            resoudre_blocage,
        )
        from apps.projets.models import Element

        crees = 0
        for reference, titre, description, severite, case, suite in BLOCAGES:
            if reference != projet.reference or Blocage.objects.filter(
                projet=projet, titre=titre
            ).exists():
                continue
            chantier = next(c for c in CHANTIERS if c.reference == reference)
            cc = self.utilisateurs[chantier.redacteurs[0][0]]
            ct = self.utilisateurs[chantier.conducteur]
            blocage = creer_blocage(
                projet=projet,
                titre=titre,
                description=description,
                severite=severite,
                auteur=cc,
                element=Element.objects.filter(projet=projet, libelle=case).first(),
            )
            ouvert = self.aujourdhui - timedelta(days=self.alea.randint(3, 12))
            Blocage.objects.filter(pk=blocage.pk).update(ouvert_le=_dt(ouvert, 10))
            blocage.refresh_from_db()
            if suite in ("PRIS_EN_CHARGE", "RESOLU"):
                prendre_en_charge_blocage(blocage=blocage, utilisateur=ct)
            if suite == "RESOLU":
                resoudre_blocage(
                    blocage=blocage, utilisateur=ct,
                    commentaire_resolution="Levé : solution mise en œuvre et vérifiée sur place.",
                )
            crees += 1
        if crees:
            self.stdout.write(f"    blocages : {crees}")
