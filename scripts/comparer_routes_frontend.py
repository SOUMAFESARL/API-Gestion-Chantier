#!/usr/bin/env python
"""
Compare les routes servies par ce backend aux appels du frontend, dans les deux sens.

Usage (depuis la racine du projet API, venv activé) :

    python scripts/comparer_routes_frontend.py
    python scripts/comparer_routes_frontend.py --domaine chantier
    python scripts/comparer_routes_frontend.py --frontend ../Application-Gestion-Chantier

Ce qu'il dit :
  1. les appels du frontend dont la route n'existe pas ici ;
  2. les routes servies ici qu'aucun code du frontend n'appelle.

Ce qu'il ne dit pas :
  * la forme des données. Une route « présente » peut encore échouer parce qu'un
    champ a changé de nom : ce contrôle se fait champ par champ, à la main.
  * les appels dont le chemin est construit par morceaux. La détection lit le
    texte des chemins ; un chemin assemblé à partir de variables lui échappe, et
    sa route apparaît à tort comme « jamais appelée ».

LECTURE SEULE : aucune requête en base, aucun fichier écrit.
Code de sortie 0 = aucun appel sans route ; 1 = au moins un.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PREFIXE = "/api/v1"

# Routes techniques : elles n'ont pas vocation à être appelées par un écran.
ROUTES_TECHNIQUES = (
    "/docs/",
    "/schema/",
    "/maintenance/",
    "/billing/cinetpay/webhook/",
    "/cinetpay/webhook/",
)

# Les verbes du client du frontend (`lib/api/client.ts`).
VERBES = {"lire": "GET", "creer": "POST", "modifier": "PATCH", "supprimer": "DELETE"}

APPEL_CLIENT = re.compile(
    r"\b(?:api|apiAdministration|apiPlateforme)\.(\w+)\s*(?:<[^;]*?>)?\(\s*([`\"'])(/.*?)\2",
    re.S,
)
APPEL_DIRECT = re.compile(
    r"\bappeler\s*<[^;]*?>\(\s*([`\"'])(/.*?)\1\s*,\s*\{[^}]*?methode:\s*\"(\w+)\"",
    re.S,
)


def normaliser(chemin: str) -> str:
    """`/projets/${id}/lots` et `/projets/{pk}/lots/` deviennent `/projets/{}/lots/`."""
    chemin = re.sub(r"\$\{[^}]*\}", "{}", chemin.split("?")[0])
    # Une interpolation coupée par le `?` d'une chaîne de requête : `/meteo/${chaine `.
    chemin = re.sub(r"\$\{[^}]*$", "", chemin)
    chemin = re.sub(r"\{[^}]*\}", "{}", chemin)
    return chemin if chemin.endswith("/") else chemin + "/"


def routes_du_backend() -> list[str]:
    sys.path.insert(0, str(RACINE))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    import django

    django.setup()
    from django.urls import URLResolver, get_resolver

    def parcourir(resolveur, prefixe=""):
        for motif in resolveur.url_patterns:
            chemin = prefixe + str(motif.pattern)
            if isinstance(motif, URLResolver):
                yield from parcourir(motif, chemin)
            else:
                yield chemin

    prefixe = PREFIXE.strip("/") + "/"
    routes = {
        "/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", chemin[len(prefixe) :])
        for chemin in parcourir(get_resolver("config.urls_tenant"))
        if chemin.startswith(prefixe)
    }
    return sorted(routes)


def sources_du_frontend(frontend: Path) -> list[tuple[Path, str]]:
    sources = []
    for dossier in ("features", "lib", "app", "components", "hooks"):
        for fichier in (frontend / dossier).rglob("*.ts*"):
            # La simulation rejoue les routes : la compter fausserait les deux sens.
            if "simulation" in fichier.name.lower():
                continue
            sources.append((fichier, fichier.read_text(encoding="utf-8", errors="ignore")))
    return sources


def appels_du_frontend(sources, frontend: Path):
    """Les appels écrits en clair, regroupés par domaine (`features/<domaine>`, `lib/api`)."""
    appels = defaultdict(set)
    for fichier, texte in sources:
        relatif = fichier.relative_to(frontend).as_posix()
        if not relatif.startswith(("features/", "lib/")):
            continue
        domaine = "/".join(relatif.split("/")[:2])
        for trouve in APPEL_CLIENT.finditer(texte):
            verbe = VERBES.get(trouve.group(1), trouve.group(1))
            appels[domaine].add((normaliser(trouve.group(3)), verbe))
        for trouve in APPEL_DIRECT.finditer(texte):
            appels[domaine].add((normaliser(trouve.group(2)), trouve.group(3)))
    return appels


def routes_sans_appelant(routes: list[str], sources) -> list[str]:
    texte = "\n".join(contenu for _, contenu in sources)
    orphelines = []
    for route in routes:
        if route.startswith(ROUTES_TECHNIQUES):
            continue
        segments = [
            r"\$\{[^}]*\}" if segment.startswith("{") else re.escape(segment)
            for segment in route.strip("/").split("/")
        ]
        motif = re.compile(r"[\"'`]/" + "/".join(segments) + r"/?(?:[\"'`?]|\$\{)")
        if not motif.search(texte):
            orphelines.append(route)
    return orphelines


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    analyseur.add_argument(
        "--frontend",
        default=str(RACINE.parent / "Application-Gestion-Chantier"),
        help="Chemin du dépôt frontend (par défaut : le dossier voisin).",
    )
    analyseur.add_argument(
        "--domaine",
        help="Ne montrer qu'un domaine : `chantier`, `projets`, `admins`, …",
    )
    options = analyseur.parse_args()

    frontend = Path(options.frontend).resolve()
    if not (frontend / "features").is_dir():
        print(f"Dépôt frontend introuvable : {frontend}", file=sys.stderr)
        return 2

    routes = routes_du_backend()
    connues = {normaliser(route) for route in routes}
    sources = sources_du_frontend(frontend)
    appels = appels_du_frontend(sources, frontend)
    filtre = options.domaine

    print(f"{len(routes)} routes servies sous {PREFIXE}/\n")
    print("1. APPELS DU FRONTEND SANS ROUTE")
    total_absentes = 0
    for domaine in sorted(appels):
        if filtre and filtre not in domaine:
            continue
        absentes = sorted(appel for appel in appels[domaine] if appel[0] not in connues)
        total_absentes += len(absentes)
        print(f"\n  {domaine} : {len(appels[domaine])} appels, {len(absentes)} sans route")
        for chemin, verbe in absentes:
            print(f"      {verbe:6} {chemin}")

    print("\n2. ROUTES SERVIES, JAMAIS APPELÉES")
    par_groupe = defaultdict(list)
    for route in routes_sans_appelant(routes, sources):
        par_groupe[route.strip("/").split("/")[0]].append(route)
    total_orphelines = 0
    for groupe in sorted(par_groupe):
        if filtre and filtre not in groupe:
            continue
        total_orphelines += len(par_groupe[groupe])
        print(f"\n  {groupe} ({len(par_groupe[groupe])})")
        for route in par_groupe[groupe]:
            print(f"      {route}")

    print(
        f"\nBilan : {total_absentes} appel(s) sans route, "
        f"{total_orphelines} route(s) sans appelant."
    )
    return 1 if total_absentes else 0


if __name__ == "__main__":
    sys.exit(main())
