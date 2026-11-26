"""Tests d'intégration GED : dépôt 6 catégories, validation, versions, épinglage et suppression.

Couvre les tâches 3.3 et 3.6 du sprint GED (F6).
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.contexte import contexte_entreprise
from apps.core.enums import CategorieDocument, RoleProjet, TypeSourceLiaison
from apps.ged.models import Document, PartageDocument
from apps.ged.services.documents import creer_document_automatique
from apps.ged.services.partages import creer_partage_document
from apps.ged.tests.conftest import (
    affecter_projet,
    client_pour,
    code_erreur,
    creer_projet,
    creer_utilisateur,
    generer_pdf,
    generer_png,
    titre_pdf_reponse,
)
from apps.ged.validators import TAILLE_MAX_FICHIER_OCTETS

pytestmark = pytest.mark.django_db

CATEGORIES_6 = (
    CategorieDocument.PLANS,
    CategorieDocument.CONTRATS,
    CategorieDocument.RAPPORTS,
    CategorieDocument.ADMINISTRATIF,
    CategorieDocument.PHOTOS,
    CategorieDocument.DIVERS,
)


def test_depot_6_categories_et_validation_formats_et_taille(entreprise_demo, monkeypatch):
    """Dépôt valide sur les 6 catégories + rejet format usurpé (400) + rejet > 50 Mo (413)."""
    assert TAILLE_MAX_FICHIER_OCTETS == 50 * 1024 * 1024

    dg = creer_utilisateur(entreprise_demo, "DG", prenom="Moussa", nom="Diallo", is_owner=True)
    projet = creer_projet(entreprise_demo, createur=dg)
    client = client_pour(dg)

    # 1. Dépôt réussi dans chacune des 6 catégories BTP
    for idx, categorie in enumerate(CATEGORIES_6, start=1):
        fichier = (
            generer_png(f"chantier_{idx}.png")
            if categorie == CategorieDocument.PHOTOS
            else generer_pdf(f"cat-{categorie}".encode(), f"piece_{idx}.pdf")
        )
        reponse = client.post(
            "/api/v1/ged/documents/",
            {
                "projet": str(projet.pk),
                "categorie": categorie,
                "nom": f"Pièce {categorie}",
                "description": f"Description {categorie}",
                "fichier": fichier,
            },
            format="multipart",
        )
        assert reponse.status_code == 201, reponse.content
        corps = reponse.json()
        assert corps["categorie"] == categorie
        assert corps["origine"] == "MANUEL"
        assert corps["est_automatique"] is False
        assert corps["nombre_versions"] == 1
        assert corps["version_active"]["numero"] == "v1"
        assert corps["version_active"]["est_active"] is True

    # 2. Extension PDF usurpée avec contenu texte -> 400 format_fichier_non_autorise
    faux_pdf = SimpleUploadedFile(
        "faux_plan.pdf",
        b"ceci est du texte brut et non un pdf",
        content_type="application/pdf",
    )
    rep_format = client.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet.pk),
            "categorie": CategorieDocument.PLANS,
            "nom": "Plan frauduleux",
            "fichier": faux_pdf,
        },
        format="multipart",
    )
    assert rep_format.status_code == 400
    assert code_erreur(rep_format) == "format_fichier_non_autorise"

    # 3. Fichier dépassant le plafond -> 413 taille_fichier_depassee
    monkeypatch.setattr("apps.ged.validators.TAILLE_MAX_FICHIER_OCTETS", 64)
    gros_pdf = generer_pdf(b"x" * 256, "gros_plan.pdf")
    rep_taille = client.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet.pk),
            "categorie": CategorieDocument.PLANS,
            "nom": "Plan trop lourd",
            "fichier": gros_pdf,
        },
        format="multipart",
    )
    assert rep_taille.status_code == 413
    assert code_erreur(rep_taille) == "taille_fichier_depassee"


def test_versioning_sans_perte_et_garde_document_automatique(entreprise_demo):
    """v1 -> v2 -> v3 sans perte, note obligatoire, téléchargement v1/v3, refus 422 sur auto."""
    cp = creer_utilisateur(entreprise_demo, "CP", prenom="Sévérin", nom="Zran")
    projet = creer_projet(entreprise_demo, createur=cp, chef_projet=cp)
    affecter_projet(cp, projet, RoleProjet.CHEF_PROJET)
    client = client_pour(cp)

    pdf_v1 = generer_pdf(b"CONTENU-V1", "plan_r0.pdf")
    rep_v1 = client.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet.pk),
            "categorie": CategorieDocument.PLANS,
            "nom": "Plan coffrage R+2",
            "fichier": pdf_v1,
        },
        format="multipart",
    )
    assert rep_v1.status_code == 201
    doc_id = rep_v1.json()["id"]
    v1_id = rep_v1.json()["version_active"]["id"]

    # Note de révision vide -> 400
    rep_sans_note = client.post(
        f"/api/v1/ged/documents/{doc_id}/versions/",
        {"fichier": generer_pdf(b"CONTENU-V2", "plan_r1.pdf"), "commentaire": "   "},
        format="multipart",
    )
    assert rep_sans_note.status_code == 400

    # Dépôt v2 puis v3
    rep_v2 = client.post(
        f"/api/v1/ged/documents/{doc_id}/versions/",
        {
            "fichier": generer_pdf(b"CONTENU-V2", "plan_r1.pdf"),
            "commentaire": "Correction poutre B4",
        },
        format="multipart",
    )
    assert rep_v2.status_code == 201
    assert rep_v2.json()["numero"] == "v2"

    rep_v3 = client.post(
        f"/api/v1/ged/documents/{doc_id}/versions/",
        {
            "fichier": generer_pdf(b"CONTENU-V3", "plan_r2.pdf"),
            "commentaire": "Visa bureau de contrôle",
            "est_reference": "true",
        },
        format="multipart",
    )
    assert rep_v3.status_code == 201
    assert rep_v3.json()["numero"] == "v3"

    # Historique complet trié v3, v2, v1 (une seule version active)
    rep_versions = client.get(f"/api/v1/ged/documents/{doc_id}/versions/")
    assert rep_versions.status_code == 200
    versions = rep_versions.json()
    assert [v["numero"] for v in versions] == ["v3", "v2", "v1"]
    assert [v["est_active"] for v in versions] == [True, False, False]

    # Téléchargement actif -> v3 ; téléchargement historique -> v1 intacte
    dl_actif = client.get(f"/api/v1/ged/documents/{doc_id}/telecharger/")
    assert dl_actif.status_code == 200
    assert dl_actif["Cache-Control"] == "private, no-store"
    assert titre_pdf_reponse(dl_actif) == "CONTENU-V3"

    dl_v1 = client.get(f"/api/v1/ged/documents/{doc_id}/versions/{v1_id}/telecharger/")
    assert dl_v1.status_code == 200
    assert titre_pdf_reponse(dl_v1) == "CONTENU-V1"

    # Document automatique : ajout manuel de version refusé en 422
    with contexte_entreprise(entreprise_demo):
        doc_auto, _, _ = creer_document_automatique(
            projet=projet,
            categorie=CategorieDocument.CONTRATS,
            fichier=generer_pdf(b"CONTRAT-AUTO", "contrat_marche.pdf"),
            source_type=TypeSourceLiaison.F1_CONTRAT,
            source_id=projet.pk,
            nom="Contrat marché auto",
            createur=cp,
        )
    rep_auto_ver = client.post(
        f"/api/v1/ged/documents/{doc_auto.pk}/versions/",
        {
            "fichier": generer_pdf(b"TENTATIVE", "hack.pdf"),
            "commentaire": "Tentative de remplacement manuel",
        },
        format="multipart",
    )
    assert rep_auto_ver.status_code == 422
    assert code_erreur(rep_auto_ver) == "document_automatique_non_modifiable"


def test_epinglage_edition_et_suppression_protegee(entreprise_demo):
    """Épinglage en tête, blocage édition métadonnées sur auto, suppression réservée AD/CP."""
    ad = creer_utilisateur(entreprise_demo, "AD", prenom="Awa", nom="Admin")
    cp = creer_utilisateur(entreprise_demo, "CP", prenom="Sévérin", nom="Zran")
    ct = creer_utilisateur(entreprise_demo, "CT", prenom="Koffi", nom="Conducteur")
    projet = creer_projet(entreprise_demo, createur=ad, chef_projet=cp)
    affecter_projet(cp, projet, RoleProjet.CHEF_PROJET)
    affecter_projet(ct, projet, RoleProjet.CONDUCTEUR_TRAVAUX)

    client_cp = client_pour(cp)
    client_ct = client_pour(ct)
    client_ad = client_pour(ad)

    doc_a = client_cp.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet.pk),
            "categorie": CategorieDocument.PLANS,
            "nom": "Plan A (non épinglé)",
            "fichier": generer_pdf(b"A", "a.pdf"),
        },
        format="multipart",
    ).json()
    doc_b = client_cp.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet.pk),
            "categorie": CategorieDocument.PLANS,
            "nom": "Plan B (à épingler)",
            "fichier": generer_pdf(b"B", "b.pdf"),
        },
        format="multipart",
    ).json()

    # Épinglage + édition métadonnées sur document manuel
    rep_patch = client_cp.patch(
        f"/api/v1/ged/documents/{doc_b['id']}/",
        {"est_reference": True, "nom": "Plan B Référence", "description": "Validé EXE"},
        format="json",
    )
    assert rep_patch.status_code == 200
    assert rep_patch.json()["est_reference"] is True
    assert rep_patch.json()["nom"] == "Plan B Référence"

    # Le document épinglé remonte en tête de liste
    liste = client_cp.get(f"/api/v1/ged/documents/?projet={projet.pk}").json()["results"]
    assert liste[0]["id"] == doc_b["id"]

    # Document automatique : épinglage autorisé, mais modification nom refusée (422)
    with contexte_entreprise(entreprise_demo):
        doc_auto, _, _ = creer_document_automatique(
            projet=projet,
            categorie=CategorieDocument.RAPPORTS,
            fichier=generer_pdf(b"RAPPORT-AUTO", "rapport.pdf"),
            source_type=TypeSourceLiaison.F2_RAPPORT,
            source_id=projet.pk,
            nom="Rapport journalier auto",
            createur=cp,
        )
    assert (
        client_cp.patch(
            f"/api/v1/ged/documents/{doc_auto.pk}/",
            {"est_reference": True},
            format="json",
        ).status_code
        == 200
    )
    rep_auto_nom = client_cp.patch(
        f"/api/v1/ged/documents/{doc_auto.pk}/",
        {"nom": "Renommage interdit"},
        format="json",
    )
    assert rep_auto_nom.status_code == 422

    # Suppression d'un document automatique -> 422 même pour AD et CP
    for client_autorite in (client_cp, client_ad):
        rep_del_auto = client_autorite.delete(f"/api/v1/ged/documents/{doc_auto.pk}/")
        assert rep_del_auto.status_code == 422
        assert code_erreur(rep_del_auto) == "document_automatique_non_supprimable"

    # Suppression d'un document manuel par CT -> 403
    assert client_ct.delete(f"/api/v1/ged/documents/{doc_a['id']}/").status_code == 403

    # Créer un partage actif avant suppression par CP -> doit être révoqué automatiquement
    with contexte_entreprise(entreprise_demo):
        doc_a_obj = Document.objects.get(pk=doc_a["id"])
        partage = creer_partage_document(document=doc_a_obj, utilisateur=cp, destinataire="BET")

    rep_del_cp = client_cp.delete(
        f"/api/v1/ged/documents/{doc_a['id']}/",
        {"motif": "Doublon obsolète"},
        format="json",
    )
    assert rep_del_cp.status_code == 204
    with contexte_entreprise(entreprise_demo):
        assert not Document.objects.filter(pk=doc_a["id"]).exists()
        assert Document.tous_objets.filter(pk=doc_a["id"], supprime_le__isnull=False).exists()
        partage.refresh_from_db()
        assert partage.revoque is True
        assert PartageDocument.objects.filter(pk=partage.pk, revoque=True).exists()
