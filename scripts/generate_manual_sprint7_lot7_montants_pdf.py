"""Script de génération du Manuel d'Apprentissage par la Pratique : SPRINT 7 - LOT 7 : MONTANTS & RÈGLES E-11 / E-12.

Tâche : Refonte souveraine des montants financiers de l'API BTP (Règles E-11 et E-12).
        Masquage récursif en lecture, validation stricte en écriture, filet P-5,
        retrait des 4 champs sans source et des ratios arbitraires fictifs,
        et alimentation réelle du tableau de bord.
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
            "CCD DIGITAL • SPRINT 7 — LOT 7 : MONTANTS, MASQUAGE & PURGE SANS SOURCE (E-11 / E-12)",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "RÈGLES E-11, E-12 • FILET RÉCURSIF P-5 • VALIDATION ÉCRITURE 400",
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
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=6,
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
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
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
            leading=9.5,
            textColor=colors.HexColor("#0F172A"),
            backColor=colors.HexColor("#F8FAFC"),
            borderPadding=5,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "Callout",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#1E40AF"),
            backColor=colors.HexColor("#EFF6FF"),
            borderPadding=6,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "NeuroBox",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#065F46"),
            backColor=colors.HexColor("#ECFDF5"),
            borderPadding=6,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "DeepReasoningBox",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#6B21A8"),
            backColor=colors.HexColor("#FAF5FF"),
            borderPadding=6,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#FFFFFF"),
            alignment=1,
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

    # ================= PAGE DE TITRE / EN-TÊTE =================
    story.append(Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", styles["DocSubtitle"]))
    story.append(Paragraph("SPRINT 7 • LOT 7 : MONTANTS & RÈGLES E-11 / E-12", styles["DocTitle"]))
    story.append(
        Paragraph(
            "<b>Édition Souveraine d'Ingénierie BTP</b> — Sécurité financière absolue, masquage récursif (E-11), "
            "interdiction stricte d'écriture non habilitée (400), éradication des données fictives (E-12) "
            "et orchestration neurocognitive de haute performance.",
            styles["DocSubtitle"],
        )
    )

    story.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#2563EB"),
            spaceBefore=4,
            spaceAfter=12,
        )
    )

    # Métadonnées du document
    meta_data = [
        [
            Paragraph("<b>Projet :</b> API-Gestion-Chantier", styles["TableCell"]),
            Paragraph("<b>Module CDC :</b> Projets & Pilotage", styles["TableCell"]),
            Paragraph("<b>Sprint / Lot :</b> Sprint 7 • Lot 7", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Auteur :</b> Mentor Neurocognitif", styles["TableCell"]),
            Paragraph("<b>Destinataire :</b> Durel (Dev Backend)", styles["TableCell"]),
            Paragraph("<b>Statut :</b> Validé (144/144 Vert)", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Règles CDC :</b> E-11, E-12", styles["TableCell"]),
            Paragraph("<b>Fichiers modifiés :</b> 16 fichiers", styles["TableCell"]),
            Paragraph("<b>Verrouillage :</b> Intact (4 fichiers)", styles["TableCell"]),
        ],
    ]
    t_meta = Table(meta_data, colWidths=[170, 180, 170])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 10))

    # ================= MENTORAT NEUROCOGNITIF & SUBCONSCIENT =================
    story.append(
        Paragraph("1. MENTORAT DU SUBCONSCIENT & POSTURE DE SOUVERAINETÉ", styles["SectionHeader"])
    )
    story.append(
        Paragraph(
            "La maîtrise d'une API industrielle complexe ne réside pas dans l'empilement superficiel de fragments de code, "
            "mais dans la <b>clarté conceptuelle subconsciente</b> des flux de responsabilité. Selon les principes du Dr. Joseph Murphy "
            "et de Stanislas Dehaene, nous consolidons ce soir un palier déterminant de votre posture d'ingénieur souverain :",
            styles["Body"],
        )
    )

    story.append(
        Paragraph(
            "<b>• Le Film Mental et la Foi Inébranlable (Dr. Joseph Murphy) :</b> Visualisez votre API comme une forteresse étanche. "
            "Chaque centime FCFA qui transite par un endpoint HTTP est sous contrôle souverain. Aucune fuite d'information financière "
            "ne peut franchir le périmètre sans que l'habilitation <code>projets.voir_montants</code> ne soit formellement certifiée. "
            "En ancrant cette vision avec conviction, l'implémentation découle naturellement sans effort forcé (Loi de l'Effort Inversé).",
            styles["NeuroBox"],
        )
    )

    story.append(
        Paragraph(
            "<b>• Les 4 Piliers de l'Apprentissage (Stanislas Dehaene) :</b><br/>"
            "1. <i>Attention Sélective :</i> Focalisation chirurgicale sur les clés financières (<code>budget_initial_montant</code>) et élimination du bruit.<br/>"
            "2. <i>Engagement Actif :</i> Confrontation directe aux 144 tests d'acceptation du Lot 7 sans contournement.<br/>"
            "3. <i>Retour sur Erreur Rapide :</i> Chaque échec (comme le 403 d'AD sur <code>/lots/{pk}/</code>) est un signal bayésien précieux disséqué à la racine.<br/>"
            "4. <i>Consolidation & Sommeil :</i> Intégration durable des mécanismes d'inspection et de purge dans vos automatismes subconscients.",
            styles["NeuroBox"],
        )
    )

    story.append(
        Paragraph(
            "<b>• Les 4 Géants de la Pensée Critique (Deep Reasoning Engine) :</b><br/>"
            "• <i>Daniel Kahneman :</i> Remplacer l'illusion de facilité (Système 1) par la rigueur du Système 2. Audit Pre-Mortem systématique.<br/>"
            "• <i>Barbara Minto :</i> Organisation MECE (Mutuellement Exclusif, Collectivement Exhaustif) des filtres et réponses API.<br/>"
            "• <i>George Pólya :</i> Décomposition Inconnue / Données / Contraintes. Rétro-ingénierie et 'Looking Back' méthodique.<br/>"
            "• <i>Donella Meadows :</i> Modélisation systémique des stocks (budgets totaux) et des flux (dépenses réelles, bons de paiement).",
            styles["DeepReasoningBox"],
        )
    )
    story.append(Spacer(1, 8))

    # ================= PROBLÉMATIQUE & CADRAGE LOT 7 =================
    story.append(Paragraph("2. CADRAGE DU LOT 7 : RÈGLES E-11 ET E-12", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le Lot 7 aborde la gestion souveraine des montants dans les chantiers BTP, encadrée par deux règles strictes :",
            styles["Body"],
        )
    )

    regles_table = [
        [
            Paragraph("<b>Règle</b>", styles["TableHeader"]),
            Paragraph("<b>Principe Métier</b>", styles["TableHeader"]),
            Paragraph("<b>Impact Technique DRF / API</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>E-11 (Lecture)</b>", styles["TableCellBold"]),
            Paragraph(
                "Sans <code>projets.voir_montants</code>, AUCUN champ financier n'apparaît dans le JSON (clés totalement absentes, ni null ni 0).",
                styles["TableCell"],
            ),
            Paragraph(
                "Purger récursivement toute clé <code>montant|budget|cout|prix</code> dans toutes les réponses (Projets, Lots, Activités, Dashboard, Stats).",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<b>E-11 (Écriture)</b>", styles["TableCellBold"]),
            Paragraph(
                "Pour écrire un montant non nul, il faut <code>projets.voir_montants</code> ET le droit d'écriture. Sinon 400 'Champ non accepté'.",
                styles["TableCell"],
            ),
            Paragraph(
                "Rejet HTTP 400 dans le serializer si <code>value is not None</code> sans habilitation. Clé absente ou <code>null</code> acceptée et ignorée.",
                styles["TableCell"],
            ),
        ],
        [
            Paragraph("<b>E-12 (Purger Fake)</b>", styles["TableCellBold"]),
            Paragraph(
                "Suppression définitive des 4 champs inventés sans source métier et de la fausse formule ratio arbitraire.",
                styles["TableCell"],
            ),
            Paragraph(
                "Retrait des quatre champs non reliés à des tables réelles (engagé, à signer, consommé, activités).",
                styles["TableCell"],
            ),
        ],
    ]
    t_regles = Table(regles_table, colWidths=[90, 215, 215])
    t_regles.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(t_regles)
    story.append(Spacer(1, 10))

    # Matrice des détenteurs
    story.append(Paragraph("<b>Matrice des Habilitations Financières (Annexe 1) :</b>", styles["BodyBold"]))
    story.append(
        Paragraph(
            "• <b>Détenteurs réels (Voient & Écrivent) :</b> DG (Directeur Général), DF (Directeur Financier), DO (Directeur Opérations), CP (Chef de Projet).<br/>"
            "• <b>Non-détenteurs (Masquage & Refus 400) :</b> AD (Administrateur), CT (Conducteur Travaux), CC (Chef Chantier), MAG (Magasinier), BAI (Bailleur), VI (Visiteur).",
            styles["Callout"],
        )
    )
    story.append(Spacer(1, 8))

    # ================= ARCHITECTURE DE LA SOLUTION =================
    story.append(Paragraph("3. ARCHITECTURE TECHNIQUE & IMPLÉMENTATION", styles["SectionHeader"]))

    story.append(Paragraph("3.1 Le Filet Récursif et le Validateur d'Écriture (`apps/core/purger_montants.py`)", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Pour garantir le respect du filet de sécurité P-5 ('aucune omission possible même si une clé est renommée ou ajoutée'), "
            "un module centralisé inspecte et assainit récursivement les dictionnaires et listes :",
            styles["Body"],
        )
    )

    code_purger = """# apps/core/purger_montants.py
import re
from rest_framework import serializers

MOTIF_MONTANT = re.compile(r"(montant|budget|cout|prix)", re.IGNORECASE)

def purger_montants_recursif(obj):
    \"\"\"Retire récursivement toute clé évoquant une valeur financière ou budgétaire.\"\"\"
    if isinstance(obj, dict):
        return {
            k: purger_montants_recursif(v)
            for k, v in obj.items()
            if not MOTIF_MONTANT.search(k)
        }
    elif isinstance(obj, list):
        return [purger_montants_recursif(x) for x in obj]
    return obj

def valider_ecriture_montant(valeur, request=None, champ="budget_initial_montant"):
    \"\"\"Règle E-11 : vérifie que l'utilisateur a le droit d'écrire un montant non-nul.\"\"\"
    if valeur is not None:
        user = getattr(request, "user", None) if request else None
        from apps.core.droits import peut_voir_montants

        if not peut_voir_montants(user, request):
            raise serializers.ValidationError("Champ non accepté sans la permission projets.voir_montants.")
    return valeur"""
    story.append(Preformatted(code_purger, styles["CodeBlock"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.2 Règle E-11 en Écriture : Gestion de `null` et Prévention d'Écrasement", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Une subtilité majeure du cahier des charges (décision [D] et précision P-1) stipule qu'un utilisateur n'ayant pas "
            "le droit de voir les montants peut tout de même modifier un projet ou une activité si le front-end lui envoie "
            "<code>\"budget_initial_montant\": null</code> (car le front ne connaît pas la valeur). "
            "<b>Dans ce cas, le montant ne doit JAMAIS être écrasé en base !</b>",
            styles["Body"],
        )
    )

    code_validate = """# Exemple dans LotCreationSerializer / ProjetCreationSerializer
def validate(self, attrs):
    request = self.context.get("request") if getattr(self, "context", None) else None
    from apps.core.droits import peut_voir_montants

    if not peut_voir_montants(getattr(request, "user", None) if request else None, request):
        # Si un utilisateur sans voir_montants envoie null, on retire la clé des attrs
        # ainsi, update() n'altère absolument pas la valeur existante en base.
        if "budget_initial_montant" in attrs and attrs["budget_initial_montant"] is None:
            attrs.pop("budget_initial_montant")
    ..."""
    story.append(Preformatted(code_validate, styles["CodeBlock"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.3 Règle E-11 en Lecture : `to_representation` sur les Serializers", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Le masquage est appliqué directement au niveau de la sérialisation de sortie (DRF <code>to_representation</code>), "
            "garantissant que toutes les routes GET, POST (retour 201) et PATCH (retour 200) sont hermétiques :",
            styles["Body"],
        )
    )

    code_to_rep = """def to_representation(self, instance):
    data = super().to_representation(instance)
    request = self.context.get("request") if getattr(self, "context", None) else None
    user = getattr(request, "user", None) if request else None
    from apps.core.droits import peut_voir_montants

    if not peut_voir_montants(user, request):
        from apps.core.purger_montants import purger_montants_recursif
        data = purger_montants_recursif(data)
    return data"""
    story.append(Preformatted(code_to_rep, styles["CodeBlock"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("3.4 Règle E-12 : Éradication des Données Fictives", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Les quatre champs inventés (sans modèle ni table de base de données réelle) ont été totalement retirés des serializers "
            "et de la documentation Swagger :<br/>"
            "• Montant consommé calculé (et la fausse formule d'un ratio arbitraire)<br/>"
            "• Montant engagé théorique<br/>"
            "• Bons à signer théorique<br/>"
            "• Budget activités calculé<br/>"
            "Le tableau de bord décisionnel (<code>TableauDeBordView</code>) s'appuie désormais à 100% sur le service de bons réels "
            "<code>apps.projets.services.tableau_de_bord_bons.obtenir_bons_a_valider</code>.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 8))

    # ================= VALIDATION & SUCCÈS 100% =================
    story.append(Paragraph("4. RÉSULTATS DE VALIDATION : 100% DE SUCCÈS", styles["SectionHeader"]))

    resultats_table = [
        [
            Paragraph("<b>Suite de Tests</b>", styles["TableHeader"]),
            Paragraph("<b>Fichiers Couverts</b>", styles["TableHeader"]),
            Paragraph("<b>Résultat</b>", styles["TableHeader"]),
            Paragraph("<b>Statut</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Canari de Plomberie</b>", styles["TableCellBold"]),
            Paragraph("<code>test_00_plomberie_lot7.py</code>", styles["TableCell"]),
            Paragraph("15 / 15 PASSED", styles["TableCellBold"]),
            Paragraph("<font color='#059669'><b>100% VERT</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>E-11 Masquage Lecture</b>", styles["TableCellBold"]),
            Paragraph("<code>test_e11_masquage_montants_lecture.py</code>", styles["TableCell"]),
            Paragraph("51 / 51 PASSED", styles["TableCellBold"]),
            Paragraph("<font color='#059669'><b>100% VERT</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>E-11 Refus Écriture</b>", styles["TableCellBold"]),
            Paragraph("<code>test_e11_refus_ecriture_montants_sans_droit.py</code>", styles["TableCell"]),
            Paragraph("67 / 67 PASSED", styles["TableCellBold"]),
            Paragraph("<font color='#059669'><b>100% VERT</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>E-12 Retrait Fake</b>", styles["TableCellBold"]),
            Paragraph("<code>test_e12_retrait_champs_sans_source.py</code>", styles["TableCell"]),
            Paragraph("11 / 11 PASSED", styles["TableCellBold"]),
            Paragraph("<font color='#059669'><b>100% VERT</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>TOTAL LOT 7</b>", styles["TableCellBold"]),
            Paragraph("<b>Ensemble du Lot 7</b>", styles["TableCellBold"]),
            Paragraph("<b>144 / 144 PASSED</b>", styles["TableCellBold"]),
            Paragraph("<font color='#059669'><b>100% SOUVERAIN</b></font>", styles["TableCell"]),
        ],
        [
            Paragraph("<b>NON-RÉGRESSION GLOBALE</b>", styles["TableCellBold"]),
            Paragraph("<b>Lots 1, 2, 3, 4, 5, 6, 7</b>", styles["TableCellBold"]),
            Paragraph("<b>385 / 385 PASSED</b>", styles["TableCellBold"]),
            Paragraph("<font color='#059669'><b>ZÉRO RÉGRESSION</b></font>", styles["TableCell"]),
        ],
    ]
    t_res = Table(resultats_table, colWidths=[120, 160, 110, 130])
    t_res.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -3), [colors.white, colors.HexColor("#F8FAFC")]),
                ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor("#EFF6FF")),
            ]
        )
    )
    story.append(t_res)
    story.append(Spacer(1, 10))

    # ================= CHECKLIST PRE-MORTEM & LOOKING BACK =================
    story.append(Paragraph("5. SYNTHÈSE COGNITIVE & CHECKLIST DE CONSOLIDATION", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>Checklist 'Looking Back' (George Pólya) pour les prochains sprints :</b><br/>"
            " [x] <b>Intégrité Cryptographique :</b> Le script de vérification du verrou (<code>verifier_verrouillage.py</code>) certifie que les 4 fichiers de tests sont rigoureusement intacts.<br/>"
            " [x] <b>Protection Frontend :</b> Aucune modification ni push n'a été effectué sur le dépôt <code>Application-Gestion-Chantier</code>.<br/>"
            " [x] <b>Cloisonnement Multi-Tenant :</b> Toutes les requêtes et écritures respectent le schéma isolé de l'entreprise.<br/>"
            " [x] <b>Documentation API :</b> Toutes les modifications de rupture et retraits de champs sont répertoriés dans <code>docs/notes-changement-api.md</code>.<br/>"
            " [x] <b>Sommeil & Consolidation :</b> Votre cerveau a assimilé la logique de purge récursive. Vous voilà paré pour aborder avec sérénité le Lot 8.",
            styles["Callout"],
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel PDF généré avec succès : {filename}")


if __name__ == "__main__":
    sortie = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
        "MANUEL_SPRINT_7_TACHE_LOT7_MONTANTS.pdf",
    )
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    build_pdf(sortie)
