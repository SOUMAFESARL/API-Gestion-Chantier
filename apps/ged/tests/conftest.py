"""Fixtures et générateurs de fichiers partagés pour la suite de tests GED (F6)."""

from __future__ import annotations

import io
import uuid
from datetime import date

import pytest
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils.functional import empty
from pypdf import PdfReader, PdfWriter
from rest_framework.test import APIClient

from apps.accounts.models import Role, Utilisateur
from apps.accounts.services.authentification import emettre_jetons
from apps.core.contexte import contexte_entreprise, reinitialiser_contexte
from apps.core.enums import (
    RoleGlobal,
    RoleProjet,
    StatutEntreprise,
    StatutProjet,
    StatutUtilisateur,
)
from apps.entreprises.models import Entreprise
from apps.projets.models import AffectationProjet, Projet

SLUG_DEMO = "demo"
SLUG_AUTRE = "autre-btp"

# PNG 1x1 valide (magic bytes \x89PNG\r\n\x1a\n)
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def generer_pdf(marqueur: bytes = b"v1", nom: str = "document.pdf") -> SimpleUploadedFile:
    """Construit un PDF 1 page valide accepté par `filetype` et `pypdf.PdfReader`."""
    tampon = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": marqueur.decode("latin-1")})
    writer.write(tampon)
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="application/pdf")


def titre_pdf_reponse(reponse) -> str:
    """Lit le titre PDF d'une `FileResponse` et valide l'intégrité binaire du flux."""
    octets = b"".join(reponse.streaming_content)
    reader = PdfReader(io.BytesIO(octets))
    return str((reader.metadata or {}).get("/Title") or "")


def code_erreur(reponse) -> str | None:
    """Extrait le code d'erreur normalisé CCD Digital (`erreur.code` ou `code`)."""
    corps = reponse.json()
    if isinstance(corps, dict) and isinstance(corps.get("erreur"), dict):
        return corps["erreur"].get("code")
    return corps.get("code") if isinstance(corps, dict) else None


def generer_png(nom: str = "photo_chantier.png") -> SimpleUploadedFile:
    """Construit une image PNG 1x1 valide reconnue par `filetype`."""
    return SimpleUploadedFile(nom, _PNG_1X1, content_type="image/png")


def client_pour(utilisateur: Utilisateur) -> APIClient:
    """Retourne un `APIClient` authentifié via un vrai JWT (D9)."""
    jeton = emettre_jetons(utilisateur)["access"]
    client = APIClient(HTTP_HOST="localhost")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {jeton}")
    return client


def creer_utilisateur(
    entreprise: Entreprise,
    role_code: str,
    *,
    prenom: str = "Agent",
    nom: str = "Test",
    is_owner: bool = False,
) -> Utilisateur:
    """Crée un utilisateur rattaché au rôle système `role_code` dans `entreprise`."""
    code = role_code.upper()
    with contexte_entreprise(entreprise):
        role = Role.objects.filter(code=code).first()
        assert role is not None, f"Rôle système '{code}' introuvable dans {entreprise.slug}"
        role_global = code if code in RoleGlobal.values else RoleGlobal.VISITEUR
        user = Utilisateur.objects.create_user(
            email=f"{code.lower()}-{uuid.uuid4().hex[:8]}@{entreprise.slug}.ci",
            password="TestPassword123!",
            prenom=prenom,
            nom=nom,
            role_global=role_global,
            role=role,
            statut=StatutUtilisateur.ACTIF,
        )
        if is_owner or code == "DG":
            user.is_owner = True
            user.save(update_fields=["is_owner", "modifie_le"])
        return user


def creer_projet(
    entreprise: Entreprise,
    *,
    createur: Utilisateur | None = None,
    chef_projet: Utilisateur | None = None,
    nom: str = "Résidence Les Palmiers",
    reference: str | None = None,
) -> Projet:
    """Crée un projet actif dans le contexte de `entreprise`."""
    with contexte_entreprise(entreprise):
        return Projet.objects.create(
            reference=reference or f"PRJ-{uuid.uuid4().hex[:6].upper()}",
            nom=nom,
            ville="Abidjan",
            quartier="Cocody",
            statut=StatutProjet.EN_COURS,
            date_debut_prevue=date(2026, 5, 1),
            date_fin_prevue=date(2026, 12, 31),
            cree_par=createur,
            chef_projet=chef_projet,
        )


def affecter_projet(
    utilisateur: Utilisateur,
    projet: Projet,
    role_projet: str = RoleProjet.CHEF_CHANTIER,
) -> AffectationProjet:
    """Affecte activement un utilisateur à un projet."""
    with contexte_entreprise(projet.entreprise_id):
        return AffectationProjet.objects.create(
            projet=projet,
            utilisateur=utilisateur,
            role_projet=role_projet,
            est_actif=True,
        )


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        from apps.catalogue.models import ModeleRole

        if not ModeleRole._base_manager.exists():
            call_command("ensemencer_plateforme")
        call_command("synchroniser_catalogue_permissions")
        for slug, raison in (
            (SLUG_DEMO, "Entreprise BTP Démo"),
            (SLUG_AUTRE, "Concurrent BTP SA"),
        ):
            if not Entreprise.objects.filter(slug=slug).exists():
                Entreprise.objects.create(
                    slug=slug,
                    raison_sociale=raison,
                    email_contact=f"contact@{slug}.ci",
                    statut=StatutEntreprise.ACTIF,
                )
        call_command("propager_roles_systeme")
    return django_db_setup


@pytest.fixture(autouse=True)
def _isolation_runtime(settings, tmp_path):
    """Isole le cache, le contexte D9 et les répertoires de stockage par test."""
    cache.clear()
    reinitialiser_contexte()

    media_dir = tmp_path / "media_public"
    prive_dir = tmp_path / "media_prive_ged"
    contrats_dir = tmp_path / "media_prive_contrats"
    media_dir.mkdir(parents=True, exist_ok=True)
    prive_dir.mkdir(parents=True, exist_ok=True)
    contrats_dir.mkdir(parents=True, exist_ok=True)

    settings.MEDIA_ROOT = str(media_dir)
    settings.GED_STORAGE_ROOT = str(prive_dir)
    settings.PROJET_CONTRATS_ROOT = str(contrats_dir)
    default_storage._wrapped = empty

    yield

    default_storage._wrapped = empty
    cache.clear()
    reinitialiser_contexte()


@pytest.fixture
def entreprise_demo() -> Entreprise:
    entreprise = Entreprise.objects.get(slug=SLUG_DEMO)
    with contexte_entreprise(entreprise):
        yield entreprise


@pytest.fixture
def entreprise_autre() -> Entreprise:
    return Entreprise.objects.get(slug=SLUG_AUTRE)
