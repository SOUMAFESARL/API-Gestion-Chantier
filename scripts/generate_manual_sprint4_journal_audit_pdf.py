"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 4 - Journal d'Audit des Reports.

Tâche : Journal d'audit des reports : enregistrement immuable (auteur, ancienne et nouvelle date, motif, écart en jours) et lecture de l'historique
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
            "CCD DIGITAL • SPRINT 4 — JOURNAL D'AUDIT DES REPORTS DE DATES (RG-07 & RG-11)",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "ENREGISTREMENT IMMUABLE, ÉCART EN JOURS & LECTURE CONSOLIDÉE",
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
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
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
            fontSize=10,
            leading=13.5,
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
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#1E293B"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyBold",
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
            "Callout",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#0369A1"),
        )
    )
    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7,
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
            leading=10.5,
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
            leading=10.5,
            textColor=colors.HexColor("#1E293B"),
        )
    )
    styles.add(
        ParagraphStyle(
            "TableCellBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10.5,
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
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def code_box(code_text, bg="#F8FAFC", border="#CBD5E1"):
    styles = create_styles()
    p = Preformatted(code_text, styles["CodeBlock"])
    t = Table([[p]], colWidths=[A4[0] - 72])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(border)),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def generate_pdf(output_path):
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
    # EN-TÊTE / BANDEAU DE COUVERTURE
    # =========================================================================
    badge_data = [
        [
            Paragraph("<b>CCD DIGITAL</b> — SYSTÈME DE GESTION DE CHANTIER BTP", styles["TableCellBold"]),
            Paragraph("SPRINT 4 • MODULE 1 (PROJETS)", styles["TableCellBold"]),
            Paragraph("RÈGLES RG-07 & RG-11", styles["TableCellBold"]),
        ]
    ]
    badge_table = Table(badge_data, colWidths=[240, 160, 122])
    badge_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("PADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    story.append(badge_table)
    story.append(Spacer(1, 10))

    story.append(
        Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", styles["DocTitle"])
    )
    story.append(
        Paragraph(
            "<b>Journal d'Audit des Reports : Enregistrement Immuable (Auteur, Dates, Motif, Écart en Jours) & Lecture Consolidée</b><br/>"
            "Architecture Append-Only, Verrous PostgreSQL Physiques, Invariants Mathématiques et Moteur de Recherche Multi-Niveaux.",
            styles["DocSubtitle"],
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

    # =========================================================================
    # SECTION 1 : FILM MENTAL & OBJECTIF SACRÉ
    # =========================================================================
    story.append(Paragraph("1. Film Mental & Objectif Sacré (Programmation Subconsciente)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Dans la théorie de la reprogrammation mentale du <b>Dr. Joseph Murphy</b>, la réussite technique découle "
            "de la clarté absolue avec laquelle l'esprit visualise le résultat final accompli. Imaginez la scène : "
            "un grand chantier de génie civil à Abidjan subit deux semaines d'intempéries torrentielles. Le Chef de Projet "
            "reprogramme les dates de coulage des fondations. Instantanément, le système consigne cet événement avec "
            "une précision chirurgicale : l'identité de l'auteur, les dates exacte avant/après, le motif officiel "
            "« Intempéries », la justification détaillée, et l'écart précis de +14 jours.",
            styles["Body"],
        )
    )
    story.append(
        Paragraph(
            "Quelques semaines plus tard, un litige contractuel surgit entre le client et l'entreprise. Un utilisateur malveillant "
            "tente de modifier la justification du report ou d'effacer la trace de ce glissement. "
            "<b>La base de données PostgreSQL refuse catégoriquement l'opération (RG-07)</b> : un trigger immuable bloque "
            "toute instruction SQL UPDATE ou DELETE avec un message d'intégrité formel. Parallèlement, le Directeur Général "
            "ouvre son tableau de bord : grâce au nouveau <b>Journal Consolidé des Reports</b>, il visualise en une seule "
            "requête l'ensemble des 27 reports survenus sur le chantier, triés par criticité, filtrables par motif et par acteur. "
            "Ressentez la paix et la certitude intérieure de concevoir un système à l'épreuve des balles juridiques et techniques.",
            styles["Body"],
        )
    )

    box_mental = callout_box(
        "<b>Loi de l'Effort Inversé (Dr. Joseph Murphy) :</b> N'essayez pas de forcer la compréhension mécanique par "
        "la tension. Ancrez simplement la conviction que l'architecture d'un journal d'audit est par nature <i>append-only</i> "
        "(ajout pur). Lorsque l'invariant d'immuabilité est posé en base de données, l'esprit est libéré de toute anxiété "
        "liée aux altérations rétroactives.",
        title="POSTURE MENTALE DU DÉVELOPPEUR SOUVERAIN",
        bg="#EFF6FF",
        border="#3B82F6",
    )
    story.append(box_mental)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2 : ARCHITECTURE & INVARIANTS SYSTÉMIQUES
    # =========================================================================
    story.append(Paragraph("2. Architecture & Invariants Systémiques (Pólya / Dehaene / Meadows)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Suivant la méthodologie de résolution de <b>George Pólya</b>, nous décomposons le problème en invariants universels : "
            "<b>Données</b>, <b>Inconnue</b> et <b>Contraintes</b>.",
            styles["Body"],
        )
    )

    invariants_table_data = [
        [
            Paragraph("Invariant", styles["TableHeader"]),
            Paragraph("Nature & Formule", styles["TableHeader"]),
            Paragraph("Garantie Métier / Règle de Gestion", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Écart en Jours (Δt)</b>", styles["TableCellBold"]),
            Paragraph("<code>ecart_jours = (valeur_apres - valeur_avant).days</code>", styles["TableCell"]),
            Paragraph("Entier relatif immuable. Positif pour un glissement/retard, négatif pour une anticipation. Persisté pour indexation SQL immédiate.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Immuabilité Physique (RG-07)</b>", styles["TableCellBold"]),
            Paragraph("<code>BEFORE UPDATE OR DELETE ON historique_date</code>", styles["TableCell"]),
            Paragraph("Interdiction absolue de modifier ou supprimer une ligne d'audit. Refusé au niveau moteur PostgreSQL (trigger) et applicatif (save/delete).", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Justification Qualifiée (RG-11)</b>", styles["TableCellBold"]),
            Paragraph("<code>len(justification.strip()) >= 30</code>", styles["TableCell"]),
            Paragraph("Obligation légale d'explication textuelle étayée d'au moins 30 caractères non-blancs.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Auteur Authentifié</b>", styles["TableCellBold"]),
            Paragraph("<code>auteur_id NOT NULL</code>", styles["TableCell"]),
            Paragraph("Attribution systématique à l'utilisateur ayant exécuté l'action de reprogrammation.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Arborescence Consolidée</b>", styles["TableCellBold"]),
            Paragraph("<code>projet_id = P OR lot__projet_id = P OR activite__lot__projet_id = P</code>", styles["TableCell"]),
            Paragraph("Capacité d'auditer en un point unique tous les reports intervenus sur un chantier (projet + lots + activités).", styles["TableCell"]),
        ],
    ]
    t_inv = Table(invariants_table_data, colWidths=[130, 182, 210])
    t_inv.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_inv)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 3 : GUIDE D'IMPLÉMENTATION PAS-À-PAS
    # =========================================================================
    story.append(Paragraph("3. Guide d'Implémentation Pas-à-Pas (Le Code Maître)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "L'implémentation respecte la séparation des responsabilités de Django REST Framework : "
            "<b>Modèle</b> (intégrité et contraintes), <b>Trigger SQL</b> (inviolabilité base de données), "
            "<b>Service</b> (orchestration métier transactionnelle), <b>Serializers</b> (contrats d'entrée/sortie), "
            "et <b>Vues DRF</b> (filtrage, pagination et permissions RBAC).",
            styles["Body"],
        )
    )

    story.append(Paragraph("3.1 Évolution du Modèle HistoriqueDate (apps/projets/models/historique_date.py)", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Nous enrichissons le modèle avec le champ persistant <code>ecart_jours</code> et nous surchargeons "
            "<code>save()</code> et <code>delete()</code> pour garantir l'immuabilité au niveau ORM Python.",
            styles["Body"],
        )
    )

    code_modele = """# apps/projets/models/historique_date.py (Extrait clé)
class HistoriqueDate(ModeleBase):
    # ... champs existants : type_objet, projet, lot, activite, champ, valeur_avant, valeur_apres, motif, justification, auteur ...
    
    ecart_jours = models.IntegerField(
        _("écart en jours"),
        help_text=_("Différence en jours entre la nouvelle date et l'ancienne (valeur_après - valeur_avant)."),
    )

    class Meta:
        db_table = "historique_date"
        verbose_name = _("historique de date")
        verbose_name_plural = _("historiques de dates")
        ordering = ["-cree_le"]
        indexes = [
            models.Index(fields=["type_objet", "champ"], name="hist_date_type_champ_idx"),
            models.Index(fields=["projet", "-cree_le"], name="hist_date_projet_idx"),
            models.Index(fields=["auteur", "-cree_le"], name="hist_date_auteur_idx"),
            models.Index(fields=["ecart_jours"], name="hist_date_ecart_idx"),
        ]

    def save(self, *args, **kwargs):
        # 1. Calcul automatique immuable de l'écart en jours
        if self.valeur_apres and self.valeur_avant:
            self.ecart_jours = (self.valeur_apres - self.valeur_avant).days
        else:
            self.ecart_jours = 0

        # 2. Règle RG-07 : Interdiction formelle de modification (append-only)
        if self.pk and HistoriqueDate.objects.filter(pk=self.pk).exists():
            raise ValidationError(_("RG-07 : L'historique d'audit des reports est strictement immuable."))

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Règle RG-07 : Interdiction formelle de suppression
        raise ValidationError(_("RG-07 : Une entrée du journal d'audit ne peut jamais être supprimée."))"""
    story.append(code_box(code_modele))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.2 Trigger PostgreSQL d'Immuabilité Physique (Migration Django)", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Le Socle Commun stipule : <i>« L'immuabilité ne se garantit pas en Python. Elle se pose en base. »</i> "
            "Nous créons un trigger PostgreSQL exécuté avant tout UPDATE ou DELETE sur la table <code>historique_date</code>.",
            styles["Body"],
        )
    )

    code_sql = """-- Trigger PostgreSQL : Interdiction UPDATE et DELETE sur historique_date (RG-07)
CREATE OR REPLACE FUNCTION verifier_immuabilite_historique_date()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'RG-07 : La table historique_date est strictement immuable (append-only). Opération % interdite.', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_historique_date_immuable ON historique_date;
CREATE TRIGGER trg_historique_date_immuable
BEFORE UPDATE OR DELETE ON historique_date
FOR EACH ROW
EXECUTE FUNCTION verifier_immuabilite_historique_date();"""
    story.append(code_box(code_sql))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.3 Synchronisation du Service (apps/projets/services/reprogrammation.py)", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Le service <code>reprogrammer_date_instance</code> transmet l'écart en jours lors de la création de chaque "
            "entrée <code>HistoriqueDate</code>, garantissant que l'opération est entièrement scellée dans la transaction atomique.",
            styles["Body"],
        )
    )

    code_svc = """# Calcul de l'écart et création sécurisée dans reprogrammer_date_instance
ecart_calc = (cible_date - ancienne_date).days

HistoriqueDate.objects.create(
    type_objet=type_objet,
    champ="date_fin_prevue",
    valeur_avant=ancienne_date,
    valeur_apres=cible_date,
    ecart_jours=ecart_calc,
    motif=motif,
    justification=justif_propre,
    auteur=auteur,
    **kwargs_lien,
)"""
    story.append(code_box(code_svc))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.4 Serializers Enrichis (apps/projets/serializers/reprogrammation.py)", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Le serializer expose toutes les dimensions décisionnelles : <code>ecart_jours</code>, données de l'auteur, "
            "motif complet, ainsi que le libellé et la référence de l'objet ciblé (Projet, Lot ou Activité).",
            styles["Body"],
        )
    )

    code_ser = """class HistoriqueDateSerializer(serializers.ModelSerializer):
    motif = MotifReportSerializer(read_only=True)
    auteur_nom = serializers.SerializerMethodField()
    objet_libelle = serializers.SerializerMethodField()
    projet_nom = serializers.SerializerMethodField()
    projet_id = serializers.SerializerMethodField()

    class Meta:
        model = HistoriqueDate
        fields = [
            "id", "type_objet", "champ", "valeur_avant", "valeur_apres",
            "ecart_jours", "motif", "justification", "auteur_id", "auteur_nom",
            "objet_libelle", "projet_id", "projet_nom", "cree_le",
        ]

    def get_auteur_nom(self, obj: HistoriqueDate) -> str:
        if not obj.auteur:
            return "Système"
        nom_complet = f"{obj.auteur.prenom} {obj.auteur.nom}".strip()
        return nom_complet or obj.auteur.email

    def get_objet_libelle(self, obj: HistoriqueDate) -> str:
        cible = obj.activite or obj.lot or obj.projet
        return getattr(cible, "libelle", getattr(cible, "nom", str(cible)))

    def get_projet_id(self, obj: HistoriqueDate) -> str | None:
        p = obj.projet or (obj.lot.projet if obj.lot else (obj.activite.lot.projet if obj.activite else None))
        return str(p.id) if p else None

    def get_projet_nom(self, obj: HistoriqueDate) -> str | None:
        p = obj.projet or (obj.lot.projet if obj.lot else (obj.activite.lot.projet if obj.activite else None))
        return p.nom if p else None"""
    story.append(code_box(code_ser))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.5 Vues DRF : Journal Consolidé & Journal Global Multi-Projets", styles["SubSectionHeader"]))
    story.append(
        Paragraph(
            "Nous mettons en place deux points d'entrée de consultation :<br/>"
            "1. <b>Journal Consolidé de Chantier :</b> <code>GET /api/v1/projets/{id}/journal-reports/</code> — "
            "regroupe tous les décalages survenus sur le projet, ses lots et ses activités enfants.<br/>"
            "2. <b>Journal Global Multi-Projets :</b> <code>GET /api/v1/projets/journal-reports/</code> — "
            "offre à la Direction Générale et aux Admins une vision transverse avec filtres (motif, auteur, dates, écart_min).",
            styles["Body"],
        )
    )

    code_views = """class JournalReportsFiltreMixin:
    \"\"\"Mixin de filtrage commun pour le journal d'audit des reports.\"\"\"
    def appliquer_filtres(self, qs, params):
        motif_id = params.get("motif_id")
        if motif_id:
            qs = qs.filter(motif_id=motif_id)
        auteur_id = params.get("auteur_id")
        if auteur_id:
            qs = qs.filter(auteur_id=auteur_id)
        type_objet = params.get("type_objet")
        if type_objet:
            qs = qs.filter(type_objet=type_objet.upper())
        ecart_min = params.get("ecart_min")
        if ecart_min is not None and ecart_min != "":
            qs = qs.filter(ecart_jours__gte=int(ecart_min))
        date_debut = params.get("date_debut")
        if date_debut:
            qs = qs.filter(cree_le__date__gte=date_debut)
        date_fin = params.get("date_fin")
        if date_fin:
            qs = qs.filter(cree_le__date__lte=date_fin)
        return qs

class ProjetJournalReportsConsolideView(APIView, JournalReportsFiltreMixin):
    \"\"\"Consulte l'historique complet et consolidé des reports d'un chantier entier.\"\"\"
    permission_classes = [IsAuthenticated, PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE), MembreDuProjet]

    def get(self, request, pk):
        projet = get_object_or_404(Projet, pk=pk)
        self.check_object_permissions(request, projet)
        qs = HistoriqueDate.objects.filter(
            models.Q(projet=projet) | models.Q(lot__projet=projet) | models.Q(activite__lot__projet=projet)
        ).select_related("motif", "auteur", "projet", "lot", "activite").order_by("-cree_le")
        qs = self.appliquer_filtres(qs, request.query_params)
        
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = HistoriqueDateSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class GlobalJournalReportsView(APIView, JournalReportsFiltreMixin):
    \"\"\"Journal global transverse des reports de dates pour le DG et l'Admin.\"\"\"
    permission_classes = [IsAuthenticated, PermissionModule.pour(ModuleChoix.PROJETS, NiveauAcces.LECTURE)]

    def get(self, request):
        qs = HistoriqueDate.objects.all().select_related("motif", "auteur", "projet", "lot", "activite").order_by("-cree_le")
        projet_id = request.query_params.get("projet_id")
        if projet_id:
            qs = qs.filter(models.Q(projet_id=projet_id) | models.Q(lot__projet_id=projet_id) | models.Q(activite__lot__projet_id=projet_id))
        qs = self.appliquer_filtres(qs, request.query_params)
        
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = HistoriqueDateSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)"""
    story.append(code_box(code_views))
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 4 : SIGNAL D'ERREUR BAYÉSIEN & PRE-MORTEM
    # =========================================================================
    story.append(Paragraph("4. Signal d'Erreur Bayésien & Pre-Mortem (Dehaene P3 / Kahneman)", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Selon la théorie cognitive du <b>Cerveau Bayésien (Stanislas Dehaene)</b>, l'apprentissage s'effectue "
            "par la correction active des prédictions erronées. En ingénierie logicielle, l'exercice du <b>Pre-Mortem "
            "(Daniel Kahneman)</b> consiste à imaginer à l'avance que le système a échoué en production afin d'éradiquer "
            "les failles avant qu'elles ne se manifestent.",
            styles["Body"],
        )
    )

    premortem_data = [
        [
            Paragraph("Scénario de Défaillance Réduit", styles["TableHeader"]),
            Paragraph("Mécanisme de Défaillance", styles["TableHeader"]),
            Paragraph("Parade Architecturale Implémentée", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Contournement par UPDATE SQL direct</b>", styles["TableCellBold"]),
            Paragraph("Un script d'administration ou une méthode <code>QuerySet.update()</code> modifie l'historique sans appeler <code>save()</code>.", styles["TableCell"]),
            Paragraph("<b>Trigger PostgreSQL natif</b> (<code>trg_historique_date_immuable</code>) : lève une exception fatale au cœur du moteur SQL.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Explosion N+1 Queries sur le journal</b>", styles["TableCellBold"]),
            Paragraph("Sérialiser 50 entrées d'audit effectue 250 requêtes SQL pour charger les auteurs, motifs, lots et projets liés.", styles["TableCell"]),
            Paragraph("<code>select_related('motif', 'auteur', 'projet', 'lot', 'activite')</code> systématique sur le QuerySet paginé.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Confusion Écart Ponctuel vs Dérive Baseline</b>", styles["TableCellBold"]),
            Paragraph("Confondre le décalage de l'opération en cours (ex: +5 jours) et le glissement total cumulé depuis l'origine (ex: +35 jours).", styles["TableCell"]),
            Paragraph("<code>ecart_jours</code> mesure le pas ponctuel (avant vs après), tandis que <code>jours_derive_baseline</code> mesure l'écart à la v0.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Tentative de purge / delete accidentel</b>", styles["TableCellBold"]),
            Paragraph("Un développeur tente un nettoyage de données de test ou une suppression en cascade.", styles["TableCell"]),
            Paragraph("Blocage immédiat par <code>delete()</code> Python (ValidationError) et blocage SQL par le trigger PostgreSQL.", styles["TableCell"]),
        ],
    ]
    t_pm = Table(premortem_data, colWidths=[140, 180, 202])
    t_pm.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_pm)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 5 : CHECKLIST DE TESTS & VALIDATION
    # =========================================================================
    story.append(Paragraph("5. Checklist de Tests & Protocole de Validation", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le banc de test automatisé <code>apps/projets/tests/test_journal_audit_reports.py</code> valide exhaustivement "
            "les exigences métier :",
            styles["Body"],
        )
    )

    checklist_items = [
        "<b>Test 1 : Calcul exact de l'écart en jours</b> — Vérifier que pour un report de 10 jours, <code>ecart_jours == 10</code>.",
        "<b>Test 2 : Immuabilité applicative Python (save & delete)</b> — Tenter de modifier un champ sur une instance existante ou d'appeler <code>delete()</code> et constater la levée de <code>ValidationError</code>.",
        "<b>Test 3 : Immuabilité moteur PostgreSQL</b> — Tenter un <code>UPDATE</code> brut via <code>connection.cursor()</code> et vérifier le blocage par le trigger SQL.",
        "<b>Test 4 : Journal Consolidé par Projet</b> — Créer des reports sur le projet, un lot et une activité, et vérifier qu'ils apparaissent tous dans <code>/api/v1/projets/{id}/journal-reports/</code>.",
        "<b>Test 5 : Journal Global & Filtrage Multi-Critères</b> — Filtrer par <code>motif_id</code>, <code>auteur_id</code>, et <code>ecart_min</code> sur <code>/api/v1/projets/journal-reports/</code>.",
        "<b>Test 6 : Permissions RBAC</b> — Vérifier qu'un membre non affecté au projet ne peut pas consulter le journal consolidé.",
    ]
    for ci in checklist_items:
        story.append(Paragraph(f"• {ci}", styles["Body"]))

    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 6 : DÉFI HOMO DOCENS & CONSOLIDATION NOCTURNE
    # =========================================================================
    story.append(Paragraph("6. Défi Homo Docens & Rituel de Somnolence Nocturne", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>Le Pilier 4 de Stanislas Dehaene (Consolidation)</b> démontre que le sommeil rejoue les circuits neuronaux "
            "fraîchement activés à une vitesse multipliée par 20. Pour ancrer définitivement ces compétences :",
            styles["Body"],
        )
    )
    story.append(
        Paragraph(
            "1. <b>Défi Homo Docens :</b> Expliquez à voix haute (ou à un collègue développeur) pourquoi une contrainte "
            "d'immuabilité purement Python est une illusion de sécurité, et comment un trigger PostgreSQL assure la garantie "
            "légale indispensable aux audits de chantiers.<br/>"
            "2. <b>Rituel de Somnolence (Dr. Joseph Murphy) :</b> Ce soir, au moment où la somnolence vous gagne, murmurez "
            "paisiblement : <i>« Mon esprit intègre l'art de l'immuabilité et de la traçabilité souveraine. Mes architectures "
            "sont robustes, fiables et incorruptibles. »</i> Votre subconscient ordonnera les concepts pendant votre repos.",
            styles["Body"],
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Manuel généré avec succès dans : {output_path}")


if __name__ == "__main__":
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
    )
    out_file = os.path.join(out_dir, "MANUEL_SPRINT_4_TACHE_JOURNAL_AUDIT_REPORTS.pdf")
    generate_pdf(out_file)
