"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 08.

Tâche : Scoping des Permissions par Module (Super Admin & Propagation Ciblée Multi-Tenants)
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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 08 : SCOPING DES PERMISSIONS PAR MODULE",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "GOUVERNANCE SUPER ADMIN & PROPAGATION CIBLÉE",
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
            fontSize=21,
            leading=25,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        )
    )

    styles.add(
        ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14.5,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14,
        )
    )

    styles.add(
        ParagraphStyle(
            "SectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=13,
            spaceAfter=6,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            "SubSectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=7,
            spaceAfter=3,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=11.8,
            textColor=colors.HexColor("#334155"),
            spaceAfter=5,
        )
    )

    styles.add(
        ParagraphStyle(
            "BodyBold",
            parent=styles["Body"],
            fontName="Helvetica-Bold",
        )
    )

    styles.add(
        ParagraphStyle(
            "CalloutText",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.2,
            leading=12,
            textColor=colors.HexColor("#0C4A6E"),
        )
    )

    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.0,
            leading=9.2,
            textColor=colors.HexColor("#0F172A"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#FFFFFF"),
            alignment=0,
        )
    )

    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.5,
            textColor=colors.HexColor("#1E293B"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableCellBold",
            parent=styles["TableCell"],
            fontName="Helvetica-Bold",
        )
    )

    return styles


def callout_box(text, styles, title="NOTE NEUROCOGNITIVE", border_color="#0284C7", bg_color="#F0F9FF"):
    content = [
        Paragraph(f"<b>{title}</b>", styles["SubSectionHeader"]),
        Spacer(1, 2),
        Paragraph(text, styles["CalloutText"]),
    ]
    t = Table([[content]], colWidths=[523])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border_color)),
                ("PADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
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
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def build_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42,
    )
    styles = create_styles()
    story = []

    # =========================================================================
    # PAGE 1 : PAGE DE TITRE & SYNTHÈSE EXÉCUTIVE
    # =========================================================================
    badge_data = [
        [
            Paragraph("<b>SPRINT 3 • SOUVERAINETÉ IAM</b>", styles["TableCellBold"]),
            Paragraph("<b>TÂCHE 08 • MODULE-SCOPED PERMISSIONS</b>", styles["TableCellBold"]),
            Paragraph("<b>SUPER ADMIN & TENANTS</b>", styles["TableCellBold"]),
        ]
    ]
    badge_table = Table(badge_data, colWidths=[174, 180, 169])
    badge_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0284C7")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(badge_table)
    story.append(Spacer(1, 14))

    story.append(
        Paragraph(
            "Scoping des Permissions par Module : Gouvernance Super Admin & Propagation Ciblée Multi-Tenants",
            styles["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "Manuel d'Apprentissage par la Pratique & d'Ingénierie Subconsciente • Architecture RBAC Granulaire • CCD Digital",
            styles["DocSubTitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=14))

    # SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ
    story.append(Paragraph("1. Film Mental & Objectif Sacré (Murphy / Subconscient)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Visualisez clairement la scène sur la plateforme CCD Digital : le Super Admin se connecte à la console de gouvernance. "
            "Il crée une nouvelle autorisation hautement spécialisée, par exemple <code>SIGNER_PV_RECEPTION</code> ou <code>METTRE_EN_LIGNE_PLAN</code>. "
            "Dans l'ancien système, cette permission était injectée aveuglément sur <b>tous les modules sans exception</b> (y compris la comptabilité, "
            "les tiers ou le pilotage). Dans la nouvelle architecture souveraine, le Super Admin garde la maîtrise absolue : "
            "il décide quels modules applicatifs ont accès à cette autorisation. En un clic ou un appel d'API, il rattache <code>SIGNER_PV_RECEPTION</code> "
            "exclusivement aux modules <b>Chantier</b> et <b>GED</b>. Instantanément, la propagation s'opère de façon ciblée dans les entreprises clientes : "
            "seules les grilles de Chantier et GED exposent ce droit ; les autres modules restent parfaitement étanches et épurés.",
            styles["Body"],
        )
    )

    story.append(
        callout_box(
            "<b>Loi de l'Effort Inversé (Dr. Joseph Murphy) :</b> Ne forcez pas la complexité. L'esprit conçoit naturellement "
            "qu'une capacité d'action n'a de sens que dans son domaine de définition. Lier la Permission à ses Modules d'application "
            "est la résolution naturelle qui élimine le bruit mental et restaure l'harmonie du modèle de données.",
            styles,
            title="PRINCIPE SUBCONSCIENT : CLARTÉ ET DOMAINE DE DÉFINITION",
            border_color="#0284C7",
            bg_color="#F0F9FF",
        )
    )
    story.append(Spacer(1, 10))

    # SECTION 2 : ARCHITECTURE & INVARIANTS
    story.append(Paragraph("2. Architecture & Invariants Formels (Pólya / Dehaene)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "L'architecture repose sur quatre invariants stricts garantissant la cohérence multi-schémas :",
            styles["Body"],
        )
    )

    invariants_data = [
        [Paragraph("<b>Invariant</b>", styles["TableHeader"]), Paragraph("<b>Description Métier & Technique</b>", styles["TableHeader"])],
        [
            Paragraph("<b>I-1 : Relation ManyToMany</b>", styles["TableCellBold"]),
            Paragraph("L'entité <code>Permission</code> dispose d'une relation ManyToMany vers <code>Module</code> (<code>modules</code>) présente dans le schéma <code>public</code> et répliquée dans chaque tenant.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>I-2 : Zéro Propagation Aveugle</b>", styles["TableCellBold"]),
            Paragraph("La création d'une permission sans module n'altère aucun <code>RoleModulePermission</code>. Elle attend la décision explicite du Super Admin.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>I-3 : Scoping Sélectif</b>", styles["TableCellBold"]),
            Paragraph("Lorsque des modules sont associés, la permission est attribuée aux rôles DG et Admin <b>uniquement sur les modules éligibles</b>.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>I-4 : Révocation Réactive Zero-Trust</b>", styles["TableCellBold"]),
            Paragraph("Si le Super Admin retire un module d'une permission, celle-ci est automatiquement purgée de tous les rôles sur ce module dans tous les tenants.", styles["TableCell"]),
        ],
    ]
    inv_table = Table(invariants_data, colWidths=[130, 393])
    inv_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(inv_table)
    story.append(Spacer(1, 14))

    # SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS
    story.append(Paragraph("3. Guide d'Implémentation Pas-à-Pas (Code Commenté)", styles["SectionHeader"]))
    
    story.append(Paragraph("<b>Étape 1 : Évolution du modèle Permission (apps/accounts/models/permission.py)</b>", styles["SubSectionHeader"]))
    story.append(
        code_box(
            """# apps/accounts/models/permission.py
class Permission(ModeleBase):
    code = models.CharField(_("code"), max_length=50, db_index=True)
    libelle = models.CharField(_("libellé"), max_length=100)
    description = models.TextField(_("description"), blank=True, default="")
    ordre = models.PositiveSmallIntegerField(_("ordre d'affichage"), default=0)
    est_actif = models.BooleanField(_("est actif"), default=True)

    # NOUVEAU : Scoping par module applicatif
    modules = models.ManyToManyField(
        "accounts.Module",
        related_name="permissions",
        blank=True,
        verbose_name=_("modules éligibles"),
        help_text=_("Modules applicatifs autorisés à porter cette permission."),
    )""",
            styles,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Étape 2 : Service de Propagation et Révocation (apps/platform_admin/services/catalogue.py)</b>", styles["SubSectionHeader"]))
    story.append(
        code_box(
            """def propager_creation_permission(*, code, libelle, description="", ordre=0, est_actif=True, modules=None, cree_par=None):
    # 1. Schéma public : création et association des modules
    with schema_context("public"):
        perm_public = Permission.objects.create(
            code=code, libelle=libelle, description=description, ordre=ordre, est_actif=est_actif, cree_par=cree_par
        )
        if modules:
            mods = Module.objects.filter(code__in=[str(m).lower() for m in modules], supprime_le__isnull=True)
            perm_public.modules.set(mods)

    # 2. Propagation ciblée dans chaque tenant
    for entreprise in Entreprise.objects.exclude(schema_name="public"):
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                perm_t, _ = Permission.objects.update_or_create(code=code, defaults={...})
                codes_m = list(perm_public.modules.values_list("code", flat=True))
                mods_t = list(Module.objects.filter(code__in=codes_m, supprime_le__isnull=True))
                perm_t.modules.set(mods_t)
                
                # Injection UNIQUEMENT sur les modules autorisés pour DG/ADMIN
                if mods_t:
                    roles_dir = Role.objects.filter(code__in=["DG", "ADMIN", "AD"], supprime_le__isnull=True)
                    for r in roles_dir:
                        for rmp in RoleModulePermission.objects.filter(role=r, module__in=mods_t):
                            rmp.permissions.add(perm_t)
    return perm_public""",
            styles,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Étape 3 : Endpoint d'Affectation A Posteriori par le Super Admin</b>", styles["SubSectionHeader"]))
    story.append(
        code_box(
            """# POST /api/v1/admin/permissions/{id}/modules/
# Payload : {"modules": ["chantier", "ged"]}
class AdminPermissionAffecterModulesView(APIView):
    permission_classes = [EstSuperAdminPlateforme]
    
    def post(self, request, pk):
        serializer = AdminPermissionAffecterModulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        perm = propager_affectation_modules_permission(
            permission_id=pk,
            modules=serializer.validated_data["modules"],
            modifie_par=request.user,
        )
        return Response(AdminPermissionSerializer(perm).data, status=status.HTTP_200_OK)""",
            styles,
        )
    )
    story.append(Spacer(1, 10))

    # SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM
    story.append(Paragraph("4. Signal d'Erreur Bayésien & Pre-Mortem (Dehaene P3 / Kahneman)", styles["SectionHeader"]))
    premortem_data = [
        [Paragraph("<b>Scénario de Défaillance Potentielle</b>", styles["TableHeader"]), Paragraph("<b>Contre-Mesure Architecturale & Invariant</b>", styles["TableHeader"])],
        [
            Paragraph("<b>Piège 1 : Passage d'instances à travers les schémas</b>", styles["TableCellBold"]),
            Paragraph("Ne jamais passer une instance <code>Module</code> de <code>public</code> dans <code>set()</code> d'un tenant. Toujours faire la translation par les <code>code</code> ou les <code>id</code> à l'intérieur du <code>schema_context</code>.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Piège 2 : Permissions orphelines lors du retrait de module</b>", styles["TableCellBold"]),
            Paragraph("Si le Super Admin retire <code>chantier</code> de la permission, les rôles ne doivent pas conserver ce droit sur Chantier en mémoire cache ou en base. Le service calcule la différence (diff) et exécute un <code>rmp.permissions.remove(perm)</code> immédiat.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Piège 3 : Régression sur les 4 permissions CRUD du socle</b>", styles["TableCellBold"]),
            Paragraph("Les permissions de base (LECTURE, ECRITURE, VALIDATION, SUPPRESSION) doivent être liées par défaut à tous les modules actifs lors de l'initialisation pour préserver le fonctionnement des rôles existants.", styles["TableCell"]),
        ],
    ]
    pm_table = Table(premortem_data, colWidths=[160, 363])
    pm_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FEF2F2")]),
            ]
        )
    )
    story.append(pm_table)
    story.append(Spacer(1, 10))

    # SECTION 5 : CHECKLIST DE TESTS & VALIDATION
    story.append(Paragraph("5. Checklist de Tests Automatisés (Pytest)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "La suite de tests automatisés valide la totalité du cycle de vie du scoping :<br/>"
            "• <b>test_creer_permission_sans_module_aucun_rmp :</b> Vérifie qu'une permission sans module n'est injectée nulle part.<br/>"
            "• <b>test_creer_permission_avec_modules_cibles :</b> Vérifie l'injection sélective sur les modules choisis uniquement.<br/>"
            "• <b>test_affecter_modules_a_posteriori :</b> Vérifie la décision différée du Super Admin via l'endpoint dédié.<br/>"
            "• <b>test_retirer_module_revoque_permission :</b> Vérifie la purge automatique des droits sur les modules désélectionnés.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 8))

    # SECTION 6 : DÉFI HOMO DOCENS
    story.append(Paragraph("6. Défi Homo Docens & Clôture Métacognitive", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>Mission d'Enseignement :</b> Expliquez à un pair pourquoi le concept de <i>Domain-Scoped Capabilities</i> "
            "est supérieur à une matrice de permissions transversale globale. Montrez-lui comment le découplage entre "
            "la capacité d'agir (l'autorisation) et le périmètre d'action (le module) préserve l'intégrité de la plateforme BTP.",
            styles["Body"],
        )
    )
    story.append(
        callout_box(
            "<b>Consolidation Nocturne (Dehaene - Pilier 4) :</b> Relisez ce schéma avant le sommeil. Durant la nuit, "
            "votre subconscient rejoue à 20x les transitions d'état entre public et tenant, transformant cette logique relationnelle "
            "en un automatisme architectural intuitif.",
            styles,
            title="REPROGRAMMATION MENTALE NOCTURNE",
            border_color="#10B981",
            bg_color="#ECFDF5",
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel généré avec succès : {filename}")


if __name__ == "__main__":
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Manuels_Apprentissage")
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, "MANUEL_SPRINT_3_TACHE_08_AFFECTATION_PERMISSIONS_MODULES_SUPER_ADMIN.pdf")
    build_pdf(pdf_path)
