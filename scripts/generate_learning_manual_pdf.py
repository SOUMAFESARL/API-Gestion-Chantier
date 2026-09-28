"""Script de génération du Manuel d'Apprentissage Actif (PDF) pour le Backend CCD Digital.

Ce script utilise ReportLab pour compiler l'intégralité du guide technique
sous une forme pédagogique active basée sur 'How Learning Works' (Lovett et al., 2023)
et 'Deep Reasoning Engine' (Kahneman, Minto, Pólya, Meadows).
"""

import os
import sys
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
    KeepTogether,
    Preformatted,
    HRFlowable,
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Canvas à deux passes pour numéroter 'Page X sur Y' et ajouter les en-têtes et pieds de page."""

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
            # Ne pas afficher d'en-tête/pied sur la page de couverture
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#475569"))

        # En-tête courant
        self.drawString(
            36,
            A4[1] - 28,
            "CCD DIGITAL • MANUEL D'APPRENTISSAGE ACTIF : ARCHITECTURE API BACKEND",
        )
        self.setFont("Helvetica", 8)
        self.drawRightString(A4[0] - 36, A4[1] - 28, "SOUMAFE SARL")

        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(36, A4[1] - 32, A4[0] - 36, A4[1] - 32)

        # Pied de page courant
        self.line(36, 36, A4[0] - 36, 36)
        self.setFont("Helvetica", 8)
        self.drawString(
            36,
            24,
            "Sciences Cognitives (How Learning Works 2023) & Deep Reasoning Engine (Kahneman / Minto / Pólya / Meadows)",
        )
        page_str = f"Page {self._pageNumber} sur {page_count}"
        self.drawRightString(A4[0] - 36, 24, page_str)

        self.restoreState()


def get_custom_styles():
    """Initialise et retourne le dictionnaire des styles typographiques."""
    base_styles = getSampleStyleSheet()

    styles = {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#0F172A"),
            alignment=0,
            spaceAfter=12,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#334155"),
            spaceAfter=20,
        ),
        "CoverMeta": ParagraphStyle(
            "CoverMeta",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#0369A1"),
        ),
        "ModuleHeader": ParagraphStyle(
            "ModuleHeader",
            parent=base_styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "SectionHeader": ParagraphStyle(
            "SectionHeader",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "SubSectionHeader": ParagraphStyle(
            "SubSectionHeader",
            parent=base_styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#334155"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "CustomBody",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        ),
        "BodyBold": ParagraphStyle(
            "CustomBodyBold",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13.5,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        ),
        "Bullet": ParagraphStyle(
            "CustomBullet",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
            leftIndent=15,
            spaceAfter=3,
        ),
        "CalloutTitle": ParagraphStyle(
            "CalloutTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=4,
        ),
        "CalloutBody": ParagraphStyle(
            "CalloutBody",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            spaceAfter=4,
        ),
        "CodeText": ParagraphStyle(
            "CodeText",
            fontName="Courier",
            fontSize=6.8,
            leading=8.6,
            textColor=colors.HexColor("#0F172A"),
        ),
        "CodeHeader": ParagraphStyle(
            "CodeHeader",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#0369A1"),
            spaceAfter=2,
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
            alignment=1,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
        ),
    }
    return styles


def make_callout(box_type, title, text_items, styles, width=523):
    """Construit un encart stylisé avec bordure latérale et fond teinté selon la nature pédagogique."""
    configs = {
        "SCQA": {
            "bg": "#EFF6FF",
            "border": "#3B82F6",
            "title_color": "#1D4ED8",
            "icon": "🎯 CADRAGE SCQA (Minto) : ",
        },
        "BIAS": {
            "bg": "#FEF2F2",
            "border": "#EF4444",
            "title_color": "#B91C1C",
            "icon": "⚠️ PIÈGE SYSTÈME 1 & WYSIATI (Kahneman) : ",
        },
        "MECE": {
            "bg": "#F0FDF4",
            "border": "#22C55E",
            "title_color": "#15803D",
            "icon": "🧩 DÉCOMPOSITION MECE (Minto / Pólya) : ",
        },
        "PREMORTEM": {
            "bg": "#FAF5FF",
            "border": "#A855F7",
            "title_color": "#6B21A8",
            "icon": "⚡ PRE-MORTEM : SIMULATION DU CRASH (Kahneman) : ",
        },
        "PRACTICE": {
            "bg": "#F0FDFA",
            "border": "#14B8A6",
            "title_color": "#0F766E",
            "icon": "🔨 DÉFI ACTIF EN ZONE PROXIMALE (Ericsson / Bjork) : ",
        },
        "METACOR": {
            "bg": "#FFFBEB",
            "border": "#F59E0B",
            "title_color": "#B45309",
            "icon": "🔍 RÉFLEXION MÉTACOGNITIVE & LOOKING BACK (Pólya) : ",
        },
    }

    cfg = configs.get(box_type, configs["SCQA"])
    flowables = []

    # Titre de l'encart
    t_style = ParagraphStyle(
        f"CalloutT_{box_type}",
        parent=styles["CalloutTitle"],
        textColor=colors.HexColor(cfg["title_color"]),
    )
    flowables.append(Paragraph(f"<b>{cfg['icon']}{title}</b>", t_style))
    flowables.append(Spacer(1, 4))

    # Corps de texte de l'encart
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
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def make_code_box(filename, code_text, styles, width=523):
    """Construit un bloc de code propre avec en-tête de fichier et typographie monospace."""
    header = Paragraph(f"📄 <b>Fichier :</b> <code>{filename}</code>", styles["CodeHeader"])
    code_block = Preformatted(code_text.strip(), styles["CodeText"])

    content = [header, Spacer(1, 3), code_block]
    table = Table([[content]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94A3B8")),
                (
                    "LINEBEFORE",
                    (0, 0),
                    (0, -1),
                    3.0,
                    colors.HexColor("#0284C7"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def build_manual_pdf(filename="MANUEL_APPRENTISSAGE_API_BACKEND.pdf"):
    print(f"Génération du manuel d'apprentissage actif : {filename}...")
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=46,
    )
    styles = get_custom_styles()
    story = []

    # =========================================================================
    # PAGE DE COUVERTURE
    # =========================================================================
    story.append(Spacer(1, 20))
    story.append(
        Paragraph("PLATEFORME CCD DIGITAL • SOUMAFE SARL", styles["CoverMeta"])
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "MANUEL D'APPRENTISSAGE ACTIF &amp; DE MAÎTRISE PRATIQUE",
            styles["CoverTitle"],
        )
    )
    story.append(
        Paragraph(
            "Conception et Développement d'API Backend Hautement Robustes (Django 5 / DRF / Multi-Tenant)",
            ParagraphStyle(
                "Sub",
                parent=styles["CoverSubtitle"],
                fontName="Helvetica-Bold",
                fontSize=14,
                textColor=colors.HexColor("#1E3A8A"),
            ),
        )
    )
    story.append(
        Paragraph(
            "Un parcours d'ingénierie cognitive et d'application métier intégrale fondé sur les sciences de l'apprentissage "
            "(<i>How Learning Works</i>, 2nd Ed. 2023) et les 4 grands piliers du raisonnement universel "
            "(Kahneman, Minto, Pólya, Meadows).",
            styles["CoverSubtitle"],
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=2,
            color=colors.HexColor("#0284C7"),
            spaceBefore=5,
            spaceAfter=15,
        )
    )

    # Grille de méta-données
    meta_table_data = [
        [
            Paragraph("<b>Stack Technologique :</b>", styles["TableCellBold"]),
            Paragraph(
                "Python 3.12+ | Django 5.x | Django REST Framework (DRF) | PostgreSQL Multi-tenant",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph(
                "<b>Architecture Fondatrice :</b>", styles["TableCellBold"]
            ),
            Paragraph(
                "Clean Architecture Django (Services &amp; Selectors) | Isolation par Schéma Tenant",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph(
                "<b>Méthodologie Cognitive :</b>", styles["TableCellBold"]
            ),
            Paragraph(
                "Règle des 70/30 (Apprentissage Actif) | Diagnostic Système 1 | Décomposition MECE | Simulation Pre-Mortem",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<b>Public &amp; Finalité :</b>", styles["TableCellBold"]),
            Paragraph(
                "Ingénieurs &amp; Développeurs Backend CCD Digital — Du Concept Théorique au Déploiement Production",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<b>Version &amp; Date :</b>", styles["TableCellBold"]),
            Paragraph("Édition 1.0 — Septembre 2026", styles["TableCell"]),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[150, 373])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#E2E8F0"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 20))

    # Avertissement Pédagogique Fondateur
    guide_intro = [
        "<b>Ce document n'est pas un tutoriel passif.</b> Si vous vous contentez de lire ce manuel comme un roman, vous "
        "subirez l'<b>illusion de compétence</b> (<i>Fluency Illusion</i>) : tout vous semblera limpide à la lecture, mais vous resterez bloqué "
        "dès qu'il faudra concevoir une nouvelle API de zéro face à une page blanche en entreprise.",
        "Ce manuel a été rigoureusement conçu selon le cycle des <b>skills d'apprentissage agentique</b>. Chaque module "
        "démarre par un <b>cadrage SCQA</b> et un <b>dé-biaisage de vos intuitions</b>, vous expose l'architecture experte en "
        "<b>arborescence MECE</b>, décortique les <b>compétences composantes</b>, vous confronte à une <b>simulation de crash Pre-Mortem</b>, "
        "et se clôture par un <b>défi actif de mise en pratique</b>.",
    ]
    story.append(
        make_callout(
            "METACOR",
            "CONTRAT D'APPRENTISSAGE ACTIF (LA RÈGLE DES 70/30)",
            guide_intro,
            styles,
        )
    )

    story.append(PageBreak())

    # =========================================================================
    # MODULE 1 : CADRAGE SCQA & VISION D'ENSEMBLE ARCHITECTURALE
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 1 : Cadrage Stratégique, Architecture &amp; Prérequis",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Phase 1 du Cycle : Diagnostic des Prérequis &amp; Changement Conceptuel (Kahneman / Minto)</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    scqa_m1 = [
        "<b>S (Situation) :</b> L'entreprise SOUMAFE SARL développe CCD Digital, une plateforme SaaS de gestion de chantier multi-tenant destinée au secteur BTP.",
        "<b>C (Complication) :</b> Les tutoriels Django classiques préconisent des « Fat Models » (toute la logique dans <code>save()</code>) et des « Fat Views » monolithiques. En production multi-tenant, cette approche provoque des failles d'étanchéité de données, des requêtes N+1 catastrophiques et une dette technique ingérable.",
        "<b>Q (Question Fondamentale) :</b> Comment structurer le backend pour que chaque endpoint soit 100% sécurisé, traçable, modulaire et testable de façon totalement étanche ?",
        "<b>A (Réponse Architecturale) :</b> L'adoption stricte du patron <b>Clean Architecture (Services &amp; Selectors)</b>, couplé au <b>Socle Commun</b> (modèle de base unifié, soft-delete, et permissions cumulatives à 2 niveaux).",
    ]
    story.append(
        make_callout(
            "SCQA", "POURQUOI L'ARCHITECTURE CLASSIQUE ÉCHOUE", scqa_m1, styles
        )
    )
    story.append(Spacer(1, 8))

    bias_m1 = [
        "<b>Idée fausse fréquente n°1 (Système 1) :</b> <i>« Les ModelViewSets de DRF sont plus rapides à coder, utilisons-les partout ! »</i><br/>"
        "<b>Réalité cognitive d'entreprise :</b> Les ViewSets magiques cachent la logique métier dans des méthodes génériques. Dès que les règles BTP se complexifient (ex: validation d'un rapport par un tiers extérieur ou contrôle d'effectif), le ViewSet devient un monstre illisible et impossible à maintenir.",
        "<b>Idée fausse fréquente n°2 (WYSIATI) :</b> <i>« <code>obj.delete()</code> supprime la ligne en base de données. »</i><br/>"
        "<b>Réalité du Socle Commun (§3.1) :</b> La suppression physique est formellement INTERDITE. Tout appel à <code>delete()</code> doit être détourné en suppression logique (<i>Soft Delete</i> avec horodatage UTC et utilisateur responsable).",
    ]
    story.append(
        make_callout(
            "BIAS", "AUDIT DES FAUSSES CONCEPTIONS INTUITIVES", bias_m1, styles
        )
    )
    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "L'Arborescence MECE d'une Application Backend CCD Digital",
            styles["SectionHeader"],
        )
    )
    story.append(
        Paragraph(
            "Chaque module métier (ex: <code>apps/chantier/</code>) est rigoureusement découpé en 10 composants fonctionnels disjoints (norme MECE de Barbara Minto) :",
            styles["Body"],
        )
    )

    table_data_mece = [
        [
            Paragraph("<b>Couche / Dossier</b>", styles["TableHeader"]),
            Paragraph("<b>Responsabilité Unique</b>", styles["TableHeader"]),
            Paragraph(
                "<b>Interdiction Formelle (Garde-fous)</b>",
                styles["TableHeader"],
            ),
        ],
        [
            Paragraph("<code>models/</code>", styles["TableCellBold"]),
            Paragraph(
                "Structure de données, types, relations, héritage <code>ModeleBase</code>.",
                styles["TableCell"],
            ),
            Paragraph(
                "Zéro logique métier complexe. Pas de suppression physique.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>selectors/</code>", styles["TableCellBold"]),
            Paragraph(
                "Lecture pure (Read-Only). Optimisation SQL (<code>select_related</code>).",
                styles["TableCell"],
            ),
            Paragraph(
                "AUCUNE écriture, modification ou suppression en base.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>services/</code>", styles["TableCellBold"]),
            Paragraph(
                "Écriture métier (Write). Règles de gestion, transactions atomiques.",
                styles["TableCell"],
            ),
            Paragraph(
                "Ne manipule pas les requêtes HTTP (<code>request</code>).",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>serializers/</code>", styles["TableCellBold"]),
            Paragraph(
                "Validation des entrées HTTP &amp; transformation JSON sortant.",
                styles["TableCell"],
            ),
            Paragraph(
                "Ne prend pas de décisions métier lourdes (délègue aux services).",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>permissions.py</code>", styles["TableCellBold"]),
            Paragraph(
                "Contrôle d'accès à 2 niveaux : Rôle Global + Assignation Projet.",
                styles["TableCell"],
            ),
            Paragraph(
                "Un rôle global seul ne donne JAMAIS accès à un chantier.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>views/</code>", styles["TableCellBold"]),
            Paragraph(
                "Contrôleur HTTP mince : dispatch verbes, codes HTTP, Swagger.",
                styles["TableCell"],
            ),
            Paragraph(
                "Ne fait aucun calcul métier ni requête SQL directe.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>urls.py</code>", styles["TableCellBold"]),
            Paragraph(
                "Routage des endpoints branchés sous <code>/api/v1/</code> dans le tenant.",
                styles["TableCell"],
            ),
            Paragraph(
                "Ne pas oublier d'inclure dans <code>config/urls_tenant.py</code>.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<code>tests/</code>", styles["TableCellBold"]),
            Paragraph(
                "Tests d'intégration Pytest avec client multi-tenant authentifié.",
                styles["TableCell"],
            ),
            Paragraph(
                "Ne jamais merger sans 100% des tests au vert.",
                styles["TableCell"],
            ),
        ],
    ]
    mece_table = Table(table_data_mece, colWidths=[100, 220, 203])
    mece_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#E2E8F0"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(mece_table)

    story.append(PageBreak())

    # =========================================================================
    # MODULE 2 : PERSISTANCE ET SOCLE COMMUN (MODÈLE & MIGRATIONS)
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 2 : La Persistance &amp; Le Socle Commun (Modèles)",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Phase 2 &amp; 3 du Cycle : Décomposition aux Invariants de George Pólya &amp; Échafaudage de Maîtrise</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    polya_m2 = [
        "Face à l'exigence métier de concevoir un système de gestion des <b>Incidents de Chantier</b> (aléas de sécurité, pannes, retards), appliquons l'analyse des invariants de Pólya :",
        "• <b>Données connues ($D$) :</b> Chaque incident est rattaché à un <code>Projet</code> obligatoire, éventuellement à un <code>Lot</code> spécifique, possède un déclarant, une gravité (Faible/Moyenne/Critique) et un statut.",
        "• <b>Contraintes absolues ($C$) :</b> Pas de suppression physique (Socle §3.1), traçabilité de l'auteur (§2.4), dates en TIMESTAMPTZ UTC (§1.2), et clé primaire UUID générée côté client.",
        "• <b>Inconnue à modéliser ($x$) :</b> La classe <code>IncidentChantier</code> qui hérite obligatoirement de <code>ModeleBase</code>.",
    ]
    story.append(
        make_callout(
            "MECE",
            "ANALYSE DES INVARIANTS STRUCTURELS (PÓLYA)",
            polya_m2,
            styles,
        )
    )
    story.append(Spacer(1, 8))

    model_code = """import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import ModeleBase

class GraviteIncident(models.TextChoices):
    FAIBLE = "FAIBLE", _("Faible - Sans impact immédiat")
    MOYENNE = "MOYENNE", _("Moyenne - Ralentissement")
    CRITIQUE = "CRITIQUE", _("Critique - Arrêt des travaux / Danger")

class StatutIncident(models.TextChoices):
    DECLARE = "DECLARE", _("Déclaré")
    EN_TRAITEMENT = "EN_TRAITEMENT", _("En cours de traitement")
    RESOLU = "RESOLU", _("Résolu")
    CLOTURE = "CLOTURE", _("Clôturé")

class IncidentChantier(ModeleBase):
    projet = models.ForeignKey("projets.Projet", on_delete=models.RESTRICT, related_name="incidents")
    lot = models.ForeignKey("projets.Lot", on_delete=models.RESTRICT, null=True, blank=True, related_name="incidents")
    titre = models.CharField(_("titre"), max_length=200)
    description = models.TextField(_("description"))
    gravite = models.CharField(_("gravité"), max_length=20, choices=GraviteIncident.choices, default=GraviteIncident.MOYENNE, db_index=True)
    statut = models.CharField(_("statut"), max_length=20, choices=StatutIncident.choices, default=StatutIncident.DECLARE, db_index=True)
    date_survenance = models.DateTimeField(_("date"), default=timezone.now)
    declare_par = models.ForeignKey("accounts.Utilisateur", on_delete=models.RESTRICT, related_name="incidents_declares")
    resolu_le = models.DateTimeField(_("résolu le"), null=True, blank=True)
    action_corrective = models.TextField(_("action corrective"), blank=True, default="")

    class Meta:
        verbose_name = _("incident de chantier")
        ordering = ["-date_survenance", "-cree_le"]
        indexes = [models.Index(fields=["projet", "statut"])]"""

    story.append(
        make_code_box(
            "apps/chantier/models/incident.py", model_code, styles, width=523
        )
    )
    story.append(Spacer(1, 8))

    prem_m2 = [
        "<b>Scénario de Crash :</b> Un développeur utilise <code>on_delete=models.CASCADE</code> au lieu de <code>models.RESTRICT</code> sur la clé étrangère <code>projet</code>.",
        "<b>Conséquence Mortelle en Production :</b> Si un utilisateur désactive ou nettoie un projet de test, la suppression physique en cascade supprime instantanément 18 mois d'historique d'incidents, de litiges juridiques et de rapports d'assurance de l'entreprise. <b>Règle : Toujours <code>RESTRICT</code> sur les relations vitales.</b>",
    ]
    story.append(
        make_callout(
            "PREMORTEM",
            "POURQUOI LE CASCADE EST INTERDIT DANS LE SOCLE COMMUN",
            prem_m2,
            styles,
        )
    )
    story.append(Spacer(1, 8))

    practice_m2 = [
        "<b>Question de mise en pratique active :</b><br/>"
        "Pourquoi n'avons-nous pas défini de champ <code>id</code>, <code>cree_le</code> ou <code>cree_par</code> dans la classe <code>IncidentChantier</code> ?",
        "<i>Indice métacognitif :</i> Consultez l'héritage de <code>ModeleBase</code> dans <code>apps/core/models/__init__.py</code>. Quels sont les deux managers par défaut fournis ?",
    ]
    story.append(
        make_callout(
            "PRACTICE", "DÉFI ACTIF #1 : L'HÉRITAGE DU SOCLE", practice_m2, styles
        )
    )

    story.append(PageBreak())

    # =========================================================================
    # MODULE 3 (PARTIE 1) : LES SÉLECTEURS (SELECTORS/) - LECTURE OPTIMISÉE
    # =========================================================================
    story.append(Paragraph("MODULE 3 (Partie 1) : Les Sélecteurs (selectors/)", styles["ModuleHeader"]))
    story.append(Paragraph("<i>Phase 3 du Cycle : L'Art de la Lecture Pure &amp; Élimination Définitive du N+1 Queries</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("La Règle d'Or de la Couche de Sélection", styles["SectionHeader"]))
    story.append(Paragraph(
        "Un sélecteur ne fait <b>qu'une seule chose</b> : exécuter des requêtes de lecture optimisées en base de données. "
        "Il ne mute JAMAIS l'état, n'écrit aucune ligne et ne reçoit jamais d'objet HTTP <code>request</code>. "
        "Il retourne toujours un <code>QuerySet</code> paresseux (<i>lazy</i>) afin de permettre à la couche vue de le filtrer ou de le paginer sans surcoût mémoire.",
        styles["Body"]
    ))

    selector_code = """# apps/chantier/selectors/incident.py
from uuid import UUID
from django.db.models import QuerySet
from apps.chantier.models.incident import IncidentChantier

def incidents_liste(
    *,
    projet_id: UUID | str | None = None,
    statut: str | None = None,
    gravite: str | None = None,
    date_apres=None
) -> QuerySet[IncidentChantier]:
    \"\"\"Retourne la liste des incidents avec jointures SQL préchauffées.\"\"\"
    # Préchauffage des relations vitales en une seule requête SQL JOIN
    qs = IncidentChantier.objects.select_related("projet", "lot", "declare_par").all()
    
    if projet_id:
        qs = qs.filter(projet_id=projet_id)
    if statut:
        qs = qs.filter(statut=statut)
    if gravite:
        qs = qs.filter(gravite=gravite)
    if date_apres:
        qs = qs.filter(date_survenance__gte=date_apres)

    return qs.order_by("-date_survenance")

def incident_par_id(incident_id: UUID | str) -> IncidentChantier | None:
    \"\"\"Récupère un incident unique ou renvoie None sans lever d'exception.\"\"\"
    try:
        return IncidentChantier.objects.select_related("projet", "lot", "declare_par").get(id=incident_id)
    except (IncidentChantier.DoesNotExist, ValueError):
        return None"""

    story.append(make_code_box("apps/chantier/selectors/incident.py", selector_code, styles, width=523))
    story.append(Spacer(1, 8))

    sql_box = [
        "<b>select_related (SQL JOIN) :</b> À utiliser pour les clés étrangères simples (<code>ForeignKey</code>, <code>OneToOne</code>). Exécute un <code>INNER JOIN</code> ou <code>LEFT JOIN</code> unique. Dans notre sélecteur ci-dessus, <code>projet</code>, <code>lot</code> et <code>declare_par</code> sont rapatriés en 1 seule requête au lieu de 301 requêtes pour une liste de 100 incidents !",
        "<b>prefetch_related (SQL IN) :</b> À utiliser pour les relations plusieurs-à-plusieurs (<code>ManyToManyField</code>) ou inverses (<code>reverse ForeignKey</code>). Exécute une 2e requête avec <code>WHERE id IN (...)</code> et assemble les objets en mémoire Python.",
    ]
    story.append(make_callout("MECE", "LA BIBLE DE L'OPTIMISATION SQL (N+1 QUERIES)", sql_box, styles))
    story.append(Spacer(1, 8))

    practice_m3a = [
        "<b>Question d'auto-évaluation active :</b><br/>"
        "Que se passerait-il si vous appeliez <code>list(incidents_liste())</code> à l'intérieur du sélecteur au lieu de retourner le QuerySet brut ?",
        "<i>Réponse attendue :</i> Vous forceriez l'évaluation immédiate de la requête SQL en chargeant 100% des lignes en mémoire RAM, détruisant tout le bénéfice de la pagination ultérieure dans la vue !",
    ]
    story.append(make_callout("PRACTICE", "DÉFI ACTIF #2A : QUERYSETS PARESSEUX", practice_m3a, styles))

    story.append(PageBreak())

    # =========================================================================
    # MODULE 3 (PARTIE 2) : LES SERVICES (SERVICES/) - ÉCRITURE & ATOMICITÉ
    # =========================================================================
    story.append(Paragraph("MODULE 3 (Partie 2) : Les Services (services/)", styles["ModuleHeader"]))
    story.append(Paragraph("<i>Phase 3 &amp; 4 : Le Sanctuaire Métier, Règles de Gestion &amp; Transactions Atomiques</i>", styles["CoverMeta"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("La Règle d'Or de la Couche de Service", styles["SectionHeader"]))
    story.append(Paragraph(
        "Toutes les mutations de la base de données (création, mise à jour, changement d'état, résolution, suppression logique) "
        "sont <b>strictement concentrées ici</b>. Chaque service est décoré de <code>@transaction.atomic</code> et applique "
        "les règles de gestion (RG) de l'entreprise avant d'enregistrer les données.",
        styles["Body"]
    ))

    service_code = """# apps/chantier/services/incident.py
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.chantier.models.incident import IncidentChantier, GraviteIncident, StatutIncident

@transaction.atomic
def creer_incident(*, projet, titre, description, declare_par, gravite=GraviteIncident.MOYENNE, lot=None, date_survenance=None) -> IncidentChantier:
    \"\"\"Crée un incident après validation stricte des règles métier.\"\"\"
    # Règle RG-02 : Cohérence spatiale du chantier
    if lot is not None and lot.projet_id != projet.id:
        raise ValidationError({\"lot\": \"Le lot sélectionné n'appartient pas au chantier spécifié.\"})
    
    incident = IncidentChantier(
        projet=projet, lot=lot, titre=titre.strip(), description=description.strip(),
        gravite=gravite, statut=StatutIncident.DECLARE,
        date_survenance=date_survenance or timezone.now(),
        declare_par=declare_par, cree_par=declare_par
    )
    incident.full_clean()
    incident.save()
    return incident

@transaction.atomic
def resoudre_incident(*, incident: IncidentChantier, action_corrective: str, utilisateur) -> IncidentChantier:
    \"\"\"Résout un incident en exigeant la consignation d'une action corrective.\"\"\"
    if not action_corrective.strip():
        raise ValidationError({\"action_corrective\": \"Une action corrective documentée est obligatoire.\"})
    incident.statut = StatutIncident.RESOLU
    incident.action_corrective = action_corrective.strip()
    incident.resolu_le = timezone.now()
    incident.save(update_fields=[\"statut\", \"action_corrective\", \"resolu_le\", \"modifie_le\"])
    return incident

@transaction.atomic
def supprimer_incident(*, incident: IncidentChantier, utilisateur) -> None:
    \"\"\"Suppression logique sécurisée (Socle Commun §3.1).\"\"\"
    incident.delete(utilisateur=utilisateur)"""

    story.append(make_code_box("apps/chantier/services/incident.py", service_code, styles, width=523))
    story.append(Spacer(1, 8))

    prem_m3 = [
        "<b>Scénario de Crash en Production :</b> Un service exécute deux écritures : 1) Enregistrer l'incident, 2) Mettre à jour les statistiques de sécurité du chantier. Le serveur subit une micro-coupure de courant entre les deux requêtes.",
        "<b>Sans @transaction.atomic :</b> La première écriture est persistée, la seconde avorte. La base de données de l'entreprise est corrompue et les tableaux de bord affichent des bilans faux.",
        "<b>Avec @transaction.atomic :</b> Le moteur PostgreSQL annule automatiquement la première écriture (Rollback). Aucune donnée corrompue ne peut subsister.",
    ]
    story.append(make_callout("PREMORTEM", "L'ABSENCE DE TRANSACTION ATOMIQUE ET CORRUPTION D'ÉTAT", prem_m3, styles))
    story.append(Spacer(1, 8))

    practice_m3b = [
        "<b>Défi d'écriture active :</b><br/>"
        "Observez l'appel <code>incident.save(update_fields=[...])</code> dans <code>resoudre_incident</code>. Pourquoi est-il vital de préciser <code>update_fields</code> plutôt qu'un <code>incident.save()</code> global ?",
        "<i>Réflexion attendue :</i> Éviter les écrasements concurrents (Race Conditions) ! Si un autre utilisateur modifiait la description au même instant, un <code>save()</code> complet écraserait sa modification.",
    ]
    story.append(make_callout("PRACTICE", "DÉFI ACTIF #2B : CONCURRENCE ET UPDATE_FIELDS", practice_m3b, styles))

    story.append(PageBreak())

    # =========================================================================
    # MODULE 4 : SÉCURITÉ & PERMISSIONS À DOUBLE NIVEAU
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 4 : Sécurité &amp; Permissions à Double Niveau",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Socle Commun §2.3 : Contrôle Cumulatif Inviolable (Rôle Global + Affectation Projet)</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    sec_principle = [
        "<b>Règle de Gestion Fondatrice (RG-01) :</b> Le rôle global seul ne donne accès à RIEN.",
        "Pour agir sur une ressource de chantier, deux verrous doivent être franchis <b>simultanément</b> :",
        "• <b>Niveau 1 (Rôle Global) :</b> L'utilisateur possède-t-il la qualification professionnelle requise (ex: Conducteur de Travaux, Chef de Chantier, Admin) ? Géré par <code>RoleRequis.pour(...)</code>.",
        "• <b>Niveau 2 (Appartenance Projet) :</b> L'utilisateur fait-il partie de l'équipe officiellement affectée à CE chantier précis ? Géré par <code>MembreDuProjet()</code>.",
        "Si un utilisateur tente de modifier l'identifiant du projet dans l'URL pour inspecter un chantier voisin, il reçoit immédiatement un code <b>403 FORBIDDEN</b>, sans aucune fuite de métadonnées.",
    ]
    story.append(
        make_callout(
            "MECE",
            "LE DOUBLE VERROU DE SÉCURITÉ DU SOCLE COMMUN",
            sec_principle,
            styles,
        )
    )
    story.append(Spacer(1, 8))

    perm_code = """# apps/chantier/permissions.py
from rest_framework import permissions
from apps.core.enums import RoleGlobal
from apps.core.permissions import RoleRequis, MembreDuProjet

class PeutConsulterIncidents(permissions.BasePermission):
    \"\"\"Lecture : l'utilisateur doit obligatoirement être affecté au projet.\"\"\"
    def has_object_permission(self, request, view, obj) -> bool:
        return MembreDuProjet().has_object_permission(request, view, obj.projet)

class PeutGererIncidents(permissions.BasePermission):
    \"\"\"Création / Mutation : Réservée au management technique de ce chantier.\"\"\"
    ROLES_AUTORISES = (
        RoleGlobal.CHEF_PROJET,
        RoleGlobal.CONDUCTEUR_TRAVAUX,
        RoleGlobal.CHEF_CHANTIER,
        RoleGlobal.ADMIN,
    )

    def has_permission(self, request, view) -> bool:
        # Niveau 1 : Rôle global valide
        return RoleRequis.pour(*self.ROLES_AUTORISES)().has_permission(request, view)

    def has_object_permission(self, request, view, obj) -> bool:
        # Niveau 2 : Affectation au projet
        return MembreDuProjet().has_object_permission(request, view, obj.projet)"""

    story.append(
        make_code_box(
            "apps/chantier/permissions.py", perm_code, styles, width=523
        )
    )
    story.append(Spacer(1, 8))

    practice_m4 = [
        "<b>Exercice de Pentesting Mental :</b><br/>"
        "Un utilisateur connecté a le rôle global de <i>Directeur Général (DG)</i>. Il appelle l'endpoint <code>PATCH /api/v1/incidents/&lt;uuid&gt;/</code> pour clôturer un incident.",
        "1. Franchit-il le Niveau 1 défini dans <code>PeutGererIncidents</code> ci-dessus ?<br/>"
        "2. Que se passe-t-il s'il n'est pas expressément listé dans la table <code>ProjetMembre</code> du chantier ciblé ?<br/>"
        "<i>Réflexion attendue :</i> Observez la liste <code>ROLES_AUTORISES</code>. Le rôle DG n'y figure pas ! Même le patron de l'entreprise ne peut pas altérer directement la conduite de travaux sans passer par les délégations formelles.",
    ]
    story.append(
        make_callout(
            "PRACTICE", "DÉFI ACTIF #2 : AUDIT D'AUTORISATION", practice_m4, styles
        )
    )

    story.append(PageBreak())

    # =========================================================================
    # MODULE 5 : SÉRIALISEURS DRF & FILTRES DE RECHERCHE
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 5 : Sérialiseurs DRF &amp; Filtres de Recherche",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Spécialisation des DTO (Data Transfer Objects) &amp; Découplage Entrée/Sortie</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    story.append(
        Paragraph(
            "Pourquoi un unique ModelSerializer est un Anti-Pattern en Entreprise",
            styles["SectionHeader"],
        )
    )
    story.append(
        Paragraph(
            "Un tableau de bord listant 100 incidents a besoin d'objets allégés. Une vue détaillée a besoin de tous les horodatages "
            "et de l'audit. Un formulaire de déclaration ne doit accepter que les champs modifiables par l'utilisateur. "
            "Nous créons donc systématiquement **4 sérialiseurs spécialisés** :",
            styles["Body"],
        )
    )

    serializer_code = """# apps/chantier/serializers/incident.py
from rest_framework import serializers
from apps.chantier.models.incident import IncidentChantier, GraviteIncident
from apps.projets.models import Lot, Projet

class IncidentListSerializer(serializers.ModelSerializer):
    \"\"\"Sérialiseur allégé pour l'affichage en tableau de bord.\"\"\"
    projet_nom = serializers.CharField(source=\"projet.nom\", read_only=True)
    lot_libelle = serializers.CharField(source=\"lot.libelle\", read_only=True, default=None)
    declare_par_nom = serializers.CharField(source=\"declare_par.nom_complet\", read_only=True)

    class Meta:
        model = IncidentChantier
        fields = [\"id\", \"titre\", \"gravite\", \"statut\", \"date_survenance\", \"projet_nom\", \"lot_libelle\", \"declare_par_nom\", \"resolu_le\"]

class IncidentDetailSerializer(serializers.ModelSerializer):
    \"\"\"Sérialiseur complet avec audit et action corrective.\"\"\"
    class Meta:
        model = IncidentChantier
        fields = [\"id\", \"titre\", \"description\", \"gravite\", \"statut\", \"date_survenance\", \"action_corrective\", \"resolu_le\", \"cree_le\", \"modifie_le\"]

class IncidentCreateSerializer(serializers.Serializer):
    \"\"\"Validation stricte de la charge utile (payload) entrante.\"\"\"
    projet_id = serializers.PrimaryKeyRelatedField(queryset=Projet.objects.all(), source=\"projet\")
    lot_id = serializers.PrimaryKeyRelatedField(queryset=Lot.objects.all(), source=\"lot\", required=False, allow_null=True)
    titre = serializers.CharField(max_length=200)
    description = serializers.CharField()
    gravite = serializers.ChoiceField(choices=GraviteIncident.choices, default=GraviteIncident.MOYENNE)
    date_survenance = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if attrs.get(\"lot\") and attrs[\"lot\"].projet_id != attrs[\"projet\"].id:
            raise serializers.ValidationError({\"lot_id\": \"Ce lot n'appartient pas au chantier spécifié.\"})
        return attrs"""

    story.append(
        make_code_box(
            "apps/chantier/serializers/incident.py",
            serializer_code,
            styles,
            width=523,
        )
    )
    story.append(Spacer(1, 8))

    filter_code = """# apps/chantier/filters.py
import django_filters
from apps.chantier.models.incident import IncidentChantier, GraviteIncident, StatutIncident

class IncidentChantierFilter(django_filters.FilterSet):
    projet = django_filters.UUIDFilter(field_name=\"projet_id\")
    gravite = django_filters.ChoiceFilter(choices=GraviteIncident.choices)
    statut = django_filters.ChoiceFilter(choices=StatutIncident.choices)
    date_apres = django_filters.DateTimeFilter(field_name=\"date_survenance\", lookup_expr=\"gte\")

    class Meta:
        model = IncidentChantier
        fields = [\"projet\", \"gravite\", \"statut\", \"date_apres\"]"""

    story.append(
        make_code_box(
            "apps/chantier/filters.py", filter_code, styles, width=523
        )
    )

    story.append(PageBreak())

    # =========================================================================
    # MODULE 6 : LES VUES API REST & DOCUMENTATION SWAGGER
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 6 : Les Vues API REST, Pagination &amp; Swagger",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Le Contrôleur HTTP Mince &amp; la Documentation Automatisée OpenAPI (drf-spectacular)</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    view_principle = [
        "<b>Règle de Conception d'une APIView Experte :</b>",
        "1. <b>Parser JSON explicite :</b> Toujours déclarer <code>parser_classes = [JSONParser]</code>.",
        "2. <b>Pagination Standardisée :</b> Toujours brancher <code>PaginationStandard</code> sur les listes.",
        "3. <b>Délégation Totale :</b> GET délègue aux <code>selectors</code>, POST/PATCH délèguent aux <code>services</code>.",
        "4. <b>Documentation Intégrée :</b> Chaque méthode HTTP porte l'annotation <code>@extend_schema</code> pour alimenter automatiquement Swagger UI (<code>/api/v1/docs/</code>).",
    ]
    story.append(
        make_callout(
            "SCQA", "ANATOMIE D'UNE VUE API CONFORME", view_principle, styles
        )
    )
    story.append(Spacer(1, 8))

    view_code = """# apps/chantier/views/incident.py
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.chantier.filters import IncidentChantierFilter
from apps.chantier.permissions import PeutConsulterIncidents, PeutGererIncidents
from apps.chantier.selectors.incident import incident_par_id, incidents_liste
from apps.chantier.serializers.incident import IncidentCreateSerializer, IncidentDetailSerializer, IncidentListSerializer
from apps.chantier.services.incident import creer_incident, resoudre_incident, supprimer_incident
from apps.core.pagination import PaginationStandard

class IncidentListCreateView(APIView):
    parser_classes = [JSONParser]
    pagination_class = PaginationStandard

    def get_permissions(self):
        if self.request.method == \"POST\":
            return [IsAuthenticated(), PeutGererIncidents()]
        return [IsAuthenticated(), PeutConsulterIncidents()]

    @extend_schema(summary=\"Lister les incidents\", responses={200: IncidentListSerializer(many=True)})
    def get(self, request):
        qs = incidents_liste()
        filtre = IncidentChantierFilter(request.GET, queryset=qs)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(filtre.qs, request)
        return paginator.get_paginated_response(IncidentListSerializer(page, many=True).data)

    @extend_schema(summary=\"Déclarer un incident\", request=IncidentCreateSerializer, responses={201: IncidentDetailSerializer})
    def post(self, request):
        serializer = IncidentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incident = creer_incident(declare_par=request.user, **serializer.validated_data)
        return Response(IncidentDetailSerializer(incident).data, status=status.HTTP_201_CREATED)"""

    story.append(
        make_code_box(
            "apps/chantier/views/incident.py", view_code, styles, width=523
        )
    )
    story.append(Spacer(1, 8))

    url_code = """# apps/chantier/urls.py
from django.urls import path
from apps.chantier.views.incident import IncidentListCreateView

app_name = \"chantier\"
urlpatterns = [
    path(\"incidents/\", IncidentListCreateView.as_view(), name=\"incident-liste-creer\"),
]
# Ce fichier est automatiquement monté sous /api/v1/ dans config/urls_tenant.py :
# path(\"api/v1/\", include(\"apps.chantier.urls\"))"""

    story.append(
        make_code_box("apps/chantier/urls.py", url_code, styles, width=523)
    )

    story.append(PageBreak())

    # =========================================================================
    # MODULE 7 : TESTS AUTOMATISÉS ET DÉFINITION OF DONE
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 7 : Tests Automatisés (Pytest) &amp; Définition of Done",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Validation Empirique de la Robustesse &amp; Intégration Continue (DoD)</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    test_code = """# apps/chantier/tests/test_api_incidents.py
import pytest
from rest_framework import status
from apps.chantier.models.incident import IncidentChantier, GraviteIncident

@pytest.mark.django_db
class TestIncidentAPI:
    def test_creation_incident_nominale(self, client_authentifie, projet_test, conducteur_travaux):
        client_authentifie.force_authenticate(user=conducteur_travaux)
        payload = {
            \"projet_id\": str(projet_test.id),
            \"titre\": \"Panne Grue G1\",
            \"description\": \"Coupure d'alimentation sur le treuil principal.\",
            \"gravite\": GraviteIncident.CRITIQUE,
        }
        res = client_authentifie.post(\"/api/v1/incidents/\", payload, format=\"json\")
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data[\"titre\"] == \"Panne Grue G1\"
        assert IncidentChantier.objects.filter(id=res.data[\"id\"]).exists()

    def test_rejet_si_non_membre_du_projet(self, client_authentifie, projet_autre_entreprise, conducteur_travaux):
        client_authentifie.force_authenticate(user=conducteur_travaux)
        payload = {\"projet_id\": str(projet_autre_entreprise.id), \"titre\": \"Intrusion\", \"description\": \"Test\"}
        res = client_authentifie.post(\"/api/v1/incidents/\", payload, format=\"json\")
        # La muraille de sécurité Niveau 2 doit immédiatement bloquer la requête
        assert res.status_code == status.HTTP_403_FORBIDDEN"""

    story.append(
        make_code_box(
            "apps/chantier/tests/test_api_incidents.py",
            test_code,
            styles,
            width=523,
        )
    )
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "Checklist de Conformité Strict avant Mise en Production (DoD)",
            styles["SectionHeader"],
        )
    )

    dod_data = [
        [
            Paragraph("<b>Jalon de Contrôle</b>", styles["TableHeader"]),
            Paragraph("<b>Exigence Technique</b>", styles["TableHeader"]),
            Paragraph("<b>Validation</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("1. Héritage Socle", styles["TableCellBold"]),
            Paragraph(
                "Le modèle hérite de <code>ModeleBase</code> (UUID, dates UTC, audit).",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("2. Zéro Delete Physique", styles["TableCellBold"]),
            Paragraph(
                "La suppression appelle <code>delete(utilisateur=...)</code> (Soft-delete).",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("3. Optimisation SQL", styles["TableCellBold"]),
            Paragraph(
                "Le sélecteur utilise <code>select_related</code> (Zéro requête N+1).",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("4. Atomicité Écriture", styles["TableCellBold"]),
            Paragraph(
                "Toute mutation dans <code>services/</code> est décorée de <code>@transaction.atomic</code>.",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("5. Sécurité 2 Niveaux", styles["TableCellBold"]),
            Paragraph(
                "La vue contrôle <code>RoleGlobal</code> ET <code>MembreDuProjet</code>.",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("6. Documentation Swagger", styles["TableCellBold"]),
            Paragraph(
                "Chaque méthode porte <code>@extend_schema</code> (visible sur <code>/api/v1/docs/</code>).",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("7. Qualité de Code", styles["TableCellBold"]),
            Paragraph(
                "Formatage et linter impeccables (<code>ruff check .</code> sans avertissement).",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
        [
            Paragraph("8. Suite de Tests", styles["TableCellBold"]),
            Paragraph(
                "Tests unitaires et intégration au vert (<code>pytest</code> à 100%).",
                styles["TableCell"],
            ),
            Paragraph("OBLIGATOIRE", styles["TableCellBold"]),
        ],
    ]
    dod_table = Table(dod_data, colWidths=[120, 313, 90])
    dod_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#E2E8F0"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(dod_table)

    story.append(PageBreak())

    # =========================================================================
    # MODULE 8 : MÉTACOGNITION & LOOKING BACK
    # =========================================================================
    story.append(
        Paragraph(
            "MODULE 8 : Régulation Métacognitive &amp; Looking Back",
            styles["ModuleHeader"],
        )
    )
    story.append(
        Paragraph(
            "<i>Phase 5 du Cycle : Dé-biaisage Dunning-Kruger &amp; Fiche d'Auto-Évaluation de Maîtrise</i>",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 6))

    looking_back = [
        "<b>L'Heuristique du 'Looking Back' de George Pólya :</b>",
        "La maîtrise ne s'arrête pas au moment où le code compile ou passe les tests. Prenez 3 minutes pour examiner la solution globale :",
        "1. <b>Généralisation :</b> Comment cette architecture (Modèle $\\rightarrow$ Sélecteur $\\rightarrow$ Service $\\rightarrow$ Sérialiseur $\\rightarrow$ Vue $\\rightarrow$ Test) s'applique-t-elle à une autre entité, par exemple la gestion du <i>Matériel de Chantier</i> ou des <i>Bons de Livraison</i> ?",
        "2. <b>Élégance &amp; Simplicité :</b> Avez-vous laissé du code mort ou des calculs redondants ? Le service est-il pur et découplé de toute logique HTTP ?",
        "3. <b>Transfert Loin :</b> Si l'entreprise décidait demain de migrer vers une API gRPC ou GraphQL, seule la couche <code>views/</code> et <code>serializers/</code> changerait ; vos <code>services/</code> et <code>selectors/</code> resteraient rigoureusement intacts. C'est l'essence même de la Clean Architecture.",
    ]
    story.append(
        make_callout(
            "METACOR", "L'ANALYSE RÉTROGRADE DE MAÎTRISE", looking_back, styles
        )
    )
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "Votre Fiche Réflexive d'Auto-Évaluation (Learning Wrapper)",
            styles["SectionHeader"],
        )
    )
    story.append(
        Paragraph(
            "Avant de déclarer une tâche backend 'Terminée' en entreprise, répondez par écrit aux 4 questions ci-dessous :",
            styles["Body"],
        )
    )

    wrapper_data = [
        [
            Paragraph("<b>Question Métacognitive</b>", styles["TableHeader"]),
            Paragraph(
                "<b>Votre Auto-Diagnostic en Situation Réelle</b>",
                styles["TableHeader"],
            ),
        ],
        [
            Paragraph(
                "1. <b>Calibration de Confiance (0-100%)</b><br/>Quel est votre degré de certitude que vos permissions bloquent un tiers non affecté ?",
                styles["TableCell"],
            ),
            Paragraph(
                "[   ] % — Avez-vous testé explicitement le code HTTP 403 dans votre suite de tests ?",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph(
                "2. <b>Audit de Charge Cognitive (Sweller)</b><br/>Avez-vous décomposé votre logique en sous-fonctions limpides dans le service ?",
                styles["TableCell"],
            ),
            Paragraph(
                "Le service contient-il plus de 40 lignes ? Si oui, isolez les sous-règles dans des fonctions privées.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph(
                "3. <b>Recherche du Point Aveugle (WYSIATI)</b><br/>Qu'avez-vous supposé comme acquis (ex: format de date, lot nul, utilisateur anonyme) ?",
                styles["TableCell"],
            ),
            Paragraph(
                "Vérifiez que votre sérialiseur gère explicitement <code>allow_null=True</code> et les chaînes vides.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph(
                "4. <b>Attitude Face à l'Erreur (Growth Mindset)</b><br/>Si un bug survient en pré-production, comment réagissez-vous ?",
                styles["TableCell"],
            ),
            Paragraph(
                "L'erreur est une information scientifique précieuse. Écrivez immédiatement un test de régression qui reproduit l'échec.",
                styles["TableCell"],
            ),
        ],
    ]
    wrapper_table = Table(wrapper_data, colWidths=[240, 283])
    wrapper_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6B21A8")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                (
                    "INNERGRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#E2E8F0"),
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(wrapper_table)
    story.append(Spacer(1, 15))

    conclusion_box = [
        "<b>Félicitations pour votre engagement dans ce cycle d'apprentissage !</b>",
        "En appliquant avec constance ces principes issus de <i>How Learning Works</i> et du <i>Deep Reasoning Engine</i>, vous ne "
        "développez pas seulement du code : vous bâtissez des systèmes pérennes et vous élevez votre pratique au rang d'<b>ingénierie logicielle d'élite</b>.",
    ]
    story.append(
        make_callout(
            "PRACTICE", "LE MOT DU LEAD ARCHITECTE", conclusion_box, styles
        )
    )

    # Construction du document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Document PDF généré avec succès : {filename}")
    return filename


if __name__ == "__main__":
    output_pdf = "MANUEL_APPRENTISSAGE_API_BACKEND.pdf"
    if len(sys.argv) > 1:
        output_pdf = sys.argv[1]
    build_manual_pdf(output_pdf)
