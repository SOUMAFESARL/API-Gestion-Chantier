"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 07.

Tâche : Cloisonnement Hermétique des Chantiers (Scoping Multi-Projets & RBAC Niveau 2)
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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 07 : CLOISONNEMENT DES CHANTIERS",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "SCOPING MULTI-PROJETS & ÉTANCHÉITÉ RBAC NIVEAU 2",
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
            spaceAfter=6,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            "SubSectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=8,
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
            leading=12,
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
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0C4A6E"),
        )
    )

    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.2,
            leading=9.5,
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


def generate_manual_pdf(output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=42,
    )

    styles = create_styles()
    story = []

    # =========================================================================
    # EN-TÊTE / PAGE DE GARDE
    # =========================================================================
    meta_table_data = [
        [
            Paragraph("<b>PROJET :</b> CCD Digital BTP (SOUMAFE SARL)", styles["TableCell"]),
            Paragraph("<b>SPRINT :</b> 3 — Gouvernance & Sécurité", styles["TableCell"]),
        ],
        [
            Paragraph("<b>TÂCHE :</b> T-07 Cloisonnement des Chantiers", styles["TableCell"]),
            Paragraph("<b>VERSION :</b> 1.0 (Production Ready)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>AUTEUR :</b> Mentor Neurocognitif & Pair Programmer", styles["TableCell"]),
            Paragraph("<b>DATE :</b> Septembre 2026", styles["TableCell"]),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[261, 262])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "MANUEL D'APPRENTISSAGE PAR LA PRATIQUE<br/>"
            "<font color='#0284C7'>Cloisonnement des Chantiers & Scoping Multi-Projets</font>",
            styles["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "<i>Architecture de Sécurité Niveau 2 : Étanchéité Stricte par Affectation, "
            "Filtrage Automatique des QuerySets et Contrôle d'Accès de Direction Consolidée.</i>",
            styles["DocSubTitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=12))

    # =========================================================================
    # SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ (MURPHY / DEHAENE)
    # =========================================================================
    story.append(Paragraph("1. Film Mental & Objectif Sacré : La Citadelle des Chantiers", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "En entreprise de BTP, un conducteur de travaux supervisant le chantier de Cocody ne doit en aucun "
            "cas découvrir les coûts, les effectifs ou les incidents du chantier concurrent d'Adjamé. "
            "Pourtant, la Direction Générale et l'Administrateur ont impérativement besoin d'une vue d'ensemble "
            "consolidée à 360° sur la totalité du portefeuille de chantiers de l'entreprise. "
            "C'est la quintessence du <b>Niveau 2 du contrôle d'accès (Socle Commun §2.3)</b>.",
            styles["Body"],
        )
    )
    story.append(
        callout_box(
            "<b>Le Film Mental (Dr. Joseph Murphy) :</b> Visualisez mentalement le système comme une série de "
            "coffres-forts étanches. Chaque conducteur ou chef de chantier n'a dans sa trousse que la clé de "
            "ses chantiers affectés. S'il tente de manipuler une URL pour inspecter le chantier du voisin, "
            "le système le stoppe net avec un <b>403 Forbidden</b> ou l'exclut silencieusement de ses listes SQL (404 Not Found). "
            "Le DG, lui, possède le passe-partout souverain. Ressentez la paix et l'infaillibilité mathématique de cette étanchéité.",
            styles,
            title="PILIER NEUROCOGNITIF : SÉCURITÉ SUBCONSCIENTE & LOI DE L'EFFORT INVERSÉ",
            border_color="#0284C7",
            bg_color="#F0F9FF",
        )
    )
    story.append(Spacer(1, 8))

    # =========================================================================
    # SECTION 2 : ARCHITECTURE & INVARIANTS (PÓLYA / MINTO / DEHAENE)
    # =========================================================================
    story.append(Paragraph("2. Architecture Conceptuelle & Invariants du Double Niveau", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Dans le système SaaS de gestion de chantier, la sécurité repose sur deux niveaux <b>strictement cumulatifs</b> :",
            styles["Body"],
        )
    )

    sec_levels_data = [
        [
            Paragraph("Niveau", styles["TableHeader"]),
            Paragraph("Entité Responsable", styles["TableHeader"]),
            Paragraph("Question Résolue", styles["TableHeader"]),
            Paragraph("Mécanisme d'Enforcement", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Niveau 1 : Rôle Global & Modules</b>", styles["TableCellBold"]),
            Paragraph("Role / RoleModulePermission", styles["TableCell"]),
            Paragraph("Quelles actions l'utilisateur peut-il exécuter ? (Lecture, Écriture, Validation)", styles["TableCell"]),
            Paragraph("<code>PermissionModule.pour(...)</code> sur les ViewSets/APIViews", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Niveau 2 : Appartenance Chantier</b>", styles["TableCellBold"]),
            Paragraph("AffectationProjet / chef_projet / conducteur_travaux", styles["TableCell"]),
            Paragraph("Sur quels chantiers spécifiques a-t-il le droit d'agir ?", styles["TableCell"]),
            Paragraph("<code>filtrer_queryset_par_affectations()</code> & <code>MembreDuProjet</code>", styles["TableCell"]),
        ],
    ]
    t_levels = Table(sec_levels_data, colWidths=[110, 120, 150, 143])
    t_levels.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(t_levels)
    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "<b>Les 4 Invariants Cardinaux du Cloisonnement :</b><br/>"
            "• <b>Invariant I1 (Transversalité Direction) :</b> Les rôles <code>ADMIN</code>, <code>DIRECTEUR_GENERAL</code>, "
            "le propriétaire fondateur (<code>is_owner=True</code>) et le super-administrateur ne subissent aucun filtrage par affectation.<br/>"
            "• <b>Invariant I2 (Hermétisme Opérationnel) :</b> Les rôles CP, CT, CC, Visiteurs/Consultants, MOA, MOE ne reçoivent "
            "en base de données <b>que</b> les chantiers où ils possèdent une <code>AffectationProjet(est_actif=True)</code> "
            "ou sont désignés responsables directs (<code>chef_projet</code> / <code>conducteur_travaux</code>).<br/>"
            "• <b>Invariant I3 (Double Barrière GET/POST) :</b> Le scoping ne s'applique pas seulement aux listes (<code>GET</code>), "
            "il interdit formellement de créer des ressources associées (ex: <code>POST /api/v1/rapports/</code>) sur un projet tiers.<br/>"
            "• <b>Invariant I4 (Mémoïsation O(1)) :</b> La liste des IDs des projets affectés est calculée <b>une seule fois par requête HTTP</b> "
            "et mémoïsée sur <code>request._rbac_projets_ids_actifs</code> pour éliminer tout risque de saturation de la base de données (zéro N+1).",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 6))

    # =========================================================================
    # SECTION 3 : GUIDE D'IMPLÉMENTATION CHIRURGICALE
    # =========================================================================
    story.append(Paragraph("3. Guide d'Implémentation Pas-à-Pas (Chirurgie du Code)", styles["SectionHeader"]))

    story.append(Paragraph("A. Le Moteur Central : <code>apps.core.permissions</code>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dans <code>apps/core/permissions.py</code>, la fonction <code>obtenir_projets_ids_actifs_utilisateur</code> "
            "doit agréger à la fois les affectations actives et les désignations directes de responsabilités sur <code>Projet</code> :",
            styles["Body"],
        )
    )

    code_core_permissions = """
def obtenir_projets_ids_actifs_utilisateur(user, request=None) -> list:
    \"\"\"Récupère et met en cache sur request la liste des IDs de projets affectés ou gérés.\"\"\"
    if not user or not user.is_authenticated:
        return []
    if request and hasattr(request, "_rbac_projets_ids_actifs"):
        return request._rbac_projets_ids_actifs

    from django.apps import apps as registre
    from django.db.models import Q

    try:
        AffectationProjet = registre.get_model("projets", "AffectationProjet")
        Projet = registre.get_model("projets", "Projet")
    except LookupError:
        return []

    # 1. Projets issus d'affectations actives
    projets_ids = set(
        AffectationProjet.objects.filter(
            utilisateur=user, est_actif=True, supprime_le__isnull=True
        ).values_list("projet_id", flat=True)
    )

    # 2. Projets où l'utilisateur est désigné comme CP ou CT direct
    projets_geres = set(
        Projet.objects.filter(
            Q(chef_projet=user) | Q(conducteur_travaux=user),
            supprime_le__isnull=True,
        ).values_list("id", flat=True)
    )

    projets_ids = list(projets_ids.union(projets_geres))
    if request:
        request._rbac_projets_ids_actifs = projets_ids
    return projets_ids
"""
    story.append(code_box(code_core_permissions, styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("B. Sécurisation de l'Équipe du Chantier : <code>apps.projets.views.affectation</code>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Deux failles critiques sont colmatées :<br/>"
            "1. <b>Lecture étanche :</b> <code>ProjetAffectationListCreateView</code> et <code>ProjetAffectationDetailView</code> "
            "intègrent <code>MembreDuProjet</code> : un collaborateur externe ne peut plus lister l'équipe d'un chantier d'autrui.<br/>"
            "2. <b>Correction de la faille CP :</b> Seul le Chef de Projet assigné à CE chantier spécifique peut administrer les affectations.",
            styles["Body"],
        )
    )

    code_affectation = """
def _verifier_droits_gestion_equipe(user, projet: Projet):
    \"\"\"Autorise l'administrateur, le DG ou le Chef de Projet assigné à ce chantier.\"\"\"
    if not user or not user.is_authenticated:
        raise PermissionDenied(_("Authentification requise."))

    est_admin = (
        getattr(user, "is_owner", False)
        or getattr(user, "is_dg", False)
        or getattr(user, "role_global", None) in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
        or getattr(user, "is_superuser", False)
    )
    # Seul le CP expressément rattaché à CE projet a autorité
    est_cp_du_projet = (
        projet.chef_projet_id == user.id
        or AffectationProjet.objects.filter(
            projet=projet,
            utilisateur=user,
            role_projet=RoleProjet.CHEF_PROJET,
            est_actif=True,
            supprime_le__isnull=True,
        ).exists()
    )

    if not (est_admin or est_cp_du_projet):
        raise PermissionDenied(_("Seul le Chef de Projet assigné ou la Direction peut gérer l'équipe du chantier."))
"""
    story.append(code_box(code_affectation, styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("C. Verrouillage des Rapports Journaliers : <code>apps.chantier.serializers</code>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dans <code>RapportJournalierCreateSerializer.validate()</code>, nous imposons le contrôle d'affectation lors de la création d'un rapport :",
            styles["Body"],
        )
    )

    code_rapport = """
user = self.context.get("request").user if self.context.get("request") else None
if user and user.is_authenticated:
    est_direction = (
        user.is_superuser
        or getattr(user, "is_owner", False)
        or getattr(user, "is_dg", False)
        or getattr(user, "role_global", None) in (RoleGlobal.ADMIN, RoleGlobal.DIRECTEUR_GENERAL)
    )
    if not est_direction:
        from apps.core.permissions import obtenir_projets_ids_actifs_utilisateur
        projets_actifs = obtenir_projets_ids_actifs_utilisateur(user, request=self.context.get("request"))
        if projet.id not in projets_actifs and str(projet.id) not in [str(p) for p in projets_actifs]:
            raise serializers.ValidationError({"projet_id": _("Vous n'êtes pas affecté à ce chantier.")})
"""
    story.append(code_box(code_rapport, styles))
    story.append(Spacer(1, 6))

    story.append(Paragraph("D. Cloisonnement de l'Annuaire Paramètres : <code>apps.accounts.views.collaborateur</code>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dans <code>ParametresCollaborateurListCreateView.get()</code>, si l'appelant est un collaborateur opérationnel, "
            "la liste des projets rattachés à chaque fiche de l'annuaire est filtrée pour ne laisser apparaître que les chantiers "
            "que l'utilisateur connecté a lui-même le droit de voir :",
            styles["Body"],
        )
    )

    # =========================================================================
    # SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM (KAHNEMAN / DEHAENE)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("4. Signal d'Erreur Bayésien & Simulation Pre-Mortem (Kahneman)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Stanislas Dehaene démontre que le cerveau apprend par comparaison entre sa prédiction et le signal "
            "d'erreur renvoyé par l'environnement. Voici les 4 pièges d'angle mort anticipés par notre analyse Pre-Mortem :",
            styles["Body"],
        )
    )

    pre_mortem_data = [
        [
            Paragraph("Anti-Pattern / Piège", styles["TableHeader"]),
            Paragraph("Manifestation & Risque Réel", styles["TableHeader"]),
            Paragraph("Parade Architecturale Adoptée", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>P1 : Faille de l'ID Direct (Insecure Direct Object Reference)</b>", styles["TableCellBold"]),
            Paragraph("L'utilisateur tape directement l'UUID d'un projet tiers dans l'URL pour inspecter ses lots ou ses rapports.", styles["TableCell"]),
            Paragraph("Vérification systématique de <code>MembreDuProjet.has_object_permission</code> sur toutes les vues de détail.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>P2 : Le Chef de Projet Imposteur</b>", styles["TableCellBold"]),
            Paragraph("Un utilisateur ayant <code>role_global='CP'</code> gère l'équipe d'un chantier sur lequel il n'est pas assigné.", styles["TableCell"]),
            Paragraph("Suppression de la vérification globale du rôle dans <code>_verifier_droits_gestion_equipe</code> : seul le CP du projet est légitime.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>P3 : Désynchronisation Affectation / Responsable</b>", styles["TableCellBold"]),
            Paragraph("Un CP ou CT créé directement sur le modèle <code>Projet</code> ne voit pas son chantier car aucune ligne <code>AffectationProjet</code> n'a été insérée.", styles["TableCell"]),
            Paragraph("Union ensembliste dans <code>obtenir_projets_ids_actifs_utilisateur</code> combinant affectations et clés étrangères directes.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>P4 : Saturation SQL (N+1 Query Explosion)</b>", styles["TableCellBold"]),
            Paragraph("Interrogation répétée de la table d'affectation à chaque élément sérialisé dans les listes.", styles["TableCell"]),
            Paragraph("Mémoïsation O(1) de <code>projets_ids</code> sur <code>request._rbac_projets_ids_actifs</code> et évaluation en une requête.", styles["TableCell"]),
        ],
    ]
    t_pm = Table(pre_mortem_data, colWidths=[130, 190, 203])
    t_pm.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#991B1B")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FEF2F2")]),
            ]
        )
    )
    story.append(t_pm)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 5 : PROTOCOLE DE VALIDATION & TESTS AUTOMATISÉS
    # =========================================================================
    story.append(Paragraph("5. Protocole de Validation & Cahier de Tests Automatisés", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le fichier de test unifié <code>apps/projets/tests/test_cloisonnement_chantiers.py</code> valide "
            "l'ensemble de la matrice de cloisonnement :",
            styles["Body"],
        )
    )

    tests_data = [
        [
            Paragraph("Scénario Testé", styles["TableHeader"]),
            Paragraph("Utilisateur Connecté", styles["TableHeader"]),
            Paragraph("Action Réalisée", styles["TableHeader"]),
            Paragraph("Résultat Attendu", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Vision Consolidée DG</b>", styles["TableCellBold"]),
            Paragraph("Directeur Général (DG)", styles["TableCell"]),
            Paragraph("GET /api/v1/projets/", styles["TableCell"]),
            Paragraph("<b>200 OK</b> — Voit les chantiers A et B", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Vision Consolidée Admin</b>", styles["TableCellBold"]),
            Paragraph("Administrateur Délégué (AD)", styles["TableCell"]),
            Paragraph("GET /api/v1/projets/", styles["TableCell"]),
            Paragraph("<b>200 OK</b> — Voit les chantiers A et B", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Cloisonnement Chef de Projet</b>", styles["TableCellBold"]),
            Paragraph("Chef de Projet A", styles["TableCell"]),
            Paragraph("GET /api/v1/projets/", styles["TableCell"]),
            Paragraph("<b>200 OK</b> — Voit uniquement Chantier A", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tentative Intrusion Chantier Tiers</b>", styles["TableCellBold"]),
            Paragraph("Chef de Projet A", styles["TableCell"]),
            Paragraph("GET /api/v1/projets/{Chantier_B_ID}/", styles["TableCell"]),
            Paragraph("<b>403 Forbidden</b> — Accès refusé", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Espionnage Équipe Tiers</b>", styles["TableCellBold"]),
            Paragraph("Conducteur Travaux A", styles["TableCell"]),
            Paragraph("GET /api/v1/projets/{Chantier_B_ID}/affectations/", styles["TableCell"]),
            Paragraph("<b>403 Forbidden</b> — Accès refusé", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Usurpation Gestion Équipe</b>", styles["TableCellBold"]),
            Paragraph("Chef de Projet A", styles["TableCell"]),
            Paragraph("POST /api/v1/projets/{Chantier_B_ID}/affectations/", styles["TableCell"]),
            Paragraph("<b>403 Forbidden</b> — Seul le CP assigné gère l'équipe", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Création Rapport Hors Projet</b>", styles["TableCellBold"]),
            Paragraph("Chef Chantier A", styles["TableCell"]),
            Paragraph("POST /api/v1/rapports/ (projet_id=Chantier B)", styles["TableCell"]),
            Paragraph("<b>400 Bad Request</b> — Non affecté au chantier", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tableau de Bord Scanné</b>", styles["TableCellBold"]),
            Paragraph("Conducteur Travaux A", styles["TableCell"]),
            Paragraph("GET /api/v1/tableau-de-bord/", styles["TableCell"]),
            Paragraph("<b>200 OK</b> — KPIs calculés sur Chantier A seul", styles["TableCell"]),
        ],
    ]
    t_tests = Table(tests_data, colWidths=[120, 110, 150, 143])
    t_tests.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065F46")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#ECFDF5")]),
            ]
        )
    )
    story.append(t_tests)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 6 : DÉFI HOMO DOCENS & ANCRAGE MÉTACOGNITIF
    # =========================================================================
    story.append(Paragraph("6. Défi Homo Docens : Consolidation Nocturne & Transmission", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le principe suprême de l'apprentissage selon Stanislas Dehaene et Barbara Minto réside dans la transmission active. "
            "Une notion n'est véritablement gravée dans vos réseaux synaptiques que lorsque vous êtes capable de l'enseigner "
            "avec une clarté limpide à un développeur junior.",
            styles["Body"],
        )
    )
    story.append(
        callout_box(
            "<b>Défi Homo Docens :</b> Expliquez à un pair pourquoi le simple filtrage du <code>GET /api/v1/projets/</code> "
            "ne suffit pas à garantir le cloisonnement d'un SaaS, et comment l'interaction entre <code>filtrer_queryset_par_affectations</code>, "
            "<code>MembreDuProjet</code> et la validation dans <code>RapportJournalierCreateSerializer</code> forme une triple barrière infranchissable.<br/><br/>"
            "<b>Rituel du Soir :</b> Avant de vous endormir, fermez les yeux et visualisez la requête HTTP traversant successivement "
            "le Middleware Multi-Tenant -> le Niveau 1 (PermissionModule) -> le Niveau 2 (MembreDuProjet) -> le QuerySet borné. "
            "Votre subconscient fera le replay synaptique à 20x durant la nuit.",
            styles,
            title="L'ÉLÉVATION AU NIVEAU HOMO DOCENS (CELUI QUI ENSEIGNE)",
            border_color="#7C3AED",
            bg_color="#F5F3FF",
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel généré avec succès : {output_path}")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.join(
        base_dir,
        "Manuels_Apprentissage",
        "MANUEL_SPRINT_3_TACHE_07_CLOISONNEMENT_CHANTIERS_SCOPING.pdf",
    )
    generate_manual_pdf(target_path)
