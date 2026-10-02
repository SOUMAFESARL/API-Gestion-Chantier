"""Script de génération du Manuel d'Apprentissage par la Pratique : Alignement API Entreprise & Frontend.

Tâche : Alignement Exhaustif des API Entreprise (Modules, Rôles, Permissions, Collaborateurs, Surcharges Projets) avec le Frontend
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
            "CCD DIGITAL • ALIGNEMENT API ENTREPRISE & APPLICATION FRONTEND",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "SOUMAFE SARL — CONTRATS REST & MULTI-TENANCY SOUVERAINE",
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
            "SOUMAFE SARL • Plateforme SaaS BTP • Confidentiel & Interne",
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
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#0284C7"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionH1",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionH2",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0369A1"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyDark",
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
            "BodyDarkBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeBox",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#0F172A"),
            backColor=colors.HexColor("#F8FAFC"),
            borderColor=colors.HexColor("#E2E8F0"),
            borderWidth=0.5,
            borderPadding=5,
            spaceBefore=4,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableHead",
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
    styles.add(
        ParagraphStyle(
            "CalloutCognitive",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1E3A8A"),
            backColor=colors.HexColor("#EFF6FF"),
            borderColor=colors.HexColor("#BFDBFE"),
            borderWidth=0.5,
            borderPadding=6,
            spaceBefore=6,
            spaceAfter=8,
        )
    )
    return styles


def build_pdf(filename="Manuels_Apprentissage/MANUEL_ENTREPRISE_ALIGNEMENT_FRONTEND.pdf"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
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

    # --- BANDEAU TITRE & MÉTADONNÉES ---
    story.append(Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", styles["DocSubTitle"]))
    story.append(
        Paragraph(
            "Alignement Exhaustif des API Entreprise avec le Frontend Next.js",
            styles["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "Architecture Multi-Tenant • Normalisation des Permissions • Cycle de Vie Collaborateurs • Surcharges Projets",
            styles["DocSubTitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284C7"), spaceAfter=10))

    meta_data = [
        [
            Paragraph("<b>Auteur :</b> Pair Programmer IA & Mentor Neurocognitif", styles["TableCell"]),
            Paragraph("<b>Destinataire :</b> Développeur Backend Souverain (CCD Digital / SOUMAFE)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Projet Backend :</b> API-Gestion-Chantier (Django 5 / DRF)", styles["TableCell"]),
            Paragraph("<b>Projet Frontend :</b> Application-Gestion-Chantier (Next.js 14 App Router)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Périmètre Métier :</b> Espace Entreprise (Tenant Scoped)", styles["TableCell"]),
            Paragraph("<b>Statut Tests :</b> 100% Succès (21 tests validés)", styles["TableCell"]),
        ],
    ]
    t_meta = Table(meta_data, colWidths=[260, 260])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 10))

    # --- SYNTHÈSE EXÉCUTIVE (BLUF) ---
    story.append(Paragraph("1. Synthèse Exécutive (BLUF — Bottom Line Up Front)", styles["SectionH1"]))
    story.append(
        Paragraph(
            "Après avoir aligné le module Super Admin (schéma public), l'immersion complète dans le code source de "
            "l'application Frontend Next.js (<code>Application-Gestion-Chantier</code>) a révélé quatre dissymétries "
            "critiques au niveau de l'espace Entreprise (Tenant Scoped). Ces écarts causaient des cases à cocher vides, "
            "des écrans d'erreur 500 sur les profils collaborateurs et l'écrasement des surcharges de permissions par chantier. "
            "Toutes les API Django ont été adaptées pour satisfaire exactement les contrats attendus par le client web.",
            styles["BodyDark"],
        )
    )

    story.append(
        Paragraph(
            "<b>Principe Fondateur de Sécurité & Non-Régression :</b> Conformément à la politique stricte de protection du "
            "Frontend, <b>aucun fichier frontend n'a été altéré</b>. Toutes les évolutions ont été réalisées côté Backend "
            "avec une compatibilité ascendante totale : l'API accepte et restitue désormais à la fois les identifiants "
            "canoniques backend (ex: <code>'ECRITURE'</code>) et les conventions ergonomiques du frontend (ex: <code>'saisie'</code>).",
            styles["CalloutCognitive"],
        )
    )

    # --- TABLEAU DES 4 ÉCARTS ET RÉSOLUTIONS ---
    story.append(Paragraph("2. Cartographie des Dissymétries et Solutions Implémentées", styles["SectionH1"]))

    ecarts_data = [
        [
            Paragraph("Module / Domaine", styles["TableHead"]),
            Paragraph("Comportement Frontend Attendu", styles["TableHead"]),
            Paragraph("Ancien Comportement Backend", styles["TableHead"]),
            Paragraph("Solution Implémentée & Impact", styles["TableHead"]),
        ],
        [
            Paragraph("<b>Catalogue Modules</b><br/><code>GET /modules/</code>", styles["TableCellBold"]),
            Paragraph("Exige <code>id</code> (UUID ou code), <code>statut='ACTIF'</code> et <code>acces_par_defaut: ['lecture', 'saisie', 'validation']</code>.", styles["TableCell"]),
            Paragraph("Renvoyait uniquement <code>code</code>, <code>nom</code>, <code>description</code>, <code>est_actif</code>, sans <code>id</code> ni <code>statut</code>.", styles["TableCell"]),
            Paragraph("<b>ModuleItemSerializer & ModuleListView</b> : Ajout dynamique de <code>id</code>, <code>statut</code> et <code>acces_par_defaut</code> normalisés.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Rôles & Permissions</b><br/><code>GET/POST/PATCH /parametres/roles/</code>", styles["TableCellBold"]),
            Paragraph("Le frontend filtre strictement avec <code>ACCES_MODULE = ['lecture', 'saisie', 'validation']</code>. Envoie <code>saisie</code> au lieu de <code>ECRITURE</code>.", styles["TableCell"]),
            Paragraph("Le backend renvoyait <code>['LECTURE', 'ECRITURE']</code> en majuscules. Le frontend ignorait les majuscules et affichait des cases vides !", styles["TableCell"]),
            Paragraph("<b>RoleSerializer & Service Roles</b> : Injection des deux représentations (minuscule et majuscule) et mapping transparent <code>saisie -> ECRITURE</code>.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Collaborateurs</b><br/><code>GET/POST /parametres/collaborateurs/</code>", styles["TableCellBold"]),
            Paragraph("Attend <code>avatar_url</code> et <code>derniere_connexion</code>. Déclenche <code>/suspendre/</code> et <code>/reactiver/</code> avec gestion 409.", styles["TableCell"]),
            Paragraph("Champs absents causant des 500. Pas d'endpoints dédiés de suspension/réactivation (statut restait inchangé).", styles["TableCell"]),
            Paragraph("<b>Vues et Serializers Collaborateur</b> : Création de <code>ParametresCollaborateurSuspendreView</code> et <code>ReactiverView</code> avec garde-fous DG/Owner.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Surcharges Projets</b><br/><code>GET/PUT /projets/{id}/permissions-roles/</code>", styles["TableCellBold"]),
            Paragraph("Envoie et reçoit <code>acces: ['lecture', 'saisie']</code> au lieu de l'entier <code>niveau (1, 2, 3)</code>.", styles["TableCell"]),
            Paragraph("Seul <code>niveau</code> était géré. L'envoi de <code>acces</code> seul écrasait la surcharge en la supprimant !", styles["TableCell"]),
            Paragraph("<b>Service Overrides & Views Projets</b> : Conversion bidirectionnelle automatique entre <code>acces</code> (tableau de chaînes) et <code>niveau</code>.", styles["TableCell"]),
        ],
    ]
    t_ecarts = Table(ecarts_data, colWidths=[90, 140, 140, 150])
    t_ecarts.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(t_ecarts)
    story.append(Spacer(1, 10))

    # --- DÉTAILS D'IMPLÉMENTATION CODE BACKEND ---
    story.append(Paragraph("3. Analyse Technique des Implémentations Backend", styles["SectionH1"]))

    story.append(Paragraph("A. Normalisation Polymorphique des Rôles (<code>apps/accounts/services/roles.py</code>)", styles["SectionH2"]))
    story.append(
        Paragraph(
            "Le service <code>_normaliser_permissions_modules</code> accepte désormais indifféremment des dictionnaires, "
            "des listes, des entiers (anciens niveaux 1/2/3) ou des codes textuels. Le mapping <code>saisie -> ECRITURE</code> "
            "permet au formulaire d'administration de l'entreprise de persister les permissions sans la moindre friction.",
            styles["BodyDark"],
        )
    )
    code_norm = (
        "EQUIVALENCES_CODES = {\n"
        "    'SAISIE': 'ECRITURE',\n"
        "    'ECRITURE': 'ECRITURE',\n"
        "    'LECTURE': 'LECTURE',\n"
        "    'VALIDATION': 'VALIDATION',\n"
        "    'SUPPRESSION': 'SUPPRESSION',\n"
        "}\n\n"
        "# Dans RoleSerializer.get_permissions_modules :\n"
        "# Renvoyer les deux codes pour garantir le match avec ACCES_MODULE frontend :\n"
        "for c in [p.code.upper() for p in perms_list]:\n"
        "    codes_finaux.append(c)\n"
        "    if c == 'ECRITURE': codes_finaux.append('saisie')\n"
        "    elif c == 'LECTURE': codes_finaux.append('lecture')\n"
        "    elif c == 'VALIDATION': codes_finaux.append('validation')"
    )
    story.append(Preformatted(code_norm, styles["CodeBox"]))

    story.append(Paragraph("B. Endpoints de Cycle de Vie Collaborateurs (<code>apps/accounts/views/collaborateur.py</code>)", styles["SectionH2"]))
    story.append(
        Paragraph(
            "Les routes <code>POST /parametres/collaborateurs/{id}/suspendre/</code> et <code>/reactiver/</code> "
            "ont été dotées d'une triple barrière de sécurité :",
            styles["BodyDark"],
        )
    )
    story.append(
        Paragraph(
            "• <b>Auto-suspension interdite (400) :</b> Un utilisateur ne peut pas scier la branche sur laquelle il est assis.<br/>"
            "• <b>Immunité DG / Owner (400) :</b> Le propriétaire du tenant et le Directeur Général ne peuvent jamais être suspendus.<br/>"
            "• <b>Idempotence stricte (409) :</b> Une tentative de suspendre un compte déjà désactivé renvoie un statut 409 Conflit.",
            styles["BodyDark"],
        )
    )

    story.append(Paragraph("C. Passerelle d'Habilitation Projets (<code>apps/projets/services/overrides.py</code>)", styles["SectionH2"]))
    story.append(
        Paragraph(
            "La vue <code>ProjetPermissionsRolesView</code> traduit automatiquement le tableau <code>acces</code> :<br/>"
            "• <code>['lecture']</code> &rarr; <code>niveau = 1</code><br/>"
            "• <code>['lecture', 'saisie']</code> &rarr; <code>niveau = 2</code><br/>"
            "• <code>['lecture', 'saisie', 'validation']</code> &rarr; <code>niveau = 3</code><br/>"
            "• <code>[]</code> &rarr; <code>niveau = 0</code> (accès révoqué pour ce projet).",
            styles["BodyDark"],
        )
    )

    story.append(PageBreak())

    # --- FONDATIONS NEUROCOGNITIVES & SUBCONSCIENT ---
    story.append(Paragraph("4. Mentorat Cognitif & Reprogrammation Subconsciente", styles["SectionH1"]))

    story.append(
        Paragraph(
            "<b>Les 4 Piliers de Stanislas Dehaene appliqués à l'Intégration d'API :</b><br/>"
            "<b>1. L'Attention Sélective :</b> Ne pas se laisser distraire par la complexité globale du frontend. "
            "Isoler chirurgicalement les adaptateurs réseau (<code>features/roles/regles.ts</code>, <code>features/invitations/adaptateur.ts</code>) "
            "pour identifier le prédicat exact de filtrage.<br/>"
            "<b>2. L'Engagement Actif :</b> Formuler une hypothèse claire : <i>'Si j'injecte les codes minuscules dans le serializer, le frontend cochera les cases automatiquement.'</i><br/>"
            "<b>3. Le Signal d'Erreur Bayésien :</b> Les tests rouges pytest ne sont pas des punitions, mais des données précieuses qui actualisent notre modèle mental de l'architecture.<br/>"
            "<b>4. La Consolidation :</b> Répéter ces schémas d'alignement pour qu'ils deviennent des réflexes subconscients automatisés.",
            styles["CalloutCognitive"],
        )
    )

    story.append(
        Paragraph(
            "<b>La Loi de l'Effort Inversé du Dr. Joseph Murphy :</b><br/>"
            "Lorsque vous êtes confronté à un bogue d'intégration récalcitrant entre React et Django, forcer mentalement "
            "engendre du stress et bloque l'intuition. Déposez mentalement le problème : visualisez clairement le tableau de "
            "bord de l'entreprise où tous les rôles, permissions et collaborateurs s'affichent avec fluidité et élégance. "
            "En laissant votre subconscient organiser la solution pendant vos pauses, la structure optimale du code émerge avec clarté.",
            styles["BodyDark"],
        )
    )

    # --- GUIDE PRATIQUE & EXERCICES ---
    story.append(Paragraph("5. Protocole de Vérification & Commandes Essentielles", styles["SectionH1"]))

    story.append(
        Paragraph(
            "Pour vérifier en tout temps la solidité des contrats d'interface Entreprise en local :",
            styles["BodyDark"],
        )
    )

    cmd_box = (
        "# 1. Exécuter la suite dédiée d'alignement Entreprise-Frontend\n"
        "pytest apps/accounts/tests/test_alignement_entreprise_frontend.py -v\n\n"
        "# 2. Exécuter la suite complète des paramètres rôles et collaborateurs\n"
        "pytest apps/accounts/tests/test_parametres_collaborateurs.py apps/accounts/tests/test_parametres_roles.py -v\n\n"
        "# 3. Vérifier le catalogue des modules applicatifs\n"
        "pytest apps/referentiels/tests/test_api_modules.py -v"
    )
    story.append(Preformatted(cmd_box, styles["CodeBox"]))

    story.append(Paragraph("Checklist Pre-Mortem pour les Prochains Développements :", styles["SectionH2"]))
    story.append(
        Paragraph(
            "[ ] Toujours inspecter le type TypeScript de retour et la fonction d'adaptation côté Next.js avant d'écrire un serializer DRF.<br/>"
            "[ ] Prévoir l'idempotence des actions de mutation (409 sur état identique, 400 sur auto-mutation interdite).<br/>"
            "[ ] Ne jamais modifier un fichier frontend avec des outils automatisés — respecter la souveraineté du développeur.<br/>"
            "[ ] Vérifier systématiquement que les champs temporels (<code>derniere_connexion</code>, <code>cree_le</code>) sont bien sérialisés au format ISO-8601.",
            styles["BodyDark"],
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Manuel d'apprentissage généré avec succès : {filename}")


if __name__ == "__main__":
    build_pdf()
