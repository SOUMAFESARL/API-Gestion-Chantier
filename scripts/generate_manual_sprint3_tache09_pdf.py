"""Script de génération du Manuel d'Apprentissage par la Pratique : Sprint 3 - Tâche 09.

Tâche : Inscription 100% Automatique, Provisionnement Tenant Résilient & Élimination des Timeouts
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
    """Canvas à deux passes pour insérer dynamiquement les en-têtes et les numéros de page."""

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
            "CCD DIGITAL • SPRINT 3 — TÂCHE 09 : INSCRIPTION AUTOMATIQUE & PROVISIONNEMENT TENANT",
        )
        self.drawRightString(
            A4[0] - 36,
            A4[1] - 28,
            "RÉSOLUTION DES TIMEOUTS & ARCHITECTURE RÉSILIENTE",
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
            "CodeInline",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.8,
            leading=10,
            textColor=colors.HexColor("#0F172A"),
        )
    )

    styles.add(
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.3,
            leading=9.8,
            textColor=colors.HexColor("#0F172A"),
            backColor=colors.HexColor("#F8FAFC"),
            borderPadding=5,
            spaceAfter=5,
        )
    )

    styles.add(
        ParagraphStyle(
            "CalloutText",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.2,
            leading=11.5,
            textColor=colors.HexColor("#1E293B"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableText",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.6,
            leading=10.2,
            textColor=colors.HexColor("#1E293B"),
        )
    )

    styles.add(
        ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=10.5,
            textColor=colors.white,
        )
    )

    return styles


def build_manual():
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Manuels_Apprentissage",
    )
    os.makedirs(output_dir, exist_ok=True)
    pdf_filename = os.path.join(
        output_dir,
        "MANUEL_SPRINT_3_TACHE_09_INSCRIPTION_AUTOMATIQUE_PROVISIONNEMENT_TENANT.pdf",
    )

    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=38,
    )

    styles = create_styles()
    story = []

    # -------------------------------------------------------------------------
    # PAGE 1 : TITRE & CADRAGE
    # -------------------------------------------------------------------------
    meta_data = [
        [
            Paragraph("<b>PROJET :</b> CCD Digital (Gestion Chantier BTP)", styles["TableText"]),
            Paragraph("<b>MODULE :</b> Inscription & Multi-Tenancy (T-020 / T-021)", styles["TableText"]),
        ],
        [
            Paragraph("<b>SPRINT :</b> 3 — Industrialisation Plateforme", styles["TableText"]),
            Paragraph("<b>TÂCHE :</b> 09 — Inscription 100% Automatique & Résilience", styles["TableText"]),
        ],
        [
            Paragraph("<b>DATE :</b> Septembre 2026", styles["TableText"]),
            Paragraph("<b>STATUT :</b> Validé & Testé (35/35 Tests Passés)", styles["TableText"]),
        ],
    ]
    t_meta = Table(meta_data, colWidths=[260, 263])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    story.append(Paragraph("MANUEL D'APPRENTISSAGE PAR LA PRATIQUE", styles["DocSubTitle"]))
    story.append(
        Paragraph(
            "Inscription 100% Automatique & Provisionnement Résilient des Tenants",
            styles["DocTitle"],
        )
    )
    story.append(
        Paragraph(
            "Guide de diagnostic, d'architecture et de résolution définitive des délais d'attente "
            "(Timeouts), du workflow asynchrone Celery/Thread sur cPanel et de la suppression du goulot Super Admin.",
            styles["DocSubTitle"],
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 10))

    # Bloc Mentorat Neurocognitif
    mentor_data = [
        [
            Paragraph(
                "<b>MENTORAT DU SUBCONSCIENT & POSTURE DE SOUVERAINETÉ (Joseph Murphy & Stanislas Dehaene)</b><br/>"
                "• <b>Loi de l'Effort Inversé (Dr. Joseph Murphy) :</b> L'angoisse d'un bogue d'attente infini en production pousse "
                "souvent à forcer des rustines hâtives. La maîtrise souveraine exige le calme : disséquer le flux de données avec clarté "
                "pour voir exactement où le signal s'arrête.<br/>"
                "• <b>Les 4 Piliers de l'Apprentissage (Stanislas Dehaene) :</b> "
                "1. <i>Attention Sélective :</i> Isoler le timing exact (clic initial vs soumission de mot de passe) ; "
                "2. <i>Engagement Actif :</i> Tracer le code de bout en bout ; "
                "3. <i>Retour sur Erreur :</i> Comprendre pourquoi le statut 'A_VALIDER' brisait la boucle du frontend ; "
                "4. <i>Consolidation :</i> Automatiser la tâche de fond sans bloquer la passerelle HTTP.",
                styles["CalloutText"],
            )
        ]
    ]
    t_mentor = Table(mentor_data, colWidths=[523])
    t_mentor.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_mentor)
    story.append(Spacer(1, 10))

    # SECTION 1
    story.append(Paragraph("1. Anatomie du Problème et Diagnostic MECE", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "En production, l'utilisateur constatait : <i>« Ça charge pendant longtemps et puis on obtient un message d'erreur "
            "(ceci lorsqu'on clique sur le lien d'activation du compte) »</i>. L'audit complet du code a révélé "
            "trois phénomènes distincts qui se conjuguaient pour créer cette panne apparente :",
            styles["Body"],
        )
    )

    causes_data = [
        [
            Paragraph("Composant", styles["TableHeader"]),
            Paragraph("Symptôme Constaté", styles["TableHeader"]),
            Paragraph("Cause Racine Sous-Jacente", styles["TableHeader"]),
            Paragraph("Impact Produit", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Backend (Commit 5e61b62)</b>", styles["TableText"]),
            Paragraph("Blocage sur statut A_VALIDER", styles["TableText"]),
            Paragraph(
                "Le backend avait été modifié pour exiger l'approbation manuelle d'un Super Admin. "
                "Le provisionnement du tenant n'était plus jamais lancé à l'activation.",
                styles["TableText"],
            ),
            Paragraph("L'espace n'était jamais créé.", styles["TableText"]),
        ],
        [
            Paragraph("<b>Frontend (EcranActivation)</b>", styles["TableText"]),
            Paragraph("Chargement de 2 minutes précises", styles["TableText"]),
            Paragraph(
                "Le frontend boucle toutes les 2s (60 tentatives = 120s) en attendant le statut PRET. "
                "Ne connaissant pas A_VALIDER, il déclenche son timeout d'abandon.",
                styles["TableText"],
            ),
            Paragraph("Erreur affichée : 'lenteurMessage'.", styles["TableText"]),
        ],
        [
            Paragraph("<b>Infrastructure (cPanel / Passenger)</b>", styles["TableText"]),
            Paragraph("Risque de 504 Gateway Timeout", styles["TableText"]),
            Paragraph(
                "Sur cPanel, CELERY_TASK_ALWAYS_EAGER=True exécute migrate_schemas (20-30s) "
                "de manière synchrone, risquant de dépasser le proxy_read_timeout.",
                styles["TableText"],
            ),
            Paragraph("Coupure HTTP brutale de la requête.", styles["TableText"]),
        ],
        [
            Paragraph("<b>Redirection (views/__init__.py)</b>", styles["TableText"]),
            Paragraph("Redirection erronée", styles["TableText"]),
            Paragraph(
                "La sonde de suivi renvoyait base_url = 'http://localhost:3000' en dur "
                "au lieu d'utiliser settings.FRONTEND_URL.",
                styles["TableText"],
            ),
            Paragraph("Redirection vers localhost en prod.", styles["TableText"]),
        ],
    ]
    t_causes = Table(causes_data, colWidths=[95, 110, 208, 110])
    t_causes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_causes)
    story.append(Spacer(1, 10))

    # SECTION 2
    story.append(Paragraph("2. Cycle de Vie de l'Inscription 100% Automatique", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Le modèle produit retenu est le <b>Self-Service SaaS intégral</b> : aucune intervention humaine d'un administrateur "
            "n'est requise. L'utilisateur qui prouve la possession de son adresse email doit obtenir son espace immédiatement :",
            styles["Body"],
        )
    )

    cycle_steps = [
        Paragraph("<b>1. Dépôt public :</b> <font face='Courier'>POST /api/v1/inscription/</font> enregistre la demande (statut <i>EN_ATTENTE</i>) et expédie l'email d'activation avec un jeton sécurisé (valable 48h). Réponse 202 immédiate.", styles["Body"]),
        Paragraph("<b>2. Vérification du jeton :</b> <font face='Courier'>POST /api/v1/inscription/verifier/</font> valide l'empreinte cryptographique sans la consommer (protection anti-passerelle antivirus).", styles["Body"]),
        Paragraph("<b>3. Activation & Mot de passe :</b> <font face='Courier'>POST /api/v1/inscription/activer/</font> valide la complexité du mot de passe, consomme le jeton, positionne le statut à <i>PROVISIONNEMENT</i> et déclenche le worker.", styles["Body"]),
        Paragraph("<b>4. Exécution non-bloquante :</b> Le service détache l'exécution de <font face='Courier'>provisionner(demande_id)</font> pour répondre au navigateur en moins de 100 ms, évitant tout blocage HTTP.", styles["Body"]),
        Paragraph("<b>5. Sonde d'état & Redirection :</b> Le frontend interroge <font face='Courier'>GET /api/v1/inscription/etat/{suivi}/</font>. Dès que les migrations et le tenant sont créés, la sonde répond <i>PRET</i> avec l'URL de connexion réelle.", styles["Body"]),
    ]
    for step in cycle_steps:
        story.append(step)

    story.append(PageBreak())

    # PAGE 2 : ARCHITECTURE TECHNIQUE & IMPLÉMENTATION
    story.append(Paragraph("3. Implémentation du Provisionnement Résilient Backend", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Pour concilier l'exécution en environnement mutualisé (cPanel / Passenger) et les architectures conteneurisées avec Redis/Celery, "
            "le mécanisme <font face='Courier'>lancer_provisionnement</font> inspecte dynamiquement le mode de configuration :",
            styles["Body"],
        )
    )

    code_lancer = """def lancer_provisionnement(demande_id: str) -> None:
    \"\"\"Déclenche la tâche de provisionnement du tenant de façon asynchrone et non-bloquante.

    Si Celery est en mode Eager (ex: cPanel sans worker Celery dédié), un thread
    d'arrière-plan est détaché pour exécuter `provisionner_entreprise` sans bloquer
    la réponse HTTP de l'activation (évitant un 504 Gateway Timeout lors de migrate_schemas).
    Si un worker Celery est actif, la tâche est déposée dans la file via `.delay()`.
    \"\"\"
    from apps.tenants.tasks import provisionner_entreprise

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        import threading
        from django.db import connection

        def _executer():
            try:
                provisionner_entreprise(demande_id)
            finally:
                connection.close()

        thread = threading.Thread(
            target=_executer, name=f"provisionner-{demande_id}", daemon=True
        )
        thread.start()
    else:
        provisionner_entreprise.delay(demande_id)"""
    story.append(Preformatted(code_lancer, styles["CodeBlock"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("4. Découplage Transactionnel & Sécurité des Données", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "<b>Pourquoi utiliser <font face='Courier'>transaction.on_commit</font> ?</b><br/>"
            "Si la tâche de provisionnement était lancée <i>à l'intérieur</i> de la transaction SQL d'activation, le worker (ou le thread) "
            "pourrait s'exécuter avant que le commit PostgreSQL ne soit validé. Le worker chercherait alors la demande en base, "
            "ne la trouverait pas encore, et échouerait avec une exception <font face='Courier'>DoesNotExist</font>. "
            "<font face='Courier'>on_commit</font> garantit que la persistance est acquise avant tout déclenchement asynchrone.",
            styles["Body"],
        )
    )

    story.append(Paragraph("5. Correction des URL de Redirection Dynamiques", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Dans <font face='Courier'>apps/tenants/views/__init__.py</font> (<font face='Courier'>EtatProvisionnementView</font>) "
            "et dans <font face='Courier'>apps/billing/tasks.py</font>, la chaîne codée en dur <font face='Courier'>'http://localhost:3000'</font> "
            "a été remplacée par une lecture dynamique :",
            styles["Body"],
        )
    )

    code_view = """# Dans EtatProvisionnementView :
if demande.statut == DemandeInscription.Statut.ACTIVEE and demande.entreprise_id:
    from django.conf import settings

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
    url_connexion = f"{frontend_url}/connexion"

    return Response({"statut": "PRET", "url_connexion": url_connexion})"""
    story.append(Preformatted(code_view, styles["CodeBlock"]))
    story.append(Spacer(1, 8))

    # SECTION 6 : VALIDATION PAR LES TESTS
    story.append(Paragraph("6. Validation & Assurance Qualité par les Tests", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "La conformité de la solution a été éprouvée par <b>35 tests automatisés pytest</b> couvrant l'ensemble du cycle :",
            styles["Body"],
        )
    )

    tests_summary = [
        [
            Paragraph("Fichier de Test", styles["TableHeader"]),
            Paragraph("Nombre", styles["TableHeader"]),
            Paragraph("Couverture & Invariants Vérifiés", styles["TableHeader"]),
            Paragraph("Résultat", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>apps/tenants/tests/test_inscription.py</b>", styles["TableText"]),
            Paragraph("28 tests", styles["TableText"]),
            Paragraph("Dépôt, validation email, complexité mot de passe, statut PROVISIONNEMENT, sonde PRET et ECHEC.", styles["TableText"]),
            Paragraph("<font color='#16A34A'><b>100% SUCCÈS</b></font>", styles["TableText"]),
        ],
        [
            Paragraph("<b>apps/platform_admin/tests/test_inscriptions.py</b>", styles["TableText"]),
            Paragraph("7 tests", styles["TableText"]),
            Paragraph("Non-régression : filtrage, audit JournalPlateforme, gestion des décisions d'administration.", styles["TableText"]),
            Paragraph("<font color='#16A34A'><b>100% SUCCÈS</b></font>", styles["TableText"]),
        ],
    ]
    t_tests = Table(tests_summary, colWidths=[150, 55, 238, 80])
    t_tests.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_tests)
    story.append(Spacer(1, 10))

    # SECTION 7 : CHECKLIST DE PRODUCTION
    story.append(Paragraph("7. Checklist de Déploiement en Production (cPanel / Serveur)", styles["SectionHeader"]))
    checklist_items = [
        Paragraph("• <b>Variable FRONTEND_URL :</b> Vérifier dans le fichier <font face='Courier'>.env</font> de production que <font face='Courier'>FRONTEND_URL=https://chantier.soumafe.com</font> (ou le domaine public réel du frontend) et non <font face='Courier'>localhost</font>.", styles["Body"]),
        Paragraph("• <b>Variable DOMAINE_PRINCIPAL :</b> Vérifier que <font face='Courier'>DOMAINE_PRINCIPAL=api-chantier.soumafe.com</font> est aligné sur le domaine servi par Apache/Passenger.", styles["Body"]),
        Paragraph("• <b>Redémarrage Passenger :</b> Après avoir déployé les modifications sur la branche <font face='Courier'>main</font>, exécuter <font face='Courier'>touch tmp/restart.txt</font> pour forcer le rechargement à chaud de l'application Python.", styles["Body"]),
        Paragraph("• <b>Base de Données Public :</b> Vérifier que la table <font face='Courier'>public.entreprise</font> contient bien le schéma <font face='Courier'>public</font> pour que <font face='Courier'>TenantResolutionMiddleware</font> résolve les routes anonymes sans friction.", styles["Body"]),
    ]
    for chk in checklist_items:
        story.append(chk)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[OK] Manuel généré avec succès : {pdf_filename}")


if __name__ == "__main__":
    build_manual()
