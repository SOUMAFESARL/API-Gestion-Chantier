"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 04.

Tâche : API d'Exposition du Référentiel des Modules (GET /api/v1/modules/)
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
            return  # Page de garde / en-tête

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#334155"))

        # En-tête courant
        self.drawString(
            36,
            A4[1] - 28,
            "CCD DIGITAL • SPRINT 3 — TÂCHE 04 : API RÉFÉRENTIEL DES MODULES",
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
            fontSize=18,
            leading=23,
            textColor=colors.HexColor("#0F172A"),
            alignment=0,
            spaceAfter=8,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14.5,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
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
            fontSize=13,
            leading=16.5,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=11,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "H2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.2,
            leading=13.5,
            textColor=colors.HexColor("#0369A1"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=12.5,
            textColor=colors.HexColor("#334155"),
            spaceBefore=5,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=12,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=4,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.3,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=4,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=11.5,
            textColor=colors.HexColor("#1E293B"),
            leftIndent=12,
            firstLineIndent=-8,
            spaceAfter=3,
        ),
        "CalloutText": ParagraphStyle(
            "CalloutText",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.3,
            leading=12,
            textColor=colors.HexColor("#0C4A6E"),
        ),
        "Preformatted": ParagraphStyle(
            "Preformatted",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.1,
            leading=9.2,
            textColor=colors.HexColor("#0F172A"),
        ),
        "TableHead": ParagraphStyle(
            "TableHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#FFFFFF"),
            alignment=1,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10.5,
            textColor=colors.HexColor("#1E293B"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=10.5,
            textColor=colors.HexColor("#0F172A"),
        ),
        "TableCellMono": ParagraphStyle(
            "TableCellMono",
            parent=base["Normal"],
            fontName="Courier-Bold",
            fontSize=7.4,
            leading=9.8,
            textColor=colors.HexColor("#0284C7"),
        ),
    }

    return styles


def callout_box(text, styles, title="PRINCIPE NEUROCOGNITIF & FONDATION"):
    content = [
        Paragraph(f"<b>{title}</b>", styles["H3"]),
        Spacer(1, 2),
        Paragraph(text, styles["CalloutText"]),
    ]
    t = Table([[content]], colWidths=[523])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F9FF")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#38BDF8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def code_box(code_text, styles, caption=None):
    story_items = []
    if caption:
        story_items.append(Paragraph(f"<b>Code :</b> {caption}", styles["TableCellBold"]))
        story_items.append(Spacer(1, 2))

    pre = Preformatted(code_text.strip(), styles["Preformatted"])
    t = Table([[pre]], colWidths=[523])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story_items.append(t)
    return KeepTogether(story_items)


def build_pdf(filename="Manuels_Apprentissage/MANUEL_SPRINT_3_TACHE_04_API_CATALOGUE_MODULES.pdf"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42,
    )

    styles = get_styles()
    story = []

    # ==========================================
    # PAGE DE GARDE / EN-TÊTE
    # ==========================================
    story.append(Paragraph("CCD DIGITAL • ARCHITECTURE DU RÉFÉRENTIEL BTP & RBAC", styles["CoverSuper"]))
    story.append(
        Paragraph(
            "MANUEL DE PRATIQUE AUTONOME : SPRINT 3 — TÂCHE 04<br/>"
            "API D'EXPOSITION DU CATALOGUE DES MODULES SOUVERAINS",
            styles["CoverTitle"],
        )
    )
    story.append(
        Paragraph(
            "Conception, typage et exposition sécurisée du catalogue des 5 modules BTP "
            "(<code>GET /api/v1/modules/</code>) avec métadonnées enrichies (libellés, descriptions, "
            "icônes, ordre de présentation et niveaux d'accès supportés) pour une consommation "
            "fluide et souveraine par les clients Web et Mobiles.",
            styles["CoverSubtitle"],
        )
    )

    # Cartouche Métadonnées
    meta_data = [
        [
            Paragraph("<b>Projet :</b> CCD Digital (SOUMAFE SARL)", styles["CoverMeta"]),
            Paragraph("<b>Sprint :</b> Sprint 3 — Sécurité, IAM & Refonte", styles["CoverMeta"]),
        ],
        [
            Paragraph("<b>Auteur :</b> Agentic AI Pair Programmer & Mentor", styles["CoverMeta"]),
            Paragraph("<b>Destinataire :</b> Développeur Backend Souverain", styles["CoverMeta"]),
        ],
        [
            Paragraph("<b>Route Exposée :</b> <code>GET /api/v1/modules/</code>", styles["CoverMetaBold"]),
            Paragraph("<b>Sécurité :</b> <code>IsAuthenticated</code> (RBAC Socle)", styles["CoverMetaBold"]),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[261, 262])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94A3B8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ
    # ==========================================
    story.append(Paragraph("1. FILM MENTAL & CONDITIONNEMENT SUBCONSCIENT", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=6))

    murphy_text = (
        "Le Dr. Joseph Murphy souligne dans <i>The Power of Your Subconscious Mind</i> que la clarté de "
        "la représentation mentale précède toujours la perfection de la matérialisation physique. "
        "Lorsque le client frontend doit coder des modules en dur, il crée de la friction cognitive et un "
        "couplage toxique (Défaut D-4).<br/><br/>"
        "<b>Votre Film Mental :</b> Visualisez l'application cliente interrogeant un point de terminaison "
        "unique, net et instantané : <code>GET /api/v1/modules/</code>. En une seule requête authentifiée, "
        "le frontend reçoit la liste ordonnée des 5 modules BTP souverains avec leurs descriptions métier et "
        "la granularité de leurs 4 niveaux d'accès. Les menus de navigation, la matrice des rôles et les écrans "
        "de paramétrage s'illuminent dynamiquement, sans aucun code en dur. Ressentez la maîtrise de l'architecte "
        "qui offre une source unique de vérité (Single Source of Truth) à l'ensemble du système."
    )
    story.append(callout_box(murphy_text, styles, "POSTURE MENTALE DU DÉVELOPPEUR SOUVERAIN (MURPHY / DEHAENE)"))
    story.append(Spacer(1, 8))

    # ==========================================
    # SECTION 2 : ARCHITECTURE & INVARIANTS
    # ==========================================
    story.append(Paragraph("2. ARCHITECTURE, CONTRAT D'API & INVARIANTS MÉTIER", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=6))

    story.append(
        Paragraph(
            "Dans le paradigme Pólya / Sweller, la résolution d'un problème repose sur l'identification stricte des "
            "<b>Invariants</b>. Les modules ne sont pas de simples chaînes de caractères, mais les piliers opérationnels "
            "du produit BTP. Voici la cartographie canonique des 5 modules souverains de CCD Digital :",
            styles["Body"],
        )
    )

    modules_table_data = [
        [
            Paragraph("Code", styles["TableHead"]),
            Paragraph("Libellé Métier", styles["TableHead"]),
            Paragraph("Ordre", styles["TableHead"]),
            Paragraph("Description Métier Canonique", styles["TableHead"]),
        ],
        [
            Paragraph("<code>projets</code>", styles["TableCellMono"]),
            Paragraph("Gestion des Projets", styles["TableCellBold"]),
            Paragraph("1", styles["TableCell"]),
            Paragraph("Fiches projets, lots, activités, jalons et planification des chantiers.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>chantier</code>", styles["TableCellMono"]),
            Paragraph("Suivi Technique / Chantier", styles["TableCellBold"]),
            Paragraph("2", styles["TableCell"]),
            Paragraph("Rapports journaliers, avancement des travaux, blocages terrain et pointages.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>ged</code>", styles["TableCellMono"]),
            Paragraph("Gestion Documentaire (GED)", styles["TableCellBold"]),
            Paragraph("3", styles["TableCell"]),
            Paragraph("Classeurs, plans d'exécution, procès-verbaux et traçabilité des pièces jointes.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>pilotage</code>", styles["TableCellMono"]),
            Paragraph("Tableaux de bord & Pilotage", styles["TableCellBold"]),
            Paragraph("4", styles["TableCell"]),
            Paragraph("Indicateurs d'avancement, indice de santé global, météo et aide à la décision.", styles["TableCell"]),
        ],
        [
            Paragraph("<code>tiers</code>", styles["TableCellMono"]),
            Paragraph("Parties Prenantes / Tiers", styles["TableCellBold"]),
            Paragraph("5", styles["TableCell"]),
            Paragraph("Clients, maîtres d'ouvrage, sous-traitants, fournisseurs et partenaires.", styles["TableCell"]),
        ],
    ]
    t_mod = Table(modules_table_data, colWidths=[65, 120, 38, 300])
    t_mod.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284C7")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_mod)
    story.append(Spacer(1, 8))

    story.append(Paragraph("2.1. Contrat JSON de l'Endpoint <code>GET /api/v1/modules/</code>", styles["H2"]))
    json_contract_example = """[
  {
    "code": "projets",
    "libelle": "Gestion des Projets",
    "description": "Fiches projets, lots, activités, jalons et planification des chantiers.",
    "ordre": 1,
    "icone": "folder-kanban",
    "niveaux_supportes": [
      {"niveau": 0, "code": "AUCUN", "libelle": "Aucun"},
      {"niveau": 1, "code": "LECTURE", "libelle": "Lecture"},
      {"niveau": 2, "code": "ECRITURE", "libelle": "Écriture / Saisie"},
      {"niveau": 3, "code": "VALIDATION", "libelle": "Validation / Approbation"}
    ]
  },
  {
    "code": "chantier",
    "libelle": "Suivi Technique / Chantier",
    "description": "Rapports journaliers, avancement des travaux, blocages terrain et pointages.",
    "ordre": 2,
    "icone": "hard-hat",
    "niveaux_supportes": [ ... ]
  }
]"""
    story.append(code_box(json_contract_example, styles, "Exemple de réponse HTTP 200"))
    story.append(Spacer(1, 8))

    # ==========================================
    # SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("3. GUIDE D'IMPLÉMENTATION PAS-À-PAS", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=6))

    story.append(
        Paragraph(
            "Suivez les 4 étapes chirurgicales d'implémentation ci-dessous. Chaque fichier est pensé pour "
            "garantir un découplage total et une maintenabilité maximale.",
            styles["Body"],
        )
    )

    story.append(Paragraph("Étape 1 : Référentiel canonique dans <code>apps/core/enums.py</code>", styles["H2"]))
    story.append(
        Paragraph(
            "Dans <code>apps/core/enums.py</code>, la structure <code>MODULES_DETAILS</code> associe à chaque valeur de "
            "<code>ModuleChoix</code> ses métadonnées riches (description, icône, ordre d'affichage).",
            styles["Body"],
        )
    )
    code_enums = """# apps/core/enums.py (extrait d'enrichissement)

MODULES_DETAILS = {
    ModuleChoix.PROJETS: {
        "description": "Fiches projets, lots, activités, jalons et planification des chantiers.",
        "ordre": 1,
        "icone": "folder-kanban",
    },
    ModuleChoix.CHANTIER: {
        "description": "Rapports journaliers, avancement des travaux, blocages terrain et pointages.",
        "ordre": 2,
        "icone": "hard-hat",
    },
    ModuleChoix.GED: {
        "description": "Classeurs, plans d'exécution, procès-verbaux et traçabilité des pièces jointes.",
        "ordre": 3,
        "icone": "file-text",
    },
    ModuleChoix.PILOTAGE: {
        "description": "Indicateurs d'avancement, indice de santé global, météo et aide à la décision.",
        "ordre": 4,
        "icone": "bar-chart-3",
    },
    ModuleChoix.TIERS: {
        "description": "Clients, maîtres d'ouvrage, sous-traitants, fournisseurs et partenaires.",
        "ordre": 5,
        "icone": "users",
    },
}"""
    story.append(code_box(code_enums, styles, "apps/core/enums.py"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Étape 2 : Sérialiseurs DRF dans <code>apps/referentiels/serializers/module.py</code>", styles["H2"]))
    story.append(
        Paragraph(
            "Deux sérialiseurs typent la réponse pour drf-spectacular (OpenAPI / Swagger) et la sérialisation standard.",
            styles["Body"],
        )
    )
    code_serializer = """# apps/referentiels/serializers/module.py
from rest_framework import serializers

class NiveauAccesDetailSerializer(serializers.Serializer):
    niveau = serializers.IntegerField(help_text="Valeur numérique du niveau (0 à 3)")
    code = serializers.CharField(help_text="Code symbolique (AUCUN, LECTURE, ECRITURE, VALIDATION)")
    libelle = serializers.CharField(help_text="Libellé lisible en français")

class ModuleItemSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Code machine unique du module (ex: projets)")
    libelle = serializers.CharField(help_text="Libellé officiel du module")
    description = serializers.CharField(help_text="Description du périmètre métier du module")
    ordre = serializers.IntegerField(help_text="Position ordonnée d'affichage dans la navigation")
    icone = serializers.CharField(help_text="Identifiant d'icône recommandé pour le frontend")
    niveaux_supportes = NiveauAccesDetailSerializer(many=True, help_text="Liste des niveaux d'accès RBAC")
"""
    story.append(code_box(code_serializer, styles, "apps/referentiels/serializers/module.py"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Étape 3 : Vue API dans <code>apps/referentiels/views/module.py</code>", styles["H2"]))
    code_view = """# apps/referentiels/views/module.py
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.enums import ModuleChoix, NiveauAcces, MODULES_DETAILS
from apps.referentiels.serializers.module import ModuleItemSerializer

class ModuleListView(APIView):
    \"\"\"`GET /api/v1/modules/` — Catalogue des 5 modules BTP souverains et de leurs droits.\"\"\"
    permission_classes = [IsAuthenticated]
    serializer_class = ModuleItemSerializer

    @extend_schema(
        summary="Lister les modules BTP du socle",
        description="Renvoie le catalogue complet des 5 modules souverains avec descriptions, ordre et niveaux d'accès RBAC.",
        responses={200: ModuleItemSerializer(many=True)},
    )
    def get(self, request):
        niveaux_supportes = [
            {"niveau": code, "code": NiveauAcces(code).name, "libelle": str(libelle)}
            for code, libelle in NiveauAcces.choices
        ]
        
        modules = []
        for code, libelle in ModuleChoix.choices:
            details = MODULES_DETAILS.get(code, {})
            modules.append({
                "code": code,
                "libelle": str(libelle),
                "description": details.get("description", ""),
                "ordre": details.get("ordre", 99),
                "icone": details.get("icone", "box"),
                "niveaux_supportes": niveaux_supportes,
            })
            
        modules.sort(key=lambda m: m["ordre"])
        serializer = ModuleItemSerializer(modules, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
"""
    story.append(code_box(code_view, styles, "apps/referentiels/views/module.py"))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Étape 4 : Déclaration de la Route dans <code>apps/referentiels/urls.py</code>", styles["H2"]))
    code_url = """# apps/referentiels/urls.py
from django.urls import path
from apps.referentiels.views import EnumerationsView, ReglesMotDePasseView
from apps.referentiels.views.module import ModuleListView

app_name = "referentiels"

urlpatterns = [
    path("modules/", ModuleListView.as_view(), name="modules-liste"),
    path("referentiels/enumerations/", EnumerationsView.as_view(), name="enumerations"),
    path("referentiels/regles-mot-de-passe/", ReglesMotDePasseView.as_view(), name="regles-mot-de-passe"),
]
"""
    story.append(code_box(code_url, styles, "apps/referentiels/urls.py"))
    story.append(Spacer(1, 6))

    # ==========================================
    # SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("4. SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM (DEHAENE / KAHNEMAN)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=6))

    story.append(
        Paragraph(
            "Le 3ème pilier de Dehaene (Retour sur Erreur) et la technique Pre-Mortem de Kahneman consistent à "
            "anticiper dès maintenant les causes d'échec potentielles avant même l'exécution des tests.",
            styles["Body"],
        )
    )

    premortem_data = [
        [
            Paragraph("Scénario de Défaillance", styles["TableHead"]),
            Paragraph("Cause Racine Sous-Jacente", styles["TableHead"]),
            Paragraph("Parade & Invariant d'Architecture", styles["TableHead"]),
        ],
        [
            Paragraph("Erreur 401 Unauthorized inattendue", styles["TableCellBold"]),
            Paragraph("L'appelant tente d'appeler l'API sans Bearer token ou avec un token expiré.", styles["TableCell"]),
            Paragraph("Conformément au choix d'arbitrage A3, la route requiert <code>IsAuthenticated</code>. Documenter l'exigence d'authentification dans la collection Postman.", styles["TableCell"]),
        ],
        [
            Paragraph("Mauvaise URL résolue (404 Not Found)", styles["TableCellBold"]),
            Paragraph("L'URL est montée en <code>referentiels/modules/</code> au lieu de <code>modules/</code>.", styles["TableCell"]),
            Paragraph("Puisque <code>apps.referentiels.urls</code> est monté sous <code>api/v1/</code>, déclarer <code>path('modules/', ...)</code> produit fidèlement <code>/api/v1/modules/</code>.", styles["TableCell"]),
        ],
        [
            Paragraph("Désynchronisation des 4 niveaux d'accès", styles["TableCellBold"]),
            Paragraph("Les niveaux (0, 1, 2, 3) sont écrits en dur dans la vue plutôt que dérivés de l'Enum.", styles["TableCell"]),
            Paragraph("Itérer dynamiquement sur <code>NiveauAcces.choices</code> pour garantir une vérité absolue et zéro duplication.", styles["TableCell"]),
        ],
    ]
    t_pm = Table(premortem_data, colWidths=[150, 170, 203])
    t_pm.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_pm)
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 5 : CHECKLIST DE TESTS & VALIDATION
    # ==========================================
    story.append(Paragraph("5. CHECKLIST DE TESTS AUTOMATISÉS (PYTEST)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=6))

    code_test = """# apps/referentiels/tests/test_api_modules.py
import pytest
from rest_framework import status
from apps.core.enums import ModuleChoix

@pytest.mark.django_db
class TestApiModules:
    def test_acces_anonyme_refuse(self, client):
        \"\"\"Un client non authentifié doit recevoir un code HTTP 401.\"\"\"
        response = client.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_lister_modules_authentifie(self, client_authentifie):
        \"\"\"Un collaborateur connecté reçoit exactement les 5 modules ordonnés.\"\"\"
        response = client_authentifie.get("/api/v1/modules/")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert len(data) == 5
        
        codes = [m["code"] for m in data]
        assert codes == ["projets", "chantier", "ged", "pilotage", "tiers"]
        
        # Vérification des niveaux d'accès inclus
        premier_module = data[0]
        assert "niveaux_supportes" in premier_module
        assert len(premier_module["niveaux_supportes"]) == 4
        assert premier_module["niveaux_supportes"][0]["niveau"] == 0
        assert premier_module["niveaux_supportes"][3]["niveau"] == 3
"""
    story.append(code_box(code_test, styles, "apps/referentiels/tests/test_api_modules.py"))
    story.append(Spacer(1, 8))

    # ==========================================
    # SECTION 6 : DÉFI HOMO DOCENS
    # ==========================================
    story.append(Paragraph("6. DÉFI HOMO DOCENS & CONSOLIDATION NOCTURNE", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=6))

    homo_docens_text = (
        "<b>L'effet Protégé (Dehaene / Pilier 4) :</b> La façon la plus pérenne de graver une connaissance "
        "dans le réseau synaptique est de se préparer à l'enseigner à autrui.<br/><br/>"
        "<b>Votre Défi :</b> Prenez 5 minutes pour expliquer à voix haute (ou à un collègue) :<br/>"
        "1. Pourquoi avoir créé un endpoint dédié <code>/api/v1/modules/</code> au lieu de laisser le frontend "
        "coder les modules en dur dans ses fichiers TypeScript ?<br/>"
        "2. Comment le serializer garantit que si demain un module 'finance' est ajouté dans <code>ModuleChoix</code>, "
        "la documentation Swagger et la réponse API se synchroniseront immédiatement sans retoucher à la vue ?<br/><br/>"
        "Après avoir implémenté et validé la suite de tests, accordez-vous un moment de calme : votre cerveau "
        "effectuera le <i>Replay neuronal nocturne accéléré</i> ($20\\times$) pour ancrer ces réflexes au niveau subconscient."
    )
    story.append(callout_box(homo_docens_text, styles, "ÉLÉVATION AU RANG HOMO DOCENS"))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Manuel genere avec succes : {filename}")


if __name__ == "__main__":
    build_pdf()
