"""Compatibilité des migrations historiques RLS et contrôle de son retrait.

Arbitrage du développeur : isolation par Django seul. Ces générateurs SQL
restent pour rejouer les migrations existantes ; aucune session ne change de rôle.
"""

import re

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import migrations

REGLAGE_ENTREPRISE = "ccd.entreprise_id"
TABLES_A_ENTREPRISE_NULLABLE = frozenset({"utilisateur", "jeton_reinitialisation", "journal_audit"})
NOM_POLITIQUE = "isolation_entreprise"
_COURANTE = "nullif(current_setting('ccd.entreprise_id', true), '')::uuid"


def role_plateforme():
    """Uniquement pour les migrations historiques qui référencent l'ancien rôle."""
    role = getattr(settings, "CCD_ROLE_PLATEFORME", "ccd_plateforme")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role or ""):
        raise ImproperlyConfigured(f"Nom de rôle historique invalide : {role!r}")
    return role


def _sql_politique(table: str, nullable: bool) -> str:
    condition = (
        f"(entreprise_id = {_COURANTE} OR (entreprise_id IS NULL AND {_COURANTE} IS NULL))"
        if nullable
        else f"(entreprise_id = {_COURANTE})"
    )
    return (
        f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;\n'
        f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;\n'
        f'DROP POLICY IF EXISTS {NOM_POLITIQUE} ON "{table}";\n'
        f'CREATE POLICY {NOM_POLITIQUE} ON "{table}" USING {condition} WITH CHECK {condition};'
    )


def isolation_entreprise(table: str) -> migrations.RunSQL:
    """Opération de migration : RLS forcée et politique d'entreprise sur `table`.

    À ajouter dans la migration qui crée toute nouvelle table d'entreprise — la commande
    `verifier_isolation` (et `check --database default`) signale une table oubliée.
    """
    return migrations.RunSQL(
        sql=_sql_politique(table, table in TABLES_A_ENTREPRISE_NULLABLE),
        reverse_sql=(
            f'DROP POLICY IF EXISTS {NOM_POLITIQUE} ON "{table}";\n'
            f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;\n'
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;'
        ),
    )


# --------------------------------------------------------------------------
# Diagnostic : la deuxième couche est-elle réellement en place ?
# --------------------------------------------------------------------------
def tables_attendues() -> set[str]:
    """Les tables qui doivent porter la politique : tout `ModeleEntreprise` concret, et les
    tables d'entreprise à colonne nullable."""

    from apps.core.models import ModeleEntreprise

    tables = {
        modele._meta.db_table
        for modele in apps.get_models()
        if issubclass(modele, ModeleEntreprise) and modele._meta.managed
    }
    return tables | set(TABLES_A_ENTREPRISE_NULLABLE)


def diagnostic_isolation(connexion, *, tables=True):
    """Signale les tables métier conservant une RLS incompatible avec le mode Django seul."""
    if not tables:
        return []
    with connexion.cursor() as curseur:
        curseur.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND (c.relrowsecurity OR c.relforcerowsecurity)"
        )
        restantes = {nom for (nom,) in curseur} & tables_attendues()
    return [
        f"Table « {nom} » : RLS encore active ; appliquer core.0004 avec le propriétaire."
        for nom in sorted(restantes)
    ]
