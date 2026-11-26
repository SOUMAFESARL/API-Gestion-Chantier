"""Tests d'intégration GED : liens de partage externe temporaire 72 h & accès public D9.

Couvre la tâche 3.9 du sprint GED (F6).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import JournalAudit
from apps.core.contexte import contexte_entreprise
from apps.core.enums import ActionAudit, CategorieDocument, RoleProjet
from apps.ged.models import PartageDocument
from apps.ged.services.audit import TYPE_ENTITE_DOCUMENT_GED
from apps.ged.services.documents import deposer_document
from apps.ged.services.partages import creer_partage_document
from apps.ged.tests.conftest import (
    affecter_projet,
    client_pour,
    code_erreur,
    creer_projet,
    creer_utilisateur,
    generer_pdf,
    titre_pdf_reponse,
)

pytestmark = pytest.mark.django_db


def test_partage_reserve_ad_dg_do_cp_et_consultation_anonyme_version_active(entreprise_demo):
    """Partage réservé AD/DG/DO/CP ; lien anonyme sert toujours la version active (v3)."""
    ad = creer_utilisateur(entreprise_demo, "AD")
    dg = creer_utilisateur(entreprise_demo, "DG", is_owner=True)
    do = creer_utilisateur(entreprise_demo, "DO")
    cp = creer_utilisateur(entreprise_demo, "CP")
    ct = creer_utilisateur(entreprise_demo, "CT")
    cc = creer_utilisateur(entreprise_demo, "CC")
    mag = creer_utilisateur(entreprise_demo, "MAG")

    projet = creer_projet(entreprise_demo, createur=dg, chef_projet=cp)
    affecter_projet(cp, projet, RoleProjet.CHEF_PROJET)
    affecter_projet(ct, projet, RoleProjet.CONDUCTEUR_TRAVAUX)
    affecter_projet(cc, projet, RoleProjet.CHEF_CHANTIER)
    affecter_projet(mag, projet, RoleProjet.VISITEUR)

    doc, _ = deposer_document(
        projet=projet,
        categorie=CategorieDocument.DIVERS,
        fichier=generer_pdf(b"VERSION-1-PARTAGE", "dossier_v1.pdf"),
        nom="Dossier technique BET",
        createur=cp,
        notifier=False,
    )

    # 1. CT, CC, MAG refusés (403) en création et en liste des partages
    for interdit in (ct, cc, mag):
        cli = client_pour(interdit)
        rep_post = cli.post(f"/api/v1/ged/documents/{doc.pk}/partages/", {}, format="json")
        assert rep_post.status_code == 403
        assert cli.get(f"/api/v1/ged/documents/{doc.pk}/partages/").status_code == 403

    # 2. AD, DG, DO, CP autorisés
    for autorise in (ad, dg, do, cp):
        cli = client_pour(autorise)
        assert cli.get(f"/api/v1/ged/documents/{doc.pk}/partages/").status_code == 200

    # 3. Création d'un lien 72 h par CP
    client_cp = client_pour(cp)
    rep_partage = client_cp.post(
        f"/api/v1/ged/documents/{doc.pk}/partages/",
        {"destinataire": "Bureau Veritas", "note": "Pour visa structure"},
        format="json",
    )
    assert rep_partage.status_code == 201
    partage_data = rep_partage.json()
    jeton = partage_data["jeton"]
    assert jeton.startswith("tok_")
    assert partage_data["url_publique"] == f"/partage/{jeton}"
    assert partage_data["revoque"] is False

    # 4. Consultation & téléchargement anonymes (AUCUN JWT) -> 200 + audit sans jeton
    anonyme = APIClient(HTTP_HOST="localhost")
    rep_pub = anonyme.get(f"/api/v1/public/partages/{jeton}/")
    assert rep_pub.status_code == 200
    assert rep_pub.json()["document"]["version"] == "v1"
    assert rep_pub.json()["entreprise_nom"] == entreprise_demo.raison_sociale

    rep_dl_v1 = anonyme.get(f"/api/v1/public/partages/{jeton}/telecharger/")
    assert rep_dl_v1.status_code == 200
    assert rep_dl_v1["Cache-Control"] == "private, no-store"
    assert titre_pdf_reponse(rep_dl_v1) == "VERSION-1-PARTAGE"

    with contexte_entreprise(entreprise_demo):
        partage_obj = PartageDocument.objects.get(pk=partage_data["id"])
        assert partage_obj.consultations == 1

    # Vérifier l'entrée JournalAudit anonyme et l'absence absolue du jeton dans l'audit
    entree_dl = (
        JournalAudit.objects.filter(
            entreprise_id=entreprise_demo.pk,
            type_entite=TYPE_ENTITE_DOCUMENT_GED,
            entite_id=doc.pk,
            action=ActionAudit.TELECHARGEMENT,
        )
        .order_by("-horodatage")
        .first()
    )
    assert entree_dl is not None
    assert entree_dl.utilisateur_id is None
    assert entree_dl.valeur_apres.get("externe") is True
    assert jeton not in str(entree_dl.valeur_apres)

    # 5. Règle validée : publication d'une v2 puis v3 pendant la fenêtre 72 h -> sert v3
    client_cp.post(
        f"/api/v1/ged/documents/{doc.pk}/versions/",
        {"fichier": generer_pdf(b"VERSION-2-PARTAGE", "dossier_v2.pdf"), "commentaire": "Rev 2"},
        format="multipart",
    )
    client_cp.post(
        f"/api/v1/ged/documents/{doc.pk}/versions/",
        {"fichier": generer_pdf(b"VERSION-3-ACTIVE", "dossier_v3.pdf"), "commentaire": "Rev 3"},
        format="multipart",
    )

    rep_pub_v3 = anonyme.get(f"/api/v1/public/partages/{jeton}/")
    assert rep_pub_v3.status_code == 200
    assert rep_pub_v3.json()["document"]["version"] == "v3"
    assert rep_pub_v3.json()["document"]["nom_fichier"] == "dossier_v3.pdf"

    rep_dl_v3 = anonyme.get(f"/api/v1/public/partages/{jeton}/telecharger/")
    assert rep_dl_v3.status_code == 200
    assert titre_pdf_reponse(rep_dl_v3) == "VERSION-3-ACTIVE"

    with contexte_entreprise(entreprise_demo):
        partage_obj.refresh_from_db()
        assert partage_obj.consultations == 2


def test_partage_expiration_revocation_suppression_et_isolation_d9(
    entreprise_demo, entreprise_autre
):
    """404 sur jeton inconnu, 410 si expiré/révoqué/supprimé, isolation D9 sur 2 entreprises."""
    dg_demo = creer_utilisateur(entreprise_demo, "DG", is_owner=True)
    dg_autre = creer_utilisateur(entreprise_autre, "DG", is_owner=True)

    projet_demo = creer_projet(entreprise_demo, createur=dg_demo, nom="Projet Démo")
    projet_autre = creer_projet(entreprise_autre, createur=dg_autre, nom="Projet Autre")

    with contexte_entreprise(entreprise_demo):
        doc_demo, _ = deposer_document(
            projet=projet_demo,
            categorie=CategorieDocument.PLANS,
            fichier=generer_pdf(b"BYTES-DEMO", "demo.pdf"),
            nom="Plan Démo",
            createur=dg_demo,
            notifier=False,
        )
        partage_demo = creer_partage_document(document=doc_demo, utilisateur=dg_demo)

    with contexte_entreprise(entreprise_autre):
        doc_autre, _ = deposer_document(
            projet=projet_autre,
            categorie=CategorieDocument.PLANS,
            fichier=generer_pdf(b"BYTES-AUTRE", "autre.pdf"),
            nom="Plan Autre",
            createur=dg_autre,
            notifier=False,
        )
        partage_autre = creer_partage_document(document=doc_autre, utilisateur=dg_autre)

    anonyme = APIClient(HTTP_HOST="localhost")

    # 1. Jeton inconnu -> 404
    assert anonyme.get("/api/v1/public/partages/tok_inexistant_123456/").status_code == 404
    assert (
        anonyme.get("/api/v1/public/partages/tok_inexistant_123456/telecharger/").status_code == 404
    )

    # 2. Isolation D9 : chaque jeton sert uniquement le document de son entreprise
    rep_demo = anonyme.get(f"/api/v1/public/partages/{partage_demo.jeton}/")
    rep_autre = anonyme.get(f"/api/v1/public/partages/{partage_autre.jeton}/")
    assert rep_demo.status_code == 200
    assert rep_autre.status_code == 200
    assert rep_demo.json()["entreprise_nom"] == entreprise_demo.raison_sociale
    assert rep_autre.json()["entreprise_nom"] == entreprise_autre.raison_sociale

    # 3. Expiration (> 72 h) -> 410 partage_expire
    with contexte_entreprise(entreprise_demo):
        PartageDocument.tous_objets.filter(pk=partage_demo.pk).update(
            expire_le=timezone.now() - timedelta(minutes=1)
        )
    rep_exp = anonyme.get(f"/api/v1/public/partages/{partage_demo.jeton}/")
    assert rep_exp.status_code == 410
    assert code_erreur(rep_exp) == "partage_expire"
    assert (
        anonyme.get(f"/api/v1/public/partages/{partage_demo.jeton}/telecharger/").status_code == 410
    )

    # 4. Révocation manuelle -> 410
    client_demo = client_pour(dg_demo)
    with contexte_entreprise(entreprise_demo):
        partage_rev = creer_partage_document(document=doc_demo, utilisateur=dg_demo)
    assert client_demo.delete(f"/api/v1/ged/partages/{partage_rev.pk}/").status_code == 204
    assert anonyme.get(f"/api/v1/public/partages/{partage_rev.jeton}/").status_code == 410

    # 5. Suppression logique du document parent -> 410
    with contexte_entreprise(entreprise_demo):
        partage_suppr = creer_partage_document(document=doc_demo, utilisateur=dg_demo)
    assert client_demo.delete(f"/api/v1/ged/documents/{doc_demo.pk}/").status_code == 204
    assert anonyme.get(f"/api/v1/public/partages/{partage_suppr.jeton}/").status_code == 410
