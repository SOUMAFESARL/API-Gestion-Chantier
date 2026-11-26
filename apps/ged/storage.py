"""Stockage privé dédié aux documents GED, isolé du dossier public MEDIA_ROOT.

Sur FileSystemStorage (développement local, cPanel / VPS sans S3), les fichiers
sont écrits sous `settings.GED_STORAGE_ROOT` (hors `/media/`), ce qui garantit
qu'aucune pièce confidentielle (contrats, avenants, plans) n'est accessible sans
contrôle d'accès API. En production S3, il délègue au bucket privé `default_storage`.
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage, default_storage
from django.utils.deconstruct import deconstructible


@deconstructible
class StockageGed(Storage):
    """Coffre de stockage privé pour `VersionDocument.fichier`."""

    def _est_local(self) -> bool:
        return isinstance(default_storage, FileSystemStorage)

    def _backend(self):
        if self._est_local():
            racine = getattr(settings, "GED_STORAGE_ROOT", None) or settings.PROJET_CONTRATS_ROOT
            return FileSystemStorage(location=racine)
        return default_storage

    def _open(self, name, mode="rb"):
        backend = self._backend()
        # Repli lecture seule pour d'éventuels fichiers historiques créés avant migration
        # vers le coffre privé (migrés physiquement par `manage.py synchroniser_ged`).
        if (
            "r" in mode
            and self._est_local()
            and not backend.exists(name)
            and default_storage.exists(name)
        ):
            return default_storage.open(name, mode)
        return backend.open(name, mode)

    def _save(self, name, content):
        return self._backend().save(name, content)

    def exists(self, name):
        if self._backend().exists(name):
            return True
        if self._est_local():
            return default_storage.exists(name)
        return False

    def delete(self, name):
        backend = self._backend()
        if backend.exists(name):
            backend.delete(name)

    def size(self, name):
        backend = self._backend()
        if self._est_local() and not backend.exists(name) and default_storage.exists(name):
            return default_storage.size(name)
        return backend.size(name)
