"""Tests d'intégration GED : matrice rôles/catégories, isolation D9, verrou F1 et audit unique.

Couvre la tâche 3.8 et le verrouillage `ged.voir_contrats` des routes contrats F1.
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.audit.models import JournalAudit
from apps.core.enums import ActionAudit, CategorieDocument, RoleProjet
from apps.ged.services.audit import TYPE_ENTITE_DOCUMENT_GED
from apps.ged.services.documents import deposer_document
from apps.ged.tests.conftest import (
    affecter_projet,
    client_pour,
    creer_projet,
    creer_utilisateur,
    generer_pdf,
)
from apps.projets.services.avenants import enregistrer_avenant
from apps.projets.services.contrats import ajouter_contrats

pytestmark = pytest.mark.django_db


def test_matrice_roles_categories_portee_projet_et_magasinier(entreprise_demo, entreprise_autre):
    """MAG accède à DIVERS sans `projets.lire`, CT/CC ne voient pas CONTRATS, isolation D9."""
    dg = creer_utilisateur(entreprise_demo, "DG", prenom="Moussa", nom="Diallo", is_owner=True)
    cp = creer_utilisateur(entreprise_demo, "CP", prenom="Sévérin", nom="Zran")
    ct = creer_utilisateur(entreprise_demo, "CT", prenom="Koffi", nom="Yao")
    cc = creer_utilisateur(entreprise_demo, "CC", prenom="Bamba", nom="Koné")
    mag = creer_utilisateur(entreprise_demo, "MAG", prenom="Issa", nom="Traoré")

    projet_1 = creer_projet(entreprise_demo, createur=dg, chef_projet=cp, nom="Chantier A")
    projet_2 = creer_projet(entreprise_demo, createur=dg, nom="Chantier B Non Affecté")

    affecter_projet(cp, projet_1, RoleProjet.CHEF_PROJET)
    affecter_projet(ct, projet_1, RoleProjet.CONDUCTEUR_TRAVAUX)
    affecter_projet(cc, projet_1, RoleProjet.CHEF_CHANTIER)
    affecter_projet(mag, projet_1, RoleProjet.VISITEUR)

    doc_contrat, _ = deposer_document(
        projet=projet_1,
        categorie=CategorieDocument.CONTRATS,
        fichier=generer_pdf(b"SECRET-CONTRAT", "marche.pdf"),
        nom="Contrat confidentiel",
        createur=dg,
        notifier=False,
    )
    doc_divers, _ = deposer_document(
        projet=projet_1,
        categorie=CategorieDocument.DIVERS,
        fichier=generer_pdf(b"BON-LIVRAISON", "divers.pdf"),
        nom="Bordereau matériel",
        createur=dg,
        notifier=False,
    )

    # 1. MAG (sans `projets.lire`) accède à DIVERS (200) mais jamais à CONTRATS (absent + 403)
    client_mag = client_pour(mag)
    rep_mag_liste = client_mag.get(f"/api/v1/ged/documents/?projet={projet_1.pk}")
    assert rep_mag_liste.status_code == 200
    ids_mag = [d["id"] for d in rep_mag_liste.json()["results"]]
    assert str(doc_divers.pk) in ids_mag
    assert str(doc_contrat.pk) not in ids_mag

    assert client_mag.get(f"/api/v1/ged/documents/{doc_divers.pk}/").status_code == 200
    assert client_mag.get(f"/api/v1/ged/documents/{doc_divers.pk}/telecharger/").status_code == 200
    assert client_mag.get(f"/api/v1/ged/documents/{doc_contrat.pk}/").status_code == 403
    assert client_mag.get(f"/api/v1/ged/documents/{doc_contrat.pk}/telecharger/").status_code == 403

    # 2. CT et CC ne voient jamais CONTRATS (liste, détail, téléchargement)
    for role_user in (ct, cc):
        cli = client_pour(role_user)
        ids = [d["id"] for d in cli.get("/api/v1/ged/documents/").json()["results"]]
        assert str(doc_contrat.pk) not in ids
        assert cli.get(f"/api/v1/ged/documents/{doc_contrat.pk}/").status_code == 403
        assert cli.get(f"/api/v1/ged/documents/{doc_contrat.pk}/telecharger/").status_code == 403

    # 3. CC refusé (403) s'il tente de déposer sur un projet où il n'est pas affecté
    client_cc = client_pour(cc)
    rep_cc_hors_projet = client_cc.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet_2.pk),
            "categorie": CategorieDocument.PHOTOS,
            "nom": "Photo non affecté",
            "fichier": generer_pdf(b"X", "x.pdf"),
        },
        format="multipart",
    )
    assert rep_cc_hors_projet.status_code == 403

    # 4. Flags SSOT `peut_partager` et `peut_voir_historique` alignés sur AD/DG/DO/CP
    docs_cp = client_pour(cp).get(f"/api/v1/ged/documents/?projet={projet_1.pk}").json()["results"]
    assert docs_cp[0]["peut_partager"] is True
    assert docs_cp[0]["peut_voir_historique"] is True

    docs_ct = client_pour(ct).get(f"/api/v1/ged/documents/?projet={projet_1.pk}").json()["results"]
    assert all(d["peut_partager"] is False and d["peut_voir_historique"] is False for d in docs_ct)

    # 5. Isolation multi-tenant D9 : un DG d'une autre entreprise reçoit 404 / liste vide
    dg_autre = creer_utilisateur(entreprise_autre, "DG", prenom="Paul", nom="Autre", is_owner=True)
    client_autre = client_pour(dg_autre)
    assert client_autre.get("/api/v1/ged/documents/").json()["results"] == []
    assert client_autre.get(f"/api/v1/ged/documents/{doc_divers.pk}/").status_code == 404
    assert (
        client_autre.get(f"/api/v1/ged/documents/{doc_divers.pk}/telecharger/").status_code == 404
    )
    assert (
        client_autre.get(f"/api/v1/ged/documents/{doc_divers.pk}/historique/").status_code == 404
    )


def test_verrou_ged_voir_contrats_sur_routes_f1(entreprise_demo):
    """CT/CC reçoivent 403 sur les routes F1 contrats/OS/avenants ; CP/DG reçoivent 200."""
    dg = creer_utilisateur(entreprise_demo, "DG", is_owner=True)
    cp = creer_utilisateur(entreprise_demo, "CP")
    ct = creer_utilisateur(entreprise_demo, "CT")
    cc = creer_utilisateur(entreprise_demo, "CC")

    projet = creer_projet(entreprise_demo, createur=dg, chef_projet=cp)
    affecter_projet(cp, projet, RoleProjet.CHEF_PROJET)
    affecter_projet(ct, projet, RoleProjet.CONDUCTEUR_TRAVAUX)
    affecter_projet(cc, projet, RoleProjet.CHEF_CHANTIER)

    # Enregistrer contrat, ordre de service et avenant signé
    contrat = ajouter_contrats(
        projet,
        [generer_pdf(b"CONTRAT-F1", "contrat_marche.pdf")],
        dg,
        [],
    )

    projet.ordre_service.save("os_demarrage.pdf", generer_pdf(b"OS-F1", "os_demarrage.pdf"))
    projet.ordre_service_nom = "os_demarrage.pdf"
    projet.ordre_service_type = "application/pdf"
    projet.save(update_fields=["ordre_service", "ordre_service_nom", "ordre_service_type"])

    avenant = enregistrer_avenant(
        projet,
        numero="AV-01",
        date_signature=date(2026, 6, 15),
        objet="Prolongation fondations",
        jours_accordes=15,
        document=generer_pdf(b"AVENANT-DOC", "avenant_01.pdf"),
        ordre_service=generer_pdf(b"AVENANT-OS", "os_avenant_01.pdf"),
        auteur=dg,
    )

    routes_confidentielles = [
        f"/api/v1/projets/{projet.pk}/?contrat={contrat.pk}",
        f"/api/v1/projets/{projet.pk}/ordre-service/",
        f"/api/v1/projets/{projet.pk}/contrats/",
        f"/api/v1/avenants/{avenant.pk}/document/",
        f"/api/v1/avenants/{avenant.pk}/ordre-service/",
    ]

    # CT et CC -> 403 partout (pas de permission `ged.voir_contrats`)
    for non_autorise in (ct, cc):
        cli = client_pour(non_autorise)
        for url in routes_confidentielles:
            rep = cli.get(url)
            assert rep.status_code == 403, f"Attendu 403 sur {url}, obtenu {rep.status_code}"

    # CP et DG -> 200 partout
    for autorise in (cp, dg):
        cli = client_pour(autorise)
        for url in routes_confidentielles:
            rep = cli.get(url)
            assert rep.status_code == 200, f"Attendu 200 sur {url}, obtenu {rep.status_code}"


def test_journal_audit_unique_et_acces_historique_ad_dg_do_cp(entreprise_demo):
    """Chaque action GED est tracée dans `JournalAudit` ; lecture réservée à AD/DG/DO/CP."""
    ad = creer_utilisateur(entreprise_demo, "AD", prenom="Awa", nom="Admin")
    dg = creer_utilisateur(entreprise_demo, "DG", prenom="Moussa", nom="Diallo", is_owner=True)
    do = creer_utilisateur(entreprise_demo, "DO", prenom="Claire", nom="Operations")
    cp = creer_utilisateur(entreprise_demo, "CP", prenom="Sévérin", nom="Zran")
    ct = creer_utilisateur(entreprise_demo, "CT", prenom="Koffi", nom="Yao")
    mag = creer_utilisateur(entreprise_demo, "MAG", prenom="Issa", nom="Traoré")

    projet = creer_projet(entreprise_demo, createur=dg, chef_projet=cp)
    affecter_projet(cp, projet, RoleProjet.CHEF_PROJET)
    affecter_projet(ct, projet, RoleProjet.CONDUCTEUR_TRAVAUX)
    affecter_projet(mag, projet, RoleProjet.VISITEUR)

    client_cp = client_pour(cp)
    # 1. Dépôt -> DEPOT
    doc_id = client_cp.post(
        "/api/v1/ged/documents/",
        {
            "projet": str(projet.pk),
            "categorie": CategorieDocument.DIVERS,
            "nom": "Note de chantier",
            "fichier": generer_pdf(b"NOTE-V1", "note_v1.pdf"),
        },
        format="multipart",
    ).json()["id"]

    # 2. Consultation -> CONSULTATION
    assert client_cp.get(f"/api/v1/ged/documents/{doc_id}/").status_code == 200
    # 3. Téléchargement -> TELECHARGEMENT
    assert client_cp.get(f"/api/v1/ged/documents/{doc_id}/telecharger/").status_code == 200
    # 4. Nouvelle version -> NOUVELLE_VERSION
    assert (
        client_cp.post(
            f"/api/v1/ged/documents/{doc_id}/versions/",
            {"fichier": generer_pdf(b"NOTE-V2", "note_v2.pdf"), "commentaire": "Mise à jour"},
            format="multipart",
        ).status_code
        == 201
    )
    # 5. Épinglage -> EPINGLAGE
    assert (
        client_cp.patch(
            f"/api/v1/ged/documents/{doc_id}/",
            {"est_reference": True},
            format="json",
        ).status_code
        == 200
    )
    # 6. Partage + révocation -> PARTAGE, REVOCATION_PARTAGE
    partage_id = client_cp.post(
        f"/api/v1/ged/documents/{doc_id}/partages/",
        {"destinataire": "Bureau contrôle"},
        format="json",
    ).json()["id"]
    assert client_cp.delete(f"/api/v1/ged/partages/{partage_id}/").status_code == 204
    # 7. Suppression -> SUPPRESSION
    assert client_cp.delete(f"/api/v1/ged/documents/{doc_id}/").status_code == 204

    # Vérification dans la table unique immuable `JournalAudit`
    actions_enregistrees = set(
        JournalAudit.objects.filter(
            entreprise_id=entreprise_demo.pk,
            type_entite=TYPE_ENTITE_DOCUMENT_GED,
            entite_id=doc_id,
        ).values_list("action", flat=True)
    )
    assert {
        ActionAudit.DEPOT,
        ActionAudit.CONSULTATION,
        ActionAudit.TELECHARGEMENT,
        ActionAudit.NOUVELLE_VERSION,
        ActionAudit.EPINGLAGE,
        ActionAudit.PARTAGE,
        ActionAudit.REVOCATION_PARTAGE,
        ActionAudit.SUPPRESSION,
    }.issubset(actions_enregistrees)

    # Lecture de l'historique (y compris sur document supprimé) : autorisée pour AD, DG, DO, CP
    for gestionnaire in (ad, dg, do, cp):
        cli = client_pour(gestionnaire)
        rep_doc = cli.get(f"/api/v1/ged/documents/{doc_id}/historique/")
        assert rep_doc.status_code == 200
        assert any(e["action"] == ActionAudit.SUPPRESSION for e in rep_doc.json())

        rep_global = cli.get(f"/api/v1/ged/historique/?projet={projet.pk}&action=SUPPRESSION")
        assert rep_global.status_code == 200
        assert any(e["document_id"] == doc_id for e in rep_global.json())

    # Refusée en 403 pour CT et MAG
    for non_gestionnaire in (ct, mag):
        cli = client_pour(non_gestionnaire)
        assert cli.get(f"/api/v1/ged/documents/{doc_id}/historique/").status_code == 403
        assert cli.get("/api/v1/ged/historique/").status_code == 403
