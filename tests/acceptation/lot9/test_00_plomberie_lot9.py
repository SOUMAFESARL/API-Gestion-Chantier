"""Plomberie du lot 9 : vérification des prérequis et des fabriques."""
import pytest
from django_tenants.utils import get_public_schema_name, schema_context


@pytest.mark.carac
@pytest.mark.django_db
def test_plomberie_deux_entreprises_reelles(fab):
    """Vérifie la disponibilité des deux entreprises réelles pour le lot 9 (P3)."""
    ea = fab.entreprise_a()
    eb = fab.entreprise_b()
    assert ea.schema_name == "demo"
    assert eb.schema_name in ("nouvelle_entreprise_btp", "tenant_b")
    assert ea.id != eb.id


@pytest.mark.carac
@pytest.mark.django_db
def test_plomberie_super_admin_schema_public(fab):
    """Vérifie que le client super admin vit dans le schéma public."""
    client = fab.client_super_admin()
    assert client.admin_user.is_staff is True
    with schema_context(get_public_schema_name()):
        from apps.accounts.models import Utilisateur
        assert Utilisateur.objects.filter(id=client.admin_user.id).exists()
