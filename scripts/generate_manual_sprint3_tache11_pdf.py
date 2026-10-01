"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 11.

Tâche : Permissions Modules Granulaires et Dynamiques — Émancipation du Scalaire vers le Matriciel M2M
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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 11 : PERMISSIONS MODULES 100% DYNAMIQUES & GRANULAIRES",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "SOCIÉTÉ SOUMAFE SARL — RBAC MATRICIEL M2M",
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
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "DocSubtitle",
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
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "SubsectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0284C7"),
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "CustomBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "CustomBodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "CalloutText",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#1E293B"),
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeBlockText",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#0F172A"),
        )
    )
    styles.add(
        ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=1,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#1E293B"),
        )
    )
    styles.add(
        ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#0F172A"),
        )
    )

    return styles


def callout_box(text, title="PRINCIPE COGNITIF & INVARIANT", color_hex="#1E3A8A", bg_hex="#F0F9FF"):
    st = create_styles()
    p_title = Paragraph(f"<b>{title}</b>", ParagraphStyle("CTitle", parent=st["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor(color_hex)))
    p_text = Paragraph(text, st["CalloutText"])
    t = Table([[p_title], [p_text]], colWidths=[523])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_hex)),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(color_hex)),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    return t


def code_box(code_str):
    st = create_styles()
    p = Preformatted(code_str.strip(), st["CodeBlockText"])
    t = Table([[p]], colWidths=[523])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return t


def build_pdf(filepath):
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=40,
    )
    st = create_styles()
    story = []

    # Titre & En-tête
    story.append(Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", st["DocSubtitle"]))
    story.append(
        Paragraph(
            "Sprint 3 — Tâche 11 : Permissions Modules 100% Dynamiques & Granulaires",
            st["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "<b>Émancipation du Scalaire vers le Matriciel M2M :</b> Élimination des chiffres arbitraires (0, 1, 2, 3), "
            "sérialisation granulaire en listes de codes techniques, zéro code en dur et réactivité temps réel aux mutations du catalogue de permissions.",
            st["DocSubtitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

    # SECTION 1
    story.append(Paragraph("1. Neuro-Pédagogie, Film Mental & Objectif Sacré (Murphy & Dehaene)", st["SectionHeader"]))
    story.append(
        Paragraph(
            "Dans la conception logicielle d'entreprise, l'illusion la plus fréquente est de croire qu'une habilitation est <i>cumulative</i>. "
            "On imagine qu'un niveau 3 (Validation) contient nécessairement le niveau 2 (Écriture) et le niveau 1 (Lecture). "
            "Dans la réalité opérationnelle des chantiers BTP, ce postulat est faux : un Maître d'Ouvrage (Client) ou un Contrôleur Technique "
            "doit pouvoir <b>valider</b> des situations de travaux ou des procès-verbaux sans jamais pouvoir <b>altérer ni saisir</b> des données de chantier.",
            st["CustomBody"],
        )
    )
    story.append(
        callout_box(
            "<b>Le Film Mental (Joseph Murphy) :</b> Visualise un administrateur créant une nouvelle permission 'EXPORT_EXCEL' ou 'SIGNATURE_PROVISOIRE' "
            "directement dans l'interface ou en base de données. Instantanément, sans redémarrer le serveur Django, sans recompiler, sans toucher une seule ligne "
            "de code Python, l'API GET /api/v1/roles/ expose la clé dans 'permissions_modules'. L'architecture respire, libre de toute chaîne de caractères codée en dur.",
            title="FILM MENTAL DU SUBCONSCIENT",
            color_hex="#047857",
            bg_hex="#ECFDF5",
        )
    )
    story.append(Spacer(1, 8))

    # SECTION 2
    story.append(Paragraph("2. Architecture & Invariants Fondamentaux (Barbara Minto & George Pólya)", st["SectionHeader"]))
    story.append(
        Paragraph(
            "L'architecture repose sur le découplage strict entre trois concepts orthogonaux :",
            st["CustomBody"],
        )
    )

    table_data = [
        [
            Paragraph("Attribut", st["TableHeader"]),
            Paragraph("Type & Rôle", st["TableHeader"]),
            Paragraph("Stabilité / Mutabilité", st["TableHeader"]),
            Paragraph("Impact en cas de modification", st["TableHeader"]),
        ],
        [
            Paragraph("<b>id (UUID)</b>", st["TableCellBold"]),
            Paragraph("Clé primaire immuable en BDD", st["TableCell"]),
            Paragraph("100% Immuable", st["TableCell"]),
            Paragraph("Les relations M2M ne se brisent JAMAIS car elles pointent sur l'UUID.", st["TableCell"]),
        ],
        [
            Paragraph("<b>code</b>", st["TableCellBold"]),
            Paragraph("Jeton technique lisible ('LECTURE')", st["TableCell"]),
            Paragraph("Stable (Contrat API)", st["TableCell"]),
            Paragraph("Utilisé par le Frontend pour ses tests logiques (hasPermission('VALIDATION')).", st["TableCell"]),
        ],
        [
            Paragraph("<b>libelle</b>", st["TableCellBold"]),
            Paragraph("Nom d'affichage humain", st["TableCell"]),
            Paragraph("100% Modifiable par l'Admin", st["TableCell"]),
            Paragraph("Changer 'Lecture / Consultation' en 'Visualisation' ne casse aucun code.", st["TableCell"]),
        ],
    ]
    t_arch = Table(table_data, colWidths=[90, 140, 110, 183])
    t_arch.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
        ])
    )
    story.append(t_arch)
    story.append(Spacer(1, 8))

    story.append(
        callout_box(
            "<b>Invariant de Complétude :</b> Tout rôle renvoyé par l'API expose OBLIGATOIREMENT l'ensemble des modules actifs du catalogue "
            "comme clés du dictionnaire 'permissions_modules'. Si un module n'a aucune habilitation attribuée au rôle, sa valeur est explicitement "
            "une liste vide <b>[]</b>, et jamais null ou une clé absente.",
            title="INVARIANT MÉTIER D7 — COMPLÉTUDE DU DICTIONNAIRE",
            color_hex="#B45309",
            bg_hex="#FFFBEB",
        )
    )
    story.append(Spacer(1, 10))

    # SECTION 3
    story.append(Paragraph("3. Guide d'Implémentation Pas-à-Pas (Zéro Code en Dur)", st["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>Étape 1 : Le Serializer Dynamique (RoleSerializer)</b><br/>"
            "Nous éliminons la lecture du scalaire <code>p.niveau</code> pour interroger directement la relation M2M <code>permissions</code> :",
            st["CustomBody"],
        )
    )

    code_serializer = """# apps/accounts/serializers/role.py
def get_permissions_modules(self, obj: Role) -> dict[str, list[str]]:
    \"\"\"Dictionnaire dynamique associant chaque module actif à la liste ordonnée de ses codes de permissions.
    Zéro hardcodage : interroge directement les relations M2M en base de données.
    \"\"\"
    modules_actifs = list(
        Module.objects.filter(est_actif=True, supprime_le__isnull=True).order_by("ordre", "code")
    )
    rpm_qs = (
        RoleModulePermission.objects.filter(
            role=obj,
            supprime_le__isnull=True,
            module__in=modules_actifs,
        )
        .select_related("module")
        .prefetch_related("permissions")
    )
    rpm_par_module_id = {rmp.module_id: rmp for rmp in rpm_qs}

    resultat: dict[str, list[str]] = {}
    for mod in modules_actifs:
        rmp = rpm_par_module_id.get(mod.id)
        if rmp:
            perms = list(
                rmp.permissions.filter(est_actif=True, supprime_le__isnull=True)
                .order_by("ordre", "code")
                .values_list("code", flat=True)
            )
            resultat[mod.code] = perms
        else:
            resultat[mod.code] = []
    return resultat"""
    story.append(code_box(code_serializer))
    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "<b>Étape 2 : Le Contrat JSON en Entrée et en Sortie</b><br/>"
            "Voici la structure exacte renvoyée à présent par le point d'entrée <code>GET /api/v1/roles/</code> :",
            st["CustomBody"],
        )
    )

    code_json = """{
    "id": "6aa7940c-2e07-40fa-b6f6-7375439f2e40",
    "code": "AD",
    "libelle": "Administrateur",
    "est_systeme": true,
    "permissions_modules": {
        "projets": ["LECTURE", "ECRITURE", "VALIDATION"],
        "chantier": [],
        "ged": ["LECTURE", "ECRITURE", "VALIDATION"],
        "pilotage": ["LECTURE", "ECRITURE", "VALIDATION"],
        "tiers": ["LECTURE", "ECRITURE", "VALIDATION"]
    }
}"""
    story.append(code_box(code_json))
    story.append(Spacer(1, 10))

    # SECTION 4
    story.append(Paragraph("4. Signal d'Erreur Bayésien & Pre-Mortem (Stanislas Dehaene / Kahneman)", st["SectionHeader"]))
    story.append(
        Paragraph(
            "L'audit Pre-Mortem nous impose d'anticiper les pièges susceptibles d'entraîner une régression en production :",
            st["CustomBody"],
        )
    )

    pm_data = [
        [
            Paragraph("Anti-Pattern / Risque", st["TableHeader"]),
            Paragraph("Mécanisme d'Échec", st["TableHeader"]),
            Paragraph("Parade Architecturale Implémentée", st["TableHeader"]),
        ],
        [
            Paragraph("<b>Filtrage textuel en dur</b>", st["TableCellBold"]),
            Paragraph("Écrire <code>if p.code == 'LECTURE'</code> dans le serializer.", st["TableCell"]),
            Paragraph("Utilisation stricte de <code>values_list('code', flat=True)</code> sans filtrage sur les noms.", st["TableCell"]),
        ],
        [
            Paragraph("<b>Module sans permissions absent</b>", st["TableCellBold"]),
            Paragraph("Le frontend reçoit <code>undefined</code> pour <code>permissions_modules.chantier</code>.", st["TableCell"]),
            Paragraph("Boucle systématique sur <code>modules_actifs</code> avec valeur de repli <code>[]</code>.", st["TableCell"]),
        ],
        [
            Paragraph("<b>Régression des clients envoyant un entier</b>", st["TableCellBold"]),
            Paragraph("Un client legacy envoie <code>{'projets': 2}</code> lors d'un POST.", st["TableCell"]),
            Paragraph("<code>_normaliser_permissions_modules</code> convertit silencieusement 2 en <code>['LECTURE', 'ECRITURE']</code>.", st["TableCell"]),
        ],
    ]
    t_pm = Table(pm_data, colWidths=[120, 190, 213])
    t_pm.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#991B1B")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#FEF2F2")]),
        ])
    )
    story.append(t_pm)
    story.append(Spacer(1, 10))

    # SECTION 5
    story.append(Paragraph("5. Suite de Tests Automatisés & Preuve d'Exécution", st["SectionHeader"]))
    story.append(
        Paragraph(
            "La suite de validation automatisée a été exécutée sous <b>Pytest 9.1.1 & Django 5.2.17</b>. "
            "L'intégralité des <b>30 tests</b> sur les rôles et permissions dynamiques a réussi avec succès (0 échec, 100% passants) :",
            st["CustomBody"],
        )
    )

    code_tests = """apps/accounts/tests/test_gouvernance_dg.py::test_admin_delegue_peut_inviter_autres_roles PASSED
apps/accounts/tests/test_parametres_collaborateurs.py::test_post_parametres_collaborateurs_interdit_role_dg PASSED
apps/accounts/tests/test_parametres_collaborateurs.py::test_rattacher_collaborateur_a_role_personnalise PASSED
apps/accounts/tests/test_parametres_collaborateurs.py::test_interdiction_modifier_role_proprietaire PASSED
apps/accounts/tests/test_parametres_roles.py::test_get_parametres_roles_liste PASSED
apps/accounts/tests/test_parametres_roles.py::test_post_parametres_roles_creer_par_admin PASSED
apps/accounts/tests/test_parametres_roles.py::test_post_parametres_roles_creer_par_dg PASSED
apps/accounts/tests/test_parametres_roles.py::test_post_parametres_roles_refuse_aux_collaborateurs PASSED
apps/accounts/tests/test_parametres_roles.py::test_modifier_permissions_role_en_post_et_patch PASSED
apps/accounts/tests/test_parametres_roles.py::test_supprimer_role_avec_reassignation_par_admin PASSED
apps/accounts/tests/test_roles.py::test_initialiser_roles_par_defaut PASSED
apps/accounts/tests/test_roles.py::test_interdiction_supprimer_role_systeme PASSED
apps/accounts/tests/test_roles.py::test_seuls_dg_et_admin_sont_roles_systeme PASSED
apps/accounts/tests/test_roles.py::test_supprimer_role_avec_reassignation_obligatoire PASSED
apps/accounts/tests/test_roles.py::test_surcharge_permissions_par_projet PASSED
apps/accounts/tests/test_roles.py::test_api_roles_crud PASSED
apps/accounts/tests/test_roles.py::test_permission_module_enforcement PASSED
apps/accounts/tests/test_roles_dg.py::test_rec_s1_10_a_action_reservee_dg PASSED
apps/accounts/tests/test_roles_dg.py::test_rec_s1_10_b_substitution_obligatoire PASSED
apps/accounts/tests/test_roles_dg.py::test_rec_s1_10_c_suppression_et_reaffectation_atomique PASSED
apps/accounts/tests/test_roles_modules_dynamiques.py::test_role_obligatoirement_lie_a_tous_les_modules PASSED
apps/accounts/tests/test_roles_modules_dynamiques.py::test_tableau_dynamique_modules_et_permissions_api PASSED
apps/accounts/tests/test_roles_modules_dynamiques.py::test_non_hierarchie_permissions_validation_seule PASSED
apps/accounts/tests/test_roles_modules_dynamiques.py::test_permissions_modules_format_liste_codes_dynamique PASSED
apps/accounts/tests/test_roles_modules_dynamiques.py::test_dynamisme_ajout_et_modification_permission_en_base PASSED

======================== 30 passed, 114 deselected in 35.20s ========================"""
    story.append(code_box(code_tests))
    story.append(Spacer(1, 10))

    # SECTION 6
    story.append(Paragraph("6. Défi Homo Docens & Clôture Métacognitive (Carol Dweck)", st["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>Le Défi de Transmission :</b> Explique à un collègue développeur pourquoi l'utilisation d'un champ entier <code>niveau = 3</code> "
            "pour modéliser des droits d'accès constitue un <i>anti-pattern</i> dans une application de gestion, et comment le passage à une relation "
            "ManyToMany couplée à une sérialisation dynamique par <code>values_list()</code> résout simultanément les problèmes d'extensibilité, "
            "d'étanchéité et de performance.<br/><br/>"
            "<b>Consolidation Nocturne (Stanislas Dehaene - Pilier 4) :</b> Ce soir, avant de t'endormir, repense à la structure de cette requête ORM. "
            "Le subconscient procédera à un replay neuronal à vitesse accélérée (20x), ancrant pour toujours le modèle RBAC matriciel dans tes automatismes d'ingénieur.",
            st["CustomBody"],
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel généré avec succès : {filepath}")


if __name__ == "__main__":
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
    )
    os.makedirs(output_dir, exist_ok=True)
    target_pdf = os.path.join(
        output_dir,
        "MANUEL_SPRINT_3_TACHE_11_PERMISSIONS_MODULES_DYNAMIQUES.pdf",
    )
    build_pdf(target_pdf)
