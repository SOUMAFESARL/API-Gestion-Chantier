#!/usr/bin/env python
"""
Audit LECTURE SEULE du catalogue Module / Permission : public vs tenants.

Usage (depuis la racine du projet API, venv activé) :

    # Audit, sortie JSON horodatée
    python audit_catalogue.py --settings config.settings.production --out audit_avant.json

    # Comparer deux audits (avant / après une phase de migration), sans Django
    python audit_catalogue.py --comparer audit_avant.json audit_apres.json

Garanties :
  * La session PostgreSQL est forcée en `default_transaction_read_only = on`
    à chaque connexion, et le script refuse de démarrer si ce n'est pas confirmé.
  * Tout est lu via `_base_manager` : les lignes soft-deletées sont incluses.
  * Un tenant cassé (migrations en retard, table absente...) est listé,
    il n'arrête pas l'audit.
  * Code de sortie 0 = aucun problème bloquant ; 1 = problèmes ; 2 = erreur fatale.

A ADAPTER (non vérifié, je n'ai pas vu les modèles) :
  - le bloc IMPORTS ci-dessous ;
  - PRMO_CLES : champs qui forment la clé d'unicité de ProjetRoleModuleOverride
    (hors module). Les noms absents du modèle sont ignorés et signalés.
Après la migration vers `apps.catalogue`, seul le bloc IMPORTS change.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

CHAMPS_MODULE = ["libelle", "description", "ordre", "icone", "est_actif", "supprime_le"]
CHAMPS_PERMISSION = ["libelle", "description", "ordre", "est_actif", "supprime_le"]
PRMO_CLES = ["projet_id", "role_id"]


# --------------------------------------------------------------------------- #
# Mode comparaison (sans Django)
# --------------------------------------------------------------------------- #
def comparer(avant_path, apres_path):
    with open(avant_path, encoding="utf-8") as f:
        a = json.load(f)
    with open(apres_path, encoding="utf-8") as f:
        b = json.load(f)
    cles = [
        ("modules", "nb"), ("roles", "nb"),
        ("role_module_permission", "total"), ("projet_role_module_override", "total"),
        ("permission_modules", "total"), ("role_permissions", "total"),
    ]
    ecarts = 0
    tenants = sorted(set(a["tenants"]) | set(b["tenants"]))
    for t in tenants:
        ta, tb = a["tenants"].get(t), b["tenants"].get(t)
        if ta is None or tb is None:
            print(f"[{t}] présent d'un seul côté")
            ecarts += 1
            continue
        if "erreur" in ta or "erreur" in tb:
            print(f"[{t}] erreur d'audit : avant={ta.get('erreur')} apres={tb.get('erreur')}")
            ecarts += 1
            continue
        for bloc, cle in cles:
            va = (ta.get(bloc) or {}).get(cle)
            vb = (tb.get(bloc) or {}).get(cle)
            if va != vb:
                print(f"[{t}] {bloc}.{cle} : {va} -> {vb}")
                ecarts += 1
    print(f"\n{ecarts} écart(s) sur {len(tenants)} tenant(s).")
    return 1 if ecarts else 0


# --------------------------------------------------------------------------- #
# Django
# --------------------------------------------------------------------------- #
def init_django(settings_module):
    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    sys.path.insert(0, os.getcwd())
    import django
    from django.db.backends.signals import connection_created

    def forcer_lecture_seule(sender, connection, **kwargs):
        with connection.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")

    connection_created.connect(forcer_lecture_seule)
    django.setup()

    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        etat = cur.fetchone()[0]
    if etat != "on":
        print("ERREUR FATALE : la session n'est pas en lecture seule.", file=sys.stderr)
        sys.exit(2)


def champs_existants(model, voulus):
    noms = {f.name for f in model._meta.concrete_fields}
    return [c for c in voulus if c in noms]


def lignes(model, champs):
    return list(model._base_manager.values("id", "code", *champs))


def analyser_catalogue(pub_rows, ten_rows, champs):
    """Compare le catalogue d'un tenant à public, par `code`."""
    def doublons(rows):
        c = Counter(r["code"] for r in rows)
        return sorted(k for k, v in c.items() if v > 1)

    def actifs(rows):
        return [r for r in rows if r.get("supprime_le") is None] if "supprime_le" in champs else rows

    def par_code(rows):
        d = {}
        for r in rows:  # une ligne active écrase une ligne supprimée
            if r["code"] not in d or r.get("supprime_le") is None:
                d[r["code"]] = r
        return d

    p, t = par_code(pub_rows), par_code(ten_rows)
    divergences = []
    uuid_divergents = 0
    for code, tr in t.items():
        pr = p.get(code)
        if not pr:
            continue
        if tr["id"] != pr["id"]:
            uuid_divergents += 1
        diff = {c: [tr.get(c), pr.get(c)] for c in champs if tr.get(c) != pr.get(c)}
        if diff:
            divergences.append({"code": code, "champs": {k: [str(x) for x in v] for k, v in diff.items()}})
    return {
        "nb": len(ten_rows),
        "doublons_code": doublons(ten_rows),
        "doublons_code_actifs": doublons(actifs(ten_rows)),
        "manquants_dans_tenant": sorted(set(p) - set(t)),
        "en_trop_dans_tenant": sorted(set(t) - set(p)),
        "uuid_divergents": uuid_divergents,
        "divergences_champs": divergences,
    }


def doublons_groupes(qs, cles, compte="id"):
    from django.db.models import Count
    res = qs.values(*cles).annotate(n=Count(compte)).filter(n__gt=1)
    return [{**{k: str(r[k]) for k in cles}, "n": r["n"]} for r in res[:50]]


def auditer_tenant(M, codes_modules, codes_perms):
    Module, Permission, Role, RMP, PRMO = M["Module"], M["Permission"], M["Role"], M["RMP"], M["PRMO"]
    out = {}

    cm, cp = champs_existants(Module, CHAMPS_MODULE), champs_existants(Permission, CHAMPS_PERMISSION)
    out["modules"] = analyser_catalogue(M["pub_modules"], lignes(Module, cm), cm)
    out["permissions"] = analyser_catalogue(M["pub_perms"], lignes(Permission, cp), cp)
    out["roles"] = {"nb": Role._base_manager.count()}

    # --- RoleModulePermission
    qs = RMP._base_manager.all()
    rmp = {
        "total": qs.count(),
        "orphelins": qs.exclude(module__code__in=codes_modules).count(),
        # groupé par CODE de module : détecte les collisions futures après repointage
        "doublons_role_code_module": doublons_groupes(qs, ["role_id", "module__code"]),
    }
    if "supprime_le" in {f.name for f in RMP._meta.concrete_fields}:
        rmp["supprimees"] = qs.filter(supprime_le__isnull=False).count()
    out["role_module_permission"] = rmp

    # --- ProjetRoleModuleOverride
    noms = {f.attname for f in PRMO._meta.concrete_fields}
    cles = [c for c in PRMO_CLES if c in noms]
    manquantes = [c for c in PRMO_CLES if c not in noms]
    qs = PRMO._base_manager.all()
    prmo = {
        "total": qs.count(),
        "orphelins": qs.exclude(module__code__in=codes_modules).count(),
        "doublons_cles_module": doublons_groupes(qs, cles + ["module__code"]) if cles else [],
    }
    if manquantes:
        prmo["avertissement"] = f"champs PRMO_CLES absents du modèle : {manquantes}"
    out["projet_role_module_override"] = prmo

    # --- Permission.modules (M2M)
    PM = Permission.modules.through
    qs = PM._base_manager.all()
    out["permission_modules"] = {
        "total": qs.count(),
        "orphelins_module": qs.exclude(module__code__in=codes_modules).count(),
        "orphelins_permission": qs.exclude(permission__code__in=codes_perms).count(),
        "doublons": doublons_groupes(qs, ["permission__code", "module__code"]),
    }

    # --- RoleModulePermission.permissions (M2M vers Permission)
    try:
        RP = RMP.permissions.through
        qs = RP._base_manager.all()
        out["role_permissions"] = {
            "total": qs.count(),
            "orphelins_permission": qs.exclude(permission__code__in=codes_perms).count(),
        }
    except AttributeError:
        out["role_permissions"] = {"total": None, "avertissement": "pas de M2M permissions sur RMP"}
    return out


def problemes(res):
    """Liste des problèmes BLOQUANTS pour un tenant."""
    if "erreur" in res:
        return [f"audit impossible : {res['erreur']}"]
    p = []
    for bloc in ("modules", "permissions"):
        b = res[bloc]
        if b["doublons_code"]:
            p.append(f"{bloc}: codes en double {b['doublons_code']}")
        if b["manquants_dans_tenant"]:
            p.append(f"{bloc}: manquants {b['manquants_dans_tenant']}")
        if b["en_trop_dans_tenant"]:
            p.append(f"{bloc}: en trop {b['en_trop_dans_tenant']}")
        if b["divergences_champs"]:
            p.append(f"{bloc}: {len(b['divergences_champs'])} divergence(s) de champs")
    for bloc, cle in [("role_module_permission", "orphelins"), ("projet_role_module_override", "orphelins"),
                      ("permission_modules", "orphelins_module"), ("permission_modules", "orphelins_permission"),
                      ("role_permissions", "orphelins_permission")]:
        if res.get(bloc, {}).get(cle):
            p.append(f"{bloc}.{cle} = {res[bloc][cle]}")
    for bloc, cle in [("role_module_permission", "doublons_role_code_module"),
                      ("projet_role_module_override", "doublons_cles_module"),
                      ("permission_modules", "doublons")]:
        if res.get(bloc, {}).get(cle):
            p.append(f"{bloc}: doublons {len(res[bloc][cle])}")
    return p


def lancer(args):
    init_django(args.settings)

    # IMPORTS : à adapter si les chemins diffèrent
    from django_tenants.utils import schema_context
    from apps.tenants.models import Entreprise
    from apps.accounts.models import Module, Permission, Role, RoleModulePermission as RMP
    from apps.projets.models import ProjetRoleModuleOverride as PRMO

    with schema_context("public"):
        cm, cp = champs_existants(Module, CHAMPS_MODULE), champs_existants(Permission, CHAMPS_PERMISSION)
        pub_modules, pub_perms = lignes(Module, cm), lignes(Permission, cp)
    codes_modules = {r["code"] for r in pub_modules}
    codes_perms = {r["code"] for r in pub_perms}

    M = {"Module": Module, "Permission": Permission, "Role": Role, "RMP": RMP, "PRMO": PRMO,
         "pub_modules": pub_modules, "pub_perms": pub_perms}

    resultat = {
        "meta": {
            "date_utc": datetime.now(timezone.utc).isoformat(),
            "settings": args.settings,
            "lecture_seule_confirmee": True,
        },
        "public": {
            "modules": [{k: str(v) for k, v in r.items()} for r in pub_modules],
            "permissions": [{k: str(v) for k, v in r.items()} for r in pub_perms],
            "doublons_code_modules": [k for k, v in Counter(r["code"] for r in pub_modules).items() if v > 1],
            "doublons_code_permissions": [k for k, v in Counter(r["code"] for r in pub_perms).items() if v > 1],
        },
        "tenants": {},
    }

    nb_problemes = len(resultat["public"]["doublons_code_modules"]) + len(resultat["public"]["doublons_code_permissions"])
    entreprises = Entreprise._base_manager.exclude(schema_name="public").order_by("schema_name")
    for e in entreprises:
        try:
            with schema_context(e.schema_name):
                res = auditer_tenant(M, codes_modules, codes_perms)
        except Exception as exc:  # un tenant cassé ne doit pas arrêter l'audit
            res = {"erreur": f"{type(exc).__name__}: {exc}"}
        res["problemes"] = problemes(res)
        nb_problemes += len(res["problemes"])
        resultat["tenants"][e.schema_name] = res
        etat = "OK " if not res["problemes"] else "KO "
        print(f"{etat}{e.schema_name}")
        for ligne in res["problemes"]:
            print(f"      - {ligne}")

    resultat["meta"]["nb_tenants"] = len(resultat["tenants"])
    resultat["meta"]["nb_problemes"] = nb_problemes
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n{len(resultat['tenants'])} tenant(s), {nb_problemes} problème(s) bloquant(s). Détail : {args.out}")
    return 1 if nb_problemes else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", default=os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.production"))
    ap.add_argument("--out", default=f"audit_catalogue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    ap.add_argument("--comparer", nargs=2, metavar=("AVANT", "APRES"))
    args = ap.parse_args()
    sys.exit(comparer(*args.comparer) if args.comparer else lancer(args))


if __name__ == "__main__":
    main()
