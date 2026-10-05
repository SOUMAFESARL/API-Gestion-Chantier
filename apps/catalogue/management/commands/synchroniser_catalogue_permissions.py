"""Commande de synchronisation du catalogue de permissions depuis le REGISTRE unique.

Règles : A-01, A-02, A-06.
Source unique : apps.core.registre_permissions.REGISTRE.
Exécutée dans le schéma public, strictement idempotente.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

from apps.catalogue.models import CatalogueModule, CataloguePermission
from apps.core.registre_permissions import REGISTRE


class Command(BaseCommand):
    help = "Synchronise CataloguePermission depuis le REGISTRE officiel (idempotent)."

    def handle(self, *args, **options):
        with schema_context(get_public_schema_name()):
            with transaction.atomic():
                self._synchroniser()

    def _synchroniser(self):
        codes_synchronises = set()
        crees = 0
        mis_a_jour = 0

        for code, def_perm in REGISTRE.items():
            codes_synchronises.add(code)
            mod_code = def_perm.module

            # S'assurer que le module du catalogue existe
            module, _ = CatalogueModule.objects.get_or_create(
                code=mod_code,
                defaults={
                    "libelle": mod_code.capitalize(),
                    "ordre": 1,
                    "est_actif": True,
                },
            )

            perm = CataloguePermission.objects.filter(
                code=code, supprime_le__isnull=True
            ).first()

            if perm is None:
                perm = CataloguePermission(
                    code=code,
                    libelle=def_perm.libelle,
                    description=def_perm.libelle,
                    ordre=def_perm.rang,
                    est_actif=True,
                    reservee_administration=def_perm.reservee_administration,
                )
                perm.save()
                perm.modules.set([module])
                crees += 1
            else:
                a_change = False
                if perm.libelle != def_perm.libelle:
                    perm.libelle = def_perm.libelle
                    a_change = True
                if perm.ordre != def_perm.rang:
                    perm.ordre = def_perm.rang
                    a_change = True
                if not perm.est_actif:
                    perm.est_actif = True
                    a_change = True
                if hasattr(perm, "reservee_administration") and perm.reservee_administration != def_perm.reservee_administration:
                    perm.reservee_administration = def_perm.reservee_administration
                    a_change = True

                if a_change:
                    perm.save()
                    mis_a_jour += 1

                # Mettre à jour l'association au module sans casser si déjà présent
                modules_actuels = set(perm.modules.values_list("id", flat=True))
                if modules_actuels != {module.id}:
                    perm.modules.set([module])

        # Désactiver les permissions qui ne sont plus dans le REGISTRE (A-06)
        desactives = 0
        perms_hors_registre = CataloguePermission.objects.filter(
            supprime_le__isnull=True,
            est_actif=True,
        ).exclude(code__in=codes_synchronises)

        for p in perms_hors_registre:
            p.est_actif = False
            p.save(update_fields=["est_actif", "modifie_le"])
            desactives += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Synchronisation terminée : {crees} créées, {mis_a_jour} mises à jour, {desactives} désactivées."
            )
        )
