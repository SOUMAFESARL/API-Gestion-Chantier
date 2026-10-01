from django.contrib import admin

from apps.accounts.models import Module, Role, RoleModulePermission, Utilisateur


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "ordre", "icone", "est_actif", "cree_le"]
    list_filter = ["est_actif"]
    search_fields = ["code", "libelle", "description"]
    ordering = ["ordre", "code"]


class RoleModulePermissionInline(admin.TabularInline):
    model = RoleModulePermission
    extra = 0
    fields = ["module", "niveau"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["code", "libelle", "est_systeme", "est_actif", "cree_le"]
    list_filter = ["est_systeme", "est_actif"]
    search_fields = ["code", "libelle"]
    inlines = [RoleModulePermissionInline]


@admin.register(RoleModulePermission)
class RoleModulePermissionAdmin(admin.ModelAdmin):
    list_display = ["role", "module", "niveau", "cree_le"]
    list_filter = ["module", "niveau"]
    search_fields = ["role__libelle", "role__code", "module__libelle", "module__code"]
