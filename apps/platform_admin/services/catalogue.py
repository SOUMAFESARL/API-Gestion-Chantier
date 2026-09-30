"""Service de gestion dynamique du catalogue des modules et des permissions avec propagation multi-tenants.

Socle IAM / Super Admin :
Fournit les opérations de création, modification et suppression logique de Modules et de Permissions
exécutées au niveau de la plateforme par le Super Admin, avec propagation immédiate dans tous les
schémas tenants d'entreprises clientes.

Invariants garantis :
1. Tout rôle est obligatoirement lié à TOUS les modules actifs.
2. Lorsqu'un nouveau module apparaît :
   - DG et Administrateur reçoivent toutes les permissions actives.
   - Les autres rôles reçoivent un tableau vide [] de permissions (Zero-Trust).
3. Lorsqu'une nouvelle permission apparaît :
   - Elle est automatiquement ajoutée aux habilitations des rôles DG et Administrateur.
4. La suppression d'un module ou d'une permission est un Soft-Delete (supprime_le non nul, est_actif=False),
   préservant l'intégrité historique des données sans aucune perte.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import schema_context

from apps.accounts.models import Module, Permission, Role, RoleModulePermission
from apps.core.enums import NiveauAcces
from apps.tenants.models import Entreprise

__all__ = [
    "propager_creation_module",
    "propager_creation_permission",
    "propager_modification_module",
    "propager_modification_permission",
    "propager_suppression_module",
    "propager_suppression_permission",
    "synchroniser_modules_et_permissions_nouveau_tenant",
]


def propager_creation_module(
    *,
    code: str,
    libelle: str,
    description: str = "",
    ordre: int = 0,
    icone: str = "box",
    est_actif: bool = True,
    cree_par=None,
) -> Module:
    """Crée un module dans le schéma public et le propage immédiatement à tous les tenants.

    Invariant métier :
    - Dans chaque tenant, tous les rôles existants reçoivent une liaison RoleModulePermission.
    - Pour les rôles DG et ADMIN : toutes les permissions actives sont accordées.
    - Pour les autres rôles : aucune permission accordée (tableau vide []), respectant le Zero-Trust.
    """
    code = code.strip().lower()
    if not code:
        raise ValidationError(_("Le code du module est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé du module est obligatoire."))

    # 1. Création dans le schéma public
    with schema_context("public"):
        if Module.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise ValidationError(_(f"Un module avec le code '{code}' existe déjà."))

        module_public = Module.objects.create(
            code=code,
            libelle=libelle.strip(),
            description=description.strip(),
            ordre=ordre,
            icone=icone.strip() or "box",
            est_actif=est_actif,
            cree_par=cree_par,
        )

    # 2. Propagation dans tous les tenants clients
    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                mod, _ = Module.objects.update_or_create(
                    code=code,
                    defaults={
                        "id": module_public.id,
                        "libelle": libelle.strip(),
                        "description": description.strip(),
                        "ordre": ordre,
                        "icone": icone.strip() or "box",
                        "est_actif": est_actif,
                        "supprime_le": None,
                        "supprime_par": None,
                    },
                )
                perms_actives = list(
                    Permission.objects.filter(est_actif=True, supprime_le__isnull=True)
                )

                roles = Role.objects.filter(supprime_le__isnull=True)
                for role in roles:
                    rmp, _ = RoleModulePermission.objects.get_or_create(
                        role=role,
                        module=mod,
                        defaults={"cree_par": None},
                    )
                    if role.code in ("DG", "ADMIN", "AD") or role.est_systeme:
                        rmp.permissions.set(perms_actives)
                        rmp.niveau = NiveauAcces.VALIDATION
                    else:
                        rmp.permissions.clear()
                        rmp.niveau = NiveauAcces.AUCUN
                    rmp.save()

    return module_public


def propager_modification_module(
    *,
    module_id,
    libelle: str | None = None,
    description: str | None = None,
    ordre: int | None = None,
    icone: str | None = None,
    est_actif: bool | None = None,
    modifie_par=None,
) -> Module:
    """Met à jour un module dans le schéma public et synchronise les métadonnées dans tous les tenants."""
    with schema_context("public"):
        try:
            module_public = Module.objects.get(id=module_id, supprime_le__isnull=True)
        except Module.DoesNotExist:
            raise ValidationError(_("Module introuvable."))

        if libelle is not None and libelle.strip():
            module_public.libelle = libelle.strip()
        if description is not None:
            module_public.description = description.strip()
        if ordre is not None:
            module_public.ordre = ordre
        if icone is not None:
            module_public.icone = icone.strip()
        if est_actif is not None:
            module_public.est_actif = est_actif
        module_public.save()

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                mod = Module.objects.filter(
                    code=module_public.code, supprime_le__isnull=True
                ).first()
                if not mod:
                    mod = Module.objects.filter(
                        id=module_public.id, supprime_le__isnull=True
                    ).first()
                if mod:
                    if libelle is not None and libelle.strip():
                        mod.libelle = libelle.strip()
                    if description is not None:
                        mod.description = description.strip()
                    if ordre is not None:
                        mod.ordre = ordre
                    if icone is not None:
                        mod.icone = icone.strip()
                    if est_actif is not None:
                        mod.est_actif = est_actif
                    mod.save()

    return module_public


def propager_suppression_module(*, module_id, supprime_par=None) -> dict:
    """Soft-delete un module dans public et dans tous les tenants (supprime_le = now(), est_actif = False)."""
    maintenant = timezone.now()
    code_supprime = ""
    with schema_context("public"):
        try:
            module_public = Module.objects.get(id=module_id, supprime_le__isnull=True)
        except Module.DoesNotExist:
            raise ValidationError(_("Module introuvable ou déjà supprimé."))

        code_supprime = module_public.code
        module_public.supprime_le = maintenant
        module_public.supprime_par = supprime_par
        module_public.est_actif = False
        module_public.save()

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                Module.objects.filter(
                    code=code_supprime, supprime_le__isnull=True
                ).update(
                    supprime_le=maintenant,
                    supprime_par=None,
                    est_actif=False,
                )

    return {"module_supprime": code_supprime}


def propager_creation_permission(
    *,
    code: str,
    libelle: str,
    description: str = "",
    ordre: int = 0,
    est_actif: bool = True,
    cree_par=None,
) -> Permission:
    """Crée une permission dans public et la propage à tous les tenants.

    Dans chaque tenant, cette nouvelle permission est automatiquement ajoutée aux rôles DG et ADMIN
    pour tous les modules actifs.
    """
    code = code.strip().upper()
    if not code:
        raise ValidationError(_("Le code de la permission est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé de la permission est obligatoire."))

    with schema_context("public"):
        if Permission.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise ValidationError(_(f"Une permission avec le code '{code}' existe déjà."))

        perm_public = Permission.objects.create(
            code=code,
            libelle=libelle.strip(),
            description=description.strip(),
            ordre=ordre,
            est_actif=est_actif,
            cree_par=cree_par,
        )

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                perm_tenant, _ = Permission.objects.update_or_create(
                    code=code,
                    defaults={
                        "id": perm_public.id,
                        "libelle": libelle.strip(),
                        "description": description.strip(),
                        "ordre": ordre,
                        "est_actif": est_actif,
                        "supprime_le": None,
                        "supprime_par": None,
                    },
                )
                roles_direction = Role.objects.filter(
                    code__in=["DG", "ADMIN", "AD"], supprime_le__isnull=True
                )
                for role in roles_direction:
                    for rmp in RoleModulePermission.objects.filter(
                        role=role, supprime_le__isnull=True
                    ):
                        rmp.permissions.add(perm_tenant)

    return perm_public


def propager_modification_permission(
    *,
    permission_id,
    libelle: str | None = None,
    description: str | None = None,
    ordre: int | None = None,
    est_actif: bool | None = None,
    modifie_par=None,
) -> Permission:
    """Modifie une permission dans public et synchronise ses métadonnées dans tous les tenants."""
    with schema_context("public"):
        try:
            perm_public = Permission.objects.get(id=permission_id, supprime_le__isnull=True)
        except Permission.DoesNotExist:
            raise ValidationError(_("Permission introuvable."))

        if libelle is not None and libelle.strip():
            perm_public.libelle = libelle.strip()
        if description is not None:
            perm_public.description = description.strip()
        if ordre is not None:
            perm_public.ordre = ordre
        if est_actif is not None:
            perm_public.est_actif = est_actif
        perm_public.save()

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                perm = Permission.objects.filter(
                    code=perm_public.code, supprime_le__isnull=True
                ).first()
                if not perm:
                    perm = Permission.objects.filter(
                        id=perm_public.id, supprime_le__isnull=True
                    ).first()
                if perm:
                    if libelle is not None and libelle.strip():
                        perm.libelle = libelle.strip()
                    if description is not None:
                        perm.description = description.strip()
                    if ordre is not None:
                        perm.ordre = ordre
                    if est_actif is not None:
                        perm.est_actif = est_actif
                    perm.save()

    return perm_public


def propager_suppression_permission(*, permission_id, supprime_par=None) -> dict:
    """Soft-delete une permission dans public et dans tous les tenants."""
    maintenant = timezone.now()
    code_supprime = ""
    with schema_context("public"):
        try:
            perm_public = Permission.objects.get(id=permission_id, supprime_le__isnull=True)
        except Permission.DoesNotExist:
            raise ValidationError(_("Permission introuvable ou déjà supprimée."))

        code_supprime = perm_public.code
        perm_public.supprime_le = maintenant
        perm_public.supprime_par = supprime_par
        perm_public.est_actif = False
        perm_public.save()

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                Permission.objects.filter(
                    code=code_supprime, supprime_le__isnull=True
                ).update(
                    supprime_le=maintenant,
                    supprime_par=None,
                    est_actif=False,
                )

    return {"permission_supprimee": code_supprime}


def synchroniser_modules_et_permissions_nouveau_tenant(schema_name: str) -> None:
    """Synchronise l'ensemble du catalogue maître de public vers un nouveau tenant à sa création."""
    if schema_name == "public":
        return

    with schema_context("public"):
        modules_publics = list(Module.objects.filter(supprime_le__isnull=True))
        permissions_publiques = list(Permission.objects.filter(supprime_le__isnull=True))

    with schema_context(schema_name):
        with transaction.atomic():
            for p in permissions_publiques:
                Permission.objects.update_or_create(
                    code=p.code,
                    defaults={
                        "id": p.id,
                        "libelle": p.libelle,
                        "description": p.description,
                        "ordre": p.ordre,
                        "est_actif": p.est_actif,
                    },
                )
            for m in modules_publics:
                Module.objects.update_or_create(
                    code=m.code,
                    defaults={
                        "id": m.id,
                        "libelle": m.libelle,
                        "description": m.description,
                        "ordre": m.ordre,
                        "icone": m.icone,
                        "est_actif": m.est_actif,
                    },
                )
