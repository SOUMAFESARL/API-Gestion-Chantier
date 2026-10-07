"""Migration de données : traduction des niveaux vers CataloguePermission (E-02) et application de l'Annexe 1.

Règles : E-02, Annexe 1.
S'exécute sur chaque tenant (schémas locataires).
"""

from django.db import migrations, models


def migrer_niveaux_vers_permissions(apps, schema_editor):
    schema_name = getattr(schema_editor.connection, "schema_name", "public")
    if schema_name == "public":
        return

    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")

    from apps.core.registre_permissions import REGISTRE, permissions_du_module

    # Matrice de l'Annexe 1 pour les 6 codes projets nouveaux
    ANNEXE1_CODES_PAR_ROLE = {
        "DG": {"projets.creer", "projets.changer_statut", "projets.resilier_archiver", "projets.affecter_membres", "projets.gerer_equipes", "projets.voir_montants"},
        "AD": {"projets.creer", "projets.changer_statut", "projets.resilier_archiver", "projets.affecter_membres", "projets.gerer_equipes"},
        "DO": {"projets.creer", "projets.changer_statut", "projets.resilier_archiver", "projets.voir_montants"},
        "DF": {"projets.voir_montants"},
        "CP": {"projets.changer_statut", "projets.affecter_membres", "projets.gerer_equipes", "projets.voir_montants"},
        "CT": {"projets.gerer_equipes"},
        "CC": set(),
        "MAG": set(),
        "BAI": set(),
        "VI": set(),
    }

    cat_perms_by_code = {
        p.code: p for p in CataloguePermission.objects.filter(supprime_le__isnull=True)
    }
    cat_mods_by_code = {
        m.code.lower(): m for m in CatalogueModule.objects.filter(supprime_le__isnull=True)
    }
    mod_projets = cat_mods_by_code.get("projets")

    for role in Role.objects.filter(supprime_le__isnull=True):
        code_role = (role.code or "").upper()
        est_systeme = getattr(role, "est_systeme", False) or code_role in ANNEXE1_CODES_PAR_ROLE

        for rmp in RoleModulePermission.objects.filter(role=role, supprime_le__isnull=True):
            mod_code = None
            if rmp.module_catalogue_id and rmp.module_catalogue:
                mod_code = rmp.module_catalogue.code
            elif rmp.module_id and rmp.module:
                mod_code = rmp.module.code
                if not rmp.module_catalogue_id and mod_code.lower() in cat_mods_by_code:
                    rmp.module_catalogue = cat_mods_by_code[mod_code.lower()]
                    rmp.save(update_fields=["module_catalogue"])

            if not mod_code:
                continue

            mod_key = mod_code.lower()
            niveau = getattr(rmp, "niveau", 0) or 0
            perms_a_ajouter = set()

            # E-02 : codes de rang <= niveau
            if niveau > 0:
                codes_niveau = permissions_du_module(mod_key, niveau)
                for c in codes_niveau:
                    if c in cat_perms_by_code:
                        perms_a_ajouter.add(cat_perms_by_code[c])

            # Annexe 1 : codes nouveaux pour les rôles système sur projets
            if mod_key == "projets" and est_systeme and code_role in ANNEXE1_CODES_PAR_ROLE:
                codes_annexe = ANNEXE1_CODES_PAR_ROLE[code_role]
                for c in codes_annexe:
                    if c in cat_perms_by_code:
                        perms_a_ajouter.add(cat_perms_by_code[c])

            if perms_a_ajouter:
                rmp.permissions_catalogue.add(*perms_a_ajouter)

        # Si le rôle système n'a pas encore de rmp pour projets, le créer et lier l'annexe 1
        if est_systeme and code_role in ANNEXE1_CODES_PAR_ROLE and mod_projets:
            rmp_projets = RoleModulePermission.objects.filter(
                role=role,
                supprime_le__isnull=True,
            ).filter(
                models.Q(module_catalogue=mod_projets) | models.Q(module__code="projets")
            ).first()
            if not rmp_projets:
                rmp_projets = RoleModulePermission.objects.create(
                    role=role,
                    module_catalogue=mod_projets,
                    niveau=1,
                )
            codes_annexe = ANNEXE1_CODES_PAR_ROLE[code_role]
            perms_annexe = [cat_perms_by_code[c] for c in codes_annexe if c in cat_perms_by_code]
            if perms_annexe:
                rmp_projets.permissions_catalogue.add(*perms_annexe)


def desallouer(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0023_rolemodulepermission_module_nullable"),
        ("catalogue", "0005_cataloguepermission_reservee_administration"),
    ]

    operations = [
        migrations.RunPython(migrer_niveaux_vers_permissions, desallouer),
    ]
