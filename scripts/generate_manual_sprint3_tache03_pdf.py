"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 03.

Tâche : Refonte du Périmètre Produit à 5 Modules & Architecture RBAC Avancée
        (QuerySet Scoping, Cache de Requête & Généralisation des Permissions).
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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 03 : RÉDUCTION 5 MODULES & RBAC AVANCÉ",
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
            fontSize=19,
            leading=24,
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
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#0369A1"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "H3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#334155"),
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=5,
        ),
        "BodyBold": ParagraphStyle(
            "BodyBold",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#1E293B"),
            leftIndent=12,
            firstLineIndent=-8,
            spaceAfter=3,
        ),
        "CalloutText": ParagraphStyle(
            "CalloutText",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0C4A6E"),
        ),
        "Preformatted": ParagraphStyle(
            "Preformatted",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.2,
            leading=9.5,
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
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#0284C7"),
        ),
    }

    return styles


def callout_box(text, styles, title="PRINCIPE NEUROCOGNITIF & FONDATION"):
    content = [
        Paragraph(f"<b>{title}</b>", styles["H3"]),
        Spacer(1, 3),
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
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
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


def build_pdf(filename="MANUEL_SPRINT_3_TACHE_03_REDUCTION_5_MODULES_ET_RBAC_AVANCE.pdf"):
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
    story.append(Paragraph("CCD DIGITAL • ARCHITECTURE DU SOCLE BTP & SÉCURITÉ RBAC", styles["CoverSuper"]))
    story.append(
        Paragraph(
            "MANUEL DE PRATIQUE AUTONOME : SPRINT 3 — TÂCHE 03<br/>"
            "RÉDUCTION À 5 MODULES & ARCHITECTURE RBAC AVANCÉE",
            styles["CoverTitle"],
        )
    )
    story.append(
        Paragraph(
            "Recentrage souverain du périmètre applicatif (Projets, Suivi Chantier, Documents GED, "
            "Tableaux de Bord, Tiers), élagage chirurgical des modules superflus, généralisation des "
            "permissions, filtrage automatique des QuerySets et mémoïsation haute performance O(1).",
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
            Paragraph("<b>Cadre Méthodologique :</b> Stanislas Dehaene • Joseph Murphy • Daniel Kahneman • George Pólya", styles["CoverMetaBold"]),
            Paragraph("<b>Statut :</b> Pratique Délibérée • Niveau Homo Docens", styles["CoverMetaBold"]),
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
    story.append(Spacer(1, 12))

    # ==========================================
    # SECTION 1 : FILM MENTAL & POSTURE MENTALE
    # ==========================================
    story.append(Paragraph("1. FILM MENTAL & OBJECTIF SACRÉ DU DÉVELOPPEUR", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    murphy_text = (
        "Le Dr. Joseph Murphy enseigne la <b>Loi de l'Effort Inversé</b> : forcer consciemment une solution "
        "complexe engendre la tension, le doute et le sentiment de submersion. Lorsqu'un projet s'éparpille "
        "sur trop de fronts (12 modules hétérogènes dont plusieurs inachevés), la charge cognitive dépasse "
        "le seuil de rétention (Sweller).<br/><br/>"
        "<b>Votre Film Mental :</b> Visualisez votre API débarrassée de tout bruit inutile. Les tables et routes "
        "incomplètes ont disparu, laissant place à un noyau resserré de 5 modules parfaitement maîtrisés. "
        "À chaque appel d'API, le moteur de permissions évalue les droits en complexité O(1) grâce au cache "
        "de requête, et les QuerySets se restreignent automatiquement aux seuls chantiers où l'utilisateur est affecté. "
        "Ressentez la sérénité du maître d'œuvre qui bâtit sur un socle épuré et inébranlable."
    )
    story.append(callout_box(murphy_text, styles, "REPROGRAMMATION SUBCONSCIENTE — JOSEPH MURPHY"))
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 2 : ARCHITECTURE & INVARIANTS
    # ==========================================
    story.append(Paragraph("2. ARCHITECTURE, CADRAGE MECE & INVARIANTS", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(
        Paragraph(
            "Selon Stanislas Dehaene (<i>Apprendre !</i>), le <b>Cerveau Bayésien</b> affine continuellement ses "
            "modèles internes en comparant ses prédictions aux signaux d'erreur. Pour éliminer tout flou architectural, "
            "le périmètre est redéfini de façon Mutuellement Exclusive et Collectivement Exhaustive (MECE).",
            styles["Body"],
        )
    )

    modules_data = [
        [
            Paragraph("Module Cible", styles["TableHead"]),
            Paragraph("Code Enum", styles["TableHead"]),
            Paragraph("Rôle Métier BTP", styles["TableHead"]),
            Paragraph("Périmètre Retenu", styles["TableHead"]),
        ],
        [
            Paragraph("<b>Gestion des Projets</b>", styles["TableCellBold"]),
            Paragraph("<code>projets</code>", styles["TableCellMono"]),
            Paragraph("Référentiel maître", styles["TableCell"]),
            Paragraph("Lots WBS, activités, calendrier prévisionnel, équipe affectée, météo.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Suivi Chantier</b>", styles["TableCellBold"]),
            Paragraph("<code>chantier</code>", styles["TableCellMono"]),
            Paragraph("Exploitation terrain", styles["TableCell"]),
            Paragraph("Rapport journalier (RJC), avancement physique, blocages/incidents, approbations.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Documents (GED)</b>", styles["TableCellBold"]),
            Paragraph("<code>ged</code>", styles["TableCellMono"]),
            Paragraph("Traçabilité technique", styles["TableCell"]),
            Paragraph("Plans architectes, indices de révision, PV de réception, attestations liées aux chantiers.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tableaux de Bord</b>", styles["TableCellBold"]),
            Paragraph("<code>pilotage</code>", styles["TableCellMono"]),
            Paragraph("Décisionnel DG / CP", styles["TableCell"]),
            Paragraph("Consolidation portefeuille, avancement global, détection dérives et alertes.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Parties Prenantes</b>", styles["TableCellBold"]),
            Paragraph("<code>tiers</code>", styles["TableCellMono"]),
            Paragraph("Écosystème externe", styles["TableCell"]),
            Paragraph("Clients (MOA), maîtres d'œuvre (MOE), sous-traitants, bureaux de contrôle.", styles["TableCell"]),
        ],
    ]
    mod_table = Table(modules_data, colWidths=[110, 65, 110, 238])
    mod_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(mod_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Les Trois Piliers du RBAC Avancé", styles["H2"]))
    story.append(
        Paragraph(
            "<b>Pilier 1 — Cache par Requête (Request-Scoped Memoization) :</b> L'évaluation des permissions "
            "d'un utilisateur ne doit jamais exécuter plus d'une requête SQL par module/projet durant le cycle "
            "de vie d'une requête HTTP. Les résultats sont mémorisés dans <code>request._rbac_cache</code>.<br/>"
            "<b>Pilier 2 — Scoping Automatique des QuerySets :</b> Tout endpoint de listing (ex: <code>GET /api/v1/projets/</code>) "
            "doit filtrer automatiquement la collection pour ne renvoyer que les données des chantiers auxquels "
            "l'utilisateur opérationnel est activement affecté (<code>AffectationProjet</code>). Seuls le DG, l'Admin "
            "et le Propriétaire ont une visibilité transversale.<br/>"
            "<b>Pilier 3 — Généralisation de PermissionModule :</b> Fin des vues protégées par un simple <code>IsAuthenticated</code>. "
            "Chaque action HTTP est soumise au niveau d'accès requis (1: Lecture, 2: Saisie/Écriture, 3: Validation).",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS
    # ==========================================
    story.append(Paragraph("3. GUIDE D'IMPLÉMENTATION PAS-À-PAS", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(Paragraph("Étape 3.1 : Réduction de l'Enumération ModuleChoix (apps/core/enums.py)", styles["H2"]))
    code_enum = """class ModuleChoix(models.TextChoices):
    \"\"\"Les 5 modules applicatifs souverains de CCD Digital.\"\"\"
    PROJETS = "projets", "Gestion des Projets"
    CHANTIER = "chantier", "Suivi Technique / Chantier"
    GED = "ged", "Gestion Documentaire (GED)"
    PILOTAGE = "pilotage", "Tableaux de bord & Pilotage"
    TIERS = "tiers", "Parties Prenantes / Tiers"
"""
    story.append(code_box(code_enum, styles, "apps/core/enums.py"))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Étape 3.2 : Mise en Cache d'Habilitations par Requête (apps/core/permissions.py)", styles["H2"]))
    code_cache = """class PermissionModule(permissions.BasePermission):
    \"\"\"Contrôle d'accès dynamique avec mémoïsation O(1) par requête HTTP.\"\"\"
    module: str = ""
    niveau_requis: int = 1

    @classmethod
    def pour(cls, module: str, niveau_requis: int = 1):
        return type("PermissionModuleSpecifique", (cls,), {"module": module, "niveau_requis": int(niveau_requis)})

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, "is_owner", False) or getattr(user, "is_dg", False):
            return True
        if user.role_global in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL):
            return True

        # Initialisation du cache de requête éphémère
        if not hasattr(request, "_rbac_module_cache"):
            request._rbac_module_cache = {}

        if self.module in request._rbac_module_cache:
            return request._rbac_module_cache[self.module] >= self.niveau_requis

        # Résolution du rôle effectif
        role = user.role_personnalise or Role.objects.filter(code=user.role_global, supprime_le__isnull=True).first()
        if not role:
            request._rbac_module_cache[self.module] = 0
            return False

        perm = RoleModulePermission.objects.filter(role=role, module=self.module, supprime_le__isnull=True).first()
        niveau_effectif = perm.niveau if perm else 0
        request._rbac_module_cache[self.module] = niveau_effectif
        return niveau_effectif >= self.niveau_requis
"""
    story.append(code_box(code_cache, styles, "apps/core/permissions.py - Mémoïsation"))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Étape 3.3 : Scoping Automatique des QuerySets (apps/core/permissions.py)", styles["H2"]))
    code_scoping = """def filtrer_queryset_par_affectations(qs, user, champ_projet="id"):
    \"\"\"Restreint un QuerySet aux seuls chantiers où l'utilisateur est affecté.\"\"\"
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser or getattr(user, "is_owner", False) or getattr(user, "is_dg", False):
        return qs
    if user.role_global in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL):
        return qs

    from django.apps import apps as registre
    AffectationProjet = registre.get_model("projets", "AffectationProjet")
    projets_ids = AffectationProjet.objects.filter(utilisateur=user, est_actif=True).values_list("projet_id", flat=True)
    
    filtre = {f"{champ_projet}__in": projets_ids}
    return qs.filter(**filtre)
"""
    story.append(code_box(code_scoping, styles, "apps/core/permissions.py - Helper de Scoping"))
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM
    # ==========================================
    story.append(Paragraph("4. SIGNAL D'ERREUR BAYÉSIEN & AUDIT PRE-MORTEM", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    prem_text = (
        "Le psychologue Daniel Kahneman (<i>Système 1 / Système 2</i>) préconise la technique du <b>Pre-Mortem</b> : "
        "imaginez que nous sommes dans un mois et que la refonte a échoué. Pourquoi ?<br/><br/>"
        "<b>Piège 1 : Les migrations orphelines.</b> Lors de la suppression des modules, les tables PostgreSQL "
        "contenant d'anciennes clés étrangères risquent de casser les migrations. <i>Parade :</i> Éliminer "
        "proprement les références dans TENANT_APPS et vérifier la cohérence du schéma avant tout commit.<br/>"
        "<b>Piège 2 : Le cache persistant entre requêtes.</b> Attacher un cache au modèle Utilisateur ou à une "
        "variable globale partagerait les droits entre utilisateurs distincts. <i>Parade :</i> Attacher le cache "
        "exclusivement à l'instance <code>request</code> du cycle WSGI/ASGI courant.<br/>"
        "<b>Piège 3 : La fuite de données par omission de scoping.</b> Un développeur crée une nouvelle vue "
        "et écrit <code>Projet.objects.all()</code>. <i>Parade :</i> Systématiser l'usage du helper de scoping "
        "dans le sélecteur ou la vue."
    )
    story.append(callout_box(prem_text, styles, "PRE-MORTEM DE KAHNEMAN & DÉ-BIAISAGE"))
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 5 : PROTOCOLE DE TEST & VALIDATION
    # ==========================================
    story.append(Paragraph("5. PROTOCOLE DE TEST & VALIDATION AUTOMATISÉE", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    story.append(
        Paragraph(
            "Pour ancrer la trace neuronale (Dehaene - Pilier 3), chaque composant fait l'objet d'un test "
            "automatisé rigoureux exécuté via <code>pytest</code> :",
            styles["Body"],
        )
    )

    code_test = """@pytest.mark.django_db
def test_scoping_queryset_collaborateur_operationnel(client, projet_a, projet_b, user_cc):
    # user_cc est uniquement affecté à projet_a
    AffectationProjet.objects.create(utilisateur=user_cc, projet=projet_a, role_projet="CC", est_actif=True)
    
    client.force_authenticate(user=user_cc)
    reponse = client.get("/api/v1/projets/")
    assert reponse.status_code == 200
    ids_vus = [p["id"] for p in reponse.json()]
    assert str(projet_a.id) in ids_vus
    assert str(projet_b.id) not in ids_vus  # Étanchéité absolue !
"""
    story.append(code_box(code_test, styles, "apps/accounts/tests/test_rbac_5_modules_avance.py"))
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 6 : DÉFI HOMO DOCENS
    # ==========================================
    story.append(Paragraph("6. LE DÉFI HOMO DOCENS (ENSEIGNER POUR MAÎTRISER)", styles["H1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284C7"), spaceAfter=8))

    docens_text = (
        "Le stade ultime de la maîtrise cognitive est le niveau <b>Homo Docens</b> (l'Homme qui enseigne). "
        "Pour valider l'intégration définitive de cette architecture dans votre mémoire à long terme :<br/><br/>"
        "<b>Mission :</b> Expliquez à un pair développeur pourquoi la combinaison d'un cache par requête O(1) "
        "et d'un scoping de QuerySet au niveau ORM est infiniment supérieure à des vérifications 'if user.role' "
        "éparpillées dans chaque méthode de vue. Montrez-lui comment l'invariant US-04 et le scoping "
        "rendent l'application mathématiquement impossible à pirater par altération d'identifiant dans l'URL."
    )
    story.append(callout_box(docens_text, styles, "MISSION DE TRANSMISSION SOUVERAINE"))

    # Compilation
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel PDF généré avec succès : {filename}")


if __name__ == "__main__":
    dest = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
        "MANUEL_SPRINT_3_TACHE_03_REDUCTION_5_MODULES_ET_RBAC_AVANCE.pdf",
    )
    build_pdf(dest)
