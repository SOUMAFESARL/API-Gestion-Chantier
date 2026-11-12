"""Modèle VersionDocument — Historique des révisions de fichiers (F6 MVP).

Versioning sans perte : v1 -> v2... Toutes les versions sont conservées.
Stockage clé fichier, taille max 50 Mo, formats autorisés et empreinte SHA-256.
Table d'entreprise (`ModeleEntreprise` — isolation D9).
"""

import contextlib
import hashlib
import mimetypes
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import ModeleEntreprise
from apps.entreprises.selectors import slug_courant
from apps.ged.models.exceptions import (
    FormatFichierNonAutorise,
    SuppressionVersionInterdite,
    TailleFichierDepassee,
)

# Périmètre MVP F6 (§2)
EXTENSIONS_AUTORISEES = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".xlsx"}
TAILLE_MAX_OCTETS = 50 * 1024 * 1024  # 50 Mo


def chemin_version_document(instance, filename: str) -> str:
    """Clé de stockage S3/local sous la forme `{slug}/ged/{document_id}/v{version}_{nom}`."""
    slug = slug_courant() or "plateforme"
    doc_id = instance.document_id or "temp"
    v = instance.numero_version or 1
    clean_filename = Path(filename).name
    return f"{slug}/ged/{doc_id}/v{v}_{clean_filename}"


def calculer_hash_fichier(fichier) -> str:
    """Calcule l'empreinte SHA-256 hexadécimale d'un fichier."""
    hasher = hashlib.sha256()
    pos = fichier.tell() if hasattr(fichier, "tell") else 0
    if hasattr(fichier, "seek"):
        fichier.seek(0)
    if hasattr(fichier, "chunks"):
        for chunk in fichier.chunks():
            hasher.update(chunk)
    else:
        for chunk in iter(lambda: fichier.read(65536), b""):
            if not chunk:
                break
            hasher.update(chunk)
    if hasattr(fichier, "seek"):
        fichier.seek(pos)
    return hasher.hexdigest()


class VersionDocument(ModeleEntreprise):
    """Version horodatée d'un document avec fichier physique et empreinte de contrôle."""

    document = models.ForeignKey(
        "ged.Document",
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("document"),
        db_index=True,
    )
    numero_version = models.PositiveIntegerField(
        _("numéro de version"),
        default=1,
        help_text=_("Numéro séquentiel de version (1 pour v1, 2 pour v2...)."),
    )
    fichier = models.FileField(
        _("fichier"),
        upload_to=chemin_version_document,
        max_length=500,
        help_text=_("Fichier physique (formats acceptés : PDF, JPG, PNG, DOCX, XLSX ; max 50 Mo)."),
    )
    taille = models.PositiveBigIntegerField(
        _("taille"),
        help_text=_("Taille en octets (maximum 50 Mo)."),
    )
    mime_type = models.CharField(
        _("type MIME"),
        max_length=100,
        blank=True,
        help_text=_("Type MIME détecté (ex. application/pdf, image/jpeg)."),
    )
    hash_sha256 = models.CharField(
        _("empreinte SHA-256"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("Empreinte hexadécimale SHA-256 du fichier pour garantie d'intégrité."),
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="versions_documents_deposees",
        verbose_name=_("auteur / déposé par"),
        help_text=_("Collaborateur ayant déposé cette version."),
    )
    commentaire = models.TextField(
        _("commentaire de version"),
        blank=True,
        default="",
        help_text=_("Note facultative expliquant les modifications de cette révision."),
    )
    est_active = models.BooleanField(
        _("version active"),
        default=True,
        db_index=True,
        help_text=_("Indique si cette révision est la version de référence courante."),
    )

    class Meta:
        db_table = "version_document"
        verbose_name = _("version de document")
        verbose_name_plural = _("versions de documents")
        ordering = ["document", "-numero_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "numero_version"],
                name="uq_version_document_numero",
            ),
        ]
        indexes = [
            models.Index(fields=["document", "est_active"], name="idx_ver_doc_active"),
            models.Index(fields=["hash_sha256"], name="idx_ver_doc_sha256"),
        ]

    def __str__(self) -> str:
        return f"{self.document.nom} (v{self.numero_version})"

    # -- Propriétés de commodité & compatibilité MLD ------------------------

    @property
    def numero(self) -> str:
        """Représentation textuelle de la version (v1, v2...)."""
        return f"v{self.numero_version}"

    @property
    def date(self):
        """Date de dépôt de cette version."""
        return self.cree_le

    @property
    def taille_octets(self) -> int:
        """Alias pour `taille` (MLD §5.7)."""
        return self.taille

    @taille_octets.setter
    def taille_octets(self, val: int) -> None:
        self.taille = val

    @property
    def type_mime(self) -> str:
        """Alias pour `mime_type` (MLD §5.7)."""
        return self.mime_type

    @type_mime.setter
    def type_mime(self, val: str) -> None:
        self.mime_type = val

    @property
    def depose_par(self):
        """Alias pour `auteur` (MLD §5.7)."""
        return self.auteur

    @depose_par.setter
    def depose_par(self, val) -> None:
        self.auteur = val

    # -- Intégrité et conservation sans perte --------------------------------

    def delete(self, using=None, keep_parents=False, utilisateur=None):
        """Interdit la suppression d'une version individuelle (conservation sans perte F6 §2)."""
        raise SuppressionVersionInterdite()

    def clean(self):
        super().clean()
        self._valider_fichier()

    def _valider_fichier(self) -> None:
        """Contrôle d'extension et de taille maximale (50 Mo)."""
        if self.fichier:
            nom_fichier = getattr(self.fichier, "name", "")
            if nom_fichier:
                ext = Path(nom_fichier).suffix.lower()
                if ext not in EXTENSIONS_AUTORISEES:
                    raise FormatFichierNonAutorise()

            if (
                hasattr(self.fichier, "size")
                and self.fichier.size
                and self.fichier.size > TAILLE_MAX_OCTETS
            ):
                raise TailleFichierDepassee()

        if self.taille and self.taille > TAILLE_MAX_OCTETS:
            raise TailleFichierDepassee()

    def save(self, *args, **kwargs):
        # Propagation de l'entreprise depuis le document parent
        if not self.entreprise_id and self.document_id:
            self.entreprise_id = self.document.entreprise_id

        # Synchronisation auteur / cree_par du socle
        if self.auteur_id and not self.cree_par_id:
            self.cree_par_id = self.auteur_id
        elif self.cree_par_id and not self.auteur_id:
            self.auteur_id = self.cree_par_id

        # Validation de cohérence de fichier
        self._valider_fichier()

        # Calcul automatique de la taille si non spécifiée
        if not self.taille and self.fichier and hasattr(self.fichier, "size"):
            self.taille = self.fichier.size

        # Détection du type MIME si non renseigné
        if not self.mime_type and self.fichier:
            nom = getattr(self.fichier, "name", "")
            type_devine, _ = mimetypes.guess_type(nom)
            self.mime_type = type_devine or "application/octet-stream"

        # Calcul de l'empreinte SHA-256 si le fichier physique est accessible
        if not self.hash_sha256 and self.fichier:
            with contextlib.suppress(Exception):
                self.hash_sha256 = calculer_hash_fichier(self.fichier)

        # Attribution automatique du numéro séquentiel à la création
        if not self.pk and self.document_id:
            max_v = VersionDocument.tous_objets.filter(
                document_id=self.document_id
            ).aggregate(max_num=models.Max("numero_version"))["max_num"]
            if max_v is not None and max_v >= 1:
                self.numero_version = max_v + 1
            elif not self.numero_version:
                self.numero_version = 1

        super().save(*args, **kwargs)

        # Si cette version est active, désactiver les autres versions du même document
        if self.est_active and self.document_id:
            VersionDocument.tous_objets.filter(
                document_id=self.document_id,
                est_active=True,
            ).exclude(pk=self.pk).update(est_active=False)
