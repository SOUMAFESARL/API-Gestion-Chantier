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
from django.db import models, transaction
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
    "propager_roles_systeme",
    "propager_suppression_module",
    "propager_suppression_permission",
    "synchroniser_modules_et_permissions_nouveau_tenant",
]


def _permissions_du_catalogue(permissions_input) -> list[CataloguePermission]:
    """Les permissions du catalogue désignées par une liste de codes ou d'identifiants.

    Un identifiant (UUID) se cherche par `id`, un code par `code__iexact`, toujours parmi les
    permissions non supprimées. Lève `ValidationError` (« Permission inconnue : … ») si un élément
    ne correspond à rien. Accepte aussi des dictionnaires `{"code": …}` ou `{"id": …}`.
    Renvoie une liste sans doublon, triée par (ordre, code).
    """
    if not permissions_input:
        return []

    from uuid import UUID

    perms_trouvees = {}
    inconnus = []

    with schema_context("public"):
        for p in permissions_input:
            p_val = None
            if isinstance(p, dict):
                p_val = p.get("code") or p.get("id")
            elif hasattr(p, "code") and hasattr(p, "id"):
                perms_trouvees[p.id] = p
                continue
            else:
                p_val = p

            if not p_val:
                continue

            p_str = str(p_val).strip()
            perm = None
            try:
                val_uuid = UUID(p_str)
                perm = CataloguePermission.objects.filter(
                    id=val_uuid, supprime_le__isnull=True
                ).first()
            except (ValueError, AttributeError):
                perm = None

            if not perm:
                perm = CataloguePermission.objects.filter(
                    code__iexact=p_str, supprime_le__isnull=True
                ).first()

            if perm:
                perms_trouvees[perm.id] = perm
            else:
                inconnus.append(p_str)

    if inconnus:
        cites = ", ".join(f"« {c} »" for c in inconnus)
        raise ValidationError(_(f"Permission inconnue : {cites}."))

    return sorted(perms_trouvees.values(), key=lambda p: (p.ordre, p.code))


def _verifier_prefixes(module_code: str, permissions: list[CataloguePermission]) -> None:
    """D2 : chaque permission `x.action` appartient au module `x`. Lève `ValidationError`."""
    mod_code_normalise = (module_code or "").strip().lower()
    for p in permissions:
        if "." in p.code:
            perm_prefix = p.code.split(".")[0].strip().lower()
            if perm_prefix != mod_code_normalise:
                raise ValidationError(
                    _(
                        f"La permission « {p.code} » appartient au module « {perm_prefix} » : "
                        f"elle ne peut pas être rattachée au module « {mod_code_normalise} »."
                    )
                )


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
) -> CatalogueModule:
    """Crée un module dans le schéma public et le propage immédiatement à tous les tenants."""
    code = code.strip().lower()
    if not code:
        raise ValidationError(_("Le code du module est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé du module est obligatoire."))

    perms_catalogue = _permissions_du_catalogue(permissions)
    _verifier_prefixes(code, perms_catalogue)

    with schema_context("public"), transaction.atomic():
        if CatalogueModule.objects.filter(code=code, supprime_le__isnull=True).exists():
            raise ValidationError(_(f"Un module avec le code '{code}' existe déjà."))

        cat_mod, _ = CatalogueModule.objects.update_or_create(
            code=code,
            defaults={
                "libelle": libelle.strip(),
                "description": description.strip(),
                "ordre": ordre,
                "icone": icone.strip() or "box",
                "est_actif": est_actif,
                "cree_par": cree_par,
                "supprime_le": None,
                "supprime_par": None,
            },
        )
        cat_mod.permissions.set(perms_catalogue)

        # Ancien référentiel au mieux
        mod_pub = Module.objects.filter(code=code, supprime_le__isnull=True).first()
        if not mod_pub:
            mod_pub, _ = Module.objects.update_or_create(
                id=cat_mod.id,
                defaults={
                    "code": code,
                    "libelle": libelle.strip(),
                    "description": description.strip(),
                    "ordre": ordre,
                    "icone": icone.strip() or "box",
                    "est_actif": est_actif,
                    "cree_par": cree_par,
                    "supprime_le": None,
                    "supprime_par": None,
                },
            )
        if mod_pub:
            codes_perms = [p.code for p in perms_catalogue]
            if codes_perms:
                perms_pub = list(
                    Permission.objects.filter(code__in=codes_perms, supprime_le__isnull=True)
                )
                mod_pub.permissions.set(perms_pub)
            else:
                mod_pub.permissions.clear()

        for entreprise in Entreprise.objects.exclude(schema_name="public"):
            EntrepriseModule.objects.update_or_create(
                entreprise=entreprise,
                module=cat_mod,
                defaults={"est_actif": est_actif},
            )

    codes_perms = [p.code for p in perms_catalogue]
    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name), transaction.atomic():
            mod = Module.objects.filter(code=code, supprime_le__isnull=True).first()
            if not mod:
                mod, _ = Module.objects.update_or_create(
                    id=cat_mod.id,
                    defaults={
                        "code": code,
                        "libelle": libelle.strip(),
                        "description": description.strip(),
                        "ordre": ordre,
                        "icone": icone.strip() or "box",
                        "est_actif": est_actif,
                        "supprime_le": None,
                        "supprime_par": None,
                    },
                )
            if mod:
                if codes_perms:
                    perms_tenant = list(
                        Permission.objects.filter(
                            code__in=codes_perms, supprime_le__isnull=True
                        )
                    )
                    mod.permissions.set(perms_tenant)
                else:
                    mod.permissions.clear()

            roles = Role.objects.filter(supprime_le__isnull=True)
            for role in roles:
                rmp, _ = RoleModulePermission.objects.get_or_create(
                    role=role,
                    module=mod,
                    defaults={"cree_par": None, "module_catalogue": cat_mod},
                )
                rmp.module_catalogue = cat_mod
                if role.code in ("DG", "DIRECTEUR_GENERAL"):
                    rmp.permissions_catalogue.set(perms_catalogue)
                    rmp.niveau = (
                        NiveauAcces.VALIDATION if perms_catalogue else NiveauAcces.AUCUN
                    )
                else:
                    rmp.permissions_catalogue.clear()
                    rmp.niveau = NiveauAcces.AUCUN
                rmp.save()

    return cat_mod


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
) -> CatalogueModule:
    """Met à jour un module dans le schéma public et synchronise les métadonnées et permissions dans tous les tenants."""
    retirees = set()
    nouvelles = None
    with schema_context("public"), transaction.atomic():
        cat_mod = CatalogueModule.objects.filter(id=module_id, supprime_le__isnull=True).first()
        if not cat_mod:
            mod_old = Module.objects.filter(id=module_id, supprime_le__isnull=True).first()
            if mod_old:
                cat_mod = CatalogueModule.objects.filter(
                    code=mod_old.code, supprime_le__isnull=True
                ).first()
        if not cat_mod:
            raise ValidationError(_("Module introuvable."))

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

        if permissions is not None:
            nouvelles = _permissions_du_catalogue(permissions)
            _verifier_prefixes(cat_mod.code, nouvelles)
            anciennes_codes = set(
                cat_mod.permissions.filter(supprime_le__isnull=True).values_list(
                    "code", flat=True
                )
            )
            cat_mod.permissions.set(nouvelles)
            retirees = anciennes_codes - {p.code for p in nouvelles}

        cat_mod.save()

        # Ancien référentiel au mieux
        module_public = Module.objects.filter(
            code=cat_mod.code, supprime_le__isnull=True
        ).first()
        if not module_public:
            module_public = Module.objects.filter(
                id=cat_mod.id, supprime_le__isnull=True
            ).first()
        if module_public:
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
            if nouvelles is not None:
                codes_perms = [p.code for p in nouvelles]
                perms_pub = list(
                    Permission.objects.filter(code__in=codes_perms, supprime_le__isnull=True)
                )
                module_public.permissions.set(perms_pub)
            module_public.save()

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    perms_retirees_objs = (
        list(CataloguePermission.objects.filter(code__in=retirees)) if retirees else []
    )

    for entreprise in entreprises:
        with schema_context(entreprise.schema_name), transaction.atomic():
            mod = Module.objects.filter(code=cat_mod.code, supprime_le__isnull=True).first()
            if not mod:
                mod = Module.objects.filter(id=cat_mod.id, supprime_le__isnull=True).first()
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

                if nouvelles is not None:
                    codes_perms = [p.code for p in nouvelles]
                    perms_tenant = list(
                        Permission.objects.filter(
                            code__in=codes_perms, supprime_le__isnull=True
                        )
                    )
                    mod.permissions.set(perms_tenant)

            # 1. Révocation des permissions retirées du module sur tous les rôles
            if perms_retirees_objs:
                rmps = RoleModulePermission.objects.filter(supprime_le__isnull=True).filter(
                    models.Q(module__code=cat_mod.code) | models.Q(module_catalogue=cat_mod)
                )
                for rmp in rmps:
                    rmp.permissions_catalogue.remove(*perms_retirees_objs)

            # 2. Règle A-05 : aucune attribution automatique aux rôles stockés
            pass

    return cat_mod


def propager_affectation_permissions_module(
    *,
    module_id,
    permissions: list,
    modifie_par=None,
) -> CatalogueModule:
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
    with schema_context("public"), transaction.atomic():
        cat_mod = CatalogueModule.objects.filter(id=module_id, supprime_le__isnull=True).first()
        if not cat_mod:
            mod_old = Module.objects.filter(id=module_id, supprime_le__isnull=True).first()
            if mod_old:
                cat_mod = CatalogueModule.objects.filter(
                    code=mod_old.code, supprime_le__isnull=True
                ).first()
        if not cat_mod:
            raise ValidationError(_("Module introuvable ou déjà supprimé."))

        code_supprime = cat_mod.code
        cat_mod.supprime_le = maintenant
        cat_mod.supprime_par = supprime_par
        cat_mod.est_actif = False
        cat_mod.save()

        Module.objects.filter(code=code_supprime, supprime_le__isnull=True).update(
            supprime_le=maintenant,
            supprime_par=supprime_par,
            est_actif=False,
        )
        EntrepriseModule.objects.filter(module=cat_mod).update(est_actif=False)

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name), transaction.atomic():
            Module.objects.filter(code=code_supprime, supprime_le__isnull=True).update(
                supprime_le=maintenant,
                supprime_par=None,
                est_actif=False,
            )
            RoleModulePermission.objects.filter(
                models.Q(module__code=code_supprime)
                | models.Q(module_catalogue__code=code_supprime),
                supprime_le__isnull=True,
            ).update(
                supprime_le=maintenant,
                supprime_par=None,
            )

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

    with schema_context("public"):
        for m in modules_input:
            if isinstance(m, dict):
                m_val = m.get("code") or m.get("id")
            elif hasattr(m, "code"):
                codes.add(m.code.lower())
                continue
            else:
                m_val = m
            if not m_val:
                continue
            m_str = str(m_val).strip()
            try:
                val_uuid = UUID(m_str)
                mod = CatalogueModule.objects.filter(id=val_uuid, supprime_le__isnull=True).first()
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
) -> CataloguePermission:
    """Crée une permission dans public et la propage de façon ciblée à tous les tenants.

    Invariant métier (Module-Scoped Permissions) :
    - Le module se déduit du préfixe : module_code = code.split('.')[0].
    - Si modules est fourni et contient autre chose que ce module -> 400 (D2).
    - Si modules est vide, la permission est rattachée à son module (module_code),
      s'il existe au catalogue ; sinon 400.
    - Si une permission supprimée porte déjà ce code, la rétablir au lieu d'en créer une seconde.
    - Aucune attribution automatique aux rôles stockés (A-05).
    """
    code = code.strip()
    if not code:
        raise ValidationError(_("Le code de la permission est obligatoire."))
    if not libelle.strip():
        raise ValidationError(_("Le libellé de la permission est obligatoire."))

    module_code = code.split(".")[0].strip().lower()
    codes_modules = _resoudre_modules_codes(modules)

    with schema_context("public"), transaction.atomic():
        cat_mod = CatalogueModule.objects.filter(
            code=module_code, supprime_le__isnull=True
        ).first()
        if not cat_mod:
            raise ValidationError(
                _(f"Le module « {module_code} » n'existe pas au catalogue : créez-le d'abord.")
            )

        if codes_modules:
            for mc in codes_modules:
                if mc != module_code:
                    raise ValidationError(
                        _(
                            f"La permission « {code} » appartient au module « {module_code} » : "
                            f"elle ne peut pas être rattachée au module « {mc} »."
                        )
                    )
        else:
            codes_modules = [module_code]

        cat_perm = CataloguePermission.tous_objets.filter(code=code).first()
        if cat_perm:
            cat_perm.supprime_le = None
            cat_perm.supprime_par = None
            cat_perm.est_actif = est_actif
            cat_perm.libelle = libelle.strip()
            cat_perm.description = description.strip()
            cat_perm.ordre = ordre
            cat_perm.save()
        else:
            cat_perm = CataloguePermission.objects.create(
                code=code,
                libelle=libelle.strip(),
                description=description.strip(),
                ordre=ordre,
                est_actif=est_actif,
                cree_par=cree_par,
            )

        cat_mods = list(
            CatalogueModule.objects.filter(code__in=codes_modules, supprime_le__isnull=True)
        )
        cat_perm.modules.set(cat_mods)

        # Ancien référentiel au mieux
        perm_public = Permission.tous_objets.filter(code=code).first()
        if perm_public:
            perm_public.supprime_le = None
            perm_public.supprime_par = None
            perm_public.est_actif = est_actif
            perm_public.libelle = libelle.strip()
            perm_public.description = description.strip()
            perm_public.ordre = ordre
            perm_public.save()
        else:
            perm_public = Permission.objects.create(
                id=cat_perm.id,
                code=code,
                libelle=libelle.strip(),
                description=description.strip(),
                ordre=ordre,
                est_actif=est_actif,
                cree_par=cree_par,
            )
        mods_public = list(
            Module.objects.filter(code__in=codes_modules, supprime_le__isnull=True)
        )
        perm_public.modules.set(mods_public)

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name), transaction.atomic():
            perm_tenant, _cree = Permission.objects.update_or_create(
                code=code,
                defaults={
                    "id": cat_perm.id,
                    "libelle": libelle.strip(),
                    "description": description.strip(),
                    "ordre": ordre,
                    "est_actif": est_actif,
                    "supprime_le": None,
                    "supprime_par": None,
                },
            )
            mods_tenant = list(
                Module.objects.filter(code__in=codes_modules, supprime_le__isnull=True)
            )
            perm_tenant.modules.set(mods_tenant)

    return cat_perm


def propager_affectation_modules_permission(
    *,
    permission_id,
    modules: list,
    modifie_par=None,
) -> CataloguePermission:
    """Affecte ou modifie les modules d'une permission et synchronise les tenants.

    Règles de sécurité :
    - D2 s'applique : seul le module du préfixe est admis ([] ou [module_du_prefixe]).
    - Retirer le module ([]) retire la permission de tous les rôles sur ce module.
    - Ajouter le module n'attribue la permission à aucun rôle stocké (A-05).
    """
    from uuid import UUID

    modules_retires = set()
    cat_mods_cibles = []
    perm_prefix = ""

    with schema_context("public"), transaction.atomic():
        cat_perm = CataloguePermission.objects.filter(
            id=permission_id, supprime_le__isnull=True
        ).first()
        if not cat_perm:
            perm_old = Permission.objects.filter(
                id=permission_id, supprime_le__isnull=True
            ).first()
            if perm_old:
                cat_perm = CataloguePermission.objects.filter(
                    code=perm_old.code, supprime_le__isnull=True
                ).first()
        if not cat_perm:
            raise ValidationError(_("Permission introuvable."))

        perm_prefix = cat_perm.code.split(".")[0].strip().lower()

        if modules:
            for m in modules:
                if isinstance(m, dict):
                    m_val = m.get("code") or m.get("id")
                elif hasattr(m, "code"):
                    m_val = m.code
                else:
                    m_val = m
                if not m_val:
                    continue
                m_str = str(m_val).strip()
                mod_obj = None
                try:
                    val_uuid = UUID(m_str)
                    mod_obj = CatalogueModule.objects.filter(
                        id=val_uuid, supprime_le__isnull=True
                    ).first()
                except (ValueError, AttributeError):
                    mod_obj = None
                if not mod_obj:
                    mod_obj = CatalogueModule.objects.filter(
                        code__iexact=m_str, supprime_le__isnull=True
                    ).first()

                if not mod_obj:
                    raise ValidationError(_(f"Module inconnu : « {m_str} »."))

                if mod_obj.code.lower() != perm_prefix:
                    raise ValidationError(
                        _(
                            f"La permission « {cat_perm.code} » appartient au "
                            f"module « {perm_prefix} » : elle ne peut pas être "
                            f"rattachée au module « {mod_obj.code} »."
                        )
                    )
                if mod_obj not in cat_mods_cibles:
                    cat_mods_cibles.append(mod_obj)

        anciens_modules_codes = set(
            cat_perm.modules.filter(supprime_le__isnull=True).values_list("code", flat=True)
        )
        nouveaux_modules_codes = {m.code for m in cat_mods_cibles}
        modules_retires = anciens_modules_codes - nouveaux_modules_codes

        cat_perm.modules.set(cat_mods_cibles)
        if modifie_par:
            cat_perm.modifie_par = modifie_par
            cat_perm.save()

        # Ancien référentiel au mieux
        perm_public = Permission.objects.filter(
            code=cat_perm.code, supprime_le__isnull=True
        ).first()
        if perm_public:
            if cat_mods_cibles:
                mods_pub = list(
                    Module.objects.filter(
                        code__in=[m.code for m in cat_mods_cibles], supprime_le__isnull=True
                    )
                )
                perm_public.modules.set(mods_pub)
            else:
                perm_public.modules.clear()

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name), transaction.atomic():
            # Retrait du module => révocation de la permission de tous les rôles sur ce module
            if modules_retires or not cat_mods_cibles:
                rmps = RoleModulePermission.objects.filter(supprime_le__isnull=True).filter(
                    models.Q(module__code=perm_prefix)
                    | models.Q(module_catalogue__code=perm_prefix)
                )
                for rmp in rmps:
                    rmp.permissions_catalogue.remove(cat_perm)

            # Ancien référentiel au mieux
            perm_tenant = Permission.objects.filter(
                code=cat_perm.code, supprime_le__isnull=True
            ).first()
            if perm_tenant:
                if cat_mods_cibles:
                    mods_tenant = list(
                        Module.objects.filter(
                            code__in=[m.code for m in cat_mods_cibles], supprime_le__isnull=True
                        )
                    )
                    perm_tenant.modules.set(mods_tenant)
                else:
                    perm_tenant.modules.clear()

    return cat_perm


def propager_modification_permission(
    *,
    permission_id,
    libelle: str | None = None,
    description: str | None = None,
    ordre: int | None = None,
    est_actif: bool | None = None,
    modules: list | None = None,
    modifie_par=None,
) -> CataloguePermission:
    """Modifie une permission dans public et synchronise ses métadonnées dans tous les tenants."""
    with schema_context("public"), transaction.atomic():
        cat_perm = CataloguePermission.objects.filter(
            id=permission_id, supprime_le__isnull=True
        ).first()
        if not cat_perm:
            perm_old = Permission.objects.filter(
                id=permission_id, supprime_le__isnull=True
            ).first()
            if perm_old:
                cat_perm = CataloguePermission.objects.filter(
                    code=perm_old.code, supprime_le__isnull=True
                ).first()
        if not cat_perm:
            raise ValidationError(_("Permission introuvable."))

        if libelle is not None and libelle.strip():
            cat_perm.libelle = libelle.strip()
        if description is not None:
            cat_perm.description = description.strip()
        if ordre is not None:
            cat_perm.ordre = ordre
        if est_actif is not None:
            cat_perm.est_actif = est_actif
        if modifie_par:
            cat_perm.modifie_par = modifie_par
        cat_perm.save()

        # Ancien référentiel au mieux
        perm_public = Permission.objects.filter(
            code=cat_perm.code, supprime_le__isnull=True
        ).first()
        if perm_public:
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
        with schema_context(entreprise.schema_name), transaction.atomic():
            perm = Permission.objects.filter(
                code=cat_perm.code, supprime_le__isnull=True
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
            permission_id=cat_perm.id,
            modules=modules,
            modifie_par=modifie_par,
        )

    if est_actif is False:
        from apps.platform_admin.services.notifications import (
            SUJET_MODIFICATION_PLATEFORME,
            journaliser_plateforme,
            journaliser_tenant,
            notifier_dg_action_plateforme,
        )

        email_admin = getattr(modifie_par, "email", "") or "admin@plateforme.local"
        corps = (
            f"Bonjour,\n\n"
            f"La permission '{cat_perm.code}' ({cat_perm.libelle}) a été désactivée par l'administration de la plateforme.\n"
            f"Super admin acteur : {email_admin}\n"
        )
        for ea in entreprises:
            journaliser_tenant(
                entreprise=ea,
                action="MODIFICATION",
                type_entite="CataloguePermission",
                entite_id=cat_perm.id,
                valeur_apres={"code": cat_perm.code, "est_actif": False},
                acteur=modifie_par,
            )
            notifier_dg_action_plateforme(
                entreprise=ea,
                sujet=SUJET_MODIFICATION_PLATEFORME,
                message=corps,
                super_admin_email=email_admin,
            )
        journaliser_plateforme(
            action="DESACTIVATION_PERMISSION",
            acteur=modifie_par,
            detail={"permission_code": cat_perm.code, "permission_id": str(cat_perm.id)},
        )

    return cat_perm


def propager_suppression_permission(*, permission_id, supprime_par=None) -> dict:
    """Soft-delete une permission dans public et dans tous les tenants."""
    maintenant = timezone.now()
    code_supprime = ""
    with schema_context("public"), transaction.atomic():
        cat_perm = CataloguePermission.objects.filter(
            id=permission_id, supprime_le__isnull=True
        ).first()
        if not cat_perm:
            perm_old = Permission.objects.filter(
                id=permission_id, supprime_le__isnull=True
            ).first()
            if perm_old:
                cat_perm = CataloguePermission.objects.filter(
                    code=perm_old.code, supprime_le__isnull=True
                ).first()
        if not cat_perm:
            raise ValidationError(_("Permission introuvable ou déjà supprimée."))

        code_supprime = cat_perm.code
        cat_perm.supprime_le = maintenant
        cat_perm.supprime_par = supprime_par
        cat_perm.est_actif = False
        cat_perm.save()

        Permission.objects.filter(code=code_supprime, supprime_le__isnull=True).update(
            supprime_le=maintenant,
            supprime_par=supprime_par,
            est_actif=False,
        )

    entreprises = list(Entreprise.objects.exclude(schema_name="public"))
    for entreprise in entreprises:
        with schema_context(entreprise.schema_name), transaction.atomic():
            for rmp in RoleModulePermission.objects.filter(permissions_catalogue=cat_perm):
                rmp.permissions_catalogue.remove(cat_perm)

            Permission.objects.filter(code=code_supprime, supprime_le__isnull=True).update(
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

    with schema_context(schema_name), transaction.atomic():
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


def propager_roles_systeme(acteur=None) -> dict:
    """Propage les modèles de rôles système à l'ensemble des entreprises clientes existantes (A-07, A-08, A-09).

    Règles :
    - A-07 : Ne crée QUE les rôles système manquants. Ne modifie JAMAIS un rôle existant.
    - A-07 : Lignes RoleModulePermission créées UNIQUEMENT pour les modules actifs du tenant.
    - A-09 : Conflit de code ou de nom avec un rôle personnalisé :
             Le rôle personnalisé est renommé '{code}_perso' et '{nom} (personnalisé)'.
             Le rôle système manquant est ensuite créé avec son code et son nom normaux.
    - A-14 & L9-1 : Audit tenant pour chaque renommage et pour l'entreprise modifiée.
    - A-14 : Courriel au DG de chaque entreprise ayant subi des modifications (créations ou renommages).
             Strictement aucun courriel si rien n'a été modifié (idempotence).
    - H-02 : Journalisation dans JournalPlateforme.
    """
    from apps.catalogue.models import ModeleRole
    from apps.platform_admin.services.notifications import (
        SUJET_MODIFICATION_PLATEFORME,
        journaliser_plateforme,
        journaliser_tenant,
        notifier_dg_action_plateforme,
    )

    with schema_context("public"):
        modeles_actifs = list(
            ModeleRole.objects.filter(est_actif=True, supprime_le__isnull=True).prefetch_related(
                "modules_plafonds"
            )
        )
        cat_modules_map = {
            m.code.lower(): m
            for m in CatalogueModule.objects.filter(est_actif=True, supprime_le__isnull=True)
        }
        entreprises = list(Entreprise.objects.exclude(schema_name="public"))

    entreprises_modifiees_count = 0

    for ea in entreprises:
        with schema_context("public"):
            em_qs = list(EntrepriseModule.objects.filter(entreprise=ea, supprime_le__isnull=True))
            inactifs = {m.module.code.lower() for m in em_qs if not m.est_actif and m.module}
            actifs_souscrits = {m.module.code.lower() for m in em_qs if m.est_actif and m.module}
            tous_actifs = set(cat_modules_map.keys())
            modules_actifs_ea = (tous_actifs | actifs_souscrits) - inactifs

        with schema_context(ea.schema_name):
            with transaction.atomic():
                ea_modifiee = False
                roles_crees = []
                renommages_details = []

                for modele in modeles_actifs:
                    # 1. Vérifier si un rôle système avec ce code existe déjà
                    role_sys_existant = Role.objects.filter(
                        code__iexact=modele.code, est_systeme=True, supprime_le__isnull=True
                    ).first()
                    if role_sys_existant:
                        continue  # Invariant A-07 : on ne touche jamais à un rôle existant

                    # 2. Gestion des conflits (A-09) : rôles personnalisés ayant le même code ou libellé
                    import unicodedata

                    def _norm(s: str) -> str:
                        return "".join(
                            c
                            for c in unicodedata.normalize("NFD", (s or "").lower())
                            if unicodedata.category(c) != "Mn"
                        )

                    code_m_norm = _norm(modele.code)
                    lib_m_norm = _norm(modele.libelle)

                    tous_perso = list(
                        Role.objects.filter(est_systeme=False, supprime_le__isnull=True)
                    )
                    conflits = [
                        rc
                        for rc in tous_perso
                        if _norm(rc.code) == code_m_norm or _norm(rc.libelle) == lib_m_norm
                    ]
                    for rc in conflits:
                        ancien_code = rc.code
                        ancien_libelle = rc.libelle

                        # Calcul nouveau code
                        base_code = f"{rc.code}_perso"
                        nouveau_code = base_code
                        idx_c = 2
                        while (
                            Role.objects.filter(code__iexact=nouveau_code, supprime_le__isnull=True)
                            .exclude(id=rc.id)
                            .exists()
                        ):
                            nouveau_code = f"{base_code}{idx_c}"
                            idx_c += 1

                        # Calcul nouveau libellé
                        if "(personnalisé" in rc.libelle:
                            nouveau_libelle = f"{rc.libelle} (personnalisé 2)"
                        else:
                            nouveau_libelle = f"{rc.libelle} (personnalisé)"
                        idx_l = 2
                        while (
                            Role.objects.filter(
                                libelle__iexact=nouveau_libelle, supprime_le__isnull=True
                            )
                            .exclude(id=rc.id)
                            .exists()
                        ):
                            nouveau_libelle = f"{rc.libelle} (personnalisé {idx_l})"
                            idx_l += 1

                        rc.code = nouveau_code
                        rc.libelle = nouveau_libelle
                        rc.save(update_fields=["code", "libelle"])
                        ea_modifiee = True

                        msg_r = f"Rôle personnalisé {ancien_code} renommé en {nouveau_code} ({nouveau_libelle})"
                        renommages_details.append(msg_r)

                        journaliser_tenant(
                            entreprise=ea,
                            action="MODIFICATION",
                            type_entite="Role",
                            entite_id=rc.id,
                            valeur_apres={
                                "message": msg_r,
                                "ancien_code": ancien_code,
                                "nouveau_code": nouveau_code,
                                "ancien_libelle": ancien_libelle,
                                "nouveau_libelle": nouveau_libelle,
                            },
                            acteur=acteur,
                        )

                    # 3. Création du rôle système manquant
                    portee_role = getattr(modele, "portee", "PROJET") or "PROJET"
                    nouveau_role = Role.objects.create(
                        code=modele.code,
                        libelle=modele.libelle,
                        description=modele.description,
                        portee=portee_role,
                        est_systeme=True,
                        est_actif=True,
                    )
                    roles_crees.append(nouveau_role.code)
                    ea_modifiee = True

                    # 4. Rattachement aux modules actifs uniquement
                    modules_modele_map = {
                        mrm.module_code.lower(): mrm for mrm in modele.modules_plafonds.all()
                    }

                    for mod_code_raw in modules_actifs_ea:
                        mod_code_l = mod_code_raw.lower()
                        # Si le modèle spécifie explicitement certains modules, on ne crée que pour ceux-ci
                        if modules_modele_map and mod_code_l not in modules_modele_map:
                            continue

                        cat_mod = cat_modules_map.get(mod_code_l)
                        local_mod = Module.objects.filter(
                            code__iexact=mod_code_l, supprime_le__isnull=True
                        ).first()

                        rmp = RoleModulePermission.objects.create(
                            role=nouveau_role,
                            module=local_mod,
                            module_catalogue=cat_mod,
                            niveau=NiveauAcces.AUCUN,
                        )

                        if cat_mod:
                            perms_actives = list(
                                CataloguePermission.objects.filter(
                                    modules=cat_mod, est_actif=True, supprime_le__isnull=True
                                )
                            )
                            if perms_actives:
                                rmp.permissions_catalogue.set(perms_actives)

                # Si l'entreprise a subi des modifications, tracer et notifier
                if ea_modifiee:
                    entreprises_modifiees_count += 1

                    journaliser_tenant(
                        entreprise=ea,
                        action="MODIFICATION",
                        type_entite="Entreprise",
                        entite_id=ea.id,
                        valeur_apres={
                            "action": "PROPAGATION_ROLES_SYSTEME",
                            "roles_crees": roles_crees,
                            "renommages": renommages_details,
                        },
                        acteur=acteur,
                    )

                    email_admin = getattr(acteur, "email", "") or "admin@plateforme.local"
                    corps_lignes = [
                        "Bonjour,",
                        "",
                        "L'administration de la plateforme a procédé à une mise à jour des rôles système sur votre espace.",
                        f"Super admin acteur : {email_admin}",
                    ]
                    if roles_crees:
                        corps_lignes.append(f"Rôles système créés : {', '.join(roles_crees)}")
                    if renommages_details:
                        corps_lignes.append("Renommages de rôles personnalisés en conflit :")
                        for r in renommages_details:
                            corps_lignes.append(f"- {r}")

                    notifier_dg_action_plateforme(
                        entreprise=ea,
                        sujet=SUJET_MODIFICATION_PLATEFORME,
                        message="\n".join(corps_lignes),
                        super_admin_email=email_admin,
                    )

    # Journalisation globale dans JournalPlateforme (H-02)
    journaliser_plateforme(
        action="PROPAGATION_ROLES_SYSTEME",
        acteur=acteur,
        detail={
            "entreprises_modifiees": entreprises_modifiees_count,
            "total_entreprises": len(entreprises),
        },
    )

    return {
        "entreprises_modifiees": entreprises_modifiees_count,
        "total_entreprises": len(entreprises),
    }
