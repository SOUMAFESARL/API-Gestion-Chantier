import uuid

from django.db import models
from django.db.models.functions import Now
from django.utils import timezone


class ModeleBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, db_default=models.Func(function='gen_random_uuid'), editable=False)
    cree_le = models.DateTimeField(default=timezone.now, db_default=Now(), editable=False)
    modifie_le = models.DateTimeField(default=timezone.now, db_default=Now(), editable=False)
    supprime_le = models.DateTimeField(null=True, blank=True)
    cree_par = models.UUIDField(null=True, blank=True)
    modifie_par = models.UUIDField(null=True, blank=True)
    supprime_par = models.UUIDField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.modifie_le = timezone.now()
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'modifie_le'}
        return super().save(*args, **kwargs)
