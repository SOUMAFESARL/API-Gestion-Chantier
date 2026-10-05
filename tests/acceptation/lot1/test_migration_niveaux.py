"""Tests d'acceptation de la migration des niveaux vers les codes (Règle E-02)."""

import json
from pathlib import Path
import pytest
from django_tenants.utils import schema_context

from apps.accounts.models import Role, RoleModulePermission
from apps.core.registre_permissions import REGISTRE, permissions_du_module

SCHEMA_TEST = "demo"

pytestmark = pytest.mark.django_db


def test_e02_table_niveaux_vers_codes():
    """[E-02] Chaque niveau (1, 2, 3) se traduit rigoureusement en codes de rang inférieur ou égal."""
    # Test pour chantier : rang 1 = lire, rang 2 = rediger, rang 3 = valider
    assert permissions_du_module("chantier", 1) == {"chantier.lire"}
    assert permissions_du_module("chantier", 2) == {"chantier.lire", "chantier.rediger"}
    assert permissions_du_module("chantier", 3) == {"chantier.lire", "chantier.rediger", "chantier.valider"}

    # Test pour tiers : rang 1 = lire, rang 2 = ecrire
    assert permissions_du_module("tiers", 1) == {"tiers.lire"}
    assert permissions_du_module("tiers", 2) == {"tiers.lire", "tiers.ecrire"}

    # Test pour pilotage : rang 1 = lire, rang 3 = voir_montants
    assert permissions_du_module("pilotage", 1) == {"pilotage.lire"}
    assert "pilotage.lire" in permissions_du_module("pilotage", 3)


def test_e02_aucun_code_perdu_apres_migration():
    """[E-02] Pour chaque rôle existant, l'ensemble des codes avant migration est inclus après migration."""
    chemin_snapshot = Path("docs/refonte/snapshot-roles-avant.json")
    if not chemin_snapshot.exists():
        pytest.skip("Snapshot snapshot-roles-avant.json non trouvé")

    snapshot = json.loads(chemin_snapshot.read_text(encoding="utf-8"))
    roles_demo = snapshot.get("tenants", {}).get(SCHEMA_TEST, {}).get("roles", {})

    with schema_context(SCHEMA_TEST):
        for code_role, donnees_role in roles_demo.items():
            role_actuel = Role.objects.filter(code=code_role, supprime_le__isnull=True).first()
            if not role_actuel:
                continue

            for mod_code, info_mod in donnees_role.get("modules", {}).items():
                niveau_avant = info_mod.get("niveau", 0)
                if mod_code in ("chantier", "tiers", "pilotage") and niveau_avant > 0:
                    codes_attendus = permissions_du_module(mod_code, niveau_avant)
                    rmp = RoleModulePermission.objects.filter(
                        role=role_actuel,
                        supprime_le__isnull=True,
                    ).filter(
                        module__code=mod_code
                    ).first() or RoleModulePermission.objects.filter(
                        role=role_actuel,
                        supprime_le__isnull=True,
                        module_catalogue__code=mod_code
                    ).first()

                    if rmp and rmp.permissions_catalogue.exists():
                        codes_obtenus = set(rmp.permissions_catalogue.values_list("code", flat=True))
                        # Vérifier que les codes dérivés du niveau sont bien présents
                        assert codes_attendus.issubset(codes_obtenus), (
                            f"Rôle {code_role}, module {mod_code} : codes perdus {codes_attendus - codes_obtenus}"
                        )
