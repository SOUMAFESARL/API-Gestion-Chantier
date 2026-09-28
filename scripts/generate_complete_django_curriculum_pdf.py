"""Générateur du Manuel Complet d'Apprentissage Actif : Django & API Backend (De Zéro à l'Excellence).

Ce script produit un ouvrage pédagogique exhaustif de 20 pages au format PDF,
conçu selon les 8 principes de 'How Learning Works' (Lovett et al., 2023)
et les 4 piliers du 'Deep Reasoning Engine' (Kahneman, Minto, Pólya, Meadows).
Il intègre l'ensemble des transitions pas-à-pas niveau entreprise et explicite
systématiquement chaque sigle lors de sa première utilisation.
"""

import sys
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Preformatted,
    HRFlowable,
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Canvas à deux passes pour insérer dynamiquement les en-têtes et les numéros de page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            # Pas d'en-tête/pied sur la page de couverture
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#475569"))

        # En-tête courant
        self.drawString(
            36,
            A4[1] - 28,
            "MANUEL D'APPRENTISSAGE ACTIF : DJANGO & API BACKEND (DE ZÉRO À L'EXCELLENCE)",
        )
        self.setFont("Helvetica", 8)
        self.drawRightString(A4[0] - 36, A4[1] - 28, "SOUMAFE SARL • CCD DIGITAL")

        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(36, A4[1] - 32, A4[0] - 36, A4[1] - 32)

        # Pied de page courant
        self.line(36, 36, A4[0] - 36, 36)
        self.setFont("Helvetica", 8)
        self.drawString(
            36,
            24,
            "Sciences Cognitives (How Learning Works 2023) & Deep Reasoning Engine (Kahneman, Minto, Pólya, Meadows)",
        )
        page_str = f"Page {self._pageNumber} sur {page_count}"
        self.drawRightString(A4[0] - 36, 24, page_str)

        self.restoreState()


def get_curriculum_styles():
    """Initialise le dictionnaire typographique complet."""
    base_styles = getSampleStyleSheet()

    styles = {
        "CoverSuper": ParagraphStyle(
            "CoverSuper",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0284C7"),
            spaceAfter=6,
        ),
        "CoverMeta": ParagraphStyle(
            "CoverMeta",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#0369A1"),
        ),
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=26,
            textColor=colors.HexColor("#0F172A"),
            alignment=0,
            spaceAfter=8,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor("#334155"),
            spaceAfter=12,
        ),
        "PartHeader": ParagraphStyle(
            "PartHeader",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "ChapterHeader": ParagraphStyle(
            "ChapterHeader",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=4,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "SectionHeader": ParagraphStyle(
            "SectionHeader",
            parent=base_styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=5,
            spaceAfter=2,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "CurriculumBody",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.1,
            leading=11.8,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=3,
        ),
        "BodyBold": ParagraphStyle(
            "CurriculumBodyBold",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.1,
            leading=11.8,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=3,
        ),
        "CalloutTitle": ParagraphStyle(
            "CalloutTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=2,
        ),
        "CalloutBody": ParagraphStyle(
            "CalloutBody",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=11.2,
            textColor=colors.HexColor("#334155"),
            spaceAfter=2,
        ),
        "CodeText": ParagraphStyle(
            "CodeText",
            fontName="Courier",
            fontSize=6.6,
            leading=8.2,
            textColor=colors.HexColor("#0F172A"),
        ),
        "CodeHeader": ParagraphStyle(
            "CodeHeader",
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9.0,
            textColor=colors.HexColor("#0369A1"),
            spaceAfter=2,
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=10.2,
            textColor=colors.white,
            alignment=1,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            fontName="Helvetica",
            fontSize=7.6,
            leading=10.2,
            textColor=colors.HexColor("#1E293B"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=10.2,
            textColor=colors.HexColor("#0F172A"),
        ),
    }
    return styles


def make_callout(box_type, title, text_items, styles, width=523):
    """Génère un encart pédagogique thématique à haute visibilité cognitive."""
    configs = {
        "ANALOGY": {
            "bg": "#F0F9FF",
            "border": "#0284C7",
            "title_color": "#0369A1",
            "icon": "MODÈLE MENTAL & ANALOGIE CONCRÈTE : ",
        },
        "SCQA": {
            "bg": "#EFF6FF",
            "border": "#3B82F6",
            "title_color": "#1D4ED8",
            "icon": "CADRAGE STRATÉGIQUE SCQA (Minto) : ",
        },
        "BIAS": {
            "bg": "#FEF2F2",
            "border": "#EF4444",
            "title_color": "#B91C1C",
            "icon": "PIÈGE DÉBUTANT & SYSTÈME 1 (Kahneman) : ",
        },
        "CHALLENGE": {
            "bg": "#F0FDF4",
            "border": "#22C55E",
            "title_color": "#15803D",
            "icon": "DÉFI STIMULANT EN ZONE PROXIMALE (Ericsson) : ",
        },
        "PREMORTEM": {
            "bg": "#FAF5FF",
            "border": "#A855F7",
            "title_color": "#6B21A8",
            "icon": "PRE-MORTEM : SIMULATION DU CRASH (Kahneman) : ",
        },
        "LOOKINGBACK": {
            "bg": "#FFFBEB",
            "border": "#F59E0B",
            "title_color": "#B45309",
            "icon": "LOOKING BACK & MÉTACOGNITION (George Pólya) : ",
        },
    }

    cfg = configs.get(box_type, configs["ANALOGY"])
    flowables = []

    t_style = ParagraphStyle(
        f"CalloutT_{box_type}",
        parent=styles["CalloutTitle"],
        textColor=colors.HexColor(cfg["title_color"]),
    )
    flowables.append(Paragraph(f"<b>{cfg['icon']}{title}</b>", t_style))
    flowables.append(Spacer(1, 2))

    for item in text_items:
        if isinstance(item, str):
            flowables.append(Paragraph(item, styles["CalloutBody"]))
        else:
            flowables.append(item)

    table = Table([[flowables]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(cfg["bg"])),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                (
                    "LINEBEFORE",
                    (0, 0),
                    (0, -1),
                    3.5,
                    colors.HexColor(cfg["border"]),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def make_code_box(filename, code_text, styles, width=523):
    """Génère un bloc de code soigné avec en-tête de fichier."""
    header = Paragraph(f"<b>Fichier :</b> <code>{filename}</code>", styles["CodeHeader"])
    code_block = Preformatted(code_text.strip(), styles["CodeText"])

    content = [header, Spacer(1, 2), code_block]
    table = Table([[content]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#94A3B8")),
                (
                    "LINEBEFORE",
                    (0, 0),
                    (0, -1),
                    3.0,
                    colors.HexColor("#0284C7"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def generate_full_pdf(filename="MANUEL_APPRENTISSAGE_DJANGO_ET_API.pdf"):
    print(f"Compilation de l'ouvrage complet de formation : {filename}...")
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=38,
        bottomMargin=42,
    )

    styles = get_curriculum_styles()
    story = []

    # =========================================================================
    # PAGE 1 : COUVERTURE & MANIFESTE DE L'APPRENTISSAGE ACTIF
    # =========================================================================
    story.append(Spacer(1, 10))
    story.append(
        Paragraph("PROGRAMME D'EXCELLENCE TECHNIQUE • SOUMAFE SARL (Société à Responsabilité Limitée)", styles["CoverSuper"])
    )
    story.append(
        Paragraph(
            "DE ZÉRO À L'EXCELLENCE : LE MANUEL PRATIQUE DJANGO &amp; API (Application Programming Interface - Interface de Programmation d'Application) BACKEND",
            styles["CoverTitle"],
        )
    )
    story.append(
        Paragraph(
            "Parcours d'Apprentissage Actif Pas-à-Pas : Du Premier Script à l'Architecture d'Entreprise Multi-Tenant",
            ParagraphStyle(
                "SubT",
                parent=styles["CoverSubtitle"],
                fontName="Helvetica-Bold",
                fontSize=12,
                textColor=colors.HexColor("#1E3A8A"),
            ),
        )
    )
    story.append(
        Paragraph(
            "Ce manuel d'ingénierie prend un développeur débutant n'ayant aucune notion de Django et le guide par la "
            "pratique délibérée, les analogies visuelles et les défis progressifs jusqu'à la maîtrise des architectures "
            "SaaS (Software as a Service - Logiciel en tant que Service) critiques en production.",
            styles["CoverSubtitle"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=2,
            color=colors.HexColor("#0284C7"),
            spaceBefore=2,
            spaceAfter=10,
        )
    )

    meta_grid = [
        [
            Paragraph("<b>Stack Technique :</b>", styles["TableCellBold"]),
            Paragraph("Python 3.12+ • Django 5.x • DRF (Django REST Framework - Cadre d'Applications REST pour Django) • PostgreSQL Multi-tenant", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Projet Fil Rouge :</b>", styles["TableCellBold"]),
            Paragraph("<i>BuildTrack</i> : Gestionnaire d'Équipements, Tâches et Incidents de Chantier BTP (Bâtiment et Travaux Publics)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Piliers Scientifiques :</b>", styles["TableCellBold"]),
            Paragraph("How Learning Works (2023) • Deep Reasoning Engine (Kahneman, Minto, Pólya, Meadows)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Contrat Pédagogique :</b>", styles["TableCellBold"]),
            Paragraph("Règle des 70/30 (Pratique Active) • Zéro Prérequis Django • Zéro Rupture Cognitive", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Date &amp; Version :</b>", styles["TableCellBold"]),
            Paragraph("Édition Intégrale 2.5 — 20 Pages d'Ingénierie Structurée Pas-à-Pas", styles["TableCell"]),
        ],
    ]
    meta_table = Table(meta_grid, colWidths=[140, 383])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    manifesto = [
        "<b>Pourquoi ce livre va transformer votre cerveau :</b> La majorité des tutoriels en ligne vous font recopier "
        "du code sans vous faire réfléchir. Vous avez l'impression de comprendre (<i>Illusion de fluidité</i>), mais dès que vous "
        "vous retrouvez seul devant votre terminal, c'est le trou noir.",
        "Ce manuel applique les <b>sciences cognitives</b> : vous allez manipuler des analogies concrètes, résoudre des énigmes, "
        "comprendre le 'Pourquoi' avant le 'Comment', tester des cas de crash réels (<i>Pre-Mortem</i>) et construire de vos propres mains "
        "un système complet dont vous comprendrez chaque engrenage.",
        "<b>Règle de Transparence Linguistique :</b> Dès qu'un sigle technique apparaît pour la première fois dans cet ouvrage, sa signification "
        "complète en français et/ou anglais est systématiquement explicitée entre parenthèses pour ancrer vos modèles mentaux.",
    ]
    story.append(make_callout("LOOKINGBACK", "LE MANIFESTE DE L'APPRENTISSAGE PAR LA PRATIQUE", manifesto, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2 : CHAPITRE 1 - LE MODÈLE MENTAL CLIENT-SERVEUR & DJANGO
    # =========================================================================
    story.append(Paragraph("PARTIE I : LES FONDATIONS PRATIQUES (DE ZÉRO)", styles["PartHeader"]))
    story.append(Paragraph("CHAPITRE 1 : Le Modèle Mental du Web &amp; l'Écosystème Django", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c1 = [
        "Imaginez un <b>restaurant gastronomique</b> :",
        "1. <b>Le Client à table</b> (Le Navigateur Web / L'App Mobile) : Il ne va pas en cuisine. Il consulte le menu et émet une requête via le protocole HTTP (HyperText Transfer Protocol - Protocole de Transfert Hypertexte) : <i>« Apportez-moi la liste des chantiers en cours »</i>.",
        "2. <b>Le Maître d'Hôtel (Le Routeur <code>urls.py</code>)</b> : Il réceptionne la commande et l'oriente vers le bon poste de travail en cuisine grâce à l'URL (Uniform Resource Locator - Localisateur Uniforme de Ressource).",
        "3. <b>Le Chef de Cuisine (La Vue <code>views.py</code>)</b> : C'est le cerveau ! Il reçoit la commande, prépare le plat, va chercher les ingrédients et dresse l'assiette finale au format JSON (JavaScript Object Notation - Notation d'Objets JavaScript) ou HTML (HyperText Markup Language - Langage de Balisage Hypertexte).",
        "4. <b>Le Garde-Manger (La Base de Données)</b> : Les données y sont entreposées.",
        "5. <b>L'Économe (L'ORM / <code>models.py</code>)</b> : L'ORM (Object-Relational Mapping - Mappage Objet-Relationnel) sait exactement sur quelle étagère se trouve chaque donnée et la fournit au Chef sans que celui-ci ait besoin de fouiller dans la cave.",
    ]
    story.append(make_callout("ANALOGY", "LE RESTAURANT DU WEB (CLIENT, ROUTEUR, VUE, ORM)", analogy_c1, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("L'Architecture MTV (Model-Template-View - Modèle-Template-Vue)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Django repose sur le patron architectural <b>MTV</b>, une déclinaison pragmatique du classique "
            "<b>MVC</b> (Model-View-Controller - Modèle-Vue-Contrôleur). Le <i>Modèle</i> gère la persistance, "
            "le <i>Template</i> produit l'affichage visuel, et la <i>Vue</i> assure l'orchestration métier. "
            "Pour communiquer avec les serveurs de production, Django utilise les interfaces standardisées "
            "<b>WSGI</b> (Web Server Gateway Interface - Interface Passerelle de Serveur Web) pour le mode synchrone, "
            "ou <b>ASGI</b> (Asynchronous Server Gateway Interface - Interface Passerelle Asynchrone de Serveur) pour le mode temps réel asynchrone.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 4))

    bias_c1 = [
        "<b>L'Illusion du 'Je sais par cœur' :</b> Ne cherchez jamais à mémoriser chaque paramètre de Django. "
        "Les meilleurs architectes logiciels conservent la documentation officielle ouverte. Ce qui fait votre valeur, "
        "c'est votre <b>modèle mental</b> : savoir exactement à quelle étape du voyage HTTP une erreur s'est produite.",
    ]
    story.append(make_callout("BIAS", "MÉMORISATION SYNTAXIQUE VS MODÈLE MENTAL PROFOND", bias_c1, styles))
    story.append(Spacer(1, 4))

    chal_c1 = [
        "<b>Défi Actif #1 : Le Parcours de la Requête</b><br/>"
        "Prenez une feuille et dessinez de mémoire le parcours d'une requête tapée dans le terminal ou le CLI (Command Line Interface - Interface en Ligne de Commande) :<br/>"
        "Navigateur $\\rightarrow$ HTTP GET /chantiers/ $\\rightarrow$ urls.py $\\rightarrow$ views.py $\\rightarrow$ models.py $\\rightarrow$ Base de données $\\rightarrow$ Réponse JSON $\\rightarrow$ Écran.",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #1 : DESSINEZ LE FLUX", chal_c1, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 3 : CHAPITRE 2 - CRÉATION DU PROJET & PREMIER CONTACT HTTP
    # =========================================================================
    story.append(Paragraph("CHAPITRE 2 : Votre Premier Projet Pas-à-Pas (Le Hello World Actif)", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    story.append(Paragraph("1. Initialisation de l'Environnement Virtuel & Installation", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Ouvrez votre terminal dans votre IDE (Integrated Development Environment - Environnement de Développement Intégré) et tapez ces commandes fondamentales :",
            styles["Body"],
        )
    )

    c2_code_init = """# 1. Créer et activer un environnement virtuel isolé
python -m venv .venv
# Sur Windows : .venv\\Scripts\\activate | Sur Mac/Linux : source .venv/bin/activate

# 2. Installer Django (version 5+)
pip install django

# 3. Créer le squelette de configuration du projet
django-admin startproject config .

# 4. Créer notre première application métier
python manage.py startapp chantiers"""
    story.append(make_code_box("Terminal (Bash/PowerShell)", c2_code_init, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("2. Activer l'Application dans la Configuration Globale", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Django ignore totalement une application tant qu'elle n'est pas déclarée. Ouvrez <code>config/settings.py</code> :",
            styles["Body"],
        )
    )

    c2_code_settings = """# config/settings.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Notre application métier BTP :
    'chantiers',
]"""
    story.append(make_code_box("config/settings.py", c2_code_settings, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("3. Votre Première Vue HTTP Réelle", styles["SectionHeader"]))
    c2_code_view = """# chantiers/views.py
from django.http import HttpResponse

def hello_chantier(request):
    return HttpResponse("<h1>Bienvenue sur BuildTrack : Le Cockpit BTP de SOUMAFE SARL !</h1>")"""
    story.append(make_code_box("chantiers/views.py", c2_code_view, styles))
    story.append(Spacer(1, 5))

    c2_code_urls = """# config/urls.py
from django.contrib import admin
from django.urls import path
from chantiers.views import hello_chantier

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', hello_chantier, name='accueil'),
]"""
    story.append(make_code_box("config/urls.py", c2_code_urls, styles))
    story.append(Spacer(1, 4))

    chal_c2 = [
        "<b>Défi Stimulant #2 : Première Victoire Active</b><br/>"
        "1. Tapez <code>python manage.py runserver</code> dans votre terminal.<br/>"
        "2. Ouvrez votre navigateur sur <code>http://127.0.0.1:8000/</code>.<br/>"
        "3. Vous devez voir s'afficher votre message en grand. Vous venez de boucler votre premier cycle HTTP réel !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #2 : VOTRE PREMIER SERVEUR EN DIRECT", chal_c2, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 4 : CHAPITRE 3 - L'ORM DJANGO : VOS DONNÉES SANS SQL
    # =========================================================================
    story.append(Paragraph("CHAPITRE 3 : L'ORM Django : Vos Données sans Écrire de SQL", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c3 = [
        "<b>Pourquoi l'ORM est magique :</b><br/>"
        "Sans ORM, pour créer un chantier en base de données, vous devriez écrire du SQL (Structured Query Language - Langage de Requêtes Structurées) "
        "brut : <code>INSERT INTO chantiers_projet (nom, ville) VALUES ('Tour Alpha', 'Abidjan');</code>.<br/>"
        "Si demain votre entreprise bascule de SQLite à PostgreSQL ou Oracle, la syntaxe SQL peut changer.<br/>"
        "L'ORM (Object-Relational Mapping - Mappage Objet-Relationnel) traduit automatiquement vos objets Python purs en tables dans votre "
        "SGBD (Système de Gestion de Base de Données) sans que vous ayez à rédiger une seule ligne de SQL !",
    ]
    story.append(make_callout("ANALOGY", "LE TRADUCTEUR UNIVERSEL PYTHON <-> SQL", analogy_c3, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("1. Définition du Premier Modèle Métier : Projet de Chantier", styles["SectionHeader"]))
    c3_code_model = """# chantiers/models.py
from django.db import models

class Projet(models.Model):
    nom = models.CharField(max_length=150, verbose_name="Nom du Chantier")
    ville = models.CharField(max_length=100, default="Abidjan")
    budget_estime = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    est_actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} ({self.ville})" """
    story.append(make_code_box("chantiers/models.py", c3_code_model, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("2. Le Rituel des Migrations en Deux Temps", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Modifier <code>models.py</code> ne change RIEN à la base tant que vous n'avez pas exécuté le rituel sacré des migrations :",
            styles["Body"],
        )
    )

    c3_code_mig = """# Étape 1 : Django analyse models.py et prépare le plan de construction (le blueprint)
python manage.py makemigrations
# Sortie : Migrations for 'chantiers': 0001_initial.py - Create model Projet

# Étape 2 : Django exécute les commandes SQL réelles sur la base de données
python manage.py migrate
# Sortie : Applying chantiers.0001_initial... OK"""
    story.append(make_code_box("Terminal (Le Rituel Sacré)", c3_code_mig, styles))
    story.append(Spacer(1, 4))

    bias_c3 = [
        "<b>L'Angoisse du Fichier Fantôme :</b> Si vous ajoutez un champ dans <code>models.py</code> et lancez votre code "
        "sans faire <code>makemigrations</code> puis <code>migrate</code>, Django lèvera l'erreur redoutée : "
        "<code>OperationalError: no such column</code>. Retenez bien : <b>Code Modèle $\\neq$ Base Réelle</b> tant que migrate n'a pas tourné.",
    ]
    story.append(make_callout("BIAS", "LE PIÈGE N°1 DES DÉBUTANTS : L'OUBLI DE MIGRATE", bias_c3, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 5 : CHAPITRE 4 - L'ADMIN DJANGO : LE SUPER-POUVOIR INSTANTANÉ
    # =========================================================================
    story.append(Paragraph("CHAPITRE 4 : Le Django Admin : Le Super-Pouvoir Instantané", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c4 = [
        "<b>Le Cockpit Immédiat de l'Entreprise :</b><br/>"
        "Dans d'autres frameworks (Node.js, Express, Spring Boot), concevoir une UI (User Interface - Interface Utilisateur) d'administration pour créer, modifier "
        "et filtrer les données prend plusieurs jours de travail frontend et backend.<br/>"
        "Dans Django, cela prend exactement 30 secondes. Django lit la structure de vos modèles et génère automatiquement une interface Web "
        "sécurisée, responsive et ergonomique.",
    ]
    story.append(make_callout("ANALOGY", "L'INTERFACE DE CONTRÔLE GÉNÉRÉE PAR INTROSPECTION", analogy_c4, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("1. Créer son Compte Administrateur (Superuser)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Dans votre terminal, tapez la commande suivante et suivez les instructions interactives :",
            styles["Body"],
        )
    )

    c4_code_super = """python manage.py createsuperuser
# Exemple de saisie :
# Nom d'utilisateur (leave blank to use 'admin'): admin
# Adresse électronique: admin@soumafe.ci
# Password: ********
# Superuser created successfully."""
    story.append(make_code_box("Terminal (Création du Super-Utilisateur)", c4_code_super, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("2. Enregistrer le Modèle dans l'Interface d'Admin", styles["SectionHeader"]))
    c4_code_admin = """# chantiers/admin.py
from django.contrib import admin
from chantiers.models import Projet

@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    # Les colonnes visibles dans le tableau de bord
    list_display = ('nom', 'ville', 'budget_estime', 'est_actif', 'cree_le')
    
    # Filtres latéraux interactifs
    list_filter = ('est_actif', 'ville')
    
    # Barre de recherche plein texte sur le nom
    search_fields = ('nom',)
    
    # Trier par défaut par date de création décroissante
    ordering = ('-cree_le',)"""
    story.append(make_code_box("chantiers/admin.py", c4_code_admin, styles))
    story.append(Spacer(1, 4))

    chal_c4 = [
        "<b>Défi Stimulant #3 : Entrez dans le Cockpit !</b><br/>"
        "1. Lancez <code>python manage.py runserver</code>.<br/>"
        "2. Rendez-vous sur <code>http://127.0.0.1:8000/admin/</code> et connectez-vous.<br/>"
        "3. Cliquez sur <b>Projets</b> puis <b>Ajouter Projet</b>. Créez 2 chantiers réels (ex: 'Immeuble Riviera' et 'Pont de Cocody').<br/>"
        "4. Utilisez la barre de recherche et les filtres latéraux pour voir vos données réagir instantanément !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #3 : CRÉATION DE DONNÉES EN DIRECT", chal_c4, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 6 : CHAPITRE 5 - MANIPULER LES DONNÉES : LE SHELL INTERACTIF
    # =========================================================================
    story.append(Paragraph("CHAPITRE 5 : Manipuler les Données : Le Shell Interactif", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    story.append(Paragraph("1. Le Laboratoire Interactif & le CRUD Complet en Direct", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le Shell interactif de Django charge votre application et votre base en mémoire. Lancez : <code>python manage.py shell</code>. "
            "Vous y exécutez le <b>CRUD</b> (Create, Read, Update, Delete - Créer, Lire, Mettre à jour, Supprimer) :",
            styles["Body"],
        )
    )

    c5_code_crud = """# Dans le shell interactif Python :
from chantiers.models import Projet

# 1. C (CREATE) : Créer un nouveau chantier
p = Projet.objects.create(nom="Tour Alpha", ville="Yamoussoukro", budget_estime=75000000)
print(p.id) # Une PK (Primary Key - Clé Primaire) auto-incrémentée a été attribuée

# 2. R (READ) : Interroger la base de données
tous = Projet.objects.all()
print("Nombre de projets :", tous.count())
abidjan = Projet.objects.filter(ville="Abidjan")
alpha = Projet.objects.get(nom__icontains="Alpha")

# 3. U (UPDATE) : Modifier un champ et sauvegarder
alpha.budget_estime = 80000000
alpha.save()

# 4. D (DELETE) : Supprimer l'objet
# alpha.delete()"""
    story.append(make_code_box("Python Shell (Le CRUD en Direct)", c5_code_crud, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("2. Lier les Tables : La Clé Étrangère ou FK (Foreign Key)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Sur un chantier, il y a des Tâches. Chaque tâche est rattachée à un seul Projet, mais un projet contient "
            "plusieurs tâches : c'est une <b>relation 1-N (Un à Plusieurs)</b> matérialisée par une <b>FK</b> :",
            styles["Body"],
        )
    )

    c5_code_rel = """# chantiers/models.py (Ajout du modèle Tache)
class Tache(models.Model):
    # La clé étrangère qui relie la tâche à son projet parent
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="taches")
    titre = models.CharField(max_length=200)
    est_terminee = models.BooleanField(default=False)
    date_limite = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.titre} ({'Fait' if self.est_terminee else 'En attente'})" """
    story.append(make_code_box("chantiers/models.py (Relation 1-N)", c5_code_rel, styles))
    story.append(Spacer(1, 4))

    chal_c5 = [
        "<b>Défi Stimulant #4 : Navigation Inverse entre Objets !</b><br/>"
        "Après avoir fait <code>makemigrations</code> et <code>migrate</code>, ouvrez le shell :<br/>"
        "1. Créez un projet <code>p = Projet.objects.first()</code>.<br/>"
        "2. Créez deux tâches : <code>Tache.objects.create(projet=p, titre='Coulage béton fondation')</code>.<br/>"
        "3. Tapez : <code>p.taches.all()</code>. Observez comment Django remonte automatiquement toutes les tâches liées au projet !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #4 : EXPLORATION RELATIONNELLE", chal_c5, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 7 : CHAPITRE 6 - L'ÈRE DES API : DJANGO REST FRAMEWORK (DRF)
    # =========================================================================
    story.append(Paragraph("CHAPITRE 6 : Entrer dans l'Ère des API : DRF", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c6 = [
        "<b>Du Monolithe HTML aux API REST Découplées :</b><br/>"
        "• <b>Web Ancien :</b> Le serveur générait tout le code HTML et l'envoyait au navigateur.<br/>"
        "• <b>Web Moderne :</b> Le backend fournit uniquement des <b>données brutes en JSON</b> via une API REST (Representational State Transfer - Transfert d'État Représentationnel). "
        "Une application Next.js/React, une application mobile iOS/Android sur le chantier ou un script d'analyse consomment "
        "exactement les mêmes données. Votre backend devient un moteur universel.",
    ]
    story.append(make_callout("ANALOGY", "POURQUOI LES API JSON DOMINENT L'INDUSTRIE", analogy_c6, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("1. Installer DRF & Comprendre le Rôle du Sérialiseur", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Installez la bibliothèque : <code>pip install djangorestframework</code> puis ajoutez <code>'rest_framework'</code> dans vos <code>INSTALLED_APPS</code>. "
            "Le <b>Sérialiseur</b> prend les objets Python complexes de l'ORM et les convertit en JSON, et valide les JSON envoyés par le client.",
            styles["Body"],
        )
    )

    c6_code_ser = """# chantiers/serializers.py
from rest_framework import serializers
from chantiers.models import Projet

class ProjetSerializer(serializers.ModelSerializer):
    total_taches = serializers.IntegerField(source='taches.count', read_only=True)

    class Meta:
        model = Projet
        fields = ['id', 'nom', 'ville', 'budget_estime', 'est_actif', 'total_taches', 'cree_le']"""
    story.append(make_code_box("chantiers/serializers.py", c6_code_ser, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("2. Votre Première Vue API REST (APIView)", styles["SectionHeader"]))
    c6_code_view = """# chantiers/views.py (Ajout des vues API REST)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from chantiers.models import Projet
from chantiers.serializers import ProjetSerializer

class ProjetListCreateAPIView(APIView):
    def get(self, request):
        projets = Projet.objects.all().order_by('-cree_le')
        serializer = ProjetSerializer(projets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProjetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)"""
    story.append(make_code_box("chantiers/views.py (APIView REST)", c6_code_view, styles))
    story.append(Spacer(1, 4))

    chal_c6 = [
        "<b>Défi Stimulant #5 : Connectez l'URL et Admirez la Browsable API</b><br/>"
        "Ajoutez <code>path('api/projets/', ProjetListCreateAPIView.as_view())</code> dans votre fichier <code>config/urls.py</code>.<br/>"
        "Ouvrez votre navigateur sur <code>http://127.0.0.1:8000/api/projets/</code>. DRF vous affiche une console interactive "
        "où vous pouvez lire le JSON et soumettre des formulaires POST directement !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #5 : LE TEST DU NAVIGATEUR", chal_c6, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 8 : CHAPITRE 7 - VALIDATION CHIRURGICALE & CODES HTTP
    # =========================================================================
    story.append(Paragraph("CHAPITRE 7 : Validation Chirurgicale &amp; Codes HTTP", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c7 = [
        "<b>Les Codes HTTP : La Langue Internationale du Web :</b><br/>"
        "Votre serveur ne doit JAMAIS renvoyer un statut 200 OK quand une erreur s'est produite.<br/>"
        "• <b>200 OK :</b> La lecture s'est déroulée avec succès.<br/>"
        "• <b>201 Created :</b> La nouvelle ressource a été créée en base avec succès.<br/>"
        "• <b>400 Bad Request :</b> Données envoyées invalides ou incomplètes (rejetées par la validation).<br/>"
        "• <b>401 Unauthorized :</b> Vous devez être authentifié pour accéder à cette ressource.<br/>"
        "• <b>403 Forbidden :</b> Vous êtes authentifié, mais vous n'avez pas les droits (rôle insuffisant).<br/>"
        "• <b>404 Not Found :</b> La ressource demandée n'existe pas.",
    ]
    story.append(make_callout("ANALOGY", "LES CODES HTTP : LA GRAMMAIRE UNIVERSELLE DU WEB", analogy_c7, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("Validation Métier dans le Sérialiseur", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Vous disposez de deux niveaux de validation : champ par champ ou validation globale multi-champs :",
            styles["Body"],
        )
    )

    c7_code_val = """# chantiers/serializers.py (Validation Avancée)
class ProjetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Projet
        fields = ['id', 'nom', 'ville', 'budget_estime', 'est_actif', 'cree_le']

    # Niveau 1 : Validation ciblée d'un champ unique (format: validate_<nom_du_champ>)
    def validate_budget_estime(self, value):
        if value < 0:
            raise serializers.ValidationError("Le budget estimé d'un chantier ne peut pas être négatif.")
        if value > 50000000000:
            raise serializers.ValidationError("Montant exorbitant : vérifiez la devise (plafond à 50 Mds FCFA).")
        return value

    # Niveau 2 : Validation croisée de plusieurs champs
    def validate(self, attrs):
        nom = attrs.get('nom', '')
        ville = attrs.get('ville', '')
        if 'abidjan' in ville.lower() and len(nom) < 5:
            raise serializers.ValidationError({"nom": "Pour la zone d'Abidjan, le libellé du chantier doit être précis (min 5 car)."})
        return attrs"""
    story.append(make_code_box("chantiers/serializers.py (Règles Métier)", c7_code_val, styles))
    story.append(Spacer(1, 4))

    chal_c7 = [
        "<b>Défi Stimulant #6 : Le Crash Test des Données Pourries</b><br/>"
        "Ouvrez la Browsable API ou votre terminal :<br/>"
        "Tentez d'envoyer un POST avec : <code>{\"nom\": \"Test\", \"budget_estime\": -5000}</code>.<br/>"
        "Constater que DRF répond immédiatement un code <b>400 Bad Request</b> avec le message d'erreur précis au format JSON. "
        "Votre base de données est protégée contre la corruption !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #6 : LE TEST DU CHAMP NÉGATIF", chal_c7, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 9 : CHAPITRE 8 - AUTHENTIFICATION & SÉCURISATION DES ENDPOINTS
    # =========================================================================
    story.append(Paragraph("CHAPITRE 8 : Authentification &amp; Sécurisation des Endpoints", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c8 = [
        "<b>Authentification vs Autorisation (RBAC) :</b><br/>"
        "• <b>Authentification (Qui êtes-vous ?) :</b> Prouver son identité via un login/mot de passe ou un jeton JWT (JSON Web Token - Jeton Web JSON).<br/>"
        "• <b>Autorisation (Qu'avez-vous le droit de faire ?) :</b> Le <b>RBAC</b> (Role-Based Access Control - Contrôle d'Accès Basé sur les Rôles) "
        "définit les permissions. Un ouvrier peut consulter le planning, mais seul le Conducteur de Travaux peut valider un bon de commande.",
    ]
    story.append(make_callout("ANALOGY", "LA DISTINCTION VITALE : IDENTITÉ VS POUVOIRS", analogy_c8, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("Créer une Permission DRF Sur-Mesure", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Par défaut, DRF propose <code>IsAuthenticated</code> (accessible à tout connecté) et <code>IsAdminUser</code>. "
            "En entreprise, on conçoit des permissions chirurgicales :",
            styles["Body"],
        )
    )

    c8_code_perm = """# chantiers/permissions.py
from rest_framework import permissions

class EstChefDeChantierOuLectureSeule(permissions.BasePermission):
    \"\"\"Lecture libre pour les connectés, modification réservée aux staffs/admins.\"\"\"
    def has_permission(self, request, view):
        # Les méthodes SAFE_METHODS sont : GET, HEAD, OPTIONS (lecture seule)
        if request.method in permissions.SAFE_METHODS:
            return True
        # Pour POST, PUT, DELETE : l'utilisateur doit être membre du staff
        return bool(request.user and request.user.is_staff)"""
    story.append(make_code_box("chantiers/permissions.py", c8_code_perm, styles))
    story.append(Spacer(1, 5))

    c8_code_use = """# chantiers/views.py (Protection des Endpoints)
from rest_framework.permissions import IsAuthenticated
from chantiers.permissions import EstChefDeChantierOuLectureSeule

class ProjetListCreateAPIView(APIView):
    # Les deux gardiens à l'entrée :
    permission_classes = [IsAuthenticated, EstChefDeChantierOuLectureSeule]
    
    # ... le reste du code des méthodes get() et post() ..."""
    story.append(make_code_box("chantiers/views.py (Sécurisation)", c8_code_use, styles))
    story.append(Spacer(1, 4))

    chal_c8 = [
        "<b>Défi Stimulant #7 : Le Test de l'Intrus</b><br/>"
        "1. Appelez l'API en GET sans être connecté $\\rightarrow$ Observez le code <b>401 UNAUTHORIZED</b>.<br/>"
        "2. Connectez-vous avec un utilisateur simple non-staff et tentez un POST $\\rightarrow$ Observez le code <b>403 FORBIDDEN</b> !<br/>"
        "Votre API dispose désormais d'un bouclier de protection inviolable.",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #7 : SIMULATION DE BRÈCHE", chal_c8, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 10 : CHAPITRE 9 - LE SAUT ENTREPRISE : CLEAN ARCHITECTURE
    # =========================================================================
    story.append(Paragraph("PARTIE II : L'ÉLÉVATION VERS LE NIVEAU ENTREPRISE", styles["PartHeader"]))
    story.append(Paragraph("CHAPITRE 9 : Pourquoi l'Approche Débutant Explose en Entreprise", styles["ChapterHeader"]))
    story.append(Spacer(1, 3))

    analogy_c9 = [
        "<b>L'analogie de la Cabane vs Gratte-Ciel (Donella Meadows & Barbara Minto) :</b><br/>"
        "Pour construire une cabane en bois au fond du jardin, vous pouvez mettre tous vos outils par terre dans la même pièce. C'est ce que font les "
        "débutants en mettant toute leur logique dans <code>views.py</code> ou <code>models.py</code>.<br/>"
        "Mais pour ériger une tour de 30 étages (la plateforme SaaS critique de SOUMAFE SARL), cette méthode entraîne l'effondrement "
        "immédiat du bâtiment : effets de bord invisibles, régressions massives, requêtes SQL qui font planter le serveur et impossibilité de tester unitairement.",
    ]
    story.append(make_callout("ANALOGY", "DE LA CABANE AU GRATTE-CIEL D'ENTREPRISE", analogy_c9, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("Le Patron CQS (Command-Query Separation) & DDD (Domain-Driven Design)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Pour supporter des millions de requêtes sans faille, nous appliquons une séparation stricte entre "
            "<b>la Lecture pure (Selectors)</b> et <b>l'Écriture métier (Services)</b> :",
            styles["Body"],
        )
    )

    c9_table_data = [
        [
            Paragraph("<b>Couche Métier</b>", styles["TableHeader"]),
            Paragraph("<b>Rôle Strict</b>", styles["TableHeader"]),
            Paragraph("<b>Ce qu'on y trouve</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("1. Sélecteurs (<code>selectors/</code>)", styles["TableCellBold"]),
            Paragraph("Lecture seule optimisée.", styles["TableCell"]),
            Paragraph("Requêtes avec <code>select_related</code>, zéro écriture, retour QuerySets.", styles["TableCell"]),
        ],
        [
            Paragraph("2. Services (<code>services/</code>)", styles["TableCellBold"]),
            Paragraph("Écriture métier transactionnelle.", styles["TableCell"]),
            Paragraph("Fonctions décorées de <code>@transaction.atomic</code>, règles RG, soft-delete.", styles["TableCell"]),
        ],
        [
            Paragraph("3. Sérialiseurs DTO (<code>serializers/</code>)", styles["TableCellBold"]),
            Paragraph("Validation DTO (Data Transfer Object) d'entrée et sortie.", styles["TableCell"]),
            Paragraph("Validation des formats et types, transformation en JSON.", styles["TableCell"]),
        ],
        [
            Paragraph("4. Permissions (<code>permissions.py</code>)", styles["TableCellBold"]),
            Paragraph("Contrôle d'accès cumulatif.", styles["TableCell"]),
            Paragraph("Niveau 1 (Rôle Global) + Niveau 2 (Affectation au chantier).", styles["TableCell"]),
        ],
        [
            Paragraph("5. Vues API (<code>views/</code>)", styles["TableCellBold"]),
            Paragraph("Contrôleur HTTP mince.", styles["TableCell"]),
            Paragraph("Dispatch des verbes HTTP, pagination, documentation OpenAPI Swagger.", styles["TableCell"]),
        ],
    ]
    c9_t = Table(c9_table_data, colWidths=[130, 160, 233])
    c9_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(c9_t)
    story.append(Spacer(1, 5))

    prem_c9 = [
        "<b>Simulation Pre-Mortem (Daniel Kahneman) :</b><br/>"
        "Pourquoi est-il formellement interdit d'écrire <code>from rest_framework.request import Request</code> dans un Service ?<br/>"
        "<b>Conséquence mortelle :</b> Si votre logique métier dépend de l'objet request HTTP, vous ne pourrez JAMAIS appeler ce service "
        "depuis une tâche asynchrone Celery en tâche de fond, ni depuis un script de commande dans le terminal, ni depuis un test unitaire "
        "sans devoir simuler tout un serveur HTTP ! Les services doivent rester des <b>fonctions Python pures</b> indépendantes du web.",
    ]
    story.append(make_callout("PREMORTEM", "DÉCOUPLAGE TOTAL DU PROTOCOLE HTTP", prem_c9, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 11 : CHAPITRE 10 - RESTRUCTURATION PHYSIQUE : AUX PACKAGES MODULAIRES
    # =========================================================================
    story.append(Paragraph("CHAPITRE 10 : Restructuration Physique : De l'App à Plat aux Packages Modulaires", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Étape Charnière : Comprendre la Métamorphose des Fichiers et la Découverte par Django</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    analogy_c10 = [
        "<b>De la Feuille Volante au Classeur Structuré :</b><br/>"
        "Dans l'approche débutant (Partie I), tous les modèles étaient entassés dans un unique <code>models.py</code>, "
        "et toutes les vues dans <code>views.py</code>. Dans un système d'entreprise gérant 50 tables et 200 règles de gestion, "
        "ces fichiers atteignent 3000 lignes et deviennent illisibles.<br/>"
        "<b>La règle d'or :</b> En Python, un dossier contenant un fichier <code>__init__.py</code> est traité exactement "
        "comme un fichier de code (un <i>Package</i>). Nous transformons donc nos fichiers uniques en répertoires spécialisés.",
    ]
    story.append(make_callout("ANALOGY", "TRANSFORMER DES FICHIERS EN PACKAGES PYTHON", analogy_c10, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("L'Arborescence Complète d'une Application d'Entreprise Modularisée", styles["SectionHeader"]))

    tree_str = """apps/chantier/
├── __init__.py
├── apps.py                  <-- Configuration de l'application (name = 'apps.chantier')
├── models/
│   ├── __init__.py          <-- POINT CRITIQUE VITAL : Exporte les modèles pour makemigrations !
│   └── projet.py            <-- Modèle métier Projet isolé
├── selectors/
│   ├── __init__.py
│   └── projet.py            <-- Fonctions pures de LECTURE SQL optimisées
├── services/
│   ├── __init__.py
│   └── projet.py            <-- Fonctions pures d'ÉCRITURE métier transactionnelles
├── serializers/
│   ├── __init__.py
│   └── projet.py            <-- DTOs d'entrée et de sortie
└── views/
    ├── __init__.py
    └── projet.py            <-- Contrôleurs HTTP minces"""
    story.append(make_code_box("Structure Physique du Répertoire apps/chantier/", tree_str, styles))
    story.append(Spacer(1, 4))

    bias_c10 = [
        "<b>LE PIÈGE MORTEL DU <code>__init__.py</code> DANS <code>models/</code> :</b><br/>"
        "Lorsque vous remplacez <code>models.py</code> par un dossier <code>models/</code>, Django cherche à importer <code>apps.chantier.models</code>.<br/>"
        "Si votre fichier <code>apps/chantier/models/__init__.py</code> est VIDE, Django ne charge pas le sous-fichier <code>projet.py</code>. "
        "Conséquence catastrophique : lors du prochain <code>makemigrations</code>, Django pense que vous avez supprimé votre table et propose "
        "d'effacer toutes vos données !<br/>"
        "<b>L'action corrective obligatoire :</b> Ouvrez <code>apps/chantier/models/__init__.py</code> et écrivez explicitement :<br/>"
        "<code>from .projet import Projet</code> (et ainsi pour chaque modèle ajouté au projet).",
    ]
    story.append(make_callout("BIAS", "LE SECRET DE LA DÉCOUVERTE DES MODÈLES PAR DJANGO", bias_c10, styles))
    story.append(Spacer(1, 4))

    chal_c10 = [
        "<b>Défi Stimulant #8 : Déclaration dans <code>INSTALLED_APPS</code></b><br/>"
        "Dans <code>config/settings.py</code>, remplacez <code>'chantiers'</code> par <code>'apps.chantier'</code>.<br/>"
        "Dans <code>apps/chantier/apps.py</code>, configurez <code>name = 'apps.chantier'</code>.<br/>"
        "Lancez <code>python manage.py check</code> : le message magique doit s'afficher : <i>« System check identified no issues »</i> !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #8 : VALIDATION DE LA STRUCTURE MODULAIRE", chal_c10, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 12 : CHAPITRE 11 - ATELIER DE REFACTORING GUIDÉ PAS-À-PAS
    # =========================================================================
    story.append(Paragraph("CHAPITRE 11 : Atelier de Refactoring Guidé : La Métamorphose de Projet Pas-à-Pas", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Le Pont Cognitif : Prendre le Code Connu du Chapitre 6 et le Nettoyer en Direct</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    analogy_c11_refac = [
        "<b>L'Opération Chirurgicale sur votre Propre Code :</b><br/>"
        "Pour bien comprendre, nous n'allons pas inventer un nouveau problème. Nous reprenons exactement la vue "
        "<code>ProjetListCreateAPIView</code> créée au Chapitre 6, et nous allons extraire ses organes un par un :<br/>"
        "1. La requête <code>Projet.objects.all()</code> déménage dans un <b>Sélecteur</b>.<br/>"
        "2. L'écriture <code>serializer.save()</code> est bannie et remplacée par un appel à un <b>Service</b> transactionnel.<br/>"
        "3. La vue s'amincit et devient un simple aiguilleur !",
    ]
    story.append(make_callout("ANALOGY", "LE REFACTORING PAS-À-PAS DU MODÈLE PROJET", analogy_c11_refac, styles))
    story.append(Spacer(1, 4))

    refac_sel_code = """# apps/chantier/selectors/projet.py
from apps.chantier.models.projet import Projet

def projets_liste(*, ville=None, est_actif=True):
    \"\"\"Lecture pure : retourne la liste filtrée sans aucun effet de bord.\"\"\"
    qs = Projet.objects.filter(est_actif=est_actif)
    if ville:
        qs = qs.filter(ville__iexact=ville)
    return qs.order_by("-cree_le")"""
    story.append(make_code_box("apps/chantier/selectors/projet.py (Étape 1 : Extraction Sélecteur)", refac_sel_code, styles))
    story.append(Spacer(1, 4))

    refac_srv_code = """# apps/chantier/services/projet.py
from django.db import transaction
from apps.chantier.models.projet import Projet

@transaction.atomic
def creer_projet(*, nom, ville="Abidjan", budget_estime=0):
    \"\"\"Écriture métier transactionnelle : garantit la cohérence en base.\"\"\"
    projet = Projet(
        nom=nom.strip(),
        ville=ville.strip(),
        budget_estime=budget_estime,
        est_actif=True
    )
    projet.full_clean()  # Exécute toutes les validations de modèles
    projet.save()
    return projet"""
    story.append(make_code_box("apps/chantier/services/projet.py (Étape 2 : Extraction Service)", refac_srv_code, styles))
    story.append(Spacer(1, 4))

    refac_view_code = """# apps/chantier/views/projet.py (Étape 3 : La Vue Allégée)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.chantier.selectors.projet import projets_liste
from apps.chantier.services.projet import creer_projet
from apps.chantier.serializers.projet import ProjetSerializer

class ProjetListCreateAPIView(APIView):
    def get(self, request):
        projets = projets_liste(ville=request.GET.get('ville')) # Délégation lecture
        return Response(ProjetSerializer(projets, many=True).data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProjetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # BANNISSEMENT DE serializer.save() -> Appel du Service d'entreprise :
        projet = creer_projet(**serializer.validated_data)
        return Response(ProjetSerializer(projet).data, status=status.HTTP_201_CREATED)"""
    story.append(make_code_box("apps/chantier/views/projet.py (Résultat : Le Contrôleur Mince)", refac_view_code, styles))
    story.append(Spacer(1, 4))

    look_refac = [
        "<b>Regardez votre nouveau code :</b> La vue ne contient plus AUCUNE requête SQL et n'écrit plus directement en base. "
        "Si demain vous devez créer un chantier lors de l'import d'un fichier Excel en ligne de commande, vous appelez simplement "
        "<code>creer_projet(nom=...)</code> sans avoir besoin de simuler une fausse requête web !",
    ]
    story.append(make_callout("LOOKINGBACK", "LA VICTOIRE DU DÉCOUPLAGE", look_refac, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 13 : CHAPITRE 12 - LE SOCLE COMMUN (UUID, SOFT-DELETE, RESTRICT)
    # =========================================================================
    story.append(Paragraph("CHAPITRE 12 : Le Socle Commun (UUID, Soft-Delete &amp; Sécurité SQL)", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Les Invariants Techniques Obligatoires de la Plateforme d'Entreprise</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    scqa_c12 = [
        "<b>Les 4 Lois Sacrées du Socle d'Entreprise :</b><br/>"
        "1. <b>Bannissement des ID Entiers (1, 2, 3...) :</b> Remplacés par des <b>UUID</b> (Universally Unique Identifier - Identifiant Universel Unique) v4. "
        "Pourquoi ? Un entier séquentiel permet à un concurrent de deviner vos volumes de ventes ou d'injecter des ID voisins dans l'URL. "
        "De plus, sur une application mobile hors-ligne, le technicien peut générer un UUID local sans risque de collision lors de la synchronisation !<br/>"
        "2. <b>Horodatage UTC Obligatoire :</b> Toutes les dates sont stockées en <b>UTC</b> (Coordinated Universal Time - Temps Universel Coordonné) avec TIMESTAMPTZ.<br/>"
        "3. <b>La Suppression Physique n'Existe Pas :</b> Utilisation exclusive du <b>Soft-Delete</b> (marquage logique d'horodatage).<br/>"
        "4. <b>Protection Vitale RESTRICT :</b> Interdiction formelle du <code>on_delete=CASCADE</code> sur les données sensibles.",
    ]
    story.append(make_callout("SCQA", "LES 4 LOIS DU SOCLE COMMUN D'ENTREPRISE", scqa_c12, styles))
    story.append(Spacer(1, 4))

    c12_base_code = """# apps/core/models/__init__.py (Le Socle Commun Abstrait)
import uuid
from django.db import models
from django.utils import timezone

class ManagerActif(models.Manager):
    \"\"\"Injecte automatiquement WHERE supprime_le IS NULL sur chaque requête SQL.\"\"\"
    def get_queryset(self):
        return super().get_queryset().filter(supprime_le__isnull=True)

class ManagerComplet(models.Manager):
    \"\"\"Permet aux auditeurs et administrateurs d'accéder aux données archivées.\"\"\"
    pass

class ModeleBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)
    cree_par = models.ForeignKey('accounts.Utilisateur', on_delete=models.RESTRICT, null=True, blank=True, related_name='+')
    
    # Soft-delete : non nul = ligne supprimée logiquement
    supprime_le = models.DateTimeField(null=True, blank=True, db_index=True)
    supprime_par = models.ForeignKey('accounts.Utilisateur', on_delete=models.RESTRICT, null=True, blank=True, related_name='+')

    objects = ManagerActif()       # Manager par défaut : filtre les supprimés
    tous_objets = ManagerComplet() # Manager pour restauration et audit légal

    class Meta:
        abstract = True  # Modèle abstrait : ne crée pas de table SQL 'ModeleBase'

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        \"\"\"Détourne la suppression destructive vers un archivage logique horodaté.\"\"\"
        self.supprime_le = timezone.now()
        self.supprime_par = utilisateur
        self.save(update_fields=['supprime_le', 'supprime_par', 'modifie_le'])"""
    story.append(make_code_box("apps/core/models/__init__.py (Le Socle Commun)", c12_base_code, styles))
    story.append(Spacer(1, 4))

    bias_c12 = [
        "<b>POURQUOI <code>on_delete=models.RESTRICT</code> ET JAMAIS <code>CASCADE</code> ?</b><br/>"
        "Dans les tutoriels pour débutants, on met toujours <code>CASCADE</code>. En entreprise, si un gestionnaire supprime "
        "un Projet par mégarde, <code>CASCADE</code> efface silencieusement en cascade 500 tâches, 200 incidents, 80 devis "
        "et toutes les factures associées !<br/>"
        "Avec <code>RESTRICT</code>, la base de données SQL lève une erreur et <b>interdit la suppression</b> tant qu'il subsiste des enregistrements "
        "liés. Vos données d'entreprise sont sanctuarisées.",
    ]
    story.append(make_callout("BIAS", "LE DANGER MORTEL DE CASCADE EN PRODUCTION", bias_c12, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 14 : CHAPITRE 13 - DÉCOUPLAGE SÉRIALISEURS DTO & DOUBLE VERROU
    # =========================================================================
    story.append(Paragraph("CHAPITRE 13 : Le Découplage des Sérialiseurs DTO &amp; Le Double Verrou", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Dissocier l'Entrée de la Sortie et Sécuriser aux Niveaux Global et Objet</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    analogy_c13 = [
        "<b>Pourquoi un seul Sérialiseur ne suffit plus en Entreprise :</b><br/>"
        "En lecture (GET), le client veut un JSON riche avec les noms complets des chantiers et des utilisateurs.<br/>"
        "En écriture (POST), le client n'envoie que des identifiants et des valeurs brutes.<br/>"
        "Vouloir faire les deux avec le même <code>ModelSerializer</code> crée des failles de sécurité et du code spaghetti. "
        "Nous créons deux <b>DTO</b> (Data Transfer Object - Objet de Transfert de Données) distincts : un pour l'entrée, un pour la sortie.",
    ]
    story.append(make_callout("ANALOGY", "DTO D'ENTRÉE VS DTO DE SORTIE", analogy_c13, styles))
    story.append(Spacer(1, 4))

    dto_code = """# Anatomie chirurgicale des deux DTOs :
# 1. DTO de Sortie : ModelSerializer pour formater la réponse JSON
class ProjetListSerializer(serializers.ModelSerializer):
    chef_nom = serializers.CharField(source="chef.nom_complet", read_only=True)
    class Meta:
        model = Projet
        fields = ["id", "nom", "ville", "budget_estime", "chef_nom"]

# 2. DTO d'Entrée : Serializer pur pour valider les données brutes
class ProjetCreateSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=150)
    ville = serializers.CharField(max_length=100, default="Abidjan")
    budget_estime = serializers.DecimalField(max_digits=12, decimal_places=2)
    # L'argument magique source="chef" charge l'instance Utilisateur en mémoire :
    chef_id = serializers.PrimaryKeyRelatedField(queryset=Utilisateur.objects.all(), source="chef")"""
    story.append(make_code_box("Exemple de Découplage DTO In / Out", dto_code, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("La Muraille de Sécurité RBAC à Double Verrou", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "En entreprise, vérifier que l'utilisateur est connecté ne suffit pas. Nous imposons deux verrous hermétiques :",
            styles["Body"],
        )
    )

    double_lock_code = """# apps/chantier/permissions.py
from rest_framework import permissions
from apps.core.permissions import RoleRequis, MembreDuProjet

class PeutGererProjet(permissions.BasePermission):
    # VERROU NIVEAU 1 : Rôle global requis au sein de l'entreprise
    def has_permission(self, request, view):
        return RoleRequis.pour('DIRECTEUR', 'CONDUCTEUR_TRAVAUX')().has_permission(request, view)

    # VERROU NIVEAU 2 : L'utilisateur est-il affecté à CE chantier spécifique ?
    def has_object_permission(self, request, view, obj):
        return MembreDuProjet().has_object_permission(request, view, obj)"""
    story.append(make_code_box("apps/chantier/permissions.py (Le Double Verrou)", double_lock_code, styles))
    story.append(Spacer(1, 4))

    bias_c13 = [
        "<b>LE PIÈGE INVISIBLE DE L'<code>APIView</code> :</b><br/>"
        "DRF exécute automatiquement <code>has_permission</code> sur toutes les vues.<br/>"
        "Cependant, dans une <code>APIView</code> personnalisée, DRF <b>n'exécute JAMAIS automatiquement</b> <code>has_object_permission</code> ! "
        "Si vous oubliez d'appeler explicitement <code>self.check_object_permissions(request, obj)</code> dans votre méthode de vue, "
        "le second verrou ne s'enclenche pas ! C'est pourquoi nous configurons également <code>get_permissions(self)</code> dynamiquement.",
    ]
    story.append(make_callout("BIAS", "LE PIÈGE DU CHECK_OBJECT_PERMISSIONS NON AUTOMATISÉ", bias_c13, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 15 : CHAPITRE 14 - LE CAS RÉEL : MODÈLE INCIDENTS DE CHANTIER
    # =========================================================================
    story.append(Paragraph("CHAPITRE 14 : Le Cas Réel d'Entreprise : API Incidents de Chantier", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Étape 1 : Modélisation Métier Robuste &amp; Enums TextChoices</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    scqa_c14 = [
        "<b>Situation :</b> Sur les chantiers de BTP gérés par SOUMAFE SARL, des incidents surviennent (intempéries, pannes d'engins, accidents du travail).<br/>"
        "<b>Complication :</b> Si un incident critique n'est pas documenté et résolu sous 24h, le chantier s'arrête avec des pénalités financières colossales.<br/>"
        "<b>Question :</b> Comment concevoir un endpoint hautement sécurisé pour déclarer et résoudre des incidents avec traçabilité intégrale ?<br/>"
        "<b>Answer :</b> Une architecture CQS complète avec soft-delete, transactions atomiques et documentation OpenAPI.",
    ]
    story.append(make_callout("SCQA", "GESTION ET TRAÇABILITÉ DES INCIDENTS", scqa_c14, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Modélisation avec Énumérations Strictes (TextChoices)", styles["SectionHeader"]))

    mod_inc_code = """# apps/chantier/models/incident.py
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import ModeleBase

class GraviteIncident(models.TextChoices):
    FAIBLE = "FAIBLE", _("Faible - Sans impact immédiat")
    MOYENNE = "MOYENNE", _("Moyenne - Ralentissement des travaux")
    CRITIQUE = "CRITIQUE", _("Critique - Arrêt immédiat / Danger corporel")

class StatutIncident(models.TextChoices):
    DECLARE = "DECLARE", _("Déclaré sur le terrain")
    EN_TRAITEMENT = "EN_TRAITEMENT", _("En cours de traitement")
    RESOLU = "RESOLU", _("Résolu avec action corrective")
    CLOTURE = "CLOTURE", _("Clôturé par la direction")

class IncidentChantier(ModeleBase):
    projet = models.ForeignKey("projets.Projet", on_delete=models.RESTRICT, related_name="incidents")
    lot = models.ForeignKey("projets.Lot", on_delete=models.RESTRICT, null=True, blank=True, related_name="incidents")
    titre = models.CharField(max_length=200, verbose_name=_("Titre"))
    description = models.TextField(verbose_name=_("Description détaillée"))
    gravite = models.CharField(max_length=20, choices=GraviteIncident.choices, default=GraviteIncident.MOYENNE, db_index=True)
    statut = models.CharField(max_length=20, choices=StatutIncident.choices, default=StatutIncident.DECLARE, db_index=True)
    date_survenance = models.DateTimeField(default=timezone.now)
    action_corrective = models.TextField(blank=True, default="", verbose_name=_("Action corrective apportée"))
    resolu_le = models.DateTimeField(null=True, blank=True)
    declare_par = models.ForeignKey("accounts.Utilisateur", on_delete=models.RESTRICT, related_name="incidents_declares")

    class Meta:
        verbose_name = _("Incident de chantier")
        ordering = ["-date_survenance"]

    def __str__(self):
        return f"[{self.gravite}] {self.titre} ({self.projet.nom})" """
    story.append(make_code_box("apps/chantier/models/incident.py", mod_inc_code, styles))
    story.append(Spacer(1, 4))

    chal_c14 = [
        "<b>Défi Stimulant #9 : Exportation & Migration Immédiate</b><br/>"
        "1. N'oubliez pas d'ajouter <code>from .incident import IncidentChantier, GraviteIncident, StatutIncident</code> dans <code>apps/chantier/models/__init__.py</code>.<br/>"
        "2. Lancez <code>python manage.py makemigrations</code> puis <code>python manage.py migrate</code>.<br/>"
        "Observez comment PostgreSQL crée la table avec la clé primaire UUID et les contraintes RESTRICT !",
    ]
    story.append(make_callout("CHALLENGE", "DÉFI STIMULANT #9 : LE MODÈLE EN PRODUCTION", chal_c14, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 16 : CHAPITRE 14 (SUITE) : SÉLECTEURS & SERVICES DU CAS RÉEL
    # =========================================================================
    story.append(Paragraph("CHAPITRE 14 (Suite) : Sélecteurs Purs &amp; Services Métier", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Étape 2 &amp; 3 : Séparation Hermétique entre Requêtes SQL et Mutations Métier</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    story.append(Paragraph("1. Le Sélecteur de Lecture Pure (Zéro Effet de Bord)", styles["SectionHeader"]))
    sel_inc_code = """# apps/chantier/selectors/incident.py
from apps.chantier.models.incident import IncidentChantier

def incidents_liste(*, projet_id=None, statut=None, gravite=None):
    # Élimination du problème N+1 via select_related pour joindre en une seule requête SQL :
    qs = IncidentChantier.objects.select_related("projet", "lot", "declare_par").all()
    if projet_id: qs = qs.filter(projet_id=projet_id)
    if statut:    qs = qs.filter(statut=statut)
    if gravite:   qs = qs.filter(gravite=gravite)
    return qs.order_by("-date_survenance")

def incident_par_id(incident_id):
    try:
        return IncidentChantier.objects.select_related("projet", "lot", "declare_par").get(id=incident_id)
    except (IncidentChantier.DoesNotExist, ValueError):
        return None"""
    story.append(make_code_box("apps/chantier/selectors/incident.py", sel_inc_code, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. Le Service d'Écriture Métier sous Transaction Atomique", styles["SectionHeader"]))
    srv_inc_code = """# apps/chantier/services/incident.py
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.chantier.models.incident import IncidentChantier, GraviteIncident, StatutIncident

@transaction.atomic
def creer_incident(*, projet, titre, description, declare_par, gravite=GraviteIncident.MOYENNE, lot=None, date_survenance=None):
    # Règle de Gestion RG-02 : Vérifier que le lot appartient bien à ce projet précis
    if lot is not None and lot.projet_id != projet.id:
        raise ValidationError({"lot": "Le lot sélectionné n'appartient pas au chantier spécifié."})
    
    incident = IncidentChantier(
        projet=projet, lot=lot, titre=titre.strip(), description=description.strip(),
        gravite=gravite, statut=StatutIncident.DECLARE,
        date_survenance=date_survenance or timezone.now(),
        declare_par=declare_par, cree_par=declare_par
    )
    incident.full_clean()  # Validation obligatoire des contraintes de modèle
    incident.save()
    return incident

@transaction.atomic
def resoudre_incident(*, incident, action_corrective, utilisateur):
    if not action_corrective.strip():
        raise ValidationError({"action_corrective": "Une action corrective documentée est obligatoire."})
    incident.statut = StatutIncident.RESOLU
    incident.action_corrective = action_corrective.strip()
    incident.resolu_le = timezone.now()
    # Optimisation SQL : update_fields n'écrit que les colonnes ciblées
    incident.save(update_fields=["statut", "action_corrective", "resolu_le", "modifie_le"])
    return incident"""
    story.append(make_code_box("apps/chantier/services/incident.py", srv_inc_code, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 17 : CHAPITRE 14 (SUITE) : VUES REST & ROUTAGE MULTI-TENANT
    # =========================================================================
    story.append(Paragraph("CHAPITRE 14 (Suite) : Vues API REST, Double Verrou &amp; Swagger UI", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Étape 4, 5 &amp; 6 : Le Contrôleur Mince et l'Intégration dans le Routage Multi-Tenant</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    perm_ser_code = """# apps/chantier/serializers/incident.py (DTOs Entrée / Sortie)
from rest_framework import serializers
from apps.chantier.models.incident import IncidentChantier, GraviteIncident
from apps.projets.models import Lot, Projet

class IncidentListSerializer(serializers.ModelSerializer):
    projet_nom = serializers.CharField(source="projet.nom", read_only=True)
    declare_par_nom = serializers.CharField(source="declare_par.nom_complet", read_only=True)
    class Meta:
        model = IncidentChantier
        fields = ["id", "titre", "gravite", "statut", "date_survenance", "projet_nom", "declare_par_nom", "resolu_le"]

class IncidentCreateSerializer(serializers.Serializer):
    projet_id = serializers.PrimaryKeyRelatedField(queryset=Projet.objects.all(), source="projet")
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source="lot", required=False, allow_null=True)
    titre = serializers.CharField(max_length=200)
    description = serializers.CharField()
    gravite = serializers.ChoiceField(choices=GraviteIncident.choices, default=GraviteIncident.MOYENNE)
    date_survenance = serializers.DateTimeField(required=False)"""
    story.append(make_code_box("apps/chantier/serializers/incident.py", perm_ser_code, styles))
    story.append(Spacer(1, 4))

    view_inc_full = """# apps/chantier/views/incident.py
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.chantier.selectors.incident import incidents_liste
from apps.chantier.serializers.incident import IncidentCreateSerializer, IncidentListSerializer
from apps.chantier.services.incident import creer_incident
from apps.core.pagination import PaginationStandard

class IncidentListCreateView(APIView):
    parser_classes = [JSONParser]
    pagination_class = PaginationStandard

    @extend_schema(summary="Lister les incidents de chantier", responses={200: IncidentListSerializer(many=True)})
    def get(self, request):
        qs = incidents_liste(projet_id=request.GET.get('projet'))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(IncidentListSerializer(page, many=True).data)

    @extend_schema(summary="Déclarer un nouvel incident", request=IncidentCreateSerializer, responses={201: IncidentListSerializer})
    def post(self, request):
        serializer = IncidentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incident = creer_incident(declare_par=request.user, **serializer.validated_data)
        return Response(IncidentListSerializer(incident).data, status=status.HTTP_201_CREATED)"""
    story.append(make_code_box("apps/chantier/views/incident.py", view_inc_full, styles))
    story.append(Spacer(1, 4))

    routing_box = [
        "<b>Routage Automatique Multi-Tenant dans CCD (Contrôle et Conduite Digitale) Digital :</b><br/>"
        "1. <b>Bifurcation des Plans d'URL :</b> <code>config/urls.py</code> gère l'accueil public, tandis que <code>config/urls_tenant.py</code> "
        "gère l'espace privé isolé de chaque entreprise cliente.<br/>"
        "2. Déclarez la route dans <code>apps/chantier/urls.py</code> : <code>path('incidents/', IncidentListCreateView.as_view(), name='incident-liste-creer')</code>.<br/>"
        "3. Dans <code>config/urls_tenant.py</code>, l'application est branchée sous <code>api/v1/</code> : <code>path('api/v1/', include('apps.chantier.urls'))</code>.<br/>"
        "4. Votre endpoint est immédiatement accessible sur <code>/api/v1/incidents/</code> et auto-documenté dans Swagger UI OpenAPI (Open Application Programming Interface) !",
    ]
    story.append(make_callout("SCQA", "LA TUYAUTERIE DU ROUTAGE MULTI-TENANT", routing_box, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 18 : CHAPITRE 15 - TESTS PYTEST (TDD) & DÉFINITION OF DONE
    # =========================================================================
    story.append(Paragraph("CHAPITRE 15 : Tests Automatisés (Pytest) &amp; Définition of Done (DoD)", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Phase 4 : TDD (Test-Driven Development), Validation Formelle &amp; Prévention des Régressions</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    analogy_c15 = [
        "<b>Le Filet de Sécurité du Trapéziste :</b><br/>"
        "Développer sans tests automatisés, c'est exécuter un saut périlleux sans filet de sécurité à 20 mètres de hauteur.<br/>"
        "En appliquant le <b>TDD</b> (Test-Driven Development - Développement Piloté par les Tests), chaque test unitaire "
        "devient un gardien infatigable qui vérifie 24h/24 qu'aucune régression n'a été introduite dans le code de production.",
    ]
    story.append(make_callout("ANALOGY", "LE CODE QUI SURVEILLE LE CODE", analogy_c15, styles))
    story.append(Spacer(1, 4))

    pytest_code = """# apps/chantier/tests/test_incidents_api.py
import pytest
from rest_framework import status
from apps.chantier.models.incident import GraviteIncident, IncidentChantier

@pytest.mark.django_db
class TestIncidentAPI:
    def test_creer_incident_valide_succes(self, client_conducteur, chantier_abidjan):
        \"\"\"Vérifie qu'un conducteur de travaux peut déclarer un incident valide.\"\"\"
        url = "/api/v1/incidents/"
        payload = {
            "projet_id": str(chantier_abidjan.id),
            "titre": "Fissure constatée sur le voile béton B2",
            "description": "Arrêt préventif de la zone en attente de l'avis du bureau d'études.",
            "gravite": GraviteIncident.CRITIQUE
        }
        response = client_conducteur.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert IncidentChantier.objects.count() == 1
        incident = IncidentChantier.objects.first()
        assert incident.titre == payload["titre"]
        assert incident.supprime_le is None  # Vérification du soft-delete actif

    def test_interdiction_creer_incident_lot_autre_projet(self, client_conducteur, chantier_abidjan, lot_autre_chantier):
        \"\"\"Vérifie le rejet HTTP 400 si le lot n'appartient pas au chantier spécifié.\"\"\"
        url = "/api/v1/incidents/"
        payload = {
            "projet_id": str(chantier_abidjan.id),
            "lot_id": str(lot_autre_chantier.id),
            "titre": "Incohérence projet/lot",
            "description": "Test de violation de la règle RG-02."
        }
        response = client_conducteur.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST"""
    story.append(make_code_box("apps/chantier/tests/test_incidents_api.py", pytest_code, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("La Grille d'Excellence : La Définition of Done (DoD)", styles["SectionHeader"]))
    dod_items = [
        "<b>La DoD (Definition of Done - Définition de Fini) d'un Endpoint d'Entreprise :</b><br/>"
        "1. <b>Architecture :</b> Zéro requête ORM directe dans la vue ; passage exclusif par Selector & Service.<br/>"
        "2. <b>Intégrité :</b> Le Service est sous <code>@transaction.atomic</code> et appelle <code>full_clean()</code>.<br/>"
        "3. <b>Sécurité :</b> Double verrou actif (Rôle Global + Affectation Projet) et test d'intrusion 403 validé.<br/>"
        "4. <b>Documentation :</b> Schéma OpenAPI Swagger documenté avec exemples via <code>@extend_schema</code>.<br/>"
        "5. <b>Qualité :</b> Couverture de tests Pytest $\\ge 90\\%$ avec cas nominal (201) et cas d'erreur (400, 403).",
    ]
    story.append(make_callout("SCQA", "LA GRILLE DE CONTRÔLE AVANT LIVRAISON", dod_items, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 19 : CHAPITRE 16 - BOUSSOLE MÉTACOGNITIVE DE DÉBOGAGE
    # =========================================================================
    story.append(Paragraph("CHAPITRE 16 : La Boussole Métacognitive : Guide de Débogage", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Diagnostic Rapide des Erreurs et Anti-Patterns Toxiques d'Entreprise</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    analogy_debug = [
        "<b>Dédramatiser l'Erreur : L'Erreur est une Information Précieuse (Dehaene & Pólya) :</b><br/>"
        "Un développeur novice panique quand le terminal s'affiche en rouge, copie le message au hasard sur internet "
        "ou teste des modifications frénétiques sans réfléchir (Agitation Système 1).<br/>"
        "<b>Un ingénieur expert applique l'heuristique de Pólya :</b> L'erreur n'est pas un échec, c'est le diagnostic "
        "le plus précis et le plus bienveillant que Python vous offre. Il vous indique la ligne exacte et la règle violée.",
    ]
    story.append(make_callout("ANALOGY", "L'ERREUR EST LE MEILLEUR PROFESSEUR DE L'INGÉNIEUR", analogy_debug, styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Le Tableau de Traduction des 6 Erreurs Django les Plus Fréquentes", styles["SectionHeader"]))

    err_table_data = [
        [
            Paragraph("<b>Message d'Erreur Django</b>", styles["TableHeader"]),
            Paragraph("<b>Ce que cela signifie réellement</b>", styles["TableHeader"]),
            Paragraph("<b>L'Action Corrective Immédiate</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<code>OperationalError: no such column</code>", styles["TableCellBold"]),
            Paragraph("Vous avez ajouté un champ dans <code>models.py</code> mais la migration n'a pas tourné.", styles["TableCell"]),
            Paragraph("Lancez <code>makemigrations</code> puis <code>migrate</code> dans le terminal.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>FieldError: Unknown field...</code>", styles["TableCellBold"]),
            Paragraph("Faute de frappe dans le nom d'un champ dans <code>fields</code> du sérialiseur ou de l'admin.", styles["TableCell"]),
            Paragraph("Vérifiez l'orthographe exacte dans <code>models.py</code>.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>DoesNotExist: matching query...</code>", styles["TableCellBold"]),
            Paragraph("Vous avez appelé <code>.get()</code> sur un ID qui n'existe pas en base.", styles["TableCell"]),
            Paragraph("Utilisez <code>get_object_or_404()</code> ou interceptez l'exception dans le sélecteur.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>TypeError: ... argument 'user'</code>", styles["TableCellBold"]),
            Paragraph("Oubli de passer un argument obligatoire dans la signature du service.", styles["TableCell"]),
            Paragraph("Vérifiez les paramètres nommés de votre fonction de service.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>CSRF Failed: cookie not set</code>", styles["TableCellBold"]),
            Paragraph("CSRF (Cross-Site Request Forgery - Falsification de Requête Inter-Sites) rejeté en session.", styles["TableCell"]),
            Paragraph("Passez par l'authentification par Token JWT (<code>Authorization: Bearer</code>).", styles["TableCell"]),
        ],
    ]
    err_t = Table(err_table_data, colWidths=[140, 195, 188])
    err_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(err_t)
    story.append(Spacer(1, 4))

    bias_debug = [
        "<b>LES 4 ANTI-PATTERNS TOXIQUES D'ENTREPRISE À PROSCRIRE :</b><br/>"
        "1. <b><code>serializer.save()</code> dans une vue :</b> Interdit. L'écriture appartient au Service.<br/>"
        "2. <b>Boucle N+1 :</b> Faire <code>for incident in incidents: print(incident.projet.nom)</code> sans <code>select_related('projet')</code>. Cela déclenche 1000 requêtes SQL au lieu d'une seule !<br/>"
        "3. <b>Importer <code>Request</code> dans un Service :</b> Détruit la testabilité et empêche l'exécution en tâche de fond.<br/>"
        "4. <b>Suppression physique directe en SQL :</b> Détruit la traçabilité légale exigée chez SOUMAFE SARL.",
    ]
    story.append(make_callout("BIAS", "LES 4 ANTI-PATTERNS À BANNIR DÉFINITIVEMENT", bias_debug, styles))
    story.append(PageBreak())

    # =========================================================================
    # PAGE 20 : CHAPITRE 17 - LE LEARNING WRAPPER D'INGÉNIERIE & CLÔTURE
    # =========================================================================
    story.append(Paragraph("CHAPITRE 17 : Le Learning Wrapper &amp; Looking Back Final", styles["ChapterHeader"]))
    story.append(Paragraph("<i>Phase 5 : Consolidation Métacognitive, Transfert Universel &amp; Growth Mindset</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 3))

    looking_back_final = [
        "<b>L'Analyse Rétrograde Finale (George Pólya - How to Solve It) :</b><br/>"
        "Regardez le chemin parcouru depuis la page 1 : vous êtes parti de l'analogie du restaurant sans aucune notion de Django, "
        "et vous comprenez désormais comment articuler des modèles abstraits, des migrations, des sélecteurs optimisés, "
        "des services transactionnels étanches et des tests d'intrusion 403 !<br/>"
        "<b>Le Transfert Universel :</b> Ce même patron architectural MECE (Mutually Exclusive, Collectively Exhaustive - Mutuellement Exclusif, Collectivement Exhaustif) "
        "s'applique à 100% des briques de CCD Digital :<br/>"
        "• Gestion des Matériels &amp; Engins de Chantier • Gestion des Pointages Ouvriers • Suivi des Bons de Commande<br/>"
        "Le moule est invariable : <code>ModeleBase</code> $\\rightarrow$ <code>selectors</code> $\\rightarrow$ <code>services</code> $\\rightarrow$ <code>serializers</code> $\\rightarrow$ <code>views</code> $\\rightarrow$ <code>tests</code>.",
    ]
    story.append(make_callout("LOOKINGBACK", "L'HEURISTIQUE DU LOOKING BACK ET LE TRANSFERT", looking_back_final, styles))
    story.append(Spacer(1, 5))

    story.append(Paragraph("Votre Carnet de Bord Réflexif (À Conserver Précieusement)", styles["SectionHeader"]))

    wrapper_full_data = [
        [Paragraph("<b>Question Métacognitive</b>", styles["TableHeader"]), Paragraph("<b>Votre Auto-Diagnostic en Entreprise</b>", styles["TableHeader"])],
        [
            Paragraph("1. <b>Diagnostic de Clarté</b><br/>Comprenez-vous la différence entre un sélecteur et un service ?", styles["TableCellBold"]),
            Paragraph("Un sélecteur ne fait que LIRE. Un service MODIFIE la base sous transaction atomique.", styles["TableCell"]),
        ],
        [
            Paragraph("2. <b>Chasse à la Régression</b><br/>Avez-vous testé le cas limite d'une donnée invalide ?", styles["TableCellBold"]),
            Paragraph("Vérifier qu'un test automatisé attend le code 400 Bad Request sur payload invalide.", styles["TableCell"]),
        ],
        [
            Paragraph("3. <b>Contrôle Anti-Fuite</b><br/>L'accès est-il protégé au niveau du projet ?", styles["TableCellBold"]),
            Paragraph("La permission <code>MembreDuProjet</code> a-t-elle été vérifiée sur l'objet ciblé ?", styles["TableCell"]),
        ],
        [
            Paragraph("4. <b>Découverte des Modèles</b><br/>Le modèle est-il déclaré dans <code>__init__.py</code> ?", styles["TableCellBold"]),
            Paragraph("Sans export explicite dans <code>models/__init__.py</code>, <code>makemigrations</code> ignore le modèle !", styles["TableCell"]),
        ],
    ]
    wrapper_t = Table(wrapper_full_data, colWidths=[240, 283])
    wrapper_t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6B21A8")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(wrapper_t)
    story.append(Spacer(1, 6))

    final_word = [
        "<b>Bravo pour avoir complété ce cursus d'ingénierie active !</b><br/>"
        "Vous disposez désormais de toutes les clés conceptuelles et pratiques pour concevoir, maintenir et faire évoluer "
        "des API professionnelles irréprochables au sein de <b>SOUMAFE SARL</b>. Faites de cette rigueur votre signature technique !",
    ]
    story.append(make_callout("CHALLENGE", "LE MOT DU LEAD ARCHITECTE", final_word, styles))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Ouvrage complet généré avec succès : {filename}")
    return filename


if __name__ == "__main__":
    out_pdf = "MANUEL_APPRENTISSAGE_DJANGO_ET_API.pdf"
    if len(sys.argv) > 1:
        out_pdf = sys.argv[1]
    generate_full_pdf(out_pdf)
