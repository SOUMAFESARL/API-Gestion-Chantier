#!/usr/bin/env bash
set -euo pipefail

app_root=${1:?Application root requis}
python_bin=${2:?Chemin absolu du Python cPanel requis}
commit=${3:?Commit Git requis}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]]
[[ "$app_root" == /home/* && "$python_bin" == /home/* ]]
cd -- "$app_root"
test "$(pwd -P)" = "$(git rev-parse --show-toplevel)"
test -x "$python_bin"
test -f .env
command -v flock >/dev/null
exec 9>.git/cpanel-deploy.lock
flock -n 9 || { echo 'Un deploiement est deja en cours.' >&2; exit 1; }
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain --untracked-files=no)" || {
  echo 'Modifications locales suivies par Git : deploiement interrompu.' >&2
  exit 1
}
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ requis"'
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes'
git fetch origin main
test "$(git rev-parse origin/main)" = "$commit" || {
  echo 'main a change depuis les tests ; attendre le workflow du nouveau commit.' >&2
  exit 1
}
git merge --ff-only "$commit"
export DJANGO_SETTINGS_MODULE=config.settings.cpanel
"$python_bin" -m pip install -r requirements/production.txt
"$python_bin" -m pip check
"$python_bin" manage.py check
"$python_bin" manage.py migrate_schemas --noinput
"$python_bin" manage.py collectstatic --noinput
mkdir -p tmp
touch tmp/restart.txt
printf 'Commit deploye : %s\n' "$commit"
