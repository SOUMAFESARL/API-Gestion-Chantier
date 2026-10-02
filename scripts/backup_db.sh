#!/usr/bin/env bash
# Sauvegarde PostgreSQL vérifiée, à lancer AVANT toute migration.
#
#   DB_NAME=... DB_USER=... PGPASSWORD=... ./backup_db.sh pre-migrate
#
# Variables : DB_NAME, DB_USER (obligatoires) ; DB_HOST (localhost), DB_PORT (5432),
#             BACKUP_DIR ($HOME/backups/db), KEEP (7, nombre de dumps conservés).
# Mot de passe : PGPASSWORD ou ~/.pgpass (préférable : il n'apparaît pas dans l'environnement).
# Code de sortie != 0 si la sauvegarde est absente, vide ou illisible -> le déploiement doit s'arrêter.
set -euo pipefail

: "${DB_NAME:?DB_NAME manquant}"
: "${DB_USER:?DB_USER manquant}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/db}"
KEEP="${KEEP:-7}"
LABEL="${1:-manual}"

# Sur cPanel / CloudLinux, les utilitaires postgresql peuvent se trouver dans /usr/pgsql-XX/bin
export PATH="/usr/pgsql-16/bin:/usr/pgsql-15/bin:/usr/pgsql-14/bin:/usr/pgsql-13/bin:/usr/local/bin:$PATH"

command -v pg_dump >/dev/null    || { echo "pg_dump introuvable dans le PATH ($PATH)" >&2; exit 1; }
command -v pg_restore >/dev/null || { echo "pg_restore introuvable dans le PATH ($PATH)" >&2; exit 1; }

umask 077
mkdir -p "$BACKUP_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/${DB_NAME}_${LABEL}_${TS}.dump"
TMP="${OUT}.partial"
trap 'rm -f "$TMP"' EXIT

echo "[backup] pg_dump -> $OUT"
# -Fc : format custom (restauration sélective possible, tous les schémas tenants inclus)
pg_dump -Fc --no-owner -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -f "$TMP" "$DB_NAME"

# Vérifications : fichier non vide + archive lisible
[ -s "$TMP" ] || { echo "[backup] ERREUR : dump vide" >&2; exit 1; }
pg_restore --list "$TMP" > "$TMP.list" || { echo "[backup] ERREUR : archive illisible" >&2; rm -f "$TMP.list"; exit 1; }
NB_SCHEMAS="$(grep -c ' SCHEMA - ' "$TMP.list" || true)"
NB_TABLES="$(grep -c ' TABLE ' "$TMP.list" || true)"
rm -f "$TMP.list"

mv "$TMP" "$OUT"
trap - EXIT
sha256sum "$OUT" > "$OUT.sha256"

echo "[backup] OK : $(du -h "$OUT" | cut -f1), ${NB_SCHEMAS} schéma(s) listé(s), ${NB_TABLES} table(s)"

# Rotation : on garde les KEEP derniers dumps de cette base
ls -1t "$BACKUP_DIR/${DB_NAME}"_*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r vieux; do
  echo "[backup] suppression de l'ancien dump : $vieux"
  rm -f -- "$vieux" "$vieux.sha256"
done

echo "$OUT"
