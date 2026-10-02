"""Private contract storage, independent of publicly served MEDIA_ROOT."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage, default_storage
from django.utils.deconstruct import deconstructible


@deconstructible
class StockageContrats(Storage):
    """Use private filesystem locally and the configured object store in production."""

    def _backend(self):
        if isinstance(default_storage, FileSystemStorage):
            return FileSystemStorage(location=settings.PROJET_CONTRATS_ROOT)
        return default_storage

    def _open(self, name, mode="rb"):
        return self._backend().open(name, mode)

    def _save(self, name, content):
        return self._backend().save(name, content)

    def exists(self, name):
        return self._backend().exists(name)

    def delete(self, name):
        return self._backend().delete(name)

    def size(self, name):
        return self._backend().size(name)
