"""Deuxième couche de l'isolation : PostgreSQL filtre de lui-même (D9, règle R-5).

La première couche (`apps.core.managers`) refuse, côté Python, toute requête d'entreprise hors
contexte. Celle-ci tient **même quand la première est contournée** : SQL brut, `_base_manager`,
sous-requête construite hors contexte, filtre oublié. Chaque table d'entreprise porte une politique
de sécurité au niveau des lignes (RLS), **forcée** — elle s'applique aussi au propriétaire des
tables :

    entreprise_id = <le réglage ccd.entreprise_id de la session>

**Comment la session connaît l'entreprise.** Un *execute wrapper* de Django, posé sur chaque
connexion par le moteur `apps.core.backends.postgresql`, compare avant chaque requête l'état
voulu par le contexte Python (`apps.core.contexte`) à celui de la session, et le corrige s'il
diffère :

| Contexte Python | `ccd.entreprise_id` | Rôle de la session | Ce que PostgreSQL laisse voir |
|---|---|---|---|
| une entreprise active | son identifiant | celui de connexion | ses lignes |
| rien | vide | celui de connexion | **aucune ligne d'entreprise** ; le personnel (`utilisateur`) |
| portée plateforme | vide | `ccd_plateforme` (`BYPASSRLS`) | tout |

Le réglage n'est donc jamais « oublié » sur une connexion réutilisée (`CONN_MAX_AGE`) : la
première requête de la requête HTTP suivante le remet d'accord avec son propre contexte, avant de
s'exécuter. Une connexion qui n'a jamais reçu de réglage ne voit rien.

**La portée plateforme bascule le rôle** (`SET ROLE`), sur la même connexion : les transactions
et `select_for_update` restent valables d'un bout à l'autre (arbitrage du 07/11/2026, qui remplace
la « connexion dédiée » d'abord écrite dans la D9).

**Ce que la RLS ne protège pas** : une injection SQL. Qui écrit du SQL sur la connexion peut
changer le réglage lui-même. Elle protège du **code qui oublie de filtrer**, pas du code hostile.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import migrations

from apps.core.contexte import en_portee_plateforme, entreprise_courante_id

logger = logging.getLogger(__name__)

__all__ = [
    "REGLAGE_ENTREPRISE",
    "TABLES_A_ENTREPRISE_NULLABLE",
    "appliquer_contexte_rls",
    "etat_voulu",
    "isolation_entreprise",
    "role_plateforme",
]

REGLAGE_ENTREPRISE = "ccd.entreprise_id"

# Les tables d'entreprise dont `entreprise_id` peut être nul : le personnel de l'éditeur et ce
# qui le suit (R-8), les actions de la plateforme dans le journal (R-11). Une ligne nulle n'est
# visible que **sans** entreprise active — exactement ce que fait `RequeteComptes` côté Python.
TABLES_A_ENTREPRISE_NULLABLE = frozenset({"utilisateur", "jeton_reinitialisation", "journal_audit"})

NOM_POLITIQUE = "isolation_entreprise"

_SANS_REGLAGE = frozenset({"SAVEPOINT", "RELEASE S", "ROLLBACK "})

_COURANTE = f"nullif(current_setting('{REGLAGE_ENTREPRISE}', true), '')::uuid"


def role_plateforme() -> str:
    """Le rôle PostgreSQL de la portée plateforme (`BYPASSRLS`).

    Il est interpolé dans du SQL (migrations, droits) : liste blanche, comme pour les slugs.
    """
    role = getattr(settings, "CCD_ROLE_PLATEFORME", "ccd_plateforme")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role or ""):
        raise ImproperlyConfigured(f"CCD_ROLE_PLATEFORME invalide : {role!r}")
    return role


# --------------------------------------------------------------------------
# À l'exécution : accorder la session au contexte Python
# --------------------------------------------------------------------------
def etat_voulu() -> tuple[str, str]:
    """`(entreprise, rôle)` que la session doit porter pour le contexte en cours."""
    if en_portee_plateforme():
        return "", role_plateforme()
    identifiant = entreprise_courante_id()
    return (str(identifiant) if identifiant else ""), "none"


def appliquer_contexte_rls(execute, sql, params, many, context):
    """*Execute wrapper* : met la session d'accord avec le contexte, puis exécute la requête.

    Une requête de réglage n'est envoyée que lorsque le contexte a changé depuis la précédente :
    sur une requête HTTP ordinaire, une seule, au premier accès à la base.
    """
    connexion = context["connection"]
    voulu = etat_voulu()
    # Les instructions de point de sauvegarde ne lisent aucune ligne, et `ROLLBACK TO SAVEPOINT`
    # doit pouvoir partir d'une transaction en échec, où tout autre ordre serait refusé.
    if not many and isinstance(sql, str) and sql.lstrip()[:9].upper() in _SANS_REGLAGE:
        return execute(sql, params, many, context)
    if getattr(connexion, "etat_rls", None) != voulu:
        try:
            # Le curseur brut de psycopg : ni les autres wrappers ni le journal des requêtes de
            # Django ne voient ce réglage (`assertNumQueries`, `mesurer_requetes` restent justes).
            context["cursor"].cursor.execute(
                "SELECT set_config(%s, %s, false), set_config('role', %s, false)",
                [REGLAGE_ENTREPRISE, voulu[0], voulu[1]],
            )
        except Exception:
            connexion.etat_rls = None
            if voulu[1] != "none":
                logger.error(
                    "Portée plateforme impossible : le rôle PostgreSQL « %s » n'existe pas ou "
                    "n'est pas accordé au rôle de connexion (scripts/sql/roles_rls.sql).",
                    voulu[1],
                )
            raise
        connexion.etat_rls = voulu
    return execute(sql, params, many, context)


# --------------------------------------------------------------------------
# Dans les migrations : poser la politique d'une table
# --------------------------------------------------------------------------
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
    from django.apps import apps

    from apps.core.models import ModeleEntreprise

    tables = {
        modele._meta.db_table
        for modele in apps.get_models()
        if issubclass(modele, ModeleEntreprise) and modele._meta.managed
    }
    return tables | set(TABLES_A_ENTREPRISE_NULLABLE)


def diagnostic_isolation(connexion) -> list[str]:
    """Les défauts de la deuxième couche sur `connexion` ; une liste vide si tout est en place.

    1. le rôle de connexion n'est ni superutilisateur ni `BYPASSRLS` — sinon la RLS, même
       forcée, ne s'applique pas à lui ;
    2. le rôle de la portée plateforme existe, a `BYPASSRLS`, et est accordé au rôle de
       connexion ;
    3. chaque table attendue a la RLS activée, forcée, et sa politique.
    """
    defauts: list[str] = []
    role = role_plateforme()
    with connexion.cursor() as curseur:
        curseur.execute(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        utilisateur, superutilisateur, contourne = curseur.fetchone()
        if superutilisateur or contourne:
            defauts.append(
                f"Le rôle de connexion « {utilisateur} » est superutilisateur ou BYPASSRLS : "
                "PostgreSQL ne lui applique aucune politique. Connecter Django avec un rôle "
                "applicatif (D9, R-5)."
            )

        curseur.execute(
            "SELECT rolbypassrls, pg_has_role(current_user, oid, 'MEMBER') "
            "FROM pg_roles WHERE rolname = %s",
            [role],
        )
        ligne = curseur.fetchone()
        if ligne is None:
            defauts.append(
                f"Le rôle « {role} » n'existe pas : la portée plateforme échouera "
                "(scripts/sql/roles_rls.sql)."
            )
        elif not ligne[0]:
            defauts.append(f"Le rôle « {role} » n'a pas BYPASSRLS.")
        elif not ligne[1]:
            defauts.append(f"Le rôle « {role} » n'est pas accordé à « {utilisateur} ».")

        curseur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies p
                           WHERE p.schemaname = n.nspname AND p.tablename = c.relname
                             AND p.policyname = %s)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
            """,
            [NOM_POLITIQUE],
        )
        etat = {nom: (active, forcee, politique) for nom, active, forcee, politique in curseur}

    for table in sorted(tables_attendues()):
        active, forcee, politique = etat.get(table, (False, False, False))
        if not (active and forcee and politique):
            defauts.append(
                f"Table « {table} » sans isolation complète (RLS active={active}, "
                f"forcée={forcee}, politique={politique}) : isolation_entreprise(\"{table}\")."
            )
    return defauts
