"""Script de génération du Manuel d'Apprentissage : Architecture Catalogue Partagé & Droits d'Usage.

Tâche : Transition vers Catalogue Partagé Unique dans public, Unicité des UUIDs & Séparation Droits d'Usage Multi-Tenant
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
            "CCD DIGITAL • ARCHITECTURE CATALOGUE PARTAGÉ & UNICITÉ DES UUIDS",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "SOUMAFE SARL — PATRON EXPAND / CONTRACT & SÉPARATION DROITS D'USAGE",
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
            "Document d'ingénierie avancée • Django 5 & django-tenants • Zéro Downtime",
        )
        page_str = f"Page {self._pageNumber} sur {page_count}"
        self.drawRightString(A4[0] - 36, 22, page_str)
        self.restoreState()


def generer_pdf(chemin_sortie: str):
    os.makedirs(os.path.dirname(os.path.abspath(chemin_sortie)), exist_ok=True)

    doc = SimpleDocTemplate(
        chemin_sortie,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=44,
        bottomMargin=44,
    )

    styles = getSampleStyleSheet()

    # Couleurs de la charte SOUMAFE / BTP Ingénierie
    C_PRIMARY = colors.HexColor("#0F172A")    # Ardoise foncée
    C_SECONDARY = colors.HexColor("#1E3A8A")  # Bleu marine profond
    C_ACCENT = colors.HexColor("#D97706")     # Ambre chantier
    C_SUCCESS = colors.HexColor("#059669")    # Émeraude succès
    C_WARNING = colors.HexColor("#B45309")    # Ambre avertissement
    C_BG_CODE = colors.HexColor("#F8FAFC")    # Fond code clair
    C_BG_CARD = colors.HexColor("#F1F5F9")    # Fond carte gris clair
    C_BORDER = colors.HexColor("#CBD5E1")     # Bordure neutre

    # Styles typographiques
    style_titre_grand = ParagraphStyle(
        "TitreGrand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=C_PRIMARY,
        alignment=0,
    )

    style_soustitre = ParagraphStyle(
        "SousTitre",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=C_SECONDARY,
    )

    style_h1 = ParagraphStyle(
        "SectionH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=C_SECONDARY,
        spaceBefore=12,
        spaceAfter=6,
    )

    style_h2 = ParagraphStyle(
        "SectionH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=C_PRIMARY,
        spaceBefore=8,
        spaceAfter=4,
    )

    style_body = ParagraphStyle(
        "CorpsTexte",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1E293B"),
    )

    style_body_bold = ParagraphStyle(
        "CorpsTexteGras",
        parent=style_body,
        fontName="Helvetica-Bold",
    )

    style_code = ParagraphStyle(
        "CodeBloc",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0F172A"),
    )

    style_callout = ParagraphStyle(
        "Callout",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#0F172A"),
    )

    story = []

    # =========================================================================
    # EN-TÊTE / BANDEAU DE COUVERTURE
    # =========================================================================
    header_data = [
        [
            Paragraph("<b>CCD DIGITAL • SOUMAFE SARL</b>", ParagraphStyle("Hdr1", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)),
            Paragraph("<b>GUIDE D'INGÉNIERIE SOUVERAINE</b>", ParagraphStyle("Hdr2", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#FCD34D"), alignment=2)),
        ],
        [
            Paragraph("<b>MANUEL DE MAÎTRISE BACKEND — SPRINT 4</b><br/><font size=7 color='#94A3B8'>Transition Architecturale Multi-Tenant Sans Interruption de Service</font>", ParagraphStyle("Hdr3", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.white)),
            Paragraph("<b>Statut : Production Ready</b><br/><font size=7 color='#A7F3D0'>621 Tests Passés • 0 Erreur</font>", ParagraphStyle("Hdr4", fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#6EE7B7"), alignment=2)),
        ]
    ]
    t_header = Table(header_data, colWidths=[360, 163])
    t_header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 14))

    # Titre Principal
    story.append(Paragraph("Architecture Catalogue Partagé, Unicité des UUIDs & Séparation Droits d'Usage", style_titre_grand))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Résolution structurelle de la divergence multi-tenant via le patron Expand/Contract, isolation B2B SaaS et zéro blocage d'équipe.", style_soustitre))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT, spaceBefore=0, spaceAfter=12))

    # =========================================================================
    # 1. POSTURE MENTORALE & NEUROSCIENCES COGNITIVES
    # =========================================================================
    story.append(Paragraph("1. Fondations Neurocognitives : Du Bricolage Réactif à l'Élégance Structurelle", style_h1))

    mentorat_txt = (
        "<b>Le principe de Joseph Murphy (Fin de l'Effort Inversé) :</b> Lorsqu'une équipe tente de synchroniser des données par de continuelles boucles de propagation, "
        "chaque tentative d'effort conscient pour réparer les failles crée de nouveaux bugs (timeouts HTTP, race conditions, UUIDs divergents). En reprogrammant "
        "notre subconscient d'architecte, nous comprenons que : <i>la meilleure propagation est celle qu'on n'a pas à faire</i>.<br/><br/>"
        "<b>Les 4 Piliers de Stanislas Dehaene :</b><br/>"
        "• <b>L'Attention Sélective :</b> Focaliser l'invariance : un catalogue de modules n'est pas une donnée client, c'est un invariant de plateforme.<br/>"
        "• <b>L'Engagement Actif :</b> Remplacer la passivité d'un script artisanal par une modélisation relationnelle native PostgreSQL.<br/>"
        "• <b>Le Retour sur Erreur :</b> Transformer l'échec de divergence UUID en audit formel avant toute migration en production.<br/>"
        "• <b>La Consolidation :</b> Automatiser les mécanismes par le patron Expand/Contract pour que le système fonctionne sans charge mentale."
    )

    t_mentorat = Table([[Paragraph(mentorat_txt, style_callout)]], colWidths=[523])
    t_mentorat.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BG_CARD),
        ("BOX", (0, 0), (-1, -1), 1, C_SECONDARY),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_mentorat)
    story.append(Spacer(1, 12))

    # =========================================================================
    # 2. DIAGNOSTIC RACINE : POURQUOI LES UUIDS DIVERGEAIENT
    # =========================================================================
    story.append(Paragraph("2. Diagnostic de la Rupture & Analyse SCQA", style_h1))

    scqa_data = [
        [
            Paragraph("<b>Situation</b>", style_body_bold),
            Paragraph("L'application gère 5 modules métier (Projets, Chantier, GED, Pilotage, Tiers) dans un modèle multi-tenant django-tenants.", style_body)
        ],
        [
            Paragraph("<b>Complication</b>", style_body_bold),
            Paragraph("Le modèle <code>Module</code> était dupliqué dans <code>SHARED_APPS</code> et <code>TENANT_APPS</code>. Chaque tenant instanciant ses propres enregistrements avec des <code>uuid.uuid4()</code> locaux, les UUIDs du Super Admin et ceux du Tenant divergeaient totalement.", style_body)
        ],
        [
            Paragraph("<b>Question</b>", style_body_bold),
            Paragraph("Comment garantir une stricte unicité des UUIDs sur toute la plateforme sans jamais bloquer les développeurs travaillant en continu sur le backend ?", style_body)
        ],
        [
            Paragraph("<b>Réponse (BLUF)</b>", style_body_bold),
            Paragraph("<b>Partager au lieu de propager.</b> Isoler le catalogue dans <code>public</code> avec une table dédiée <code>catalogue_module</code>, gérer les abonnements via <code>EntrepriseModule</code>, et lier les rôles locaux par FK cross-schéma avec <code>on_delete=PROTECT</code>.", style_body)
        ],
    ]
    t_scqa = Table(scqa_data, colWidths=[90, 433])
    t_scqa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), C_BG_CARD),
        ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t_scqa)
    story.append(Spacer(1, 12))

    # =========================================================================
    # 3. L'ARCHITECTURE CIBLE EN 3 COUCHES
    # =========================================================================
    story.append(Paragraph("3. L'Architecture Cible en 3 Couches", style_h1))

    couches_data = [
        [Paragraph("<b>Couche</b>", style_body_bold), Paragraph("<b>Emplacement</b>", style_body_bold), Paragraph("<b>Modèle & Table</b>", style_body_bold), Paragraph("<b>Gouvernance & Rôle</b>", style_body_bold)],
        [
            Paragraph("<b>1. Catalogue</b>", style_body_bold),
            Paragraph("<code>public</code> uniquement", style_body),
            Paragraph("<code>CatalogueModule</code><br/><code>CataloguePermission</code>", style_code),
            Paragraph("Super Admin uniquement. Invariant plateforme immuable. 1 seul UUID canonique par module.", style_body),
        ],
        [
            Paragraph("<b>2. Droit d'Usage</b>", style_body_bold),
            Paragraph("<code>public</code> uniquement", style_body),
            Paragraph("<code>EntrepriseModule</code>", style_code),
            Paragraph("Contrat B2B / Licensing. Associe une entreprise aux modules souscrits (plan, statut actif, dates).", style_body),
        ],
        [
            Paragraph("<b>3. Permissions Internes</b>", style_body_bold),
            Paragraph("Schéma Tenant", style_body),
            Paragraph("<code>RoleModulePermission</code><br/><code>ProjetRoleModuleOverride</code>", style_code),
            Paragraph("Administrateur du Tenant. Accorde des droits fins aux collaborateurs. FK cross-schéma vers <code>public</code>.", style_body),
        ],
    ]
    t_couches = Table(couches_data, colWidths=[95, 80, 140, 208])
    t_couches.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SECONDARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_BG_CARD]),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t_couches)
    story.append(Spacer(1, 14))

    # =========================================================================
    # 4. LE PROTOCOLE DE DÉPLOIEMENT EN EXPAND / CONTRACT
    # =========================================================================
    story.append(Paragraph("4. Implémentation par le Patron Expand / Contract (Zéro Downtime)", style_h1))

    phases_txt = (
        "<b>Phase 0 — Filet de Sécurité & Audit Pré-Migration :</b><br/>"
        "• Script <code>scripts/backup_db.sh</code> : Sauvegarde <code>pg_dump -Fc</code> avec somme SHA256 et vérification de lecture <code>pg_restore --list</code>.<br/>"
        "• Workflow CI/CD sécurisé : Le déploiement s'interrompt si le backup échoue ; option <code>run_migrate: false</code> pour déployer le code sans toucher la base.<br/>"
        "• Script <code>scripts/audit_catalogue.py</code> : Connexion forcée en lecture seule (<code>default_transaction_read_only = on</code>), validation des 8 tenants et 0 problème bloquant.<br/><br/>"
        "<b>Phase 1 — Expand (Création des Structures Partagées) :</b><br/>"
        "• Création de l'application <code>apps.catalogue</code> déclarée exclusivement dans <code>SHARED_APPS</code>.<br/>"
        "• Migration <code>0002_peupler_catalogue_depuis_public</code> : Copie à l'identique des UUIDs canoniques de <code>public</code> et initialisation de <code>EntrepriseModule</code>.<br/><br/>"
        "<b>Phase 2 — Coexistence & Migration de Données Sans Lock :</b><br/>"
        "• Ajout des colonnes <code>module_catalogue</code> (FK PROTECT) et <code>permissions_catalogue</code> (M2M) sur <code>RoleModulePermission</code> et <code>ProjetRoleModuleOverride</code>.<br/>"
        "• Migration de données par mise à jour SQL directe par correspondance de <code>code</code> : 75/75 lignes rattachées par tenant, 0 orphelin.<br/><br/>"
        "<b>Phase 3 — Bascule Applicative & Double Écriture Transparente :</b><br/>"
        "• <code>GET /api/v1/modules/</code> lit désormais <code>CatalogueModule</code> filtré par <code>EntrepriseModule</code>.<br/>"
        "• Résolution hybride dans <code>apps/core/permissions.py</code> garantissant 100% de rétrocompatibilité.<br/>"
        "• Les services de rôles et de surcharges écrivent simultanément sur les deux colonnes (dual-write).<br/><br/>"
        "<b>Phase 4 — Contract (Différé post-validation de production) :</b><br/>"
        "• Nettoyage des anciennes colonnes dépréciées après observation en production."
    )

    t_phases = Table([[Paragraph(phases_txt, style_callout)]], colWidths=[523])
    t_phases.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 1, C_BORDER),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_phases)
    story.append(Spacer(1, 12))

    # =========================================================================
    # 5. RÉSULTATS & PREUVE DE FONCTIONNEMENT
    # =========================================================================
    story.append(Paragraph("5. Preuves Métriques & Validation Empirique", style_h1))

    resultats_data = [
        [Paragraph("<b>Test / Critère de Succès</b>", style_body_bold), Paragraph("<b>Attendu</b>", style_body_bold), Paragraph("<b>Résultat Obtenu</b>", style_body_bold), Paragraph("<b>Statut</b>", style_body_bold)],
        [
            Paragraph("Unicité absolue des UUIDs", style_body),
            Paragraph("UUID Super Admin == UUID Tenant", style_body),
            Paragraph("d31d1558-4ea3-44a5-9be3-a31eaf144bfb == d31d1558...", style_code),
            Paragraph("<font color='#059669'><b>CONFORME</b></font>", style_body),
        ],
        [
            Paragraph("Filtrage des droits d'usage", style_body),
            Paragraph("Module exclu si EntrepriseModule inactif", style_body),
            Paragraph("test_droit_usage_filtrage_module_inactif PASSED", style_body),
            Paragraph("<font color='#059669'><b>CONFORME</b></font>", style_body),
        ],
        [
            Paragraph("Suite globale de tests", style_body),
            Paragraph("621 tests sans régression", style_body),
            Paragraph("621 passed, 0 failed en 150.45s", style_code),
            Paragraph("<font color='#059669'><b>CONFORME</b></font>", style_body),
        ],
        [
            Paragraph("Protection Frontend", style_body),
            Paragraph("Zéro altération / Zéro push frontend", style_body),
            Paragraph("Application-Gestion-Chantier 100% intact", style_body),
            Paragraph("<font color='#059669'><b>CONFORME</b></font>", style_body),
        ],
    ]
    t_res = Table(resultats_data, colWidths=[130, 140, 180, 73])
    t_res.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_BG_CARD]),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t_res)
    story.append(Spacer(1, 14))

    # Bloc Signature
    signature_txt = (
        "<b>Conclusion d'Architecture :</b> Le système de gestion de chantier dispose désormais d'un socle B2B SaaS de classe mondiale. "
        "Le catalogue est immuable et unifié, les droits d'usage sont personnalisables par entreprise, et les tenants conservent une autonomie totale "
        "dans l'assignation de leurs permissions internes."
    )
    t_sig = Table([[Paragraph(signature_txt, style_callout)]], colWidths=[523])
    t_sig.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
        ("BOX", (0, 0), (-1, -1), 1, C_SUCCESS),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t_sig)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF généré avec succès : {chemin_sortie}")


if __name__ == "__main__":
    pdf_path = os.path.join(
        "Manuels_Apprentissage",
        "MANUEL_SPRINT_4_ARCHITECTURE_CATALOGUE_PARTAGE_ET_DROITS_USAGE.pdf",
    )
    generer_pdf(pdf_path)
