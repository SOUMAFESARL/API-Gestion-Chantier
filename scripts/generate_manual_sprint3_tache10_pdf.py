"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 10.

Tâche : Harmonisation des APIs d'Invitations et Cycle de Vie Unifié des Collaborateurs
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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 10 : CYCLE DE VIE UNIFIÉ INVITATIONS & COLLABORATEURS",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "AFFECTATION CHANTIER SANS ACTIVATION & RETRAIT GLOBAL",
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
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14.5,
            textColor=colors.HexColor("#0284C7"),
            spaceAfter=12,
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
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            "SubSectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0369A1"),
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
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=4,
        )
    )

    styles.add(
        ParagraphStyle(
            "Callout",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#0C4A6E"),
        )
    )

    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7,
            leading=9,
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
            alignment=0,
        )
    )

    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#1E293B"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#0F172A"),
        )
    )

    return styles


def build_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=40,
    )
    styles = create_styles()
    story = []

    # Page de Garde / En-tête
    story.append(Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE • SPRINT 3", styles["DocSubTitle"]))
    story.append(
        Paragraph(
            "TÂCHE 10 : HARMONISATION DES APIS D'INVITATIONS & CYCLE DE VIE UNIFIÉ DES COLLABORATEURS",
            styles["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "<b>Architecture :</b> Unification sous <code>/api/v1/invitations/</code> • Affectation immédiate au chantier sans activation • Retrait local vs Retrait global plateforme • Rétrocompatibilité garantie.",
            styles["Body"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=10))

    # Cadrage Pédagogique
    cadre_neuro = [
        [
            Paragraph(
                "<b>ANCRAGE NEUROCOGNITIF (Stanislas Dehaene & Barbara Minto) :</b><br/>"
                "• <b>L'Analogie Fondatrice :</b> Le collaborateur reçoit d'abord son badge d'entrée dans la société (l'Entreprise). Ensuite, et seulement si nécessaire, on lui donne la clé d'un bureau précis (le Chantier).<br/>"
                "• <b>Découplage Temporel Terrain :</b> Sur un chantier BTP, on n'attend jamais qu'un ouvrier ou un conducteur de travaux valide son email pour le placer sur le planning. Le compte est créé avec le statut <code>INVITE</code> et l'affectation est immédiate dès la seconde zéro.",
                styles["Callout"],
            )
        ]
    ]
    t_neuro = Table(cadre_neuro, colWidths=[523])
    t_neuro.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F9FF")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#BAE6FD")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_neuro)
    story.append(Spacer(1, 10))

    # Module 1 : L'Architecture Unifiée
    story.append(Paragraph("1. Architecture des Routes : Simplification sans Rupture", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Auparavant, une ambiguïté existait entre <code>POST /api/v1/invitations/</code> (qui ne créait aucun utilisateur) et <code>POST /api/v1/parametres/collaborateurs/</code>. "
            "Désormais, <b>l'ensemble du cycle de vie est unifié sous <code>/api/v1/invitations/</code></b>, tout en conservant <code>/parametres/collaborateurs/</code> comme alias transparent pour zéro régression.",
            styles["Body"],
        )
    )

    matrix_routes = [
        [
            Paragraph("Méthode & Route", styles["TableHeader"]),
            Paragraph("Rôle & Action", styles["TableHeader"]),
            Paragraph("Niveau", styles["TableHeader"]),
            Paragraph("Statut HTTP", styles["TableHeader"]),
        ],
        [
            Paragraph("<code>POST /api/v1/invitations/</code>", styles["TableCellBold"]),
            Paragraph("Inviter un collaborateur dans l'entreprise (crée <code>Utilisateur</code> avec statut <code>INVITE</code>)", styles["TableCell"]),
            Paragraph("Entreprise", styles["TableCell"]),
            Paragraph("<b>201 Created</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>GET /api/v1/invitations/</code>", styles["TableCellBold"]),
            Paragraph("Lister tous les collaborateurs et invitations avec leurs chantiers rattachés", styles["TableCell"]),
            Paragraph("Entreprise", styles["TableCell"]),
            Paragraph("<b>200 OK</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>POST /api/v1/projets/{id}/affectations/</code>", styles["TableCellBold"]),
            Paragraph("Affecter immédiatement le collaborateur au chantier (même avec statut <code>INVITE</code>)", styles["TableCell"]),
            Paragraph("Chantier", styles["TableCell"]),
            Paragraph("<b>201 Created</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>PATCH .../affectations/{aff_id}/</code>", styles["TableCellBold"]),
            Paragraph("Retirer du chantier : désactivation locale sans perte d'historique (<code>est_actif=false</code>)", styles["TableCell"]),
            Paragraph("Chantier", styles["TableCell"]),
            Paragraph("<b>200 OK</b>", styles["TableCellBold"]),
        ],
        [
            Paragraph("<code>DELETE /api/v1/invitations/{id}/</code>", styles["TableCellBold"]),
            Paragraph("Retirer de toute la plateforme : désactivation globale, révocation sessions et détachement chantiers", styles["TableCell"]),
            Paragraph("Entreprise", styles["TableCell"]),
            Paragraph("<b>200 OK</b>", styles["TableCellBold"]),
        ],
    ]
    t_routes = Table(matrix_routes, colWidths=[150, 220, 75, 78])
    t_routes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_routes)
    story.append(Spacer(1, 10))

    # Module 2 : Cycle de Vie & Affectation Immédiate
    story.append(Paragraph("2. L'Affectation Immédiate : Le Secret de l'ID Permanent", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Pourquoi est-il possible d'affecter un collaborateur au chantier avant même qu'il ait ouvert son email ? "
            "Parce que dès l'appel à <code>POST /api/v1/invitations/</code>, Django génère la ligne dans la table <code>Utilisateur</code> avec un <b>UUID permanent</b>. "
            "La clé étrangère SQL de <code>AffectationProjet.utilisateur_id</code> est donc parfaitement satisfaite dès la première seconde !",
            styles["Body"],
        )
    )

    code_invit = (
        "# 1. Création dans l'Entreprise (Statut INVITE)\n"
        "POST {{base_url}}/api/v1/invitations/\n"
        "{\n"
        '  "email": "moussa.diallo@entreprise.ci",\n'
        '  "nom": "DIALLO",\n'
        '  "prenom": "Moussa",\n'
        '  "telephone": "+2250708091011",\n'
        '  "role_global": "CT"\n'
        "}\n"
        "# Réponse 201 Created : id = 'e3b0c442-...', statut = 'INVITE'\n\n"
        "# 2. Affectation immédiate au Chantier (sans attendre activation !)\n"
        "POST {{base_url}}/api/v1/projets/{{projet_id}}/affectations/\n"
        "{\n"
        '  "utilisateur_id": "e3b0c442-...",\n'
        '  "role_projet": "CT",\n'
        '  "date_debut": "2026-10-02"\n'
        "}\n"
        "# Réponse 201 Created : est_actif = True, utilisateur.statut = 'INVITE'"
    )
    t_code1 = Table([[Preformatted(code_invit, styles["CodeBlock"])]], colWidths=[523])
    t_code1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_code1)
    story.append(Spacer(1, 10))

    # Module 3 : Les Deux Niveaux de Retrait
    story.append(Paragraph("3. Les Deux Niveaux de Retrait : Local vs Global", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Il est crucial de bien distinguer le <b>retrait d'un chantier</b> du <b>départ de l'entreprise</b> :",
            styles["Body"],
        )
    )

    retrait_boxes = [
        [
            Paragraph(
                "<b>NIVEAU CHANTIER (Retrait Local) :</b><br/>"
                "• <b>Cas :</b> Fin de mission sur ce chantier, réaffectation ailleurs.<br/>"
                "• <b>Action :</b> <code>PATCH /projets/{id}/affectations/{aff_id}/</code> avec <code>{\"est_actif\": false}</code>.<br/>"
                "• <b>Effet :</b> Le collaborateur perd l'accès à ce chantier, mais <b>reste membre de l'entreprise</b> et conserve ses autres chantiers.<br/>"
                "• <b>Traçabilité :</b> Ses signatures passées sur le journal restent conservées.",
                styles["TableCell"],
            ),
            Paragraph(
                "<b>NIVEAU ENTREPRISE (Retrait Global Plateforme) :</b><br/>"
                "• <b>Cas :</b> Démission, fin de contrat, départ de la société.<br/>"
                "• <b>Action :</b> <code>DELETE /api/v1/invitations/{id}/</code>.<br/>"
                "• <b>Effet :</b> Déconnexion immédiate (sessions révoquées), détachement automatique de tous les chantiers, statut <code>DESACTIVE</code>.<br/>"
                "• <b>Sécurité :</b> Interdiction formelle de désactiver le DG / Propriétaire (HTTP 400).",
                styles["TableCell"],
            ),
        ]
    ]
    t_retrait = Table(retrait_boxes, colWidths=[256, 257])
    t_retrait.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FEF3C7")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FEE2E2")),
                ("BOX", (0, 0), (0, 0), 1, colors.HexColor("#FCD34D")),
                ("BOX", (1, 0), (1, 0), 1, colors.HexColor("#FCA5A5")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_retrait)
    story.append(Spacer(1, 10))

    # Module 4 : Le Service Backend Atomique
    story.append(Paragraph("4. Implémentation Backend du Service de Retrait Global", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le service <code>desactiver_collaborateur_plateforme</code> s'exécute dans une transaction atomique PostgreSQL pour garantir une étanchéité parfaite :",
            styles["Body"],
        )
    )

    code_service = (
        "@transaction.atomic\n"
        "def desactiver_collaborateur_plateforme(*, collaborateur, auteur):\n"
        "    if collaborateur.is_owner:\n"
        "        raise ValidationError('Le compte du DG / Propriétaire ne peut pas être désactivé.')\n"
        "    if collaborateur.pk == auteur.pk:\n"
        "        raise ValidationError('Vous ne pouvez pas désactiver votre propre compte.')\n\n"
        "    # 1. Soft-delete et passage au statut DESACTIVE\n"
        "    collaborateur.statut = StatutUtilisateur.DESACTIVE\n"
        "    collaborateur.is_active = False\n"
        "    collaborateur.supprime_le = timezone.now()\n"
        "    collaborateur.supprime_par = auteur\n"
        "    collaborateur.save(update_fields=['statut', 'is_active', 'supprime_le', 'supprime_par', 'modifie_le'])\n\n"
        "    # 2. Clôture automatique de tous les chantiers actifs\n"
        "    AffectationProjet.objects.filter(utilisateur=collaborateur, est_actif=True).update(est_actif=False)\n"
        "    Projet.objects.filter(chef_projet=collaborateur).update(chef_projet=None)\n\n"
        "    # 3. Révocation des invitations en attente et des sessions JWT actives (blacklist Redis)\n"
        "    Invitation.objects.filter(email__iexact=collaborateur.email, statut=ENVOYEE).update(statut=REVOQUEE)\n"
        "    revoquer_utilisateur(collaborateur.pk, ttl=86400)"
    )
    t_code2 = Table([[Preformatted(code_service, styles["CodeBlock"])]], colWidths=[523])
    t_code2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_code2)
    story.append(Spacer(1, 10))

    # Module 5 : Validation & Postman
    story.append(Paragraph("5. Synthèse des Tests & Validation d'Excellence", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>27 tests automatisés pytest</b> ont été exécutés avec 100% de succès sur la suite complète. "
            "La collection Postman officielle a été enrichie avec les requêtes 23, 24, 25 et 26 pour tester graphiquement l'intégralité du parcours.",
            styles["Body"],
        )
    )

    recap_final = [
        [
            Paragraph(
                "<b>CONTRAT ARCHITECTURAL VALIDÉ :</b><br/>"
                "• <b>Simplicité Maximale :</b> Une seule route canonique <code>/api/v1/invitations/</code>.<br/>"
                "• <b>Zéro Rupture :</b> <code>/api/v1/parametres/collaborateurs/</code> fonctionne toujours comme alias.<br/>"
                "• <b>Réalité BTP Respectée :</b> Un collaborateur invité peut travailler sur un chantier dès la première seconde sans attendre son email.<br/>"
                "• <b>Souveraineté des Données :</b> Révocation propre des sessions, traçabilité des signatures et intégrité comptable préservée.",
                styles["Callout"],
            )
        ]
    ]
    t_final = Table(recap_final, colWidths=[523])
    t_final.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFDF5")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#A7F3D0")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_final)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Manuel PDF généré avec succès : {filename}")


if __name__ == "__main__":
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
    )
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(
        output_dir,
        "MANUEL_SPRINT_3_TACHE_10_HARMONISATION_INVITATIONS_ET_CYCLE_VIE_COLLABORATEURS.pdf",
    )
    build_pdf(pdf_path)
