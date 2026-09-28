"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 02.

Tâche : Affectation des collaborateurs au projet : programmation de l'affectation avec les rôles
        Conducteur de travaux, Chef de Chantier et Consultant lecture.
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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 02 : AFFECTATION DES COLLABORATEURS AU PROJET",
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
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#0F172A"),
            alignment=0,
            spaceAfter=8,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
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
            fontSize=13.5,
            leading=17,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14.5,
            textColor=colors.HexColor("#0284C7"),
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=5,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.6,
            leading=12.5,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=12,
            textColor=colors.HexColor("#1E293B"),
            leftIndent=12,
            spaceAfter=3,
        ),
        "CodeBlock": ParagraphStyle(
            "CodeBlock",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.1,
            leading=9.4,
            textColor=colors.HexColor("#0F172A"),
        ),
        "BoxText": ParagraphStyle(
            "BoxText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.4,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
        ),
        "BoxTextBold": ParagraphStyle(
            "BoxTextBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=12,
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
            fontSize=7.6,
            leading=10.5,
            textColor=colors.HexColor("#1E293B"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=10.5,
            textColor=colors.HexColor("#0F172A"),
        ),
        "TableCellCode": ParagraphStyle(
            "TableCellCode",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.0,
            leading=9.2,
            textColor=colors.HexColor("#0284C7"),
        ),
    }

    return styles


def make_callout(text, title=None, style_type="info", styles=None):
    """Génère un encadré visuel pédagogique (info, warning, danger, success, neuro)."""
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
        flowables.append(Spacer(1, 2))

    flowables.append(Paragraph(text, styles["BoxText"]))

    t = Table([[flowables]], colWidths=[A4[0] - 72])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), conf["bg"]),
                ("BOX", (0, 0), (-1, -1), 1, conf["border"]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def make_code_box(code_text, filename=None, styles=None):
    """Crée un bloc de code soigné avec barre de titre de fichier."""
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
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
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
            "<font color='#0284C7'>SPRINT 3 — TÂCHE 02 : AFFECTATION DES COLLABORATEURS AU PROJET</font>",
            styles["CoverTitle"],
        )
    )
    story.append(
        Paragraph(
            "Guide d'ingénierie active pour programmer manuellement l'API complète d'affectation d'équipe de chantier "
            "avec les rôles Conducteur de travaux, Chef de Chantier et Consultant lecture (US-04).",
            styles["CoverSubtitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=10))

    meta_table_data = [
        [
            Paragraph("<b>Sprint :</b> Sprint 3 (Gestion de Projets & RBAC)", styles["CoverMeta"]),
            Paragraph("<b>Périmètre :</b> <code>apps/projets</code> & <code>apps/core</code>", styles["CoverMeta"]),
        ],
        [
            Paragraph("<b>Rôle Développeur :</b> Lead Backend Django / DRF", styles["CoverMeta"]),
            Paragraph("<b>Niveau de Compétence Cible :</b> <i>Homo Docens</i>", styles["CoverMeta"]),
        ],
        [
            Paragraph("<b>Architecture :</b> Multi-Tenant PostgreSQL & RBAC", styles["CoverMeta"]),
            Paragraph("<b>Spécification :</b> US-04 [P0] Contrôle d'accès granulaire", styles["CoverMeta"]),
        ],
    ]
    t_meta = Table(meta_table_data, colWidths=[260, 260])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 10))

    scqa_text = (
        "<b>Situation :</b> Dans CCD Digital, un chantier BTP est opéré par une équipe pluridisciplinaire rattachée "
        "au projet via l'entité <code>AffectationProjet</code>.<br/>"
        "<b>Complication :</b> Si les affectations initiales sont créées lors du wizard de création du projet, il n'existe "
        "pas encore d'API dédiée et modulaire permettant au Chef de Projet ou à la Direction de gérer dynamiquement "
        "les affectations tout au long de la vie du chantier. De plus, il est crucial d'assigner rigoureusement les 3 rôles "
        "clés de terrain : <b>Conducteur de travaux</b> (gestion opérationnelle et validation), <b>Chef de Chantier</b> (saisie terrain "
        "et pointages) et <b>Consultant lecture</b> (consultation sans droit d'écriture), tout en protégeant l'invariant vital "
        "US-04 : <i>chaque projet doit avoir en permanence au moins 1 Chef de Projet actif</i>.<br/>"
        "<b>Question :</b> Comment concevoir des endpoints RESTful imbriqués <code>/api/v1/projets/{id}/affectations/</code>, "
        "une couche de service robuste, des validations strictes et des tests automatisés complets ?<br/>"
        "<b>Orientation :</b> Ce manuel décompose chaque brique technique pour que vous tapiez chaque ligne de code de vos propres mains."
    )
    story.append(make_callout(scqa_text, title="Cadrage Stratégique SCQA (Minto Pyramid)", style_type="info", styles=styles))
    story.append(Spacer(1, 8))

    neuro_intro = (
        "<b>Le Principe du Recyclage Neuronal & de l'Automatisation Moteur (Stanislas Dehaene) :</b><br/>"
        "Ne déléguez pas l'écriture du code à un générateur. La compréhension passive est une illusion de compétence (Kahneman). "
        "En tapant manuellement chaque instruction de sérialiseur, de vue et de service, vos circuits neuronaux de prédiction "
        "s'ajustent (boucle bayésienne), fixant les automatismes de l'ORM Django jusqu'à l'expertise réflexe."
    )
    story.append(make_callout(neuro_intro, title="Neuro-Pédagogie Active : Zéro Copier-Coller", style_type="neuro", styles=styles))

    # =========================================================================
    # PAGE 2 : SECTION 1 - FILM MENTAL & OBJECTIF SACRÉ
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ (JOSEPH MURPHY)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(Paragraph("1.1 La Visualisation de la Réussite Finale (Le Film Mental)", styles["H2"]))
    story.append(
        Paragraph(
            "Installez-vous confortablement. Fermez les yeux pendant soixante secondes. Visualisez le résultat parfait de votre travail : "
            "Le Chef de Projet se connecte à l'application web. Il consulte la fiche du chantier de <i>'Résidence Ivoire Prestige'</i>. "
            "Il ouvre l'onglet <b>Équipe du Chantier</b>. L'API <code>GET /api/v1/projets/{id}/affectations/</code> répond en 25 ms, "
            "renvoyant la liste ordonnée des membres avec leurs avatars, téléphones, rôles lisibles et dates. "
            "Il clique sur <i>'Affecter un collaborateur'</i>, choisit Moussa Diallo avec le rôle <b>Conducteur de travaux</b>, "
            "puis Fatou Koné avec le rôle <b>Consultant lecture</b>. La requête <code>POST</code> crée les affectations instantanément. "
            "Puis, s'il essaie par inadvertance de révoquer l'unique Chef de Projet, l'API intercepte l'action et renvoie un refus "
            "clair et protecteur (HTTP 400). Les 8 tests pytest passent tous au vert. Vous ressentez le calme et la fierté d'un "
            "travail d'ingénieur accompli avec rigueur.",
            styles["Body"],
        )
    )

    film_box = (
        "<b>Affirmation d'Ancrage Subconscient :</b><br/>"
        "<i>« Mon subconscient est une source inépuisable de précision et d'ordre. Je maîtrise l'architecture des autorisations "
        "et la relation entre Projet et Utilisateur. Mon code protège les invariants du métier BTP avec une solidité inébranlable. "
        "Chaque ligne que je saisis renforce ma certitude et mon statut d'ingénieur souverain. »</i>"
    )
    story.append(make_callout(film_box, title="Auto-Suggestion & Conditionnement Mental", style_type="success", styles=styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("1.2 La Loi de l'Effort Inversé & Gestion de l'Erreur (Murphy & Dehaene)", styles["H2"]))
    story.append(
        Paragraph(
            "Lorsque le cerveau rencontre une erreur (par exemple un code HTTP 403 inattendu ou un échec d'unicité), "
            "la réaction réflexe est souvent l'agacement ou la précipitation. <b>Appliquez la Loi de l'Effort Inversé :</b> "
            "plus vous luttez sous la tension, moins votre esprit conscient a accès aux solutions créatives de votre subconscient. "
            "Respirez lentement. Considérez l'erreur non pas comme une faute, mais comme un <i>signal d'ajustement bayésien</i> "
            "(Dehaene, Pilier 3). Le test qui échoue vous indique exactement où se situe l'écart entre la réalité du code et le modèle mental.",
            styles["Body"],
        )
    )

    story.append(Spacer(1, 8))
    story.append(Paragraph("1.3 Les 4 Objectifs Sacrés de la Tâche", styles["H2"]))

    objectifs_data = [
        [
            Paragraph("<b>Objectif</b>", styles["TableHeader"]),
            Paragraph("<b>Composant Clé</b>", styles["TableHeader"]),
            Paragraph("<b>Critère de Réussite Inviolable</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>1. Rôles Métier BTP</b>", styles["TableCellBold"]),
            Paragraph("<code>apps/core/enums.py</code><br/><code>RoleProjet</code>", styles["TableCellCode"]),
            Paragraph("Support explicite de <code>CONDUCTEUR_TRAVAUX</code> ('CT'), <code>CHEF_CHANTIER</code> ('CC') et <code>VISITEUR</code> ('VI' avec libellé 'Consultant lecture').", styles["TableCell"]),
        ],
        [
            Paragraph("<b>2. Lister l'Équipe Chantier</b>", styles["TableCellBold"]),
            Paragraph("<code>GET /projets/{id}/affectations/</code>", styles["TableCellCode"]),
            Paragraph("Renvoie tous les collaborateurs affectés au projet avec leurs rôles, dates et statut actif. Requête sans N+1 (select_related).", styles["TableCell"]),
        ],
        [
            Paragraph("<b>3. Affecter un Collaborateur</b>", styles["TableCellBold"]),
            Paragraph("<code>POST /projets/{id}/affectations/</code>", styles["TableCellCode"]),
            Paragraph("Création ou réactivation propre. Contrôle de l'appartenance au même tenant. Unicité par utilisateur et par projet.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>4. Invariant Chef de Projet</b>", styles["TableCellBold"]),
            Paragraph("<code>PATCH/DELETE</code><br/>Contrôle d'intégrité US-04", styles["TableCellCode"]),
            Paragraph("Interdiction formelle de désactiver ou supprimer l'affectation du dernier Chef de Projet actif sur le chantier.", styles["TableCell"]),
        ],
    ]
    t_obj = Table(objectifs_data, colWidths=[110, 160, 253])
    t_obj.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(Paragraph("2.1 Les Invariants Inviolables de George Pólya", styles["H2"]))
    story.append(
        Paragraph(
            "Avant de concevoir l'algorithme, George Pólya prescrit d'isoler les contraintes qui ne doivent être violées "
            "sous aucun prétexte. Pour notre système d'affectation :",
            styles["Body"],
        )
    )

    invariants_list = [
        "<b>Invariant 1 (Gouvernance US-04 : 1 CP Actif Minimum) :</b> Un chantier ne peut jamais se retrouver 'orphelin'. Il doit comporter en permanence au moins <b>un Chef de Projet actif</b>. Toute tentative de désactivation (<code>est_actif=False</code>) ou de suppression de l'unique CP actif est rejetée avec une erreur 400 Bad Request.",
        "<b>Invariant 2 (Habilitation d'Affectation RBAC) :</b> Seuls les administrateurs du tenant (DG, ADMIN, Propriétaire) OU le Chef de Projet assigné au chantier (<code>projet.chef_projet_id == user.id</code>) ont le privilège d'ajouter, modifier ou révoquer une affectation. Les autres membres reçoivent un 403 Forbidden.",
        "<b>Invariant 3 (Unicité de l'Association) :</b> Un collaborateur ne peut avoir qu'une seule affectation sur un chantier donné (contrainte SQL <code>uq_affectation_utilisateur_projet</code>). Si une affectation désactivée existait déjà dans le passé, l'API la réactive avec le nouveau rôle et les nouvelles dates plutôt que d'échouer.",
        "<b>Invariant 4 (Étancheité Multi-Tenant) :</b> Le collaborateur affecté doit obligatoirement exister dans le schéma du tenant courant. Impossible d'affecter un utilisateur d'une autre entreprise cliente.",
        "<b>Invariant 5 (Matrice des Rôles Spécifiés) :</b> Les rôles autorisés lors de l'affectation couvrent notamment : <code>CONDUCTEUR_TRAVAUX</code> ('CT'), <code>CHEF_CHANTIER</code> ('CC') et <code>VISITEUR</code> ('VI', affiché 'Consultant lecture').",
    ]
    for inv in invariants_list:
        story.append(Paragraph(f"• {inv}", styles["Bullet"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("2.2 Schéma Conceptuel de Données & Flux RESTful", styles["H2"]))

    ascii_mcd = (
        "+-----------------------+         +-------------------------------+         +----------------------------+\n"
        "|        Projet         |         |       AffectationProjet       |         |        Utilisateur         |\n"
        "+-----------------------+         +-------------------------------+         +----------------------------+\n"
        "| id: UUID (PK)         |  1      | id: UUID (PK)                 |  0..*   | id: UUID (PK)              |\n"
        "| reference: CharField  |<------->| projet: FK(Projet)            |<------->| email: EmailField          |\n"
        "| nom: CharField        |   0..*  | utilisateur: FK(Utilisateur)  |   1     | nom, prenom: CharField     |\n"
        "| chef_projet: FK(User) |         | role_projet: CharField(5)     |         | role_global: CharField     |\n"
        "| conducteur_travaux: FK|         | (CT, CC, VI / Consultant lec) |         | role_personnalise: FK      |\n"
        "| statut: CharField     |         | date_debut, date_fin: Date    |         | telephone: CharField       |\n"
        "|                       |         | est_actif: BooleanField       |         | statut: ACTIF / INVITE     |\n"
        "+-----------------------+         +-------------------------------+         +----------------------------+\n"
        "                                           [uq_utilisateur_projet]"
    )
    story.append(make_code_box(ascii_mcd, filename="Structure Relationnelle AffectationProjet", styles=styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2.3 Contrat d'Interface des Endpoints RESTful", styles["H2"]))

    endpoints_data = [
        [
            Paragraph("<b>Méthode & URL</b>", styles["TableHeader"]),
            Paragraph("<b>Rôle & Action Métier</b>", styles["TableHeader"]),
            Paragraph("<b>Codes HTTP Attendus</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<code>GET /api/v1/projets/{projet_id}/affectations/</code>", styles["TableCellCode"]),
            Paragraph("Lister tous les intervenants affectés au chantier (actifs et inactifs avec filtre <code>?actifs_seulement=true</code>).", styles["TableCell"]),
            Paragraph("200 OK<br/>401 Unauthorized<br/>404 Not Found", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>POST /api/v1/projets/{projet_id}/affectations/</code>", styles["TableCellCode"]),
            Paragraph("Affecter un collaborateur au chantier avec son rôle (CT, CC, VI) et ses dates d'intervention.", styles["TableCell"]),
            Paragraph("201 Created<br/>400 Bad Request<br/>403 Forbidden", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>PATCH /api/v1/projets/{projet_id}/affectations/{id}/</code>", styles["TableCellCode"]),
            Paragraph("Modifier le rôle, prolonger/ajuster les dates ou réactiver/désactiver le collaborateur.", styles["TableCell"]),
            Paragraph("200 OK<br/>400 Bad Request (Invariant CP)<br/>403 Forbidden", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>DELETE /api/v1/projets/{projet_id}/affectations/{id}/</code>", styles["TableCellCode"]),
            Paragraph("Supprimer physiquement une affectation erronée (avec vérification stricte de l'invariant CP).", styles["TableCell"]),
            Paragraph("204 No Content<br/>400 Bad Request (Dernier CP)<br/>403 Forbidden", styles["TableCellBold"]),
        ],
    ]
    t_end = Table(endpoints_data, colWidths=[170, 230, 123])
    t_end.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t_end)

    # =========================================================================
    # PAGE 4 : SECTION 3 - GUIDE D'IMPLÉMENTATION : ÉTAPE 1 (ENUMS & SERVICES)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS POUR VOS MAINS", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(
        Paragraph(
            "<b>Consigne d'Or :</b> Tapez chaque instruction manuellement dans votre éditeur (VS Code / Cursor). "
            "Ne faites aucun copier-coller. Observez l'autocomplétion, comprenez les imports et la logique métier.",
            styles["BodyBold"],
        )
    )
    story.append(Spacer(1, 4))

    story.append(Paragraph("3.1 Étape 1 : Mettre à jour l'Énumération des Rôles de Projet", styles["H2"]))
    story.append(
        Paragraph(
            "Ouvrez le fichier <code>apps/core/enums.py</code>. Dans la classe <code>RoleProjet</code>, mettez à jour le libellé "
            "du rôle <code>VISITEUR</code> pour correspondre à <b>'Consultant lecture'</b> et déclarez un alias explicite "
            "<code>CONSULTANT_LECTURE = VISITEUR</code> :",
            styles["Body"],
        )
    )

    code_enums = (
        "class RoleProjet(models.TextChoices):\n"
        "    CHEF_PROJET = \"CP\", \"Chef de Projet\"\n"
        "    CONDUCTEUR_TRAVAUX = \"CT\", \"Conducteur de Travaux\"\n"
        "    CHEF_CHANTIER = \"CC\", \"Chef de Chantier\"\n"
        "    MAITRE_OUVRAGE = \"MOA\", \"Maître d'Ouvrage (Client)\"\n"
        "    VISITEUR = \"VI\", \"Consultant lecture\"  # Rôle de consultation en lecture seule (US-04)\n"
        "\n"
        "# Alias sémantique conforme à la spécification US-04\n"
        "RoleProjet.CONSULTANT_LECTURE = RoleProjet.VISITEUR\n"
    )
    story.append(make_code_box(code_enums, filename="apps/core/enums.py", styles=styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.2 Étape 2 : Créer la Couche Service d'Affectation", styles["H2"]))
    story.append(
        Paragraph(
            "Créez ou ouvrez le fichier <code>apps/projets/services/affectations.py</code>. Vous allez y coder les fonctions métier "
            "atomiques pour lister, créer, mettre à jour et révoquer une affectation :",
            styles["Body"],
        )
    )

    code_service_affectation = (
        "\"\"\"Services métier pour la gestion des affectations d'équipe au chantier (US-04).\"\"\"\n"
        "\n"
        "from django.core.exceptions import ValidationError\n"
        "from django.db import transaction\n"
        "from django.utils import timezone\n"
        "from django.utils.translation import gettext_lazy as _\n"
        "\n"
        "from apps.accounts.models import Utilisateur\n"
        "from apps.core.enums import RoleProjet\n"
        "from apps.projets.models import AffectationProjet, Projet\n"
        "\n"
        "\n"
        "def lister_affectations_projet(projet: Projet, actifs_seulement: bool = False):\n"
        "    \"\"\"Renvoie les affectations du projet avec chargement optimisé de l'utilisateur.\"\"\"\n"
        "    qs = (\n"
        "        AffectationProjet.objects.filter(projet=projet, supprime_le__isnull=True)\n"
        "        .select_related(\"utilisateur\", \"role\")\n"
        "        .order_by(\"role_projet\", \"utilisateur__nom\")\n"
        "    )\n"
        "    if actifs_seulement:\n"
        "        qs = qs.filter(est_actif=True)\n"
        "    return qs\n"
        "\n"
        "\n"
        "def affecter_collaborateur_projet(\n"
        "    *,\n"
        "    projet: Projet,\n"
        "    utilisateur: Utilisateur,\n"
        "    role_projet: str,\n"
        "    date_debut=None,\n"
        "    date_fin=None,\n"
        "    role_personnalise=None,\n"
        "    modifie_par: Utilisateur | None = None,\n"
        ") -> AffectationProjet:\n"
        "    \"\"\"Affecte ou réactive un collaborateur sur un chantier avec un rôle spécifique.\"\"\"\n"
        "    if role_projet not in RoleProjet.values:\n"
        "        raise ValidationError(_(\"Le rôle de projet spécifié n'est pas valide.\"))\n"
        "\n"
        "    if date_debut and date_fin and date_fin < date_debut:\n"
        "        raise ValidationError(_(\"La date de fin ne peut pas être antérieure à la date de début.\"))\n"
        "\n"
        "    date_debut_effective = date_debut or timezone.now().date()\n"
        "\n"
        "    with transaction.atomic():\n"
        "        affectation, cree = AffectationProjet.objects.get_or_create(\n"
        "            projet=projet,\n"
        "            utilisateur=utilisateur,\n"
        "            defaults={\n"
        "                \"role_projet\": role_projet,\n"
        "                \"role\": role_personnalise,\n"
        "                \"date_debut\": date_debut_effective,\n"
        "                \"date_fin\": date_fin,\n"
        "                \"est_actif\": True,\n"
        "                \"cree_par\": modifie_par,\n"
        "            },\n"
        "        )\n"
        "        if not cree:\n"
        "            # Si l'affectation existait déjà (éventuellement inactive), on la réactive et met à jour le rôle\n"
        "            affectation.role_projet = role_projet\n"
        "            if role_personnalise is not None:\n"
        "                affectation.role = role_personnalise\n"
        "            affectation.date_debut = date_debut_effective\n"
        "            affectation.date_fin = date_fin\n"
        "            affectation.est_actif = True\n"
        "            affectation.modifie_par = modifie_par\n"
        "            affectation.save(update_fields=[\"role_projet\", \"role\", \"date_debut\", \"date_fin\", \"est_actif\", \"modifie_par\", \"modifie_le\"])\n"
        "\n"
        "        # Synchronisation du rôle principal sur le Projet si conducteur de travaux\n"
        "        if role_projet == RoleProjet.CONDUCTEUR_TRAVAUX and projet.conducteur_travaux_id != utilisateur.id:\n"
        "            projet.conducteur_travaux = utilisateur\n"
        "            projet.save(update_fields=[\"conducteur_travaux\", \"modifie_le\"])\n"
        "\n"
        "    return affectation\n"
    )
    story.append(make_code_box(code_service_affectation, filename="apps/projets/services/affectations.py (Partie 1)", styles=styles))

    # =========================================================================
    # PAGE 5 : SECTION 3 - SERVICES (SUITE) & SERIALIZERS
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3.2 Couche Service (Suite) : Modification & Révocation avec Invariant CP", styles["H2"]))
    story.append(
        Paragraph(
            "Ajoutez dans <code>apps/projets/services/affectations.py</code> les fonctions de mise à jour et de révocation. "
            "Notez le respect intransigeant de <b>l'Invariant US-04</b> :",
            styles["Body"],
        )
    )

    code_service_revoquer = (
        "def verifier_invariant_chef_projet(projet: Projet, affectation_a_exclure_id=None):\n"
        "    \"\"\"Vérifie qu'il reste au moins un Chef de Projet actif sur le chantier (US-04).\"\"\"\n"
        "    qs = AffectationProjet.objects.filter(\n"
        "        projet=projet,\n"
        "        role_projet=RoleProjet.CHEF_PROJET,\n"
        "        est_actif=True,\n"
        "        supprime_le__isnull=True,\n"
        "    )\n"
        "    if affectation_a_exclure_id:\n"
        "        qs = qs.exclude(id=affectation_a_exclure_id)\n"
        "    if not qs.exists():\n"
        "        raise ValidationError(_(\"Impossible de désactiver ou supprimer le dernier Chef de Projet actif du chantier.\"))\n"
        "\n"
        "\n"
        "def modifier_affectation_projet(*, affectation: AffectationProjet, donnees: dict, modifie_par: Utilisateur | None = None) -> AffectationProjet:\n"
        "    \"\"\"Met à jour le rôle ou les dates d'une affectation avec protection de l'invariant CP.\"\"\"\n"
        "    nouveau_statut_actif = donnees.get(\"est_actif\")\n"
        "    nouveau_role = donnees.get(\"role_projet\")\n"
        "\n"
        "    # Si on désactive ou si on change le rôle d'un Chef de Projet, vérifier qu'un autre CP reste actif\n"
        "    if affectation.role_projet == RoleProjet.CHEF_PROJET:\n"
        "        if nouveau_statut_actif is False or (nouveau_role and nouveau_role != RoleProjet.CHEF_PROJET):\n"
        "            verifier_invariant_chef_projet(affectation.projet, affectation_a_exclure_id=affectation.id)\n"
        "\n"
        "    champs_maj = [\"modifie_le\"]\n"
        "    for champ in [\"role_projet\", \"date_debut\", \"date_fin\", \"est_actif\"]:\n"
        "        if champ in donnees:\n"
        "            setattr(affectation, champ, donnees[champ])\n"
        "            champs_maj.append(champ)\n"
        "\n"
        "    if \"role\" in donnees:\n"
        "        affectation.role = donnees[\"role\"]\n"
        "        champs_maj.append(\"role\")\n"
        "\n"
        "    affectation.modifie_par = modifie_par\n"
        "    champs_maj.append(\"modifie_par\")\n"
        "    affectation.save(update_fields=champs_maj)\n"
        "    return affectation\n"
        "\n"
        "\n"
        "def revoquer_affectation_projet(*, affectation: AffectationProjet, suppression_physique: bool = False, modifie_par: Utilisateur | None = None):\n"
        "    \"\"\"Révoque ou supprime une affectation après validation de l'invariant US-04.\"\"\"\n"
        "    if affectation.role_projet == RoleProjet.CHEF_PROJET and affectation.est_actif:\n"
        "        verifier_invariant_chef_projet(affectation.projet, affectation_a_exclure_id=affectation.id)\n"
        "\n"
        "    if suppression_physique:\n"
        "        affectation.delete()\n"
        "    else:\n"
        "        affectation.est_actif = False\n"
        "        affectation.modifie_par = modifie_par\n"
        "        affectation.save(update_fields=[\"est_actif\", \"modifie_par\", \"modifie_le\"])\n"
    )
    story.append(make_code_box(code_service_revoquer, filename="apps/projets/services/affectations.py (Partie 2)", styles=styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.3 Étape 3 : Créer les Sérialiseurs DRF pour les Affectations", styles["H2"]))
    story.append(
        Paragraph(
            "Créez le fichier <code>apps/projets/serializers/affectation.py</code> pour définir les contrats d'entrée et de sortie :",
            styles["Body"],
        )
    )

    code_serializers = (
        "\"\"\"Sérialiseurs pour l'API d'affectation des collaborateurs aux projets (US-04).\"\"\"\n"
        "\n"
        "from rest_framework import serializers\n"
        "from apps.accounts.models import Role, Utilisateur\n"
        "from apps.core.enums import RoleProjet\n"
        "from apps.projets.models import AffectationProjet\n"
        "\n"
        "\n"
        "class IntervenantProjetDetailSerializer(serializers.Serializer):\n"
        "    id = serializers.UUIDField()\n"
        "    nom = serializers.CharField()\n"
        "    prenom = serializers.CharField(allow_blank=True, default=\"\")\n"
        "    nom_complet = serializers.CharField()\n"
        "    email = serializers.EmailField()\n"
        "    telephone = serializers.CharField(allow_blank=True, default=\"\")\n"
        "    statut = serializers.CharField()\n"
        "\n"
        "\n"
        "class AffectationProjetResponseSerializer(serializers.ModelSerializer):\n"
        "    utilisateur = IntervenantProjetDetailSerializer(read_only=True)\n"
        "    role_projet_libelle = serializers.CharField(source=\"get_role_projet_display\", read_only=True)\n"
        "    role_personnalise_code = serializers.CharField(source=\"role.code\", read_only=True, default=None)\n"
        "\n"
        "    class Meta:\n"
        "        model = AffectationProjet\n"
        "        fields = [\n"
        "            \"id\",\n"
        "            \"projet_id\",\n"
        "            \"utilisateur\",\n"
        "            \"role_projet\",\n"
        "            \"role_projet_libelle\",\n"
        "            \"role_personnalise_code\",\n"
        "            \"date_debut\",\n"
        "            \"date_fin\",\n"
        "            \"est_actif\",\n"
        "            \"cree_le\",\n"
        "        ]\n"
        "\n"
        "\n"
        "class AffectationProjetCreateSerializer(serializers.Serializer):\n"
        "    utilisateur_id = serializers.UUIDField(required=True)\n"
        "    role_projet = serializers.ChoiceField(choices=RoleProjet.choices, required=True)\n"
        "    date_debut = serializers.DateField(required=False, allow_null=True)\n"
        "    date_fin = serializers.DateField(required=False, allow_null=True)\n"
        "    role_personnalise_id = serializers.UUIDField(required=False, allow_null=True)\n"
        "\n"
        "    def validate(self, attrs):\n"
        "        user_id = attrs.get(\"utilisateur_id\")\n"
        "        user = Utilisateur.objects.filter(id=user_id, supprime_le__isnull=True).first()\n"
        "        if not user:\n"
        "            raise serializers.ValidationError({\"utilisateur_id\": \"Collaborateur introuvable dans cette entreprise.\"})\n"
        "        attrs[\"utilisateur_instance\"] = user\n"
        "\n"
        "        role_id = attrs.get(\"role_personnalise_id\")\n"
        "        if role_id:\n"
        "            role = Role.objects.filter(id=role_id, supprime_le__isnull=True).first()\n"
        "            if not role:\n"
        "                raise serializers.ValidationError({\"role_personnalise_id\": \"Rôle personnalisé introuvable.\"})\n"
        "            attrs[\"role_instance\"] = role\n"
        "        return attrs\n"
    )
    story.append(make_code_box(code_serializers, filename="apps/projets/serializers/affectation.py", styles=styles))

    # =========================================================================
    # PAGE 6 : SECTION 3 - VUES D'API DRF & ROUTES URL
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3.4 Étape 4 : Développer les Vues DRF d'Affectation", styles["H2"]))
    story.append(
        Paragraph(
            "Créez le fichier <code>apps/projets/views/affectation.py</code>. Vous y programmez les contrôles d'habilitation "
            "RBAC et la gestion des réponses HTTP :",
            styles["Body"],
        )
    )

    code_views = (
        "\"\"\"Vues API pour la gestion de l'équipe de chantier / affectations (US-04).\"\"\"\n"
        "\n"
        "from django.core.exceptions import ValidationError as DjangoValidationError\n"
        "from django.shortcuts import get_object_or_404\n"
        "from rest_framework import status\n"
        "from rest_framework.exceptions import PermissionDenied, ValidationError\n"
        "from rest_framework.parsers import JSONParser\n"
        "from rest_framework.permissions import IsAuthenticated\n"
        "from rest_framework.response import Response\n"
        "from rest_framework.views import APIView\n"
        "\n"
        "from apps.core.enums import RoleGlobal\n"
        "from apps.projets.models import AffectationProjet, Projet\n"
        "from apps.projets.serializers.affectation import (\n"
        "    AffectationProjetCreateSerializer,\n"
        "    AffectationProjetResponseSerializer,\n"
        ")\n"
        "from apps.projets.services.affectations import (\n"
        "    affecter_collaborateur_projet,\n"
        "    lister_affectations_projet,\n"
        "    modifier_affectation_projet,\n"
        "    revoquer_affectation_projet,\n"
        ")\n"
        "\n"
        "\n"
        "def _verifier_droits_gestion_equipe(user, projet: Projet):\n"
        "    \"\"\"Autorise l'administrateur, le DG ou le Chef de Projet assigné à ce chantier.\"\"\"\n"
        "    est_admin = (\n"
        "        getattr(user, \"is_owner\", False)\n"
        "        or getattr(user, \"is_dg\", False)\n"
        "        or getattr(user, \"role_global\", None) in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)\n"
        "        or getattr(user, \"is_superuser\", False)\n"
        "    )\n"
        "    est_cp_du_projet = (projet.chef_projet_id == user.id or user.role_global == RoleGlobal.CHEF_PROJET)\n"
        "    if not (est_admin or est_cp_du_projet):\n"
        "        raise PermissionDenied(\"Seul le Chef de Projet assigné ou la Direction peut gérer l'équipe du chantier.\")\n"
        "\n"
        "\n"
        "class ProjetAffectationListCreateView(APIView):\n"
        "    \"\"`GET` et `POST /api/v1/projets/{projet_id}/affectations/`.\"\"\"\n"
        "    permission_classes = [IsAuthenticated]\n"
        "    parser_classes = [JSONParser]\n"
        "\n"
        "    def get(self, request, projet_id):\n"
        "        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)\n"
        "        actifs_seulement = request.query_params.get(\"actifs_seulement\", \"false\").lower() == \"true\"\n"
        "        qs = lister_affectations_projet(projet, actifs_seulement=actifs_seulement)\n"
        "        serializer = AffectationProjetResponseSerializer(qs, many=True)\n"
        "        return Response(serializer.data, status=status.HTTP_200_OK)\n"
        "\n"
        "    def post(self, request, projet_id):\n"
        "        projet = get_object_or_404(Projet, pk=projet_id, supprime_le__isnull=True)\n"
        "        _verifier_droits_gestion_equipe(request.user, projet)\n"
        "        serializer = AffectationProjetCreateSerializer(data=request.data)\n"
        "        serializer.is_valid(raise_exception=True)\n"
        "        try:\n"
        "            aff = affecter_collaborateur_projet(\n"
        "                projet=projet,\n"
        "                utilisateur=serializer.validated_data[\"utilisateur_instance\"],\n"
        "                role_projet=serializer.validated_data[\"role_projet\"],\n"
        "                date_debut=serializer.validated_data.get(\"date_debut\"),\n"
        "                date_fin=serializer.validated_data.get(\"date_fin\"),\n"
        "                role_personnalise=serializer.validated_data.get(\"role_instance\"),\n"
        "                modifie_par=request.user,\n"
        "            )\n"
        "        except DjangoValidationError as exc:\n"
        "            raise ValidationError({\"detail\": str(exc.message if hasattr(exc, 'message') else exc)})\n"
        "        return Response(AffectationProjetResponseSerializer(aff).data, status=status.HTTP_201_CREATED)\n"
    )
    story.append(make_code_box(code_views, filename="apps/projets/views/affectation.py (Partie 1)", styles=styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.5 Étape 5 : Déclarer les Routes URL", styles["H2"]))
    story.append(
        Paragraph(
            "Ouvrez <code>apps/projets/urls.py</code> et ajoutez les deux routes RESTful imbriquées pour les affectations :",
            styles["Body"],
        )
    )

    code_urls = (
        "from apps.projets.views.affectation import (\n"
        "    ProjetAffectationDetailView,\n"
        "    ProjetAffectationListCreateView,\n"
        ")\n"
        "\n"
        "urlpatterns = [\n"
        "    # ... routes existantes ...\n"
        "    path(\"projets/<uuid:projet_id>/affectations/\", ProjetAffectationListCreateView.as_view(), name=\"projet-affectations-liste\"),\n"
        "    path(\"projets/<uuid:projet_id>/affectations/<uuid:pk>/\", ProjetAffectationDetailView.as_view(), name=\"projet-affectation-detail\"),\n"
        "]\n"
    )
    story.append(make_code_box(code_urls, filename="apps/projets/urls.py", styles=styles))

    # =========================================================================
    # PAGE 7 : SECTION 4 - SIGNAL D'ERREUR BAYÉSIEN (PRE-MORTEM)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM (KAHNEMAN)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(
        Paragraph(
            "Dans la technique du <b>Pre-Mortem</b> (Gary Klein & Daniel Kahneman), nous nous projetons dans le scénario "
            "où la fonctionnalité est livrée et subit des dysfonctionnements critiques. Voici l'analyse préventive :",
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
            Paragraph("<b>1. Chantier sans Chef de Projet (Orphelin)</b>", styles["TableCellBold"]),
            Paragraph("Un utilisateur désactive ou supprime l'affectation du CP, laissant le chantier sans responsable habilité.", styles["TableCell"]),
            Paragraph("La fonction <code>verifier_invariant_chef_projet</code> intercepte l'action et lève une exception HTTP 400 si aucun autre CP n'est actif.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>2. Collision de Clé Unique SQL</b>", styles["TableCellBold"]),
            Paragraph("Une affectation inactive existait dans le passé. Une nouvelle affectation échoue sur <code>uq_affectation_utilisateur_projet</code>.", styles["TableCell"]),
            Paragraph("Utilisation de <code>get_or_create</code> puis réactivation explicite avec mise à jour du rôle et des dates.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>3. Usurpation par Ouvrier / Tiers</b>", styles["TableCellBold"]),
            Paragraph("Un chef de chantier ou un sous-traitant s'auto-attribue des droits de Chef de Projet via l'API.", styles["TableCell"]),
            Paragraph("Contrôle d'autorisation strict dans <code>_verifier_droits_gestion_equipe</code> (seul DG, Admin ou CP peut modifier l'équipe).", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>4. Explosion N+1 Queries SQL</b>", styles["TableCellBold"]),
            Paragraph("La liste de 30 affectations déclenche 30 requêtes SQL pour charger les profils et rôles.", styles["TableCell"]),
            Paragraph("Utilisation systématique de <code>select_related('utilisateur', 'role')</code> garantissant 1 seule requête SQL.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>5. Dates Incohérentes</b>", styles["TableCellBold"]),
            Paragraph("La date de fin est antérieure à la date de début de mission sur le chantier.", styles["TableCell"]),
            Paragraph("Validation dans le service : <code>date_fin >= date_debut</code> obligatoire.", styles["TableCellBold"]),
        ],
    ]
    t_pm = Table(premortem_data, colWidths=[130, 180, 213])
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
    # PAGE 8 : SECTION 5 - CHECKLIST DE TESTS AUTOMATISÉS
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 5 : CHECKLIST DE TESTS AUTOMATISÉS PYTEST", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(
        Paragraph(
            "Pour ancrer vos apprentissages (Pilier 2 et 3 de Dehaene : Engagement Actif & Retour sur Erreur), "
            "vous allez taper manuellement le fichier de test <code>apps/projets/tests/test_affectations_equipe.py</code> :",
            styles["Body"],
        )
    )

    code_tests = (
        "import pytest\n"
        "from rest_framework import status\n"
        "from apps.core.enums import RoleProjet\n"
        "from apps.projets.models import AffectationProjet\n"
        "\n"
        "\n"
        "@pytest.mark.django_db\n"
        "def test_affecter_conducteur_travaux_et_consultant_lecture(client_tenant, admin_user, projet_db, collaborateur_user):\n"
        "    \"\"\"Vérifie l'affectation réussie avec CT et Consultant lecture (VI).\"\"\"\n"
        "    client = _auth(client_tenant, admin_user)\n"
        "    url = f\"/api/v1/projets/{projet_db.id}/affectations/\"\n"
        "\n"
        "    # 1. Affectation Conducteur de Travaux\n"
        "    payload_ct = {\"utilisateur_id\": str(collaborateur_user.id), \"role_projet\": RoleProjet.CONDUCTEUR_TRAVAUX}\n"
        "    rep_ct = client.post(url, payload_ct, format=\"json\")\n"
        "    assert rep_ct.status_code == status.HTTP_201_CREATED\n"
        "    assert rep_ct.json()[\"role_projet\"] == RoleProjet.CONDUCTEUR_TRAVAUX\n"
        "\n"
        "    # 2. Mise à jour vers Consultant lecture (VISITEUR)\n"
        "    aff_id = rep_ct.json()[\"id\"]\n"
        "    rep_patch = client.patch(f\"{url}{aff_id}/\", {\"role_projet\": RoleProjet.VISITEUR}, format=\"json\")\n"
        "    assert rep_patch.status_code == status.HTTP_200_OK\n"
        "    assert rep_patch.json()[\"role_projet_libelle\"] == \"Consultant lecture\"\n"
        "\n"
        "\n"
        "@pytest.mark.django_db\n"
        "def test_protection_invariant_dernier_chef_projet(client_tenant, admin_user, projet_db, cp_user):\n"
        "    \"\"\"Empêche formellement de désactiver ou supprimer le dernier Chef de Projet (US-04).\"\"\"\n"
        "    client = _auth(client_tenant, admin_user)\n"
        "    aff_cp = AffectationProjet.objects.get(projet=projet_db, utilisateur=cp_user)\n"
        "    url_detail = f\"/api/v1/projets/{projet_db.id}/affectations/{aff_cp.id}/\"\n"
        "\n"
        "    # Tentative de désactivation\n"
        "    rep_desact = client.patch(url_detail, {\"est_actif\": False}, format=\"json\")\n"
        "    assert rep_desact.status_code == status.HTTP_400_BAD_REQUEST\n"
        "    assert \"dernier chef de projet\" in str(rep_desact.json()).lower()\n"
        "\n"
        "    # Tentative de suppression\n"
        "    rep_del = client.delete(url_detail)\n"
        "    assert rep_del.status_code == status.HTTP_400_BAD_REQUEST\n"
    )
    story.append(make_code_box(code_tests, filename="apps/projets/tests/test_affectations_equipe.py", styles=styles))
    story.append(Spacer(1, 8))

    cmds_text = (
        "<b>Commandes d'exécution des tests dans le terminal :</b><br/>"
        "<code>.venv\\Scripts\\pytest.exe apps/projets/tests/test_affectations_equipe.py -v</code><br/><br/>"
        "<b>Vérification de non-régression globale sur les projets :</b><br/>"
        "<code>.venv\\Scripts\\pytest.exe apps/projets/tests/test_creation_projet_v2.py -v</code>"
    )
    story.append(make_callout(cmds_text, title="Protocole de Vérification en Terminal", style_type="success", styles=styles))

    # =========================================================================
    # PAGE 9 : SECTION 6 - DÉFI HOMO DOCENS & CLÔTURE MÉTACOGNITIVE
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("SECTION 6 : DÉFI HOMO DOCENS & CLÔTURE MÉTACOGNITIVE", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(Paragraph("6.1 Le Défi de l'Homo Docens (Enseigner pour Ancrer)", styles["H2"]))
    story.append(
        Paragraph(
            "Dans la recherche cognitive (Principe 8 de Lovett et al.), l'apprenant devient un <b>Homo Docens</b> "
            "lorsqu'il est capable d'expliquer le 'pourquoi' de chaque arbitrage technique. "
            "Prenez une feuille ou votre carnet d'ingénieur et répondez à ces 3 questions sans regarder le code :",
            styles["Body"],
        )
    )

    questions_docens = [
        "<b>Question 1 :</b> Pourquoi avoir choisi des endpoints imbriqués <code>/api/v1/projets/{id}/affectations/</code> plutôt qu'un endpoint plat <code>/api/v1/affectations/</code> ?",
        "<b>Question 2 :</b> Comment la fonction <code>affecter_collaborateur_projet</code> gère-t-elle le cas où un collaborateur a déjà été affecté puis désactivé sur le chantier dans le passé sans violer la contrainte d'unicité SQL ?",
        "<b>Question 3 :</b> Comment le système garantit-il l'invariant US-04 interdisant de laisser un chantier sans Chef de Projet actif ?",
    ]
    for q in questions_docens:
        story.append(Paragraph(f"• {q}", styles["Bullet"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("6.2 Rituel de Somnolence & Replay Neuronal Nocturne", styles["H2"]))
    story.append(
        Paragraph(
            "Le sommeil lent et le sommeil paradoxal sont les phases où votre hippocampe réactive les assemblées neuronales "
            "sollicitées pendant l'exercice à un rythme accéléré ($20\\times$), les intégrant dans les réseaux corticaux stables. "
            "Pour optimiser cette consolidation biologique :",
            styles["Body"],
        )
    )

    nocturne_box = (
        "<b>Rituel du Soir avant l'Endormissement :</b><br/>"
        "1. <b>Déconnexion visuelle :</b> Éteignez vos écrans 30 minutes avant le coucher.<br/>"
        "2. <b>Revue mentale :</b> Visualisez mentalement le cycle complet : la requête HTTP qui arrive, la validation DRF, "
        "la transaction atomique PostgreSQL et la mise à jour de l'équipe.<br/>"
        "3. <b>Décharge subconsciente :</b> Dites-vous avec foi : <i>« Les compétences d'architecture et de sécurité BTP "
        "sont désormais gravées dans mon esprit. Demain, j'exécuterai chaque tâche avec aisance et souveraineté. »</i>"
    )
    story.append(make_callout(nocturne_box, title="Protocole de Consolidation Subconsciente", style_type="neuro", styles=styles))
    story.append(Spacer(1, 12))

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
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
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
            "MANUEL_SPRINT_3_TACHE_02_AFFECTATION_COLLABORATEURS_PROJET.pdf",
        )
    )
    generate_manual_pdf(out_pdf)
