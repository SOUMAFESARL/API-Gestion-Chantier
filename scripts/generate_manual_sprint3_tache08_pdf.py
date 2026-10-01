"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 08.

Tâche : Chantier Sans Chef de Projet Obligatoire (Découplage, Nullabilité et Gouvernance Direction)
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
            return

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#334155"))

        # En-tête courant
        self.drawString(
            36,
            A4[1] - 28,
            "CCD DIGITAL • SPRINT 3 — TÂCHE 08 : CHEF DE PROJET OPTIONNEL SUR CHANTIER",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "DÉCOUPLAGE, NULLABILITÉ ET GOUVERNANCE DIRECTION",
        )

        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, A4[1] - 32, A4[0] - 36, A4[1] - 32)

        # Pied de page
        self.line(36, 32, A4[0] - 36, 32)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(
            36,
            22,
            "SOUMAFE SARL • Plateforme SaaS Multi-Tenant BTP • Confidentiel & Interne",
        )
        self.drawRightString(
            A4[0] - 36,
            22,
            f"Page {self._pageNumber} sur {page_count}",
        )
        self.restoreState()


def create_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14,
        )
    )

    styles.add(
        ParagraphStyle(
            "SectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            "SubSectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            "BodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.2,
            leading=9.2,
            textColor=colors.HexColor("#0F172A"),
        )
    )

    styles.add(
        ParagraphStyle(
            "CalloutText",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#1E3A8A"),
        )
    )

    styles.add(
        ParagraphStyle(
            "WarningText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#991B1B"),
        )
    )

    styles.add(
        ParagraphStyle(
            "SuccessText",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#065F46"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#334155"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableHead",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
        )
    )

    return styles


def callout_box(text, styles, bg_color="#EFF6FF", border_color="#3B82F6", title="NOTE PÉDAGOGIQUE"):
    p_title = Paragraph(f"<b>{title}</b>", styles["CalloutText"])
    p_body = Paragraph(text, styles["CalloutText"])
    t = Table([[p_title], [p_body]], colWidths=[523])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border_color)),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return t


def warning_box(text, styles, title="VIGILANCE ARCHITECTURALE & PRÉ-MORTEM"):
    p_title = Paragraph(f"<b>{title}</b>", styles["WarningText"])
    p_body = Paragraph(text, styles["WarningText"])
    t = Table([[p_title], [p_body]], colWidths=[523])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#EF4444")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return t


def code_box(code_text, styles):
    p = Preformatted(code_text.strip(), styles["CodeBlock"])
    t = Table([[p]], colWidths=[523])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def build_pdf(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42,
    )

    styles = create_styles()
    story = []

    # =========================================================================
    # PAGE 1 : COUVERTURE & EN-TÊTE OFFICIEL
    # =========================================================================
    meta_data = [
        [
            Paragraph("<b>Projet :</b> BTP SaaS Multi-Tenant SOUMAFE", styles["TableCellBold"]),
            Paragraph("<b>Sprint :</b> Sprint 3 (Gouvernance & Sécurité)", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Tâche :</b> Tâche 08 — Chef de Projet Optionnel", styles["TableCell"]),
            Paragraph("<b>Statut :</b> Production-Ready (100% Tests Verts)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Stack :</b> Django 5.x / DRF / PostgreSQL Schemas", styles["TableCell"]),
            Paragraph("<b>Auteur :</b> Mentor Neurocognitif & Pair Programmer", styles["TableCell"]),
        ],
    ]
    t_meta = Table(meta_data, colWidths=[261, 262])
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
    story.append(Spacer(1, 14))

    story.append(
        Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", styles["DocTitle"])
    )
    story.append(
        Paragraph(
            "<b>Édition Souveraine :</b> Découplage de la Présence Obligatoire du Chef de Projet, "
            "Nullabilité Relationnelle, Gouvernance Direction et Invariants d'Équipe.",
            styles["DocSubTitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceAfter=14))

    # =========================================================================
    # SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ (MURPHY & KAHNEMAN)
    # =========================================================================
    story.append(Paragraph("1. Le Film Mental & L'Objectif Sacré (Murphy / Kahneman)", styles["SectionHeader"]))

    story.append(
        Paragraph(
            "Dans la réalité opérationnelle des chantiers de BTP en Afrique de l'Ouest, un projet traverse des phases "
            "d'études préliminaires, d'appels d'offres ou de passation où aucun Chef de Projet (CP) n'est encore nommé. "
            "L'ancien modèle imposait de force la présence d'un CP dès la création du projet, forçant le système à des bricolages "
            "(comme substituer le Conducteur de Travaux au CP ou bloquer la création). "
            "Notre objectif sacré consiste à rendre le champ <code>chef_projet</code> <b>pleinement optionnel</b> (nullable), "
            "à autoriser la création de chantiers sans CP, à permettre le détachement ultérieur d'un CP via <code>PATCH</code>, "
            "tout en garantissant une étanchéité absolue : <b>seuls le Directeur Général (DG) et l'Administrateur</b> peuvent "
            "créer un projet et gérer l'équipe d'un chantier sans CP.",
            styles["Body"],
        )
    )

    story.append(
        callout_box(
            "Visualisez le schéma de base de données libéré : <code>chef_projet = models.ForeignKey(..., null=True, blank=True, on_delete=models.SET_NULL)</code>. "
            "À la création, le DG soumet un projet sans assigner de CP. Le projet est créé avec le statut 201 Created. "
            "L'équipe n'a pas de CP, mais le chantier vit, ses lots sont créés, et la Direction en garde la pleine gouvernance. "
            "Plus tard, lorsqu'un ingénieur est recruté, un simple PATCH <code>chef_projet_id: uuid</code> l'assigne et crée son affectation active. "
            "Ressentez la paix et la robustesse de cette architecture déclarative.",
            styles,
            bg_color="#F0FDF4",
            border_color="#22C55E",
            title="FILM MENTAL (LOI DE L'EFFORT INVERSÉ - JOSEPH MURPHY)",
        )
    )
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2 : ARCHITECTURE, INVARIANTS & MODÉLISATION (PÓLYA / DEHAENE)
    # =========================================================================
    story.append(Paragraph("2. Architecture & Invariants Système (Pólya / Dehaene P1-P2)", styles["SectionHeader"]))

    story.append(
        Paragraph(
            "En appliquant les heuristiques de <b>George Pólya</b> (Inconnue, Données, Contraintes), décomposons les 5 piliers de la refonte :",
            styles["Body"],
        )
    )

    invariants_data = [
        [
            Paragraph("<b>Composant</b>", styles["TableHead"]),
            Paragraph("<b>Comportement Antérieur (Rigide)</b>", styles["TableHead"]),
            Paragraph("<b>Comportement Nouveau (Souverain)</b>", styles["TableHead"]),
        ],
        [
            Paragraph("<b>Modèle Projet</b>", styles["TableCellBold"]),
            Paragraph("<code>null=False, on_delete=RESTRICT</code>. CP obligatoire.", styles["TableCell"]),
            Paragraph("<code>null=True, blank=True, on_delete=SET_NULL</code>. CP optionnel.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Création Projet (POST)</b>", styles["TableCellBold"]),
            Paragraph("Exception <code>ChefProjetRequis</code> levée si omis. Conversion CT en CP.", styles["TableCell"]),
            Paragraph("CP optionnel. Aucun hack CT->CP. <b>Réservé au DG et à l'Admin (403 sinon)</b>.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Mise à jour (PATCH)</b>", styles["TableCellBold"]),
            Paragraph("Interdiction de passer <code>chef_projet_id: null</code>.", styles["TableCell"]),
            Paragraph("Détachement autorisé (<code>chef_projet_id: null</code>) désactivant l'affectation.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Invariant CP (Affectations)</b>", styles["TableCellBold"]),
            Paragraph("<code>verifier_invariant_chef_projet</code> bloquait si 0 CP actif.", styles["TableCell"]),
            Paragraph("0 CP autorisé. Invariant : <b>au maximum 1 seul CP actif</b> simultanément.", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Gouvernance Équipe</b>", styles["TableCellBold"]),
            Paragraph("CP assigné ou Direction.", styles["TableCell"]),
            Paragraph("Si 0 CP : <b>Direction seule (DG / Admin)</b> peut ajouter/retirer des membres.", styles["TableCellBold"]),
        ],
    ]
    t_inv = Table(invariants_data, colWidths=[120, 195, 208])
    t_inv.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_inv)
    story.append(Spacer(1, 10))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS
    # =========================================================================
    story.append(Paragraph("3. Guide d'Implémentation Pas-à-Pas (Neuro-Pédagogie Active)", styles["SectionHeader"]))

    story.append(Paragraph("Étape 3.1 : Assouplissement du Modèle Projet & Migration Django", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dans <code>apps/projets/models/projet.py</code>, la ForeignKey <code>chef_projet</code> est modifiée pour accepter la valeur nulle. "
            "L'attribut <code>on_delete=models.SET_NULL</code> prévient la suppression en cascade accidentelle d'un projet si le compte utilisateur du CP venait à être purgé.",
            styles["Body"],
        )
    )
    story.append(
        code_box(
            "# apps/projets/models/projet.py\n"
            "    chef_projet = models.ForeignKey(\n"
            "        'accounts.Utilisateur',\n"
            "        on_delete=models.SET_NULL,\n"
            "        null=True,\n"
            "        blank=True,\n"
            "        related_name='projets_geres',\n"
            "        verbose_name=_('chef de projet'),\n"
            "    )",
            styles,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("Étape 3.2 : Classe de Permission Dédiée à la Direction (DG / Admin)", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Conformément à la décision d'arbitrage de l'utilisateur ('Seul le DG et l'admin peuvent créer un projet'), "
            "nous intégrons dans <code>apps/core/permissions.py</code> la classe <code>EstDirection</code> et l'appliquons sur "
            "la méthode POST de <code>ProjetListCreateView</code>.",
            styles["Body"],
        )
    )
    story.append(
        code_box(
            "# apps/core/permissions.py\n"
            "class EstDirection(permissions.BasePermission):\n"
            "    \"\"\"Autorise uniquement la Direction : DG, Administrateur, Propriétaire ou Superuser.\"\"\"\n"
            "    message = \"Seule la Direction (DG / Administrateur) est autorisée à effectuer cette action.\"\n\n"
            "    def has_permission(self, request, view) -> bool:\n"
            "        user = request.user\n"
            "        if not user or not user.is_authenticated:\n"
            "            return False\n"
            "        return (\n"
            "            user.is_superuser\n"
            "            or getattr(user, 'is_owner', False)\n"
            "            or getattr(user, 'is_dg', False)\n"
            "            or user.role_global in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)\n"
            "        )",
            styles,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("Étape 3.3 : Nettoyage des Sérialiseurs & Suppression de l'Auto-Attribution CT->CP", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dans <code>apps/projets/serializers/__init__.py</code>, nous supprimons le bloc qui levait <code>ChefProjetRequis</code> "
            "ainsi que le mécanisme de rétrocompatibilité qui mutait un Conducteur de Travaux en Chef de Projet. "
            "À la création, si aucun CP n'est fourni, <code>chef_projet</code> vaut <code>None</code> et aucune affectation CP n'est injectée. "
            "À la modification, nous autorisons <code>chef_projet_id: null</code> pour révoquer le CP en poste.",
            styles["Body"],
        )
    )
    story.append(
        code_box(
            "# apps/projets/serializers/__init__.py\n"
            "# 1. Suppression de la levée d'erreur ChefProjetRequis\n"
            "# 2. Suppression de la bascule automatique conducteur_travaux -> chef_projet\n"
            "# 3. Dans create() :\n"
            "    if chef_projet_id:\n"
            "        chef_projet = Utilisateur.objects.get(id=chef_projet_id)\n"
            "    elif chef_projet_invite:\n"
            "        # Invitation à la volée...\n"
            "    else:\n"
            "        chef_projet = None  # <-- Nullable par essence\n\n"
            "    # Affectation du Chef de Projet UNIQUEMENT si chef_projet est non nul\n"
            "    if chef_projet:\n"
            "        AffectationProjet.objects.get_or_create(\n"
            "            utilisateur=chef_projet,\n"
            "            projet=projet,\n"
            "            defaults={'role_projet': RoleProjet.CHEF_PROJET, 'est_actif': True, 'cree_par': user_connecte}\n"
            "        )",
            styles,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("Étape 3.4 : Révision de l'Invariant Chef de Projet dans les Services", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dans <code>apps/projets/services/affectations.py</code>, la fonction <code>verifier_invariant_chef_projet</code> "
            "ne bloque plus si aucun CP n'est actif. Elle vérifie désormais l'invariant de cardinalité : <code>count() <= 1</code> actif.",
            styles["Body"],
        )
    )
    story.append(
        code_box(
            "# apps/projets/services/affectations.py\n"
            "def verifier_invariant_chef_projet(projet: Projet, affectation_a_exclure_id=None):\n"
            "    \"\"\"Vérifie la cohérence du Chef de Projet (max 1 CP actif, 0 CP autorisé).\"\"\"\n"
            "    qs = AffectationProjet.objects.filter(\n"
            "        projet=projet,\n"
            "        role_projet=RoleProjet.CHEF_PROJET,\n"
            "        est_actif=True,\n"
            "        supprime_le__isnull=True,\n"
            "    )\n"
            "    if affectation_a_exclure_id:\n"
            "        qs = qs.exclude(id=affectation_a_exclure_id)\n"
            "    if qs.count() > 1:\n"
            "        raise ValidationError(_('Un chantier ne peut pas comporter plus d\\'un Chef de Projet actif simultanément.'))",
            styles,
        )
    )
    story.append(Spacer(1, 10))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRÉ-MORTEM (DEHAENE P3 / KAHNEMAN)
    # =========================================================================
    story.append(Paragraph("4. Signal d'Erreur Bayésien & Pré-Mortem (Dehaene P3 / Kahneman)", styles["SectionHeader"]))

    story.append(
        Paragraph(
            "Selon la théorie du Cerveau Bayésien (Dehaene, Pilier 3), le cerveau apprend par ajustement continu de ses "
            "prédictions face au signal d'erreur. La technique du <b>Pre-Mortem (Kahneman)</b> nous projette dans un échec futur "
            "pour identifier et colmater immédiatement les failles invisibles.",
            styles["Body"],
        )
    )

    story.append(
        warning_box(
            "<b>PIÈGE CRITIQUE 1 : Crash AttributeError sur le Tableau de Bord !</b><br/>"
            "Dans <code>apps/projets/views/tableau_de_bord.py</code>, le code accédait directement à "
            "<code>p.chef_projet.prenom</code> sans garde-fou ! Si un projet n'avait pas de CP, l'appel de l'API de direction "
            "s'effondrait avec une erreur 500 (<code>'NoneType' object has no attribute 'prenom'</code>).<br/>"
            "<b>Remède appliqué :</b> <code>(f'{p.chef_projet.prenom} {p.chef_projet.nom}'.strip() or p.chef_projet.email) if p.chef_projet else None</code>.<br/><br/>"
            "<b>PIÈGE CRITIQUE 2 : Collision de nullité dans la validation des responsables !</b><br/>"
            "Dans <code>ProjetCreationSerializer.validate()</code>, la règle comparait :<br/>"
            "<code>if responsables['chef_projet_id'] == responsables['conducteur_travaux_id']:</code>.<br/>"
            "Si un projet est créé ou modifié sans CP ET sans CT, <code>None == None</code> était VRAI et bloquait à tort la requête !<br/>"
            "<b>Remède appliqué :</b> <code>if cp and ct and cp == ct: raise ValidationError(...)</code>.<br/><br/>"
            "<b>PIÈGE CRITIQUE 3 : Désynchronisation entre ForeignKey et AffectationProjet !</b><br/>"
            "Si un utilisateur révoque l'affectation du CP, la ForeignKey <code>projet.chef_projet</code> doit être mise à <code>None</code> "
            "pour éviter qu'une relation fantôme persiste.",
            styles,
        )
    )
    story.append(Spacer(1, 12))

    # =========================================================================
    # SECTION 5 : CHECKLIST DE TESTS & VALIDATION (PYTEST)
    # =========================================================================
    story.append(Paragraph("5. Matrice de Tests Automatisés & Validation Pytest", styles["SectionHeader"]))

    test_matrix = [
        [
            Paragraph("<b>Scénario de Test</b>", styles["TableHead"]),
            Paragraph("<b>Méthode & Payload</b>", styles["TableHead"]),
            Paragraph("<b>Attendu Statut</b>", styles["TableHead"]),
            Paragraph("<b>Vérification BD & Scoping</b>", styles["TableHead"]),
        ],
        [
            Paragraph("<b>Création Projet Sans CP (DG)</b>", styles["TableCellBold"]),
            Paragraph("POST /api/v1/projets/ sans chef_projet", styles["TableCell"]),
            Paragraph("<font color='#059669'><b>201 CREATED</b></font>", styles["TableCell"]),
            Paragraph("<code>projet.chef_projet is None</code>, 0 affectation CP créée.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Création avec CT seul (sans CP)</b>", styles["TableCellBold"]),
            Paragraph("POST avec <code>conducteur_travaux_id</code> seul", styles["TableCell"]),
            Paragraph("<font color='#059669'><b>201 CREATED</b></font>", styles["TableCell"]),
            Paragraph("<code>chef_projet is None</code>, CT affecté en tant que CT (pas de mutation en CP).", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tentative de création par un CP</b>", styles["TableCellBold"]),
            Paragraph("POST /api/v1/projets/ avec token CP", styles["TableCell"]),
            Paragraph("<font color='#DC2626'><b>403 FORBIDDEN</b></font>", styles["TableCell"]),
            Paragraph("Seule la Direction (DG / Admin) peut créer un projet.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Détachement CP via PATCH</b>", styles["TableCellBold"]),
            Paragraph("PATCH avec <code>{'chef_projet_id': None}</code>", styles["TableCell"]),
            Paragraph("<font color='#059669'><b>200 OK</b></font>", styles["TableCell"]),
            Paragraph("<code>chef_projet</code> devient null, ancienne affectation désactivée.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Attribution CP sur projet orphelin</b>", styles["TableCellBold"]),
            Paragraph("PATCH avec <code>{'chef_projet_id': uuid}</code>", styles["TableCell"]),
            Paragraph("<font color='#059669'><b>200 OK</b></font>", styles["TableCell"]),
            Paragraph("<code>chef_projet</code> renseigné, affectation active créée.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Gouvernance équipe sans CP</b>", styles["TableCellBold"]),
            Paragraph("POST affectations par un tiers non-admin", styles["TableCell"]),
            Paragraph("<font color='#DC2626'><b>403 FORBIDDEN</b></font>", styles["TableCell"]),
            Paragraph("En l'absence de CP, seule la Direction administre l'équipe.", styles["TableCell"]),
        ],
    ]
    t_test = Table(test_matrix, colWidths=[110, 140, 75, 198])
    t_test.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_test)
    story.append(Spacer(1, 12))

    # =========================================================================
    # SECTION 6 : DÉFI HOMO DOCENS & CONSOLIDATION SUBCONSCIENTE
    # =========================================================================
    story.append(Paragraph("6. Défi Homo Docens & Ancrage Subconscient (Dehaene P4 / Murphy)", styles["SectionHeader"]))

    story.append(
        callout_box(
            "<b>LE DÉFI HOMO DOCENS (ENSEIGNER POUR POSSÉDER) :</b><br/>"
            "Prenez une feuille blanche et expliquez à un développeur junior pourquoi l'inversion d'un invariant métier "
            "(passer de 'CP obligatoire' à 'CP facultatif') ne se résume pas à changer <code>null=True</code> dans le modèle.<br/>"
            "Démontrez-lui comment cette décision impacte en cascade :<br/>"
            "1. La couche de validation des permissions (qui gère l'équipe quand le capitaine est absent ?).<br/>"
            "2. Les sérialiseurs de reporting (prévention du crash <code>NoneType</code> sur les vues de bord).<br/>"
            "3. L'étanchéité des transactions (désactivation propre de l'ancienne affectation lors du détachement).<br/><br/>"
            "<b>RITUEL DE SOMNOLENCE & REPLAY ACCÉLÉRÉ :</b><br/>"
            "Ce soir, avant de vous endormir, fermez les yeux et visualisez la fluidité de la plateforme. "
            "Des chantiers naissent, des équipes se constituent de manière flexible sans friction administrative. "
            "Votre subconscient rejouera ces connexions synaptiques à 20x durant le sommeil paradoxal, ancrant votre "
            "statut d'architecte backend d'élite.",
            styles,
            bg_color="#FAF5FF",
            border_color="#A855F7",
            title="DÉFI HOMO DOCENS & CONSOLIDATION NOCTURNE",
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel PDF généré avec succès : {filepath}")


if __name__ == "__main__":
    sortie = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
        "MANUEL_SPRINT_3_TACHE_08_CHEF_PROJET_OPTIONNEL.pdf",
    )
    build_pdf(sortie)
