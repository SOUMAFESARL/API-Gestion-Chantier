"""Dérivation du nom de schéma — R-60 de T-020.

**Le test qui compte est celui de l'injection.** Le validateur de
django-tenants n'interdit que le préfixe `pg_`, et `create_schema()` interpole
le nom dans du SQL : sans la liste blanche, une raison sociale suffit à
supprimer le schéma de la plateforme.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.tenants.services import LONGUEUR_MAX_SLUG, deriver_slug


@pytest.mark.parametrize(
    ("saisie", "attendu"),
    [
        ("SOTRA BTP", "sotra_btp"),
        ("Éburnéa Constructions", "eburnea_constructions"),
        ("  BTP   du   Sud  ", "btp_du_sud"),
        ("Bâtir & Cie", "batir_cie"),
        ("SARL-2026", "sarl_2026"),
        ("Côte d'Ivoire Travaux", "cote_d_ivoire_travaux"),
    ],
)
def test_les_raisons_sociales_courantes(saisie, attendu):
    assert deriver_slug(saisie) == attendu


@pytest.mark.parametrize(
    "injection",
    [
        'a"; DROP SCHEMA public CASCADE; --',
        "a'; DELETE FROM entreprise_cliente; --",
        'x" UNION SELECT * FROM utilisateur --',
        "a\x00b",
    ],
)
def test_aucune_injection_ne_survit_a_la_liste_blanche(injection):
    """*Vérifié le 31/08/2026 : le validateur de la bibliothèque accepte la
    première de ces chaînes.* La nôtre ne laisse passer que `[a-z0-9_]`."""
    slug = deriver_slug(injection)

    assert all(c.isalnum() or c == "_" for c in slug), slug
    assert '"' not in slug
    assert ";" not in slug
    assert " " not in slug


def test_un_nom_sans_lettre_latine_est_refuse():
    """§2.5 du contrat : l'écran le dit, il n'invente pas un nom."""
    with pytest.raises(ValidationError):
        deriver_slug("建設 株式会社")


def test_un_nom_vide_est_refuse():
    with pytest.raises(ValidationError):
        deriver_slug("   ")


def test_le_slug_ne_depasse_jamais_le_plafond():
    """**63 caractères ne font pas 63 octets.**

    Le validateur de django-tenants compte des caractères ; PostgreSQL tronque
    à 63 **octets**. Soixante-trois « é » en valent cent vingt-six, et deux
    raisons sociales longues et accentuées pouvaient devenir le même schéma.
    """
    slug = deriver_slug("é" * 63)

    assert len(slug) <= LONGUEUR_MAX_SLUG
    assert len(slug.encode("utf-8")) <= LONGUEUR_MAX_SLUG


def test_un_slug_ne_commence_pas_par_un_chiffre():
    assert not deriver_slug("2026 Constructions")[0].isdigit()


@pytest.mark.parametrize("reserve", ["public", "Information Schema", "pg_toast"])
def test_les_noms_reserves_sont_ecartes(reserve):
    """Un tenant nommé `public` écraserait le schéma de la plateforme."""
    slug = deriver_slug(reserve)

    assert slug not in {"public", "information_schema"}
    assert not slug.startswith("pg_")
