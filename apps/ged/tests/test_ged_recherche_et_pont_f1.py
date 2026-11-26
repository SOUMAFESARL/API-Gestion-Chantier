"""Tests d'intégration GED : recherche rapide (< 1 s), stockage privé, pont F1 et backfill.

Couvre la tâche 3.11, l'alignement Configuration/Modification/Avenants F1 (50 Mo, retrait
synchronisé, auteur OS), le coffre privé `StockageGed` et `manage.py synchroniser_ged`.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import JournalAudit
from apps.chantier.models import RapportJournalier
from apps.core.contexte import contexte_entreprise, reinitialiser_contexte
from apps.core.enums import ActionAudit, CategorieDocument, RoleProjet, StatutRapport
from apps.ged.models import Document, LiaisonDocument, VersionDocument
from apps.ged.services.audit import TYPE_ENTITE_DOCUMENT_GED
from apps.ged.services.documents import ajouter_version, deposer_document
from apps.ged.services.partages import creer_partage_document
from apps.ged.tests.conftest import (
    affecter_projet,
    client_pour,
    creer_projet,
    creer_utilisateur,
    generer_pdf,
)
from apps.projets.models import Avenant, ProjetContrat
from apps.projets.services.avenants import enregistrer_avenant
from apps.projets.services.contrats import MAX_FICHIER, MAX_LOT, ajouter_contrats

pytestmark = pytest.mark.django_db


def test_recherche_rapide_filtres_combines_sans_doublon_ni_n_plus_1(
    entreprise_demo, django_assert_max_num_queries
):
    """Filtres combinés, zéro doublon SQL sur multi-versions, requêtes bornées et < 1 s."""
    dg = creer_utilisateur(entreprise_demo, "DG", is_owner=True)
    projet_1 = creer_projet(entreprise_demo, createur=dg, nom="Pont Ebrié")
    projet_2 = creer_projet(entreprise_demo, createur=dg, nom="Tour Plateau")

    # Document multi-versions dont v1 et v2 contiennent toutes deux "ferraillage"
    doc_multi, _ = deposer_document(
        projet=projet_1,
        categorie=CategorieDocument.PLANS,
        fichier=generer_pdf(b"FER-V1", "plan_ferraillage_v1.pdf"),
        nom="Plan ferraillage pile P2",
        description="Armatures haute adhérence",
        est_reference=True,
        createur=dg,
        notifier=False,
    )
    ajouter_version(
        document=doc_multi,
        fichier=generer_pdf(b"FER-V2", "plan_ferraillage_v2.pdf"),
        auteur=dg,
        commentaire="Indice B",
        notifier=False,
    )

    doc_autre, _ = deposer_document(
        projet=projet_2,
        categorie=CategorieDocument.ADMINISTRATIF,
        fichier=generer_pdf(b"PERMIS", "permis_construire.pdf"),
        nom="Permis de construire",
        description="Arrêté ministériel",
        createur=dg,
        notifier=False,
    )
    # Vieillir doc_autre de 10 jours pour tester la plage de dates
    hier_10j = timezone.now() - timedelta(days=10)
    Document.tous_objets.filter(pk=doc_autre.pk).update(cree_le=hier_10j)

    client = client_pour(dg)

    # Recherche plein texte sur nom de fichier présent dans 2 versions -> exactement 1 résultat
    debut = time.perf_counter()
    with django_assert_max_num_queries(15):
        rep = client.get(
            "/api/v1/ged/documents/",
            {
                "q": "ferraillage",
                "projet": str(projet_1.pk),
                "categorie": CategorieDocument.PLANS,
                "origine": "MANUEL",
                "est_reference": "true",
                "date_debut": (date.today() - timedelta(days=1)).isoformat(),
                "date_fin": (date.today() + timedelta(days=1)).isoformat(),
            },
        )
    duree = time.perf_counter() - debut

    assert rep.status_code == 200
    assert duree < 1.0
    corps = rep.json()
    assert corps["count"] == 1
    assert [d["id"] for d in corps["results"]] == [str(doc_multi.pk)]
    assert corps["results"][0]["nombre_versions"] == 2

    # Recherche par plage de dates ancienne -> retrouve uniquement le permis
    rep_ancien = client.get(
        "/api/v1/ged/documents/",
        {"date_fin": (date.today() - timedelta(days=5)).isoformat()},
    )
    assert rep_ancien.status_code == 200
    assert [d["id"] for d in rep_ancien.json()["results"]] == [str(doc_autre.pk)]


def test_stockage_prive_isole_de_media_root(entreprise_demo, settings):
    """Les fichiers GED sont écrits dans `GED_STORAGE_ROOT` et jamais dans `MEDIA_ROOT`."""
    dg = creer_utilisateur(entreprise_demo, "DG", is_owner=True)
    projet = creer_projet(entreprise_demo, createur=dg)

    _doc, version = deposer_document(
        projet=projet,
        categorie=CategorieDocument.CONTRATS,
        fichier=generer_pdf(b"CONFIDENTIEL-PRIVE", "secret.pdf"),
        nom="Contrat privé",
        createur=dg,
        notifier=False,
    )

    chemin_relatif = version.fichier.name
    chemin_prive = Path(settings.GED_STORAGE_ROOT) / chemin_relatif
    chemin_public = Path(settings.MEDIA_ROOT) / chemin_relatif
    assert chemin_prive.exists()
    assert not chemin_public.exists()


def test_pont_f1_50mo_auteur_os_et_retrait_synchronise_avenant(
    entreprise_demo, django_capture_on_commit_callbacks
):
    """Plafond 50 Mo F1, auteur réel OS sur PATCH projet, sous_type AVENANT & retrait synchro."""
    assert MAX_FICHIER == 50 * 1024 * 1024
    assert MAX_LOT == 50 * 1024 * 1024

    dg = creer_utilisateur(entreprise_demo, "DG", prenom="Moussa", nom="Diallo", is_owner=True)
    cp = creer_utilisateur(entreprise_demo, "CP", prenom="Sévérin", nom="Zran")
    projet = creer_projet(entreprise_demo, createur=dg, chef_projet=cp)
    affecter_projet(cp, projet, RoleProjet.CHEF_PROJET)

    client_dg = client_pour(dg)
    client_cp = client_pour(cp)

    # 1. Contrat initial (prérequis avenant) + OS initial via PATCH projet par DG
    with django_capture_on_commit_callbacks(execute=True):
        ajouter_contrats(
            projet, [generer_pdf(b"CONTRAT-INIT", "marche_initial.pdf")], dg, []
        )
        rep_os1 = client_dg.patch(
            f"/api/v1/projets/{projet.pk}/",
            {"ordre_service": generer_pdf(b"OS-V1", "os_v1.pdf")},
            format="multipart",
        )
        assert rep_os1.status_code == 200

    # 2. Remplacement de l'OS par CP -> v2 attribuée à CP (et non `projet.cree_par` = DG)
    with django_capture_on_commit_callbacks(execute=True):
        rep_os2 = client_cp.patch(
            f"/api/v1/projets/{projet.pk}/",
            {"ordre_service": generer_pdf(b"OS-V2-BY-CP", "os_v2.pdf")},
            format="multipart",
        )
        assert rep_os2.status_code == 200

    docs_os = [
        d
        for d in client_cp.get(
            f"/api/v1/ged/documents/?projet={projet.pk}&categorie=CONTRATS"
        ).json()["results"]
        if (d.get("source_liaison") or {}).get("sous_type") == "ORDRE_SERVICE"
    ]
    assert len(docs_os) == 1
    assert docs_os[0]["nombre_versions"] == 2
    assert docs_os[0]["version_active"]["auteur"]["id"] == str(cp.pk)

    # 3. Modification d'un champ sans lien avec l'OS (ville) -> aucune nouvelle version créée
    with django_capture_on_commit_callbacks(execute=True):
        rep_ville = client_cp.patch(
            f"/api/v1/projets/{projet.pk}/",
            {"ville": "Yamoussoukro"},
            format="json",
        )
        assert rep_ville.status_code == 200
    with contexte_entreprise(entreprise_demo):
        assert Document.objects.get(pk=docs_os[0]["id"]).versions.count() == 2

    # 4. Enregistrement d'un avenant -> 2 documents auto sous_type="AVENANT"
    with contexte_entreprise(entreprise_demo), django_capture_on_commit_callbacks(execute=True):
        avenant = enregistrer_avenant(
            projet,
            numero="AV-99",
            date_signature=date(2026, 7, 1),
            objet="Travaux supplémentaires voirie",
            jours_accordes=20,
            document=generer_pdf(b"AV99-DOC", "avenant_99.pdf"),
            ordre_service=generer_pdf(b"AV99-OS", "os_avenant_99.pdf"),
            auteur=cp,
        )

    docs_av = [
        d
        for d in client_cp.get(
            f"/api/v1/ged/documents/?projet={projet.pk}&categorie=CONTRATS"
        ).json()["results"]
        if (d.get("source_liaison") or {}).get("sous_type") == "AVENANT"
    ]
    assert len(docs_av) == 2

    # Partager un des documents d'avenant avant retrait
    with contexte_entreprise(entreprise_demo):
        doc_av_obj = Document.objects.get(pk=docs_av[0]["id"])
        partage_av = creer_partage_document(document=doc_av_obj, utilisateur=cp)

    # 5. Retrait de l'avenant via API -> retrait synchronisé GED + révocation partage + audit
    rep_retrait = client_cp.delete(f"/api/v1/avenants/{avenant.pk}/")
    assert rep_retrait.status_code == 204

    docs_av_apres = [
        d
        for d in client_cp.get(
            f"/api/v1/ged/documents/?projet={projet.pk}&categorie=CONTRATS"
        ).json()["results"]
        if (d.get("source_liaison") or {}).get("sous_type") == "AVENANT"
    ]
    assert docs_av_apres == []

    # Lien de partage révoqué -> 410 côté public
    from rest_framework.test import APIClient

    assert (
        APIClient(HTTP_HOST="localhost")
        .get(f"/api/v1/public/partages/{partage_av.jeton}/")
        .status_code
        == 410
    )

    # Audit de suppression enregistré dans JournalAudit pour les 2 pièces retirées
    for d in docs_av:
        assert JournalAudit.objects.filter(
            entreprise_id=entreprise_demo.pk,
            type_entite=TYPE_ENTITE_DOCUMENT_GED,
            entite_id=d["id"],
            action=ActionAudit.SUPPRESSION,
        ).exists()


def test_commande_synchroniser_ged_idempotente_et_migration_prive(entreprise_demo, settings):
    """`manage.py synchroniser_ged` rattrape Contrats/OS/Avenants/Rapports et migre MEDIA_ROOT."""
    dg = creer_utilisateur(entreprise_demo, "DG", is_owner=True)
    projet = creer_projet(entreprise_demo, createur=dg, reference="PRJ-BACKFILL")

    # Créer des pièces F1 & F2 existantes sans exécuter les callbacks on_commit (simule l'existant)
    c1 = ProjetContrat.objects.create(
        projet=projet,
        version=1,
        est_actif=False,
        nom="contrat_v1.pdf",
        type_contenu="application/pdf",
        taille=128,
        cree_par=dg,
    )
    c1.fichier.save("contrat_v1.pdf", generer_pdf(b"BACKFILL-C1", "contrat_v1.pdf"))

    c2 = ProjetContrat.objects.create(
        projet=projet,
        version=2,
        est_actif=True,
        nom="contrat_v2.pdf",
        type_contenu="application/pdf",
        taille=128,
        cree_par=dg,
    )
    c2.fichier.save("contrat_v2.pdf", generer_pdf(b"BACKFILL-C2", "contrat_v2.pdf"))

    projet.ordre_service.save("os_bf.pdf", generer_pdf(b"BACKFILL-OS", "os_bf.pdf"))
    projet.ordre_service_nom = "os_bf.pdf"
    projet.save(update_fields=["ordre_service", "ordre_service_nom"])

    av = Avenant.objects.create(
        projet=projet,
        numero="AV-BF",
        date_signature=date(2026, 6, 1),
        objet="Backfill avenant",
        cree_par=dg,
    )
    av.document.save("av_bf.pdf", generer_pdf(b"BACKFILL-AV", "av_bf.pdf"))
    av.document_nom = "av_bf.pdf"
    av.ordre_service.save("av_os_bf.pdf", generer_pdf(b"BACKFILL-AV-OS", "av_os_bf.pdf"))
    av.ordre_service_nom = "av_os_bf.pdf"
    av.save(update_fields=["document", "document_nom", "ordre_service", "ordre_service_nom"])

    RapportJournalier.objects.create(
        projet=projet,
        date_rapport=date(2026, 6, 2),
        auteur=dg,
        valide_par=dg,
        valide_le=timezone.now(),
        statut=StatutRapport.APPROUVE,
        observations="Journée conforme",
    )

    # Purger toute trace GED éventuelle avant de tester la commande de rattrapage
    LiaisonDocument.tous_objets.all().delete()
    VersionDocument.tous_objets.all().delete()
    Document.tous_objets.all().delete()

    # Planter un fichier historique sous MEDIA_ROOT (ancien stockage public)
    _doc_legacy, ver_legacy = deposer_document(
        projet=projet,
        categorie=CategorieDocument.DIVERS,
        fichier=generer_pdf(b"LEGACY-PUBLIC", "legacy.pdf"),
        nom="Document historique",
        createur=dg,
        notifier=False,
    )
    chemin_legacy = ver_legacy.fichier.name
    # Déplacer artificiellement du coffre privé vers MEDIA_ROOT pour simuler l'avant-migration
    prive_path = Path(settings.GED_STORAGE_ROOT) / chemin_legacy
    contenu_legacy = prive_path.read_bytes()
    prive_path.unlink()
    default_storage.save(chemin_legacy, ContentFile(contenu_legacy))
    assert not prive_path.exists()
    assert default_storage.exists(chemin_legacy)

    # 1. Mode --dry-run : ne modifie rien (hors contexte entreprise, comme en CLI)
    reinitialiser_contexte()
    call_command("synchroniser_ged", "--entreprise", entreprise_demo.slug, "--dry-run")
    with contexte_entreprise(entreprise_demo):
        assert Document.objects.count() == 1
        assert not prive_path.exists()

    # 2. Exécution réelle : 1 legacy + 1 contrat (2 versions) + 1 OS + 2 avenant + 1 rapport = 6
    reinitialiser_contexte()
    call_command("synchroniser_ged", "--entreprise", entreprise_demo.slug)
    with contexte_entreprise(entreprise_demo):
        nb_docs_1 = Document.objects.count()
        nb_versions_1 = VersionDocument.objects.count()
        assert nb_docs_1 == 6
        assert nb_versions_1 == 7  # le contrat a v1 et v2
        assert prive_path.exists()
        assert not default_storage.exists(chemin_legacy)

    # 3. Ré-exécution -> strictement idempotente (zéro doublon)
    reinitialiser_contexte()
    call_command("synchroniser_ged", "--entreprise", entreprise_demo.slug)
    with contexte_entreprise(entreprise_demo):
        assert Document.objects.count() == nb_docs_1
        assert VersionDocument.objects.count() == nb_versions_1
