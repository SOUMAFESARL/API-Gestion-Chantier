from apps.core.registre_permissions import REGISTRE, DefPermission


def test_registre_unicite_codes():
    assert len(REGISTRE) > 0
    # Every code matches its key
    for code, definition in REGISTRE.items():
        assert code == definition.code
        assert isinstance(definition, DefPermission)
        assert definition.rang in (1, 2, 3)
        assert bool(definition.module)
        assert bool(definition.libelle)
