"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 01.

Tâche : API Rôles et Permissions — Fonctions pour créer un rôle, lui attribuer des permissions
        et rattacher un collaborateur.
Auteur : Agentic AI Pair Programmer & Mentor Neurocognitif
Destinataire : Développeur Backend Souverain (CCD Digital / SOUMAFE SARL)
Format : Document PDF A4 haute définition avec ReportLab.
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
    """Canvas à deux passes pour insérer dynamiquement les en-têtes et les numéros de page 'Page X sur Y'."""

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
            return  # Page de garde

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#334155"))

        # En-tête courant
        self.drawString(
            36,
            A4[1] - 28,
            "CCD DIGITAL • SPRINT 3 — TÂCHE 01 : API RÔLES, PERMISSIONS & RATTACHEMENT",
        )
        self.setFont("Helvetica", 8)
        self.drawRightString(A4[0] - 36, A4[1] - 28, "SOUMAFE SARL • BACKEND DRF")

        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(36, A4[1] - 32, A4[0] - 36, A4[1] - 32)

        # Pied de page courant
        self.line(36, 36, A4[0] - 36, 36)
        self.setFont("Helvetica", 8)
        self.drawString(
            36,
            24,
            "Apprentissage Actif (Dehaene / Murphy / Lovett) • Zéro Copier-Coller • Maîtrise Homo Docens",
        )
        page_str = f"Page {self._pageNumber} sur {page_count}"
        self.drawRightString(A4[0] - 36, 24, page_str)

        self.restoreState()


def get_styles():
    base = getSampleStyleSheet()

    styles = {
        "CoverSuper": ParagraphStyle(
            "CoverSuper",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0284C7"),
            spaceAfter=4,
        ),
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=26,
            textColor=colors.HexColor("#0F172A"),
            alignment=0,
            spaceAfter=8,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14,
        ),
        "CoverMeta": ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
        ),
        "CoverMetaBold": ParagraphStyle(
            "CoverMetaBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=13,
            textColor=colors.HexColor("#0284C7"),
        ),
        "H1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#0284C7"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#334155"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.8,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            leftIndent=14,
            spaceAfter=3,
        ),
        "CodeBlock": ParagraphStyle(
            "CodeBlock",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.2,
            leading=9.6,
            textColor=colors.HexColor("#0F172A"),
        ),
        "BoxText": ParagraphStyle(
            "BoxText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0F172A"),
        ),
        "BoxTextBold": ParagraphStyle(
            "BoxTextBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0F172A"),
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
            alignment=1,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
        ),
        "TableCellCode": ParagraphStyle(
            "TableCellCode",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.2,
            leading=9.5,
            textColor=colors.HexColor("#0284C7"),
        ),
    }

    return styles


def make_callout(text, title=None, style_type="info", styles=None):
    """Génère un encadré visuel pédagogique (info, warning, danger, success)."""
    palette = {
        "info": {
            "bg": colors.HexColor("#F0F9FF"),
            "border": colors.HexColor("#0284C7"),
            "title_col": "#0369A1",
        },
        "warning": {
            "bg": colors.HexColor("#FFFBEB"),
            "border": colors.HexColor("#D97706"),
            "title_col": "#B45309",
        },
        "danger": {
            "bg": colors.HexColor("#FEF2F2"),
            "border": colors.HexColor("#DC2626"),
            "title_col": "#991B1B",
        },
        "success": {
            "bg": colors.HexColor("#F0FDF4"),
            "border": colors.HexColor("#16A34A"),
            "title_col": "#15803D",
        },
        "neuro": {
            "bg": colors.HexColor("#FAF5FF"),
            "border": colors.HexColor("#9333EA"),
            "title_col": "#7E22CE",
        },
    }

    conf = palette.get(style_type, palette["info"])
    flowables = []

    if title:
        header_text = f"<font color='{conf['title_col']}'><b>{title}</b></font>"
        flowables.append(Paragraph(header_text, styles["BoxTextBold"]))
        flowables.append(Spacer(1, 3))

    flowables.append(Paragraph(text, styles["BoxText"]))

    t = Table([[flowables]], colWidths=[A4[0] - 72])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), conf["bg"]),
                ("BOX", (0, 0), (-1, -1), 1, conf["border"]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return t


def make_code_box(code_text, filename=None, styles=None):
    """Crée un bloc de code propre avec barre de titre de fichier."""
    clean_code = code_text.strip()
    flowables = []

    if filename:
        fn_p = Paragraph(f"<b>Fichier :</b> <code>{filename}</code>", styles["CoverMetaBold"])
        flowables.append(fn_p)
        flowables.append(Spacer(1, 2))

    flowables.append(Preformatted(clean_code, styles["CodeBlock"]))

    t = Table([[flowables]], colWidths=[A4[0] - 72])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def generate_manual_pdf(output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = get_styles()
    story = []

    # =========================================================================
    # PAGE 1 : COUVERTURE & CADRAGE GLOBAL
    # =========================================================================
    story.append(Spacer(1, 10))
    story.append(Paragraph("CCD DIGITAL • SYSTÈME DE GESTION DE CHANTIER BTP", styles["CoverSuper"]))
    story.append(
        Paragraph(
            "MANUEL D'APPRENTISSAGE PAR LA PRATIQUE<br/>"
            "<font color='#0284C7'>SPRINT 3 — TÂCHE 01 : API RÔLES, PERMISSIONS & RATTACHEMENT</font>",
            styles["CoverTitle"],
        )
    )
    story.append(
        Paragraph(
            "Guide d'ingénierie active pour programmer de vos propres mains les fonctions de création de rôles, "
            "d'attribution matricielle des permissions par module et de rattachement sécurisé d'un collaborateur.",
            styles["CoverSubtitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=12))

    meta_table_data = [
        [
            Paragraph("<b>Sprint :</b> Sprint 3 (Gestion de Projets & RBAC)", styles["CoverMeta"]),
            Paragraph("<b>Périmètre :</b> <code>apps/accounts</code>", styles["CoverMeta"]),
        ],
        [
            Paragraph("<b>Rôle Développeur :</b> Lead Backend Django / DRF", styles["CoverMeta"]),
            Paragraph("<b>Niveau de Compétence :</b> <i>Homo Docens</i>", styles["CoverMeta"]),
        ],
        [
            Paragraph("<b>Architecture :</b> Multi-Tenant PostgreSQL (Schémas)", styles["CoverMeta"]),
            Paragraph("<b>Contraintes :</b> Zéro Copier-Coller • Saisie Manuelle", styles["CoverMeta"]),
        ],
    ]
    t_meta = Table(meta_table_data, colWidths=[260, 260])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 14))

    scqa_text = (
        "<b>Situation :</b> Le système CCD Digital entre dans son Sprint 3 avec l'objectif de livrer une plateforme "
        "robuste de structuration et de pilotage de chantiers BTP. L'entreprise cliente (le tenant) a besoin d'une matrice "
        "de contrôle d'accès basée sur les rôles (RBAC) fine et dynamique.<br/>"
        "<b>Complication :</b> Les rôles système de base (AD, DG, CP, CT, CC, etc.) ne suffisent pas à couvrir les organisations "
        "complexes du BTP (Chefs d'Équipe gros œuvre, Métreurs, Responsables QSE externes). De plus, rattacher un collaborateur "
        "à un rôle personnalisé ne doit jamais compromettre l'étanchéité multi-tenant, ni permettre l'usurpation du rôle souverain "
        "de Directeur Général / Fondateur.<br/>"
        "<b>Question :</b> Comment programmer des fonctions de service atomiques et des endpoints REST impeccables permettant "
        "1) de créer un rôle sur mesure, 2) de lui assigner des niveaux d'accès parmi 12 modules BTP, et 3) de rattacher ou "
        "réassigner un collaborateur tout en garantissant des invariants stricts de sécurité ?<br/>"
        "<b>Orientation :</b> Ce manuel décompose pas-à-pas chaque fonction, chaque contrainte de modèle, chaque sérialiseur "
        "et chaque test pour que vous tapiez vous-même chaque caractère de code et développiez des réflexes d'ingénieur souverain."
    )
    story.append(make_callout(scqa_text, title="Cadrage Stratégique SCQA (Minto Pyramid)", style_type="info", styles=styles))
    story.append(Spacer(1, 12))

    neuro_intro = (
        "<b>Le Principe du Recyclage Neuronal & de l'Automatisation Moteur (Dehaene) :</b><br/>"
        "L'IA ne doit jamais coder cette tâche à votre place. La compréhension passive est une illusion de compétence (Kahneman). "
        "En tapant chaque instruction Django, vous obligez votre cortex moteur et vos réseaux bayésiens à encoder la syntaxe, "
        "les transactions atomiques et les validations d'erreurs jusqu'à ce qu'elles deviennent des réflexes automatiques."
    )
    story.append(make_callout(neuro_intro, title="Neuro-Pédagogie Active : Zéro Copier-Coller", style_type="neuro", styles=styles))

    # =========================================================================
    # PAGE 2 : SECTION 1 - FILM MENTAL & OBJECTIF SACRÉ
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ (JOSEPH MURPHY)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=10))

    story.append(Paragraph("1.1 La Visualisation de la Réussite Finale (Murphy - Le Film Mental)", styles["H2"]))
    story.append(
        Paragraph(
            "Fermez les yeux quelques instants avant d'ouvrir votre éditeur de code. Visualisez l'état final du système : "
            "le Directeur Général de l'entreprise BTP ouvre l'interface des paramètres. Il saisit un nouveau rôle "
            "<i>'Chef d'Équipe Coffrage'</i>, coche <i>'Écriture'</i> sur le module <b>Chantier</b>, <i>'Lecture'</i> sur "
            "<b>QHSE</b>, et valide. En une fraction de seconde (moins de 40 ms), l'API DRF renvoie une réponse HTTP 201 Created "
            "avec la matrice complète JSON. Ensuite, il sélectionne un collaborateur dans sa liste et lui associe ce rôle. "
            "Immédiatement, les permissions de ce collaborateur sont recalculées sans faille. En console, la commande "
            "<code>pytest apps/accounts/tests/ -v</code> affiche 100% de pastilles vertes sans le moindre avertissement.",
            styles["Body"],
        )
    )

    film_box = (
        "<b>Affirmation d'Ancrage Subconscient :</b><br/>"
        "<i>« Mon esprit assimile avec calme et clarté les principes de l'architecture logicielle. Je comprends chaque relation "
        "entre l'Utilisateur, le Rôle et les Modules. Mon code est propre, performant, robuste et exempt de failles. Je progresse "
        "avec assurance vers l'état d'Homo Docens, capable d'enseigner ce que je maîtrise. »</i>"
    )
    story.append(make_callout(film_box, title="Auto-Suggestion & Conditionnement Mental", style_type="success", styles=styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1.2 La Loi de l'Effort Inversé & Gestion du Stress Cognitif", styles["H2"]))
    story.append(
        Paragraph(
            "Le Dr. Joseph Murphy et les neurosciences cognitives modernes démontrent que plus vous vous crispez sur une difficulté "
            "ou une erreur de compilation, plus votre cerveau bloque l'accès à la mémoire de travail (le cortex préfrontal s'inhibe). "
            "Si un test échoue ou si une validation lève une exception inattendue :<br/>"
            "• <b>Respirez profondément :</b> Ne forcez pas la solution dans la tension.<br/>"
            "• <b>Accueillez le signal d'erreur :</b> Stanislas Dehaene enseigne que l'erreur n'est pas un échec, c'est le "
            "seul moteur d'ajustement bayésien du cerveau.<br/>"
            "• <b>Décomposez le problème :</b> Isolez l'inconnu, examinez les données entrantes et l'invariant violé.",
            styles["Body"],
        )
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("1.3 Les 3 Objectifs Sacrés de la Tâche de Sprint", styles["H2"]))

    objectifs_data = [
        [
            Paragraph("<b>Objectif</b>", styles["TableHeader"]),
            Paragraph("<b>Composant Clé</b>", styles["TableHeader"]),
            Paragraph("<b>Critère de Réussite Inviolable</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>1. Créer un Rôle</b>", styles["TableCellBold"]),
            Paragraph("<code>creer_role()</code><br/>+ Vue <code>RoleListCreateView</code>", styles["TableCellCode"]),
            Paragraph("Code en majuscules, unique par tenant. Interdiction stricte de créer le rôle 'DG' ou 'ADMIN'. Transaction atomique.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>2. Attribuer des Permissions</b>", styles["TableCellBold"]),
            Paragraph("<code>RoleModulePermission</code><br/>+ Niveaux 0 à 3", styles["TableCellCode"]),
            Paragraph("Matrice complète sur les 12 modules opérationnels CCD Digital (AUCUN, LECTURE, ECRITURE, VALIDATION).", styles["TableCell"]),
        ],
        [
            Paragraph("<b>3. Rattacher un Collaborateur</b>", styles["TableCellBold"]),
            Paragraph("<code>rattacher_collaborateur_a_role()</code><br/>+ Endpoint PATCH/POST", styles["TableCellCode"]),
            Paragraph("Affectation du rôle personnalisé à l'Utilisateur. Immutabilité du compte Propriétaire/DG. Synchronisation du rôle global.", styles["TableCell"]),
        ],
    ]
    t_obj = Table(objectifs_data, colWidths=[120, 160, 240])
    t_obj.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t_obj)

    # =========================================================================
    # PAGE 3 : SECTION 2 - ARCHITECTURE & INVARIANTS SYSTÉMIQUES
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 2 : ARCHITECTURE & INVARIANTS (PÓLYA / DEHAENE)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=10))

    story.append(Paragraph("2.1 Modèle Mental & Invariants de George Pólya", styles["H2"]))
    story.append(
        Paragraph(
            "Dans <i>How to Solve It</i>, George Pólya prescrit d'isoler en premier lieu l'Inconnue, les Données et la Condition. "
            "Dans notre architecture RBAC multi-tenant, les données et invariants sont formellement définis :",
            styles["Body"],
        )
    )

    invariants_list = [
        "<b>Invariant 1 (Isolation Tenant) :</b> La table <code>role</code> et la table <code>utilisateur</code> résident dans le schéma du tenant (ex: <code>demo</code>). Aucune requête ne doit mélanger les rôles de deux entreprises clientes distinctes.",
        "<b>Invariant 2 (Souveraineté du Propriétaire / DG) :</b> L'utilisateur fondateur avec <code>is_owner=True</code> a un statut et un rôle immuables. Aucune fonction ne peut réassigner son rôle ni désactiver son compte.",
        "<b>Invariant 3 (Atomicité de la Matrice) :</b> Un rôle ne peut jamais exister sans sa matrice de permissions. Si la création du rôle réussit mais que l'insertion d'un module échoue, le rollback de base de données doit être total (ACID via <code>transaction.atomic()</code>).",
        "<b>Invariant 4 (Règle des 12 Modules CCD Digital) :</b> Tout module renseigné doit appartenir rigoureusement à l'énumération <code>ModuleChoix</code> (CHANTIER, QHSE, ACHATS, STOCKS, FINANCE, RH, GED, MATERIEL, TIERS, CONTRATS, PILOTAGE, SUPPORT).",
        "<b>Invariant 5 (Échelle Ordinale des Droits) :</b> Les niveaux d'accès sont strictement ordonnés : 0 (AUCUN) &lt; 1 (LECTURE) &lt; 2 (ECRITURE) &lt; 3 (VALIDATION).",
    ]
    for inv in invariants_list:
        story.append(Paragraph(f"• {inv}", styles["Bullet"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("2.2 Le Schéma Relationnel Entité-Association (MCD)", styles["H2"]))

    ascii_mcd = (
        "+-----------------------+         +-------------------------------+         +----------------------------+\n"
        "|      Utilisateur      |         |             Role              |         |   RoleModulePermission     |\n"
        "+-----------------------+         +-------------------------------+         +----------------------------+\n"
        "| id: UUID (PK)         |  0..*   | id: UUID (PK)                 |  1      | id: UUID (PK)              |\n"
        "| email: EmailField     |-------> | code: CharField(50) [UNIQUE]  |<------->| role_id: FK(Role)          |\n"
        "| role_global: CharField|         | libelle: CharField(100)       |   1..*  | module: CharField(30)      |\n"
        "| role_personnalise_id  |         | est_systeme: BooleanField     |         | niveau: PositiveSmallInt   |\n"
        "| is_owner: BooleanField|         | est_actif: BooleanField       |         | (0=AUCUN, 1=LEC, 2=ECR...) |\n"
        "+-----------------------+         +-------------------------------+         +----------------------------+"
    )
    story.append(make_code_box(ascii_mcd, filename="Structure Relationnelle RBAC CCD Digital", styles=styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("2.3 Les 12 Modules Opérationnels BTP et leurs Niveaux", styles["H2"]))
    story.append(
        Paragraph(
            "Le dictionnaire ci-dessous représente la matrice d'habilitation d'un rôle. Chaque clé correspond à un module "
            "BTP, et chaque valeur à son niveau de privilège.",
            styles["Body"],
        )
    )

    modules_table_data = [
        [
            Paragraph("<b>Code Module</b>", styles["TableHeader"]),
            Paragraph("<b>Description Métier BTP</b>", styles["TableHeader"]),
            Paragraph("<b>Niveau Conseillé par Défaut</b>", styles["TableHeader"]),
        ],
        [Paragraph("<code>CHANTIER</code>", styles["TableCellCode"]), Paragraph("Gestion des travaux, journal, avancement physique", styles["TableCell"]), Paragraph("2 (ECRITURE)", styles["TableCellBold"])],
        [Paragraph("<code>QHSE</code>", styles["TableCellCode"]), Paragraph("Sécurité, incidents, EPI, conformité environnementale", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>ACHATS</code>", styles["TableCellCode"]), Paragraph("Demandes d'achat, bons de commande chantiers", styles["TableCell"]), Paragraph("0 (AUCUN) ou 1", styles["TableCellBold"])],
        [Paragraph("<code>STOCKS</code>", styles["TableCellCode"]), Paragraph("Matériaux sur site, réceptions, sorties magasin", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>FINANCE</code>", styles["TableCellCode"]), Paragraph("Budgets, situations de paiement, décomptes", styles["TableCell"]), Paragraph("0 (AUCUN - Réservé DG/DF)", styles["TableCellBold"])],
        [Paragraph("<code>RH</code>", styles["TableCellCode"]), Paragraph("Pointage ouvriers, présences journalières", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>GED</code>", styles["TableCellCode"]), Paragraph("Plans, DOE, rapports d'expertise technique", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>MATERIEL</code>", styles["TableCellCode"]), Paragraph("Engins, outillage lourd, maintenance préventive", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>TIERS</code>", styles["TableCellCode"]), Paragraph("Fournisseurs, sous-traitants, bureaux de contrôle", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>CONTRATS</code>", styles["TableCellCode"]), Paragraph("Marchés publics/privés, avenants, garanties", styles["TableCell"]), Paragraph("0 (AUCUN)", styles["TableCellBold"])],
        [Paragraph("<code>PILOTAGE</code>", styles["TableCellCode"]), Paragraph("Tableaux de bord consolidés, ratios d'avancement", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
        [Paragraph("<code>SUPPORT</code>", styles["TableCellCode"]), Paragraph("Assistance technique et tickets plateforme", styles["TableCell"]), Paragraph("1 (LECTURE)", styles["TableCellBold"])],
    ]
    t_mod = Table(modules_table_data, colWidths=[90, 270, 160])
    t_mod.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    story.append(t_mod)

    # =========================================================================
    # PAGE 4 : SECTION 3 - GUIDE D'IMPLÉMENTATION : ÉTAPE 1 (SERVICES)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS POUR VOS MAINS", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=10))

    story.append(
        Paragraph(
            "<b>Consigne d'Or :</b> Tapez chaque instruction manuellement dans votre éditeur (VS Code / Cursor). "
            "Ne faites aucun copier-coller. Observez l'autocomplétion de votre IDE, comprenez les imports et "
            "la logique métier.",
            styles["BodyBold"],
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.1 Étape 1 : Programmer les Fonctions Métier dans la Couche Service", styles["H2"]))
    story.append(
        Paragraph(
            "Ouvrez le fichier <code>apps/accounts/services/roles.py</code>. Vérifiez la présence des fonctions "
            "<code>creer_role</code> et <code>modifier_role</code>. Implémentez ensuite la nouvelle fonction "
            "fondamentale de rattachement : <code>rattacher_collaborateur_a_role()</code>.",
            styles["Body"],
        )
    )

    code_service_rattachement = (
        "def rattacher_collaborateur_a_role(\n"
        "    *,\n"
        "    collaborateur: Utilisateur,\n"
        "    role: Role | None = None,\n"
        "    role_global: str | None = None,\n"
        "    modifie_par: Utilisateur | None = None,\n"
        ") -> Utilisateur:\n"
        "    \"\"\"Rattache un collaborateur à un rôle personnalisé ou met à jour son rôle global.\n"
        "\n"
        "    Règles d'intégrité et de sécurité :\n"
        "    - Le Propriétaire/Fondateur (is_owner=True) a un rôle immuable : interdiction de modification.\n"
        "    - Le rôle de Directeur Général ne peut pas être attribué à un collaborateur standard.\n"
        "    - Si un 'role' personnalisé est fourni, il doit être actif et non supprimé.\n"
        "    - Seul le DG ou un Admin peut conférer le rôle ADMIN.\n"
        "    \"\"\"\n"
        "    from django.core.exceptions import ValidationError\n"
        "    from apps.core.enums import RoleGlobal, StatutUtilisateur\n"
        "\n"
        "    # Règle 1 : Immutabilité du compte Propriétaire\n"
        "    if collaborateur.is_owner:\n"
        "        raise ValidationError(_(\"Le rôle et le statut du Propriétaire / Fondateur sont immuables.\"))\n"
        "\n"
        "    # Règle 2 : Interdiction d'attribuer le rôle DG\n"
        "    if role_global == RoleGlobal.DIRECTEUR_GENERAL:\n"
        "        raise ValidationError(_(\"Le rôle de Directeur Général est unique et ne peut pas être attribué.\"))\n"
        "\n"
        "    # Règle 3 : Validation de l'existence et de l'état du rôle personnalisé\n"
        "    if role is not None:\n"
        "        if role.supprime_le is not None or not role.est_actif:\n"
        "            raise ValidationError(_(\"Le rôle spécifié est inactif ou a été supprimé.\"))\n"
        "\n"
        "    with transaction.atomic():\n"
        "        champs_a_mettre_a_jour = [\"modifie_le\"]\n"
        "\n"
        "        if role is not None:\n"
        "            collaborateur.role_personnalise = role\n"
        "            champs_a_mettre_a_jour.append(\"role_personnalise\")\n"
        "            # Si le code du rôle personnalisé correspond à un rôle global connu, synchroniser\n"
        "            if role.code in RoleGlobal.values:\n"
        "                collaborateur.role_global = role.code\n"
        "                champs_a_mettre_a_jour.append(\"role_global\")\n"
        "\n"
        "        if role_global is not None and role_global in RoleGlobal.values:\n"
        "            collaborateur.role_global = role_global\n"
        "            if \"role_global\" not in champs_a_mettre_a_jour:\n"
        "                champs_a_mettre_a_jour.append(\"role_global\")\n"
        "\n"
        "        collaborateur.save(update_fields=champs_a_mettre_a_jour)\n"
        "\n"
        "    return collaborateur\n"
    )
    story.append(make_code_box(code_service_rattachement, filename="apps/accounts/services/roles.py", styles=styles))
    story.append(Spacer(1, 8))

    neuro_tip1 = (
        "<b>Pourquoi update_fields=['...'] ?</b><br/>"
        "En Django, faire un <code>save()</code> complet réécrit toutes les colonnes SQL. Si un autre processus "
        "a modifié <code>tentatives_echouees</code> ou <code>derniere_connexion</code> en parallèle, un save global écraserait "
        "ces valeurs (race condition). Utiliser <code>update_fields</code> génère une requête SQL <code>UPDATE utilisateur SET "
        "role_personnalise_id=..., modifie_le=... WHERE id=...</code> chirurgicale et infalsifiable."
    )
    story.append(make_callout(neuro_tip1, title="Éclairage d'Ingénierie ORM Django (Melé 2024)", style_type="info", styles=styles))

    # =========================================================================
    # PAGE 5 : SECTION 3 - GUIDE D'IMPLÉMENTATION : ÉTAPE 2 (SERIALIZERS)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3.2 Étape 2 : Définir les Contrats de Validation (Sérialiseurs DRF)", styles["H2"]))
    story.append(
        Paragraph(
            "Le sérialiseur est le premier rempart du système. Il valide les types entrants, vérifie les contraintes métier "
            "et garantit qu'aucune donnée malformée n'atteint l'ORM. Ouvrez <code>apps/accounts/serializers/collaborateur.py</code> "
            "et ajoutez le sérialiseur de rattachement de rôle :",
            styles["Body"],
        )
    )

    code_serializer_rattachement = (
        "class CollaborateurRattacherRoleSerializer(serializers.Serializer):\n"
        "    \"\"\"Sérialiseur pour la mise à jour ou le rattachement de rôle d'un collaborateur existant.\"\"\"\n"
        "\n"
        "    role_global = serializers.ChoiceField(choices=RoleGlobal.choices, required=False)\n"
        "    role_personnalise_id = serializers.UUIDField(required=False, allow_null=True)\n"
        "\n"
        "    def validate(self, attrs):\n"
        "        role_global = attrs.get(\"role_global\")\n"
        "        role_id = attrs.get(\"role_personnalise_id\")\n"
        "\n"
        "        if role_global is None and role_id is None:\n"
        "            raise serializers.ValidationError(\n"
        "                _(\"Au moins un rôle global ou un identifiant de rôle personnalisé doit être spécifié.\")\n"
        "            )\n"
        "\n"
        "        if role_global == RoleGlobal.DIRECTEUR_GENERAL:\n"
        "            raise serializers.ValidationError(\n"
        "                {\"role_global\": _(\"Le rôle de Directeur Général ne peut pas être attribué.\")}\n"
        "            )\n"
        "\n"
        "        if role_id is not None:\n"
        "            role = Role.objects.filter(id=role_id, supprime_le__isnull=True).first()\n"
        "            if not role:\n"
        "                raise serializers.ValidationError(\n"
        "                    {\"role_personnalise_id\": _(\"Rôle personnalisé introuvable ou inactif.\")}\n"
        "                )\n"
        "            attrs[\"role_instance\"] = role\n"
        "\n"
        "        return attrs\n"
    )
    story.append(make_code_box(code_serializer_rattachement, filename="apps/accounts/serializers/collaborateur.py", styles=styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("3.3 Étape 3 : Créer la Vue d'API DRF Dédiée", styles["H2"]))
    story.append(
        Paragraph(
            "Ouvrez <code>apps/accounts/views/collaborateur.py</code>. Vous allez créer la vue de détail "
            "<code>ParametresCollaborateurDetailView</code> permettant de modifier un collaborateur et de "
            "rattacher son rôle via des requêtes <code>PATCH</code> et <code>POST</code> :",
            styles["Body"],
        )
    )

    code_view_collaborateur = (
        "class ParametresCollaborateurDetailView(APIView):\n"
        "    \"\"\"`GET`, `PATCH` et `POST /api/v1/parametres/collaborateurs/{id}/`.\n"
        "    Permet de consulter le détail d'un collaborateur et de mettre à jour son rôle.\n"
        "    \"\"\"\n"
        "\n"
        "    permission_classes = [IsAuthenticated]\n"
        "    parser_classes = [JSONParser]\n"
        "\n"
        "    @extend_schema(\n"
        "        summary=\"Rattacher un rôle à un collaborateur ou modifier ses informations\",\n"
        "        request=CollaborateurRattacherRoleSerializer,\n"
        "        responses={200: CollaborateurResponseSerializer},\n"
        "    )\n"
        "    def patch(self, request, pk):\n"
        "        _autoriser_parametres_collaborateurs(request.user)\n"
        "        collaborateur = get_object_or_404(Utilisateur, pk=pk, supprime_le__isnull=True)\n"
        "\n"
        "        serializer = CollaborateurRattacherRoleSerializer(data=request.data)\n"
        "        serializer.is_valid(raise_exception=True)\n"
        "\n"
        "        role_instance = serializer.validated_data.get(\"role_instance\")\n"
        "        role_global = serializer.validated_data.get(\"role_global\")\n"
        "\n"
        "        # Règle R-DEMO-01 : Seul le DG ou Propriétaire peut attribuer le rôle ADMIN\n"
        "        if role_global == RoleGlobal.ADMIN and not (\n"
        "            getattr(request.user, \"is_dg\", False) or getattr(request.user, \"is_owner\", False)\n"
        "        ):\n"
        "            raise ActionInterditeDelegue()\n"
        "\n"
        "        try:\n"
        "            collaborateur = rattacher_collaborateur_a_role(\n"
        "                collaborateur=collaborateur,\n"
        "                role=role_instance,\n"
        "                role_global=role_global,\n"
        "                modifie_par=request.user,\n"
        "            )\n"
        "        except DjangoValidationError as exc:\n"
        "            msg = str(exc.message if hasattr(exc, \"message\") else exc)\n"
        "            raise ValidationError({\"detail\": msg}) from exc\n"
        "\n"
        "        # Recharger les données complètes pour la réponse\n"
        "        rp_data = None\n"
        "        if collaborateur.role_personnalise:\n"
        "            rp_data = {\n"
        "                \"id\": collaborateur.role_personnalise.id,\n"
        "                \"code\": collaborateur.role_personnalise.code,\n"
        "                \"libelle\": collaborateur.role_personnalise.libelle,\n"
        "            }\n"
        "        reponse_data = {\n"
        "            \"id\": collaborateur.id,\n"
        "            \"email\": collaborateur.email,\n"
        "            \"nom\": collaborateur.nom,\n"
        "            \"prenom\": collaborateur.prenom,\n"
        "            \"nom_complet\": collaborateur.nom_complet,\n"
        "            \"telephone\": collaborateur.telephone,\n"
        "            \"role_global\": collaborateur.role_global,\n"
        "            \"role_global_libelle\": collaborateur.get_role_global_display(),\n"
        "            \"role_personnalise\": rp_data,\n"
        "            \"statut\": collaborateur.statut,\n"
        "            \"is_owner\": collaborateur.is_owner,\n"
        "            \"cree_le\": collaborateur.cree_le,\n"
        "            \"projets\": [],\n"
        "            \"lien_activation\": None,\n"
        "        }\n"
        "        return Response(CollaborateurResponseSerializer(reponse_data).data, status=status.HTTP_200_OK)\n"
        "\n"
        "    def post(self, request, pk):\n"
        "        return self.patch(request, pk)\n"
    )
    story.append(make_code_box(code_view_collaborateur, filename="apps/accounts/views/collaborateur.py", styles=styles))

    # =========================================================================
    # PAGE 6 : SECTION 3 (FIN) & SECTION 4 - SIGNAL D'ERREUR BAYÉSIEN (PRE-MORTEM)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3.4 Étape 4 : Déclarer la Route URL dans l'Application", styles["H2"]))
    story.append(
        Paragraph(
            "Ouvrez <code>apps/accounts/urls.py</code> et enregistrez la route REST pour accéder au collaborateur par son identifiant UUID :",
            styles["Body"],
        )
    )

    code_urls = (
        "# Collaborateurs — Paramètres (/api/v1/parametres/collaborateurs/)\n"
        "path(\n"
        "    \"parametres/collaborateurs/\",\n"
        "    ParametresCollaborateurListCreateView.as_view(),\n"
        "    name=\"parametres-collaborateurs-liste-creer\",\n"
        "),\n"
        "path(\n"
        "    \"parametres/collaborateurs/<uuid:pk>/\",\n"
        "    ParametresCollaborateurDetailView.as_view(),\n"
        "    name=\"parametres-collaborateur-detail-modifier\",\n"
        "),\n"
    )
    story.append(make_code_box(code_urls, filename="apps/accounts/urls.py", styles=styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM (KAHNEMAN)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=10))

    story.append(
        Paragraph(
            "Dans la technique du <b>Pre-Mortem</b> (Gary Klein & Daniel Kahneman), nous nous projetons dans le futur "
            "où notre code est en production et s'est effondré. Nous analysons rétrospectivement ce qui a causé la panne "
            "afin de blinder le code dès maintenant :",
            styles["Body"],
        )
    )

    premortem_data = [
        [
            Paragraph("<b>Scénario de Panne Potentiel</b>", styles["TableHeader"]),
            Paragraph("<b>Mécanisme de Défaillance</b>", styles["TableHeader"]),
            Paragraph("<b>Parade Préventive Programmée</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>1. Usurpation de Droits Admin</b>", styles["TableCellBold"]),
            Paragraph("Un administrateur délégué s'auto-attribue des droits ou élève un complice au rôle DG.", styles["TableCell"]),
            Paragraph("Contrôle strict dans <code>rattacher_collaborateur_a_role</code> : le rôle DG est non attribuable et seul le DG peut nommer un ADMIN.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>2. Rôle Fantôme Supprimé</b>", styles["TableCellBold"]),
            Paragraph("Un collaborateur est rattaché à un rôle qui a subi une suppression logique (<code>supprime_le is not None</code>).", styles["TableCell"]),
            Paragraph("Le serializer vérifie <code>supprime_le__isnull=True</code> et <code>est_actif=True</code> avant d'accepter le rattachement.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>3. Écrasement Imprévu (Race Condition)</b>", styles["TableCellBold"]),
            Paragraph("Deux requêtes concurrentes modifient l'utilisateur en même temps.", styles["TableCell"]),
            Paragraph("Utilisation systématique de <code>save(update_fields=[...])</code> et transaction atomique <code>with transaction.atomic()</code>.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>4. Rétrocompatibilité Rôle Global</b>", styles["TableCellBold"]),
            Paragraph("Les anciens modules qui lisent <code>user.role_global</code> au lieu de <code>role_personnalise</code> ne voient pas le changement.", styles["TableCell"]),
            Paragraph("Synchronisation automatique bidirectionnelle : si le code du rôle personnalisé correspond à un rôle global, <code>role_global</code> est mis à jour.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>5. Violation de Schéma Multi-Tenant</b>", styles["TableCellBold"]),
            Paragraph("Une requête sur les rôles s'exécute dans le schéma <code>public</code> au lieu du tenant.", styles["TableCell"]),
            Paragraph("L'ORM est encapsulé dans le middleware <code>TenantMainMiddleware</code>. Les tests utilisent <code>schema_context(SCHEMA)</code>.", styles["TableCellBold"]),
        ],
    ]
    t_pm = Table(premortem_data, colWidths=[140, 180, 200])
    t_pm.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7F1D1D")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t_pm)

    # =========================================================================
    # PAGE 7 : SECTION 5 - CHECKLIST DE TESTS & VALIDATION MANUELLE
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 5 : CHECKLIST DE TESTS & VALIDATION MANUELLE", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=10))

    story.append(
        Paragraph(
            "Pour ancrer vos acquis (Pilier 3 de Dehaene : Retour sur Erreur Actif), vous allez rédiger et exécuter "
            "la suite de tests unitaires et d'intégration automatisés.",
            styles["Body"],
        )
    )

    code_tests = (
        "@pytest.mark.django_db\n"
        "def test_rattacher_collaborateur_a_role_personnalise(client_tenant, admin_user, collaborateur_user):\n"
        "    \"\"\"Vérifie qu'un administrateur peut rattacher un collaborateur à un rôle personnalisé.\"\"\"\n"
        "    with schema_context(SCHEMA):\n"
        "        role_maitre = Role.objects.create(\n"
        "            code=\"CHEF_EQUIPE_COFFRAGE\",\n"
        "            libelle=\"Chef d'Équipe Coffrage\",\n"
        "            est_systeme=False,\n"
        "            est_actif=True,\n"
        "        )\n"
        "\n"
        "    client = _auth(client_tenant, admin_user)\n"
        "    payload = {\"role_personnalise_id\": str(role_maitre.id)}\n"
        "\n"
        "    rep = client.patch(f\"/api/v1/parametres/collaborateurs/{collaborateur_user.id}/\", payload, format=\"json\")\n"
        "    assert rep.status_code == status.HTTP_200_OK\n"
        "    data = rep.json()\n"
        "    assert data[\"role_personnalise\"][\"code\"] == \"CHEF_EQUIPE_COFFRAGE\"\n"
        "\n"
        "    with schema_context(SCHEMA):\n"
        "        collaborateur_user.refresh_from_db()\n"
        "        assert collaborateur_user.role_personnalise_id == role_maitre.id\n"
        "\n"
        "\n"
        "@pytest.mark.django_db\n"
        "def test_interdiction_modifier_role_proprietaire(client_tenant, admin_user, dg_user):\n"
        "    \"\"\"Rejette toute tentative de modification du rôle du Propriétaire / DG.\"\"\"\n"
        "    client = _auth(client_tenant, admin_user)\n"
        "    payload = {\"role_global\": RoleGlobal.CHEF_CHANTIER}\n"
        "\n"
        "    rep = client.patch(f\"/api/v1/parametres/collaborateurs/{dg_user.id}/\", payload, format=\"json\")\n"
        "    assert rep.status_code == status.HTTP_400_BAD_REQUEST\n"
        "    assert \"immuable\" in str(rep.json()).lower()\n"
    )
    story.append(make_code_box(code_tests, filename="apps/accounts/tests/test_parametres_collaborateurs.py", styles=styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("5.2 Protocole de Validation en Ligne de Commande", styles["H2"]))
    cmds_text = (
        "1. Exécuter l'intégralité des tests de rôles et collaborateurs :<br/>"
        "<code>pytest apps/accounts/tests/test_parametres_roles.py apps/accounts/tests/test_parametres_collaborateurs.py -v</code><br/><br/>"
        "2. Tester avec une requête cURL réaliste via l'hôte tenant local :<br/>"
        "<code>curl -X PATCH http://demo.localhost:8000/api/v1/parametres/collaborateurs/&lt;UUID&gt;/ \\\n"
        "     -H 'Host: demo.localhost' \\\n"
        "     -H 'Authorization: Bearer &lt;TOKEN_JWT&gt;' \\\n"
        "     -H 'Content-Type: application/json' \\\n"
        "     -d '{\"role_personnalise_id\": \"&lt;ROLE_UUID&gt;\"}'</code>"
    )
    story.append(make_callout(cmds_text, title="Commandes Terminal de Vérification", style_type="success", styles=styles))

    # =========================================================================
    # PAGE 8 : SECTION 6 - DÉFI HOMO DOCENS & CONSOLIDATION NOCTURNE
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 6 : DÉFI HOMO DOCENS & CONSOLIDATION NOCTURNE", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=10))

    story.append(Paragraph("6.1 Le Défi de l'Homo Docens (Enseigner pour Maîtriser)", styles["H2"]))
    story.append(
        Paragraph(
            "L'expression latine <i>Homo Docens</i> désigne l'homme qui enseigne. En sciences cognitives (Principe 8 de Lovett et al.), "
            "le niveau le plus élevé de maîtrise métacognitive est atteint lorsque vous êtes capable d'expliquer l'architecture à un pair. "
            "Avant de considérer cette tâche terminée, prenez une feuille blanche ou ouvrez un bloc-notes et répondez aux 3 questions "
            "suivantes sans regarder le code :",
            styles["Body"],
        )
    )

    questions_docens = [
        "<b>Question 1 :</b> Pourquoi est-il indispensable d'utiliser <code>transaction.atomic()</code> lors de la création d'un rôle personnalisé avec sa matrice de permissions ?",
        "<b>Question 2 :</b> Quelle est la différence fondamentale entre <code>user.role_global</code> et <code>user.role_personnalise</code>, et comment garantit-on la rétrocompatibilité des anciens endpoints ?",
        "<b>Question 3 :</b> Comment le système empêche-t-il qu'un administrateur délégué ne révoque le compte du Directeur Général créateur du tenant ?",
    ]
    for q in questions_docens:
        story.append(Paragraph(f"• {q}", styles["Bullet"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("6.2 Rituel de Somnolence & Replay Neuronal Nocturne (Murphy / Dehaene)", styles["H2"]))
    story.append(
        Paragraph(
            "Stanislas Dehaene (Pilier 4 : Consolidation) et le Dr. Joseph Murphy soulignent le rôle déterminant du sommeil "
            "dans l'ancrage définitif des apprentissages. Pendant le sommeil lent profond, l'hippocampe 'rejoue' les circuits "
            "neuronaux stimulés pendant la journée à une vitesse 20 fois supérieure à la normale, transférant les connaissances "
            "vers le néocortex durable.",
            styles["Body"],
        )
    )

    nocturne_box = (
        "<b>Rituel du Soir avant l'Endormissement :</b><br/>"
        "1. <b>Déconnectez vos yeux des écrans</b> 30 minutes avant de dormir.<br/>"
        "2. <b>Visualisez mentalement</b> le flux de données : de la requête HTTP entrante jusqu'à l'écriture PostgreSQL, "
        "en passant par la validation du sérialiseur et l'isolation du schéma tenant.<br/>"
        "3. <b>Remerciez votre subconscient</b> pour le travail accompli : <i>« Tout ce que j'ai implémenté aujourd'hui est "
        "parfaitement assimilé, ordonné et gravé dans ma mémoire d'ingénieur. Demain, j'aborderai la suite du Sprint avec aisance et souveraineté. »</i>"
    )
    story.append(make_callout(nocturne_box, title="Protocole d'Incubation & Consolidation", style_type="neuro", styles=styles))
    story.append(Spacer(1, 14))

    # Signature finale
    cloture_table_data = [
        [
            Paragraph("<b>Validé par le Développeur :</b>", styles["CoverMetaBold"]),
            Paragraph("<b>Approuvé par le Mentor Neurocognitif :</b>", styles["CoverMetaBold"]),
        ],
        [
            Paragraph("Nom : ___________________________<br/>Date : ____ / ____ / 2026<br/>Signature :", styles["CoverMeta"]),
            Paragraph("Agentic AI Pair Programmer & Cognitive Architect<br/>Certification : CCD Digital Enterprise Grade<br/>Statut : Conforme Sprint 3 LifeCycle", styles["CoverMeta"]),
        ],
    ]
    t_cloture = Table(cloture_table_data, colWidths=[260, 260])
    t_cloture.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(t_cloture)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCES] Manuel PDF genere avec succes : {output_path}")


if __name__ == "__main__":
    out_pdf = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "Manuels_Apprentissage",
            "MANUEL_SPRINT_3_TACHE_01_ROLES_PERMISSIONS_COLLABORATEUR.pdf",
        )
    )
    generate_manual_pdf(out_pdf)
