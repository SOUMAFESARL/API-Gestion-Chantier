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
from apps.catalogue.models import CatalogueModule, CataloguePermission, EntrepriseModule
from apps.core.enums import NiveauAcces
from apps.tenants.models import Entreprise

__all__ = [
    "propager_affectation_modules_permission",
    "propager_affectation_permissions_module",
    "propager_creation_module",
    "propager_creation_permission",
    "propager_modification_module",
    "propager_modification_permission",
    "propager_suppression_module",
    "propager_suppression_permission",
    "synchroniser_modules_et_permissions_nouveau_tenant",
]


def _resoudre_permissions_codes(permissions_input) -> list[str]:
    """Extrait la liste des codes techniques normalisés à partir d'un ensemble de codes ou d'identifiants de permissions."""
    if not permissions_input:
        return []
    codes = set()
    from uuid import UUID
    for p in permissions_input:
        if isinstance(p, dict):
            p_val = p.get("code") or p.get("id")
        else:
            p_val = p
        if not p_val:
            continue
        p_str = str(p_val).strip()
        try:
            val_uuid = UUID(p_str)
            perm = Permission.objects.filter(id=val_uuid, supprime_le__isnull=True).first()
            if perm:
                codes.add(perm.code.upper())
        except (ValueError, AttributeError):
            codes.add(p_str.upper())
    return sorted(codes)


def propager_creation_module(
    *,
    code: str,
    libelle: str,
    description: str = "",
    ordre: int = 0,
    icone: str = "box",
    est_actif: bool = True,
    permissions: list | None = None,
    cree_par=None,
) -> Module:
    """Crée un module dans le schéma public et le propage immédiatement à tous les tenants.

    Invariant métier :
    - Dans chaque tenant, tous les rôles existants reçoivent une liaison RoleModulePermission.
    - Si des permissions sont associées au module :
      * Ce sont ces permissions qui sont attachées au module dans public et dans les tenants.
      * DG et Administrateur reçoivent ces permissions éligibles.
    - Si aucune permission n'est spécifiée :
      * DG et Administrateur reçoivent toutes les permissions actives de la plateforme.
    - Pour les autres rôles : aucune permission accordée (tableau vide []), respectant le Zero-Trust.
    """
    code = code.strip().lower()
    if not code:
        raise ValidationError(_("Le code du module est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé du module est obligatoire."))

    codes_perms = _resoudre_permissions_codes(permissions)

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
        if codes_perms:
            perms_pub = list(Permission.objects.filter(code__in=codes_perms, supprime_le__isnull=True))
            module_public.permissions.set(perms_pub)

        # Synchroniser CatalogueModule dans public
        cat_mod, _ = CatalogueModule.objects.update_or_create(
            id=module_public.id,
            defaults={
                "code": code,
                "libelle": libelle.strip(),
                "description": description.strip(),
                "ordre": ordre,
                "icone": icone.strip() or "box",
                "est_actif": est_actif,
                "cree_par": cree_par,
                "supprime_le": None,
            },
        )
        if codes_perms:
            cat_perms = list(CataloguePermission.objects.filter(code__in=codes_perms, supprime_le__isnull=True))
            cat_mod.permissions.set(cat_perms)
        else:
            cat_perms = []

        for entreprise in Entreprise.objects.exclude(schema_name="public"):
            EntrepriseModule.objects.update_or_create(
                entreprise=entreprise,
                module=cat_mod,
                defaults={"est_actif": est_actif},
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

                if codes_perms:
                    perms_tenant = list(
                        Permission.objects.filter(code__in=codes_perms, supprime_le__isnull=True)
                    )
                    mod.permissions.set(perms_tenant)
                    perms_direction = perms_tenant
                else:
                    perms_direction = list(
                        Permission.objects.filter(est_actif=True, supprime_le__isnull=True)
                    )

                roles = Role.objects.filter(supprime_le__isnull=True)
                for role in roles:
                    rmp, _ = RoleModulePermission.objects.get_or_create(
                        role=role,
                        module=mod,
                        defaults={"cree_par": None, "module_catalogue": cat_mod},
                    )
                    rmp.module_catalogue = cat_mod
                    if role.code in ("DG", "DIRECTEUR_GENERAL"):
                        rmp.permissions.set(perms_direction)
                        if codes_perms:
                            rmp.permissions_catalogue.set(cat_perms)
                        else:
                            rmp.permissions_catalogue.set(list(CataloguePermission.objects.filter(est_actif=True, supprime_le__isnull=True)))
                        rmp.niveau = NiveauAcces.VALIDATION
                    else:
                        rmp.permissions.clear()
                        rmp.permissions_catalogue.clear()
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
    permissions: list | None = None,
    modifie_par=None,
) -> Module:
    """Met à jour un module dans le schéma public et synchronise les métadonnées et permissions dans tous les tenants."""
    codes_perms = _resoudre_permissions_codes(permissions) if permissions is not None else None

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

        if codes_perms is not None:
            perms_pub = list(Permission.objects.filter(code__in=codes_perms, supprime_le__isnull=True))
            module_public.permissions.set(perms_pub)

        module_public.save()

        # Synchroniser CatalogueModule dans public
        cat_mod = CatalogueModule.objects.filter(id=module_public.id).first()
        if cat_mod:
            if libelle is not None and libelle.strip():
                cat_mod.libelle = libelle.strip()
            if description is not None:
                cat_mod.description = description.strip()
            if ordre is not None:
                cat_mod.ordre = ordre
            if icone is not None:
                cat_mod.icone = icone.strip()
            if est_actif is not None:
                cat_mod.est_actif = est_actif
            if modifie_par:
                cat_mod.modifie_par = modifie_par
            cat_mod.save()
            if codes_perms is not None:
                cat_perms = list(CataloguePermission.objects.filter(code__in=codes_perms, supprime_le__isnull=True))
                cat_mod.permissions.set(cat_perms)

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

                    if codes_perms is not None:
                        anciennes_codes = set(mod.permissions.values_list("code", flat=True))
                        nouvelles_codes = set(codes_perms)
                        codes_ajoutes = nouvelles_codes - anciennes_codes
                        codes_retires = anciennes_codes - nouvelles_codes

                        perms_tenant = list(
                            Permission.objects.filter(code__in=nouvelles_codes, supprime_le__isnull=True)
                        )
                        mod.permissions.set(perms_tenant)

                        # 1. Révocation des permissions retirées du module sur tous les rôles
                        if codes_retires:
                            perms_retires = list(Permission.objects.filter(code__in=codes_retires))
                            for rmp in RoleModulePermission.objects.filter(module=mod, supprime_le__isnull=True):
                                rmp.permissions.remove(*perms_retires)

                        # 2. Attribution automatique des nouvelles permissions aux rôles de direction (DG/ADMIN)
                        if codes_ajoutes:
                            perms_ajoutes = list(
                                Permission.objects.filter(code__in=codes_ajoutes, supprime_le__isnull=True)
                            )
                            roles_direction = Role.objects.filter(
                                code__in=["DG", "ADMIN", "AD"], supprime_le__isnull=True
                            )
                            for role in roles_direction:
                                rmp = RoleModulePermission.objects.filter(
                                    role=role, module=mod, supprime_le__isnull=True
                                ).first()
                                if rmp:
                                    rmp.permissions.add(*perms_ajoutes)

    return module_public


def propager_affectation_permissions_module(
    *,
    module_id,
    permissions: list,
    modifie_par=None,
) -> Module:
    """Affecte ou remplace la liste des autorisations autorisées pour un module donné et synchronise les tenants."""
    return propager_modification_module(
        module_id=module_id,
        permissions=permissions,
        modifie_par=modifie_par,
    )


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

        CatalogueModule.objects.filter(id=module_id).update(
            supprime_le=maintenant,
            supprime_par=supprime_par,
            est_actif=False,
        )

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
                RoleModulePermission.objects.filter(
                    module__code=code_supprime, supprime_le__isnull=True
                ).update(
                    supprime_le=maintenant,
                    supprime_par=None,
                )
                RoleModulePermission.objects.filter(
                    module_catalogue__code=code_supprime, supprime_le__isnull=True
                ).update(
                    supprime_le=maintenant,
                    supprime_par=None,
                )
                try:
                    from apps.projets.models import ProjetRoleModuleOverride
                    ProjetRoleModuleOverride.objects.filter(
                        module__code=code_supprime, supprime_le__isnull=True
                    ).update(
                        supprime_le=maintenant,
                        supprime_par=None,
                    )
                    ProjetRoleModuleOverride.objects.filter(
                        module_catalogue__code=code_supprime, supprime_le__isnull=True
                    ).update(
                        supprime_le=maintenant,
                        supprime_par=None,
                    )
                except LookupError:
                    pass

    return {
        "module_supprime": code_supprime,
        "message": _("Module et autorisations associées supprimés avec succès."),
    }


def _resoudre_modules_codes(modules_input) -> list[str]:
    """Extrait la liste des codes techniques normalisés à partir d'un ensemble de codes ou d'identifiants."""
    if not modules_input:
        return []
    codes = set()
    from uuid import UUID
    for m in modules_input:
        if isinstance(m, dict):
            m_val = m.get("code") or m.get("id")
        else:
            m_val = m
        if not m_val:
            continue
        m_str = str(m_val).strip()
        try:
            val_uuid = UUID(m_str)
            mod = Module.objects.filter(id=val_uuid, supprime_le__isnull=True).first()
            if mod:
                codes.add(mod.code.lower())
        except (ValueError, AttributeError):
            codes.add(m_str.lower())
    return sorted(codes)


def propager_creation_permission(
    *,
    code: str,
    libelle: str,
    description: str = "",
    ordre: int = 0,
    est_actif: bool = True,
    modules: list | None = None,
    cree_par=None,
) -> Permission:
    """Crée une permission dans public et la propage de façon ciblée à tous les tenants.

    Invariant métier (Module-Scoped Permissions) :
    - Si des modules sont spécifiés, la permission est liée à ces modules dans public et dans les tenants.
    - Seuls les RoleModulePermission correspondant aux modules spécifiés reçoivent cette permission pour DG/ADMIN.
    - Si aucun module n'est spécifié, la permission est créée sans aucun rattachement (Zero-Trust).
    """
    code = code.strip().upper()
    if not code:
        raise ValidationError(_("Le code de la permission est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé de la permission est obligatoire."))

    codes_modules: list[str] = []
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

        codes_modules = _resoudre_modules_codes(modules)
        if codes_modules:
            mods_public = list(Module.objects.filter(code__in=codes_modules, supprime_le__isnull=True))
            perm_public.modules.set(mods_public)

        # Synchroniser CataloguePermission dans public
        cat_perm, _ = CataloguePermission.objects.update_or_create(
            id=perm_public.id,
            defaults={
                "code": code,
                "libelle": libelle.strip(),
                "description": description.strip(),
                "ordre": ordre,
                "est_actif": est_actif,
                "cree_par": cree_par,
                "supprime_le": None,
            },
        )
        if codes_modules:
            cat_mods = list(CatalogueModule.objects.filter(code__in=codes_modules, supprime_le__isnull=True))
            cat_perm.modules.set(cat_mods)
        else:
            cat_mods = []

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                perm_tenant, _cree = Permission.objects.update_or_create(
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
                if codes_modules:
                    mods_tenant = list(Module.objects.filter(code__in=codes_modules, supprime_le__isnull=True))
                    perm_tenant.modules.set(mods_tenant)

                    roles_direction = Role.objects.filter(
                        code__in=["DG", "DIRECTEUR_GENERAL"], supprime_le__isnull=True
                    )
                    for role in roles_direction:
                        for rmp in RoleModulePermission.objects.filter(
                            role=role, module__in=mods_tenant, supprime_le__isnull=True
                        ):
                            rmp.permissions.add(perm_tenant)
                else:
                    perm_tenant.modules.clear()

    return perm_public


def propager_affectation_modules_permission(
    *,
    permission_id,
    modules: list,
    modifie_par=None,
) -> Permission:
    """Affecte ou modifie la liste des modules éligibles pour une permission donnée et synchronise les tenants.

    Règles de sécurité :
    - Les modules nouvellement affectés accordent la permission aux rôles DG et ADMIN dans chaque tenant.
    - Les modules retirés révoquent immédiatement la permission de TOUS les rôles sur ce module.
    """
    with schema_context("public"):
        try:
            perm_public = Permission.objects.get(id=permission_id, supprime_le__isnull=True)
        except Permission.DoesNotExist:
            raise ValidationError(_("Permission introuvable."))

        codes_modules = _resoudre_modules_codes(modules)
        mods_public = list(Module.objects.filter(code__in=codes_modules, supprime_le__isnull=True))
        perm_public.modules.set(mods_public)
        if modifie_par:
            perm_public.modifie_par = modifie_par
            perm_public.save()

        # Synchroniser CataloguePermission dans public
        cat_perm = CataloguePermission.objects.filter(id=permission_id).first()
        if cat_perm:
            cat_mods = list(CatalogueModule.objects.filter(code__in=codes_modules, supprime_le__isnull=True))
            cat_perm.modules.set(cat_mods)

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name):
            with transaction.atomic():
                perm_tenant = Permission.objects.filter(code=perm_public.code, supprime_le__isnull=True).first()
                if not perm_tenant:
                    perm_tenant = Permission.objects.filter(id=perm_public.id, supprime_le__isnull=True).first()

                if perm_tenant:
                    anciennes_codes = set(perm_tenant.modules.values_list("code", flat=True))
                    nouvelles_codes = set(codes_modules)
                    codes_ajoutes = nouvelles_codes - anciennes_codes
                    codes_retires = anciennes_codes - nouvelles_codes

                    mods_tenant = list(Module.objects.filter(code__in=nouvelles_codes, supprime_le__isnull=True))
                    perm_tenant.modules.set(mods_tenant)

                    # 1. Révocation immédiate sur les modules désélectionnés
                    if codes_retires:
                        rmp_retires = RoleModulePermission.objects.filter(
                            module__code__in=codes_retires,
                            supprime_le__isnull=True,
                        )
                        for rmp in rmp_retires:
                            rmp.permissions.remove(perm_tenant)

                    # 2. Ajout pour DG/ADMIN sur les modules nouvellement autorisés
                    if codes_ajoutes:
                        roles_direction = Role.objects.filter(
                            code__in=["DG", "ADMIN", "AD"], supprime_le__isnull=True
                        )
                        rmp_ajoutes = RoleModulePermission.objects.filter(
                            role__in=roles_direction,
                            module__code__in=codes_ajoutes,
                            supprime_le__isnull=True,
                        )
                        for rmp in rmp_ajoutes:
                            rmp.permissions.add(perm_tenant)

    return perm_public


def propager_modification_permission(
    *,
    permission_id,
    libelle: str | None = None,
    description: str | None = None,
    ordre: int | None = None,
    est_actif: bool | None = None,
    modules: list | None = None,
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

        # Synchroniser CataloguePermission dans public
        cat_perm = CataloguePermission.objects.filter(id=permission_id).first()
        if cat_perm:
            if libelle is not None and libelle.strip():
                cat_perm.libelle = libelle.strip()
            if description is not None:
                cat_perm.description = description.strip()
            if ordre is not None:
                cat_perm.ordre = ordre
            if est_actif is not None:
                cat_perm.est_actif = est_actif
            cat_perm.save()

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

    if modules is not None:
        propager_affectation_modules_permission(
            permission_id=permission_id,
            modules=modules,
            modifie_par=modifie_par,
        )

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

        CataloguePermission.objects.filter(id=permission_id).update(
            supprime_le=maintenant,
            supprime_par=supprime_par,
            est_actif=False,
        )

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
        permissions_publiques = list(
            Permission.objects.filter(supprime_le__isnull=True).prefetch_related("modules")
        )

    with schema_context(schema_name):
        with transaction.atomic():
            # 1. Synchroniser d'abord les modules
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

            # 2. Synchroniser les permissions et leurs rattachements ManyToMany
            for p in permissions_publiques:
                perm_t, _cree = Permission.objects.update_or_create(
                    code=p.code,
                    defaults={
                        "id": p.id,
                        "libelle": p.libelle,
                        "description": p.description,
                        "ordre": p.ordre,
                        "est_actif": p.est_actif,
                    },
                )
                codes_m = list(p.modules.values_list("code", flat=True))
                mods_t = list(Module.objects.filter(code__in=codes_m, supprime_le__isnull=True))
                perm_t.modules.set(mods_t)
