"""Donnees figees et rendu PDF des factures d'abonnement."""

from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def contexte_facturation(entreprise, plan, cycle):
    return {
        "client": {
            champ: getattr(entreprise, champ)
            for champ in (
                "raison_sociale",
                "nom_commercial",
                "adresse",
                "ville",
                "pays",
                "rccm",
                "nif",
                "email_contact",
                "telephone_contact",
            )
        },
        "emetteur": dict(settings.FACTURATION_EMETTEUR),
        "prestation": {
            "reference": plan.code,
            "designation": f"Abonnement {plan.libelle}",
            "cycle": cycle,
            "quantite": 1,
        },
    }


def generer_pdf_facture(donnees):
    tampon = BytesIO()
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 13

    def paragraphe(texte, style="Normal"):
        return Paragraph(escape(str(texte or "")).replace("\n", "<br/>"), styles[style])

    def montant(centimes):
        return f"{Decimal(centimes) / 100:,.2f} FCFA".replace(",", " ")

    contenu = [paragraphe(f"FACTURE {donnees['numero']}", "Title")]
    contenu.append(paragraphe(donnees["statut_affichage"], "Heading2"))
    contexte = donnees["contexte_facturation"]
    for titre, cle in (("Emetteur", "emetteur"), ("Facture a", "client")):
        contenu.append(paragraphe(titre, "Heading2"))
        for champ, valeur in contexte.get(cle, {}).items():
            if valeur:
                contenu.append(paragraphe(f"{champ.replace('_', ' ').capitalize()} : {valeur}"))
    if not contexte:
        contenu.append(paragraphe("Facture historique : coordonnees non archivees."))
    for titre, cle in (("Emission", "date_emission"), ("Echeance", "date_echeance")):
        contenu.append(paragraphe(f"{titre} : {donnees[cle]}"))
    contenu.append(paragraphe(f"Periode : {donnees['periode_debut']} au {donnees['periode_fin']}"))
    contenu.append(Spacer(1, 6 * mm))
    prestation = contexte.get("prestation", {})
    lignes = [
        ["Designation", "Qte", "Total HT (XOF)"],
        [
            paragraphe(
                prestation.get("designation", "Abonnement SaaS") + " " + prestation.get("cycle", "")
            ),
            "1",
            montant(donnees["montant_ht"]),
        ],
    ]
    tableau = Table(lignes, colWidths=[105 * mm, 15 * mm, 50 * mm])
    tableau.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9edf2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    contenu.append(tableau)
    contenu.append(paragraphe(f"TVA ({donnees['taux_tva']} %) : {montant(donnees['montant_tva'])}"))
    contenu.append(paragraphe(f"TOTAL TTC : {montant(donnees['montant_ttc'])}", "Heading2"))
    for paiement in donnees["paiements"]:
        if paiement["statut"] == "CONFIRME":
            contenu.append(
                paragraphe(
                    f"Reglement : {paiement['mode']} / "
                    f"{paiement['reference_transaction']} / {paiement['paye_le']}"
                )
            )
    doc = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=donnees["numero"],
    )
    doc.build(contenu)
    return tampon.getvalue()
