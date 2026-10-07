"""Tests d'acceptation du REGISTRE des permissions (Règles A-01, A-02, A-15, B-05, E-01)."""

import pytest

from apps.core.registre_permissions import REGISTRE, DefPermission


def test_a01_registre_est_source_unique():
    """[A-01] Le REGISTRE est un dictionnaire unique associant chaque code à sa définition."""
    assert isinstance(REGISTRE, dict)
    assert len(REGISTRE) > 0
    for code, def_p in REGISTRE.items():
        assert def_p.code == code
        assert isinstance(def_p, DefPermission)


def test_a02_structure_def_permission():
    """[A-02] Chaque entrée du REGISTRE possède code, module, rang, libelle et reservee_administration."""
    for code, def_p in REGISTRE.items():
        assert hasattr(def_p, "code") and isinstance(def_p.code, str)
        assert hasattr(def_p, "module") and isinstance(def_p.module, str)
        assert hasattr(def_p, "rang") and isinstance(def_p.rang, int)
        assert hasattr(def_p, "libelle") and isinstance(def_p.libelle, str)
        assert hasattr(def_p, "reservee_administration")
        assert isinstance(def_p.reservee_administration, bool)


def test_a02_module_est_prefixe_du_code():
    """[A-02] Pour chaque permission, le module est le préfixe strict du code (module.verbe)."""
    for code, def_p in REGISTRE.items():
        prefixe = code.split(".")[0]
        assert def_p.module == prefixe, (
            f"Incohérence pour {code} : module attendu {prefixe}, trouvé {def_p.module}"
        )


def test_a15_registre_sans_ged():
    """[A-15] Le REGISTRE ne contient aucun code du module GED (ged.*)."""
    codes_ged = [code for code in REGISTRE.keys() if code.startswith("ged.")]
    assert codes_ged == [], f"Des codes GED subsistent dans le REGISTRE : {codes_ged}"


def test_b05_marqueur_reservee_administration_coherent():
    """[B-05] Tout code du module administration a reservee_administration=True, aucun autre ne l'a."""
    for code, def_p in REGISTRE.items():
        if def_p.module == "administration":
            assert def_p.reservee_administration is True, (
                f"Le code {code} doit avoir reservee_administration=True"
            )
        else:
            assert def_p.reservee_administration is False, (
                f"Le code métier {code} ne doit pas avoir reservee_administration=True"
            )


def test_e01_codes_projets_presents():
    """[E-01] Les 8 codes métier du module projets sont présents dans le REGISTRE."""
    codes_attendus = {
        "projets.lire",
        "projets.ecrire",
        "projets.creer",
        "projets.changer_statut",
        "projets.resilier_archiver",
        "projets.affecter_membres",
        "projets.gerer_equipes",
        "projets.voir_montants",
    }
    codes_reels = set(REGISTRE.keys())
    manquants = codes_attendus - codes_reels
    assert not manquants, f"Codes du module projets manquants dans le REGISTRE : {manquants}"
