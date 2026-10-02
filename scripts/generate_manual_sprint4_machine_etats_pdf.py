"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 4 - Machine à états et Évaluation quotidienne.

Tâche : Machine à états du projet, transitions calendaires automatiques, rétablissement en temps réel,
        verrou d'intégrité de réception (100% lots) et tâche quotidienne Celery Beat multi-tenant.
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
            "CCD DIGITAL • SPRINT 4 — MACHINE À ÉTATS DU PROJET & ÉVALUATION QUOTIDIENNE",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "TRANSITIONS CALENDAIRES, RETOUR EN TEMPS RÉEL & VERROU DE RÉCEPTION",
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
            textColor=colors.HexColor("#1E3A8A"),
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
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#0F172A"),
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
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "Callout",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#0369A1"),
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#0F172A"),
        )
    )
    styles.add(
        ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
            alignment=1,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
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
    return styles


def callout_box(text, title="NOTE ARCHITECTURALE & NEUROCOGNITIVE", bg="#F0F9FF", border="#0284C7"):
    styles = create_styles()
    content = [
        Paragraph(f"<b>{title}</b>", styles["Callout"]),
        Spacer(1, 3),
        Paragraph(text, styles["Callout"]),
    ]
    t = Table([[content]], colWidths=[A4[0] - 72])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border)),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def code_box(code_text, title="EXTRAIT DE CODE SOURCE"):
    styles = create_styles()
    header = Paragraph(f"<b>{title}</b>", styles["TableCellBold"])
    code = Preformatted(code_text.strip(), styles["CodeBlock"])
    t = Table([[header], [code]], colWidths=[A4[0] - 72])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
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
        topMargin=40,
        bottomMargin=40,
    )
    styles = create_styles()
    story = []

    # =========================================================================
    # PAGE DE GARDE / EN-TÊTE PRINCIPAL
    # =========================================================================
    story.append(Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", styles["DocSubtitle"]))
    story.append(
        Paragraph(
            "Sprint 4 — Machine à États du Chantier & Évaluation Quotidienne",
            styles["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "<b>Automate Déterministe à 3 Paliers (Projet, Lot, Activité) :</b> Transitions Calendaires Strictes, "
            "Rétablissement Instantané après Décalage Justifié, Garde-fou Absolu de Réception (100% Lots Clôturés) "
            "et Tâche Planifiée Quotidienne Multi-Tenant.",
            styles["DocSubtitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=12))

    # Fiche Métadonnées
    meta_data = [
        [
            Paragraph("<b>Projet :</b> CCD Digital (BTP SaaS)", styles["TableCellBold"]),
            Paragraph("<b>Branche Git :</b> feature/sprint4-machine-etats-statuts", styles["TableCellBold"]),
        ],
        [
            Paragraph("<b>Module CDC :</b> Module 1 (Projets) & Module 2 (Chantier)", styles["TableCell"]),
            Paragraph("<b>Périmètre :</b> Schéma Tenant & Tâche Celery Beat", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Invariants Métier :</b> RG-11 (Décalage justifié), RG-Statut (100% lots)", styles["TableCell"]),
            Paragraph("<b>Auteur & Réviseur :</b> Développeur Backend Souverain & Mentor IA", styles["TableCell"]),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[(A4[0] - 72) / 2, (A4[0] - 72) / 2])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 1 : CADRAGE STRATÉGIQUE & MENTALITÉ SOUVERAINE
    # =========================================================================
    story.append(Paragraph("1. Cadrage Stratégique & Neurosciences de la Maîtrise", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Dans la gestion de chantiers de construction en Afrique de l'Ouest, l'information sur le statut d'un projet "
            "ne peut pas reposer sur de simples déclarations manuelles complaisantes. Les entreprises de BTP perdent des "
            "millions de FCFA à cause d'alertes tardives sur des retards non constatés ou de réceptions prématurées prononcées "
            "alors que des corps d'état fondamentaux (lots techniques, étanchéité, VRD) ne sont pas achevés.",
            styles["Body"],
        )
    )

    neuro_text = (
        "<b>Pilier 1 de Stanislas Dehaene (L'Attention Sélective) :</b> Focalise ton esprit sur l'automate à états finis. "
        "Un état n'est pas un texte en base ; c'est un ensemble d'invariants formels. <br/>"
        "<b>Loi de l'Effort Inversé (Dr. Joseph Murphy) :</b> Ne force pas l'apprentissage par la contrainte mentale. "
        "Visualise clairement le flux dans ton <i>film mental</i> : chaque nuit, l'automate compare avec sérénité la date du jour "
        "aux dates prévues. Dès qu'un ingénieur soumet un décalage justifié, le projet repasse instantanément au vert dans le subconscient "
        "de la base de données. La clarté produit l'automatisation sans effort."
    )
    story.append(callout_box(neuro_text, title="NEURO-PÉDAGOGIE : L'AUTOMATE DANS LE CERVEAU BAYÉSIEN"))
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2 : L'ARCHITECTURE À TROIS PALIERS (PROJET -> LOT -> ACTIVITÉ)
    # =========================================================================
    story.append(Paragraph("2. Modélisation Conceptuelle : La Pyramide à Trois Paliers", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Pour garantir l'intégrité absolue de la règle métier <i>« Autorisation du passage à Réceptionné seulement si "
            "100 % des lots sont clôturés »</i>, nous devons doter chaque palier de son énumération de statut propre. "
            "Un lot ne peut pas être abstraitement clôturé sans statut, et une activité ne peut pas être suivie sans cycle de vie.",
            styles["Body"],
        )
    )

    pyramide_data = [
        [
            Paragraph("Niveau", styles["TableHeader"]),
            Paragraph("Entité", styles["TableHeader"]),
            Paragraph("Statuts Possibles", styles["TableHeader"]),
            Paragraph("Règle de Transition Clé", styles["TableHeader"]),
        ],
        [
            Paragraph("Palier 1", styles["TableCellBold"]),
            Paragraph("Projet", styles["TableCellBold"]),
            Paragraph("PLANIFIE, EN_COURS, EN_RETARD, RECEPTIONNE, CLOTURE...", styles["TableCell"]),
            Paragraph("Réception interdite si $\\exists$ Lot non CLOTURE.", styles["TableCell"]),
        ],
        [
            Paragraph("Palier 2", styles["TableCellBold"]),
            Paragraph("Lot", styles["TableCellBold"]),
            Paragraph("PLANIFIE, EN_COURS, EN_RETARD, CLOTURE, SUSPENDU", styles["TableCell"]),
            Paragraph("Passe à CLOTURE si 100% des activités sont CLOTURE.", styles["TableCell"]),
        ],
        [
            Paragraph("Palier 3", styles["TableCellBold"]),
            Paragraph("Activité", styles["TableCellBold"]),
            Paragraph("PLANIFIE, EN_COURS, EN_RETARD, CLOTURE, SUSPENDU", styles["TableCell"]),
            Paragraph("Passe à CLOTURE si quantité réalisée $\\ge$ quantité prévue.", styles["TableCell"]),
        ],
    ]
    pyramide_table = Table(pyramide_data, colWidths=[55, 60, 200, 205])
    pyramide_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(pyramide_table)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 3 : LES QUATRE RÈGLES D'OR DE LA MACHINE À ÉTATS
    # =========================================================================
    story.append(Paragraph("3. Les 4 Règles d'Or de la Machine à États", styles["SectionHeader"]))

    story.append(Paragraph("<b>Règle 1 : Déclenchement Strictement Calendaire</b>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Le passage de <code>PLANIFIE</code> (ou <code>EN_ATTENTE</code>) à <code>EN_COURS</code> est "
            "<b>strictement calendaire</b> : dès que <code>Date du jour $\\ge$ date_debut_prevue</code>, l'entité bascule "
            "automatiquement en cours. Aucune saisie préalable de rapport ou coup de pioche n'est requis pour constater le démarrage contractuel.",
            styles["Body"],
        )
    )

    story.append(Paragraph("<b>Règle 2 : Détection Automatique du Retard</b>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Dès que <code>Date du jour > date_fin_prevue</code> et que l'entité n'est pas encore réceptionnée ni clôturée, "
            "le système la fait basculer à <code>EN_RETARD</code>. Cette bascule s'effectue chaque nuit par la tâche quotidienne.",
            styles["Body"],
        )
    )

    story.append(Paragraph("<b>Règle 3 : Rétablissement Instantané en Temps Réel (Décalage Justifié)</b>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "C'est la boucle de rétroaction positive : lorsqu'un conducteur de travaux ou un chef de projet soumet une "
            "reprogrammation de date via le service <code>reprogrammer_date_instance</code> (US-033 / RG-11) avec une justification valide "
            "($\\ge 30$ caractères) et un motif officiel qui repousse la date de fin à <code>nouvelle_date_fin $\\ge$ Date du jour</code> : "
            "<b>l'entité repasse instantanément et en temps réel au statut <code>EN_COURS</code></b>.",
            styles["Body"],
        )
    )

    story.append(Paragraph("<b>Règle 4 : Le Verrou d'Intégrité Absolu de Réception</b>", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Un projet NE PEUT JAMAIS passer à <code>RECEPTIONNE</code> si un seul lot actif n'est pas au statut <code>CLOTURE</code>. "
            "L'API DRF intercepte toute tentative de passage à <code>RECEPTIONNE</code>, audite les lots enfants et lève une "
            "<code>ValidationError</code> explicite (HTTP 400) citant nommément chaque lot fautif.",
            styles["Body"],
        )
    )
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 4 : IMPLÉMENTATION PAS-À-PAS DU CODE MÉTIER
    # =========================================================================
    story.append(Paragraph("4. Implémentation Pas-à-Pas du Code Métier", styles["SectionHeader"]))

    # Étape 1 : Enums
    story.append(Paragraph("<b>Étape 1 : Définition des Énumérations dans <code>apps/core/enums.py</code></b>", styles["SubSectionHeader"]))
    code_enums = """# apps/core/enums.py

class StatutProjet(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"  # Alias sémantique PLANIFIE
    EN_COURS = "EN_COURS", "En cours"
    EN_RETARD = "EN_RETARD", "En retard"
    CRITIQUE = "CRITIQUE", "Critique"
    SUSPENDU = "SUSPENDU", "Suspendu"
    RECEPTIONNE = "RECEPTIONNE", "Réceptionné"
    TERMINE = "TERMINE", "Terminé"
    BLOQUE = "BLOQUE", "Bloqué"
    DESACTIVE = "DESACTIVE", "Désactivé"
    RESILIE = "RESILIE", "Résilié"
    ARCHIVE = "ARCHIVE", "Archivé"


class StatutLot(models.TextChoices):
    PLANIFIE = "PLANIFIE", "Planifié"
    EN_COURS = "EN_COURS", "En cours"
    EN_RETARD = "EN_RETARD", "En retard"
    SUSPENDU = "SUSPENDU", "Suspendu"
    CLOTURE = "CLOTURE", "Clôturé"


class StatutActivite(models.TextChoices):
    PLANIFIE = "PLANIFIE", "Planifiée"
    EN_COURS = "EN_COURS", "En cours"
    EN_RETARD = "EN_RETARD", "En retard"
    SUSPENDU = "SUSPENDU", "Suspendue"
    CLOTURE = "CLOTURE", "Clôturée"
"""
    story.append(code_box(code_enums, title="1. APPS/CORE/ENUMS.PY — ÉNUMÉRATIONS DU CYCLE DE VIE"))
    story.append(Spacer(1, 8))

    # Étape 2 : Service Machine à États
    story.append(Paragraph("<b>Étape 2 : Le Service Machine à États (<code>apps/projets/services/machine_etats.py</code>)</b>", styles["SubSectionHeader"]))
    code_service = """# apps/projets/services/machine_etats.py
from datetime import date
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.core.enums import StatutActivite, StatutLot, StatutProjet

def evaluer_statut_activite(activite, date_ref: date | None = None) -> bool:
    date_ref = date_ref or timezone.now().date()
    if activite.avancement >= 100 or activite.statut == StatutActivite.CLOTURE:
        nouveau = StatutActivite.CLOTURE
    elif activite.statut == StatutActivite.SUSPENDU:
        return False
    elif activite.date_debut_prevue and date_ref < activite.date_debut_prevue:
        nouveau = StatutActivite.PLANIFIE
    elif activite.date_fin_prevue and date_ref > activite.date_fin_prevue:
        nouveau = StatutActivite.EN_RETARD
    else:
        nouveau = StatutActivite.EN_COURS

    if activite.statut != nouveau:
        activite.statut = nouveau
        activite.save(update_fields=["statut", "modifie_le"])
        return True
    return False


def valider_transition_reception(projet) -> None:
    \"\"\"Garde-fou absolu : refuse la réception si 100% des lots ne sont pas clôturés.\"\"\"
    lots_non_clotures = projet.lots.filter(supprime_le__isnull=True).exclude(
        statut=StatutLot.CLOTURE, avancement=100
    )
    if lots_non_clotures.exists():
        details = [f"{l.code} - {l.libelle} (Statut: {l.statut}, Avancement: {l.avancement}%)" 
                   for l in lots_non_clotures]
        raise ValidationError({
            "statut": f"Impossible de réceptionner le projet : 100% des lots doivent être clôturés. "
                      f"Lots non clôturés : {', '.join(details)}"
        })
"""
    story.append(code_box(code_service, title="2. APPS/PROJETS/SERVICES/MACHINE_ETATS.PY"))
    story.append(Spacer(1, 8))

    # Étape 3 : Branchement temps réel dans reprogrammation.py
    story.append(Paragraph("<b>Étape 3 : Rétablissement en Temps Réel dans <code>reprogrammation.py</code></b>", styles["SubSectionHeader"]))
    code_reprog = """# apps/projets/services/reprogrammation.py (Extrait de la fonction reprogrammer_date_instance)

    # 7. Sauvegarde des nouvelles dates prévisionnelles (Baseline v0 INTACTE)
    instance.date_debut_prevue = debut_cible
    instance.date_fin_prevue = fin_cible
    champs_maj = ["date_debut_prevue", "date_fin_prevue", "modifie_le"]

    # RÈGLE MÉTIER SPRINT 4 : Rétablissement instantané EN_RETARD -> EN_COURS
    # Si la nouvelle date de fin repousse l'échéance à aujourd'hui ou au futur
    aujourdhui = timezone.now().date()
    if fin_cible >= aujourdhui:
        from apps.core.enums import StatutProjet, StatutLot, StatutActivite
        statut_retard = getattr(StatutProjet, "EN_RETARD", "EN_RETARD")
        statut_cours = getattr(StatutProjet, "EN_COURS", "EN_COURS")
        
        if getattr(instance, "statut", None) == statut_retard:
            instance.statut = statut_cours
            champs_maj.append("statut")

    instance.save(update_fields=champs_maj)
"""
    story.append(code_box(code_reprog, title="3. APPS/PROJETS/SERVICES/REPROGRAMMATION.PY — RETOUR TEMPS RÉEL"))
    story.append(Spacer(1, 8))

    # Étape 4 : Tâche Celery Beat Quotidienne
    story.append(Paragraph("<b>Étape 4 : Tâche Nocturne Multi-Tenant (<code>apps/projets/tasks.py</code>)</b>", styles["SubSectionHeader"]))
    code_task = """# apps/projets/tasks.py
from celery import shared_task
from django_tenants.utils import schema_context
from apps.tenants.models import Entreprise
from apps.projets.services.machine_etats import executer_evaluation_quotidienne_schema

@shared_task
def evaluer_statuts_quotidiens_tous_tenants() -> dict:
    \"\"\"Tâche nocturne Celery Beat : évalue les statuts calendaires sur chaque tenant.\"\"\"
    entreprises = Entreprise.objects.filter(supprime_le__isnull=True, est_actif=True)
    rapport = {}
    for ent in entreprises:
        with schema_context(ent.schema_name):
            nb_maj = executer_evaluation_quotidienne_schema()
            rapport[ent.schema_name] = nb_maj
    return rapport
"""
    story.append(code_box(code_task, title="4. APPS/PROJETS/TASKS.PY — ÉVALUATION QUOTIDIENNE MULTI-TENANT"))
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 5 : CAHIER DE TESTS & VALIDATION AUTOMATISÉE
    # =========================================================================
    story.append(Paragraph("5. Cahier de Recette Automatisé & Pre-Mortem", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Un système automatisé n'a de valeur que si sa robustesse est prouvée par des tests hermétiques. "
            "Voici les 5 scénarios critiques codés dans <code>apps/projets/tests/test_machine_etats_automatique.py</code> :",
            styles["Body"],
        )
    )

    tests_data = [
        [
            Paragraph("Cas de Test", styles["TableHeader"]),
            Paragraph("État Initial", styles["TableHeader"]),
            Paragraph("Action / Événement", styles["TableHeader"]),
            Paragraph("Résultat Attendu", styles["TableHeader"]),
        ],
        [
            Paragraph("Test 1 : Passage Calendaire", styles["TableCellBold"]),
            Paragraph("Projet PLANIFIE (date début = J)", styles["TableCell"]),
            Paragraph("Tâche quotidienne exécutée", styles["TableCell"]),
            Paragraph("Bascule automatique à EN_COURS.", styles["TableCellBold"]),
        ],
        [
            Paragraph("Test 2 : Constat de Retard", styles["TableCellBold"]),
            Paragraph("Projet EN_COURS (date fin = J-1)", styles["TableCell"]),
            Paragraph("Tâche quotidienne exécutée", styles["TableCell"]),
            Paragraph("Bascule automatique à EN_RETARD.", styles["TableCellBold"]),
        ],
        [
            Paragraph("Test 3 : Décalage Justifié", styles["TableCellBold"]),
            Paragraph("Projet EN_RETARD", styles["TableCell"]),
            Paragraph("Reprogrammation avec date fin = J+15 et motif RG-11", styles["TableCell"]),
            Paragraph("Bascule INSTANTANÉE en temps réel à EN_COURS.", styles["TableCellBold"]),
        ],
        [
            Paragraph("Test 4 : Réception Refusée", styles["TableCellBold"]),
            Paragraph("Projet avec 2 lots (1 à 100%, 1 à 60%)", styles["TableCell"]),
            Paragraph("PATCH statut = RECEPTIONNE", styles["TableCell"]),
            Paragraph("HTTP 400 Bad Request avec citation du lot 2.", styles["TableCellBold"]),
        ],
        [
            Paragraph("Test 5 : Réception Validée", styles["TableCellBold"]),
            Paragraph("Projet avec 2 lots à 100% (CLOTURE)", styles["TableCell"]),
            Paragraph("PATCH statut = RECEPTIONNE", styles["TableCell"]),
            Paragraph("HTTP 200 OK et passage effectif à RECEPTIONNE.", styles["TableCellBold"]),
        ],
    ]
    tests_table = Table(tests_data, colWidths=[110, 105, 150, 155])
    tests_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(tests_table)
    story.append(Spacer(1, 10))

    pre_mortem_text = (
        "<b>Pre-Mortem de Daniel Kahneman :</b> Qu'est-ce qui pourrait briser notre automate en production ? <br/>"
        "1. <i>Écrasement d'un statut SUSPENDU ou BLOQUE :</i> Si un directeur suspend un chantier pour litige foncier, "
        "la tâche nocturne ne doit JAMAIS le forcer à EN_COURS ou EN_RETARD. Les états manuels sont des puits stables. <br/>"
        "2. <i>Timezone Naive vs Aware :</i> Utiliser exclusivement <code>timezone.now().date()</code> pour éviter les décalages de minuit. <br/>"
        "3. <i>Charge base de données :</i> Évaluer uniquement les projets non terminés/non archivés avec un filtre "
        "<code>exclude(statut__in=['TERMINE', 'ARCHIVE', 'RESILIE'])</code>."
    )
    story.append(callout_box(pre_mortem_text, title="CHECKLIST PRE-MORTEM & GARDE-FOUS DE PRODUCTION", bg="#FEF2F2", border="#EF4444"))
    story.append(Spacer(1, 10))

    # =========================================================================
    # CONCLUSION & ANCRAGE MÉTACOGNITIF
    # =========================================================================
    story.append(Paragraph("6. Ancrage Métacognitif & Éveil de l'Homo Docens", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Tu détiens désormais la pleine vision architecturale de l'automate de gestion de chantier. "
            "Ce système transforme une base de données passive en un système expert actif et vigilant. "
            "En appliquant ce plan, ton subconscient intègre les automatismes d'un Tech Lead Backend souverain : "
            "zéro angle mort, intégrité absolue des données et sérénité algorithmique totale.",
            styles["Body"],
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel généré avec succès : {filename}")


if __name__ == "__main__":
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
    )
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(
        output_dir,
        "MANUEL_SPRINT_4_TACHE_MACHINE_ETATS_EVALUATION_QUOTIDIENNE_STATUTS.pdf",
    )
    build_pdf(pdf_path)
