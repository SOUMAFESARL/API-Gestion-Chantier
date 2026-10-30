"""Les rôles système existants passent au circuit par permissions (décision du 30/10/2026).

Le journal ne lit plus le nom des rôles : celui qui a « rédiger » écrit son propre rapport. Le
chef de projet et le conducteur avaient « rédiger » ; le garder leur ferait attendre un rapport
chacun, chaque jour. Ils le perdent, et reçoivent les permissions de leur fonction :

- chef de projet : approuver un rapport, approuver la synthèse, alertes modérées ;
- conducteur de travaux : rédiger la synthèse, alertes modérées (il garde « valider ») ;
- directeur des opérations : alertes élevées.

Le DG a toutes les permissions sans qu'on les coche. Seuls les rôles **système** sont touchés :
un rôle créé par l'entreprise garde ses réglages.
"""

from django.db import migrations

AJOUTS = {
    "CP": {
        "chantier": ["chantier.approuver", "chantier.synthese_approuver"],
        "projets": ["projets.alertes_moderees"],
    },
    "CT": {
        "chantier": ["chantier.synthese_rediger"],
        "projets": ["projets.alertes_moderees"],
    },
    "DO": {"projets": ["projets.alertes_elevees"]},
}
RETRAITS = {
    "CP": {"chantier": ["chantier.rediger"]},
    "CT": {"chantier": ["chantier.rediger"]},
}


def _appliquer(apps, reglages, ajouter):
    Role = apps.get_model("accounts", "Role")
    RoleModulePermission = apps.get_model("accounts", "RoleModulePermission")
    CataloguePermission = apps.get_model("catalogue", "CataloguePermission")
    CatalogueModule = apps.get_model("catalogue", "CatalogueModule")
    for code_role, par_module in reglages.items():
        for role in Role.objects.filter(code=code_role, est_systeme=True, supprime_le__isnull=True):
            for code_module, codes in par_module.items():
                module = CatalogueModule.objects.filter(
                    code=code_module, supprime_le__isnull=True
                ).first()
                if module is None:
                    continue
                rmp = RoleModulePermission.objects.filter(
                    role=role, module_catalogue=module, supprime_le__isnull=True
                ).first()
                if rmp is None:
                    continue
                perms = list(
                    CataloguePermission.objects.filter(code__in=codes, supprime_le__isnull=True)
                )
                if ajouter:
                    rmp.permissions_catalogue.add(*perms)
                else:
                    rmp.permissions_catalogue.remove(*perms)


def migrer(apps, schema_editor):
    if getattr(schema_editor.connection, "schema_name", "public") == "public":
        return
    _appliquer(apps, AJOUTS, ajouter=True)
    _appliquer(apps, RETRAITS, ajouter=False)


class Migration(migrations.Migration):
    dependencies = [
        ("projets", "0046_unicite_role_reglable"),
        ("catalogue", "0017_permissions_journal"),
        ("accounts", "0033_role_unique_par_projet"),
    ]

    operations = [
        migrations.RunPython(migrer, migrations.RunPython.noop),
    ]
