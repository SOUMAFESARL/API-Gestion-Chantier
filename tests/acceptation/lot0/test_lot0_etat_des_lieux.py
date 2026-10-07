"""
TESTS D'ACCEPTATION DU LOT 0, VERROUILLÉS.

RÈGLES POUR GEMINI (rappel, voir 02-plan-par-lots.md, section « Protocole ») :
  - Ce fichier ne se modifie JAMAIS. Ni assertion, ni message, ni constante, ni import.
  - Aucun skip, xfail, try/except ou « if » ne se rajoute pour faire passer un test.
  - Si un test échoue parce que ce qu'il demande semble impossible ou absurde,
    Gemini s'arrête et écrit une question dans docs/refonte/questions-ouvertes.md.

CE QUE LE LOT 0 FAIT : aucun changement de comportement. Gemini produit un inventaire
(docs/refonte/inventaire-lot0.md, gabarit : gabarit-inventaire-lot0.md) et des tests de
caractérisation. Ces tests vérifient l'inventaire CONTRE LE VRAI CODE (lignes citées,
recomptages), pour qu'il soit impossible d'inventer une référence.

PRÉREQUIS HUMAINS (faits par Durel, pas par Gemini) :
  1. Branche `refonte-droits` créée, et tag `base-refonte` posé sur le commit de départ.
  2. Cahier gelé copié dans docs/refonte/cahier-regles.md avec la ligne « Statut : GELÉ ».
  3. Variable d'environnement FRONT_REPO = chemin du dépôt Application-Gestion-Chantier.
  4. Ce fichier commité, puis tag `verrouille-lot0` posé sur ce commit.

HYPOTHÈSES À CONFIRMER (non vérifiables sans le dépôt) :
  - ce fichier est dans <racine_backend>/tests/acceptation/lot0/ ;
  - `python manage.py migrate_schemas` existe à la racine (django-tenants) ;
  - pytest se lance depuis la racine du backend.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(os.environ.get("BACKEND_ROOT", Path(__file__).resolve().parents[3]))
REFONTE = ROOT / "docs" / "refonte"
INVENTAIRE = REFONTE / "inventaire-lot0.md"
QUESTIONS = REFONTE / "questions-ouvertes.md"
CAHIER = REFONTE / "cahier-regles.md"
BASELINE = REFONTE / "baseline-tests.txt"
NOTES = ROOT / "docs" / "notes-changement-api.md"
CARACT = ROOT / "tests" / "caracterisation"

BRANCHE = "refonte-droits"
TAG_BASE = "base-refonte"
TAG_VERROU = "verrouille-lot0"

EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv", "env",
    "migrations", "staticfiles", "htmlcov", ".pytest_cache", ".mypy_cache",
}

PREFIXES_AUTORISES = ("docs/refonte/", "tests/caracterisation/", "tests/acceptation/lot0/")
FICHIERS_AUTORISES = {"docs/notes-changement-api.md"}

SECTIONS_REQUISES = [f"I-{n:02d}" for n in range(1, 11)]

MOTS_I09 = [
    "PermissionModule", "MembreDuProjet", "RoleRequis", "RoleGlobal", "role_global",
    "ROLES_DIRECTION", "ROLES_GESTION_CHANTIER", "ROLES_VALIDATION_CHANTIER",
    "ContexteCreationProjetView", "ProjetRoleModuleOverride", "appliquer_modeles_roles",
]

CLES_I03 = [
    "Limite collaborateurs actifs", "Limite projets", "Erreur dédiée à la limite",
    "Abonnement expiré (lecture seule)", "Actions de paiement",
]
CLES_I04 = [
    "Claim read_only émis", "Middleware lecteur du claim", "Méthodes bloquées",
    "Journalisation début de session", "Journalisation fin de session", "E-mail au DG",
]
CLES_I10 = [
    "Tâche de fond (mécanisme)", "Envoi d'e-mail existant", "Journal d'audit existant",
]

MOTS_INTERDITS = [
    "TODO", "TBD", "à compléter", "probablement", "sans doute", "je suppose",
    "il semble", "peut-être", "vraisemblablement", "?",
]

REF = re.compile(r"(?<![\w/.\-])((?:[\w.\-]+/)*[\w.\-]+\.\w+):(\d+)\b")
ENTREE = re.compile(r"^- (\S+?):(\d+) \| (.+)$")
CLE_VALEUR = re.compile(r"^- (.+?) : (.*?) \| (.+)$")
ID_REGLE = re.compile(r"\b[A-H]-\d{2}\b")


# ----------------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------------
def git(*args, cwd=None):
    r = subprocess.run(
        ["git", *args], cwd=cwd or ROOT, capture_output=True, text=True
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def lire(chemin: Path) -> str:
    assert chemin.exists(), f"Fichier manquant : {chemin.relative_to(ROOT) if ROOT in chemin.parents else chemin}"
    return chemin.read_text(encoding="utf-8")


def fichiers_py(production_seulement: bool):
    for dossier, sous, fichiers in os.walk(ROOT):
        d = Path(dossier)
        rel = d.relative_to(ROOT).as_posix()
        sous[:] = [s for s in sous if s not in EXCLUDED_DIRS and not s.endswith(".egg-info")]
        if rel.startswith(("tests/acceptation", "tests/caracterisation", "docs")):
            sous[:] = []
            continue
        if production_seulement and ({"tests", "test"} & set(d.relative_to(ROOT).parts)):
            sous[:] = []
            continue
        for f in fichiers:
            if not f.endswith(".py"):
                continue
            if production_seulement and (
                f.startswith("test_") or f.endswith("_test.py") or f == "conftest.py"
            ):
                continue
            yield d / f


def lignes_de(chemin: Path):
    return chemin.read_text(encoding="utf-8", errors="replace").splitlines()


def verifier_ref(chemin_rel: str, ligne: int):
    p = ROOT / chemin_rel
    assert p.is_file(), f"Référence invalide : fichier inexistant {chemin_rel}"
    n = len(lignes_de(p))
    assert 1 <= ligne <= n, f"Référence invalide : {chemin_rel}:{ligne} (le fichier a {n} lignes)"


def decouper_sections(texte: str):
    res, courant = {}, None
    for ligne in texte.splitlines():
        m = re.match(r"^##\s+(I-\d{2})\b", ligne)
        if m:
            courant = m.group(1)
            res[courant] = []
            continue
        if re.match(r"^##\s", ligne):
            courant = None
            continue
        if courant:
            res[courant].append(ligne)
    return res


def lire_total(lignes):
    for l in lignes:
        m = re.match(r"^Total : (\d+)\s*$", l.strip())
        if m:
            return int(m.group(1))
    pytest.fail("Ligne « Total : N » manquante dans la section")


def entrees(lignes):
    res = []
    for l in lignes:
        if l.startswith("- "):
            m = ENTREE.match(l)
            assert m, f"Entrée mal formée (attendu « - chemin:ligne | description ») : {l!r}"
            res.append((m.group(1), int(m.group(2)), m.group(3)))
    return res


def cles_valeurs(lignes):
    res = {}
    for l in lignes:
        m = CLE_VALEUR.match(l)
        if m:
            res[m.group(1)] = (m.group(2), m.group(3).strip())
    return res


def verifier_refs_ou_absent(refs: str, cle: str):
    if refs == "ABSENT":
        return
    trouvees = REF.findall(refs)
    assert trouvees, f"{cle} : après « | » mettre « ABSENT » ou des références chemin:ligne, trouvé {refs!r}"
    for chemin, ligne in trouvees:
        verifier_ref(chemin, int(ligne))


def ids_du_cahier():
    texte = lire(CAHIER)
    return set(re.findall(r"^\*\*([A-H]-\d{2})\b", texte, flags=re.M))


def questions():
    """Retourne la liste des (id, regle, statut) du fichier de questions."""
    texte = lire(QUESTIONS)
    res = []
    for l in texte.splitlines():
        if l.startswith("## "):
            m = re.match(r"^## (Q-\d{3}) \| ([A-H]-\d{2}|GENERAL) \| (OUVERTE|RESOLUE)\s*$", l)
            assert m, (
                "Titre de question mal formé (attendu « ## Q-001 | B-03 | OUVERTE ») : "
                f"{l!r}"
            )
            res.append(m.groups())
    return res


@pytest.fixture(scope="module")
def inv():
    return decouper_sections(lire(INVENTAIRE))


# ----------------------------------------------------------------------------
# Git, périmètre, méthode (G-01, G-05)
# ----------------------------------------------------------------------------
def test_g05_branche_refonte_droits():
    """[G-05] Le travail se fait sur la branche refonte-droits."""
    code, out, err = git("rev-parse", "--abbrev-ref", "HEAD")
    assert code == 0, err
    assert out == BRANCHE, f"Branche courante : {out!r}, attendue : {BRANCHE!r}"


def test_g05_tags_de_reference_presents():
    """[G-05] Les tags posés par Durel existent."""
    for tag in (TAG_BASE, TAG_VERROU):
        code, _, _ = git("rev-parse", "-q", "--verify", f"refs/tags/{tag}")
        assert code == 0, f"Tag manquant : {tag} (à poser par Durel, pas par Gemini)"


def test_g05_tests_verrouilles_intacts():
    """[G-05] Aucun fichier de tests/acceptation/lot0 n'a changé depuis le verrouillage."""
    code, out, err = git("diff", "--name-only", TAG_VERROU, "HEAD", "--", "tests/acceptation/lot0")
    assert code == 0, err
    assert out == "", f"Tests verrouillés modifiés :\n{out}"


def test_lot0_aucun_code_de_production_modifie():
    """[G-05] Le lot 0 n'ajoute que docs/refonte, tests/caracterisation, et les notes API."""
    code, out, err = git("diff", "--name-status", f"{TAG_BASE}..HEAD")
    assert code == 0, err
    interdits = []
    for l in out.splitlines():
        champs = l.split("\t")
        statut, chemins = champs[0], champs[1:]
        for chemin in chemins:
            autorise = chemin.startswith(PREFIXES_AUTORISES) or chemin in FICHIERS_AUTORISES
            if not autorise:
                interdits.append(f"{statut}\t{chemin}")
            elif chemin not in FICHIERS_AUTORISES and statut[0] != "A":
                interdits.append(f"{statut}\t{chemin} (seuls les ajouts sont permis)")
    assert not interdits, "Fichiers hors périmètre du lot 0 :\n" + "\n".join(interdits)


def test_lot0_arbre_de_travail_propre():
    """[G-05] Tout est commité à la fin du lot."""
    code, out, err = git("status", "--porcelain")
    assert code == 0, err
    assert out == "", f"Modifications non commitées :\n{out}"


def test_g01_depot_front_intact():
    """[G-01] Le dépôt front n'a aucune modification."""
    chemin = os.environ.get("FRONT_REPO")
    assert chemin, "Variable d'environnement FRONT_REPO non définie (à définir par Durel)"
    p = Path(chemin)
    assert p.is_dir(), f"FRONT_REPO ne pointe pas sur un dossier : {chemin}"
    code, out, err = git("status", "--porcelain", cwd=p)
    assert code == 0, err
    assert out == "", f"Le dépôt front a été modifié :\n{out}"


def test_g04_migrate_schemas_passe():
    """[G-04] Les migrations s'appliquent sur les schémas de développement."""
    r = subprocess.run(
        [sys.executable, "manage.py", "migrate_schemas"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    assert r.returncode == 0, f"migrate_schemas a échoué :\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"


# ----------------------------------------------------------------------------
# Cahier gelé et notes (G-03)
# ----------------------------------------------------------------------------
def test_cahier_gele_present():
    """Le cahier gelé est dans le dépôt, avec ses identifiants de règles."""
    texte = lire(CAHIER)
    assert re.search(r"^Statut : GELÉ\s*$", texte, flags=re.M), "Ligne « Statut : GELÉ » manquante"
    ids = ids_du_cahier()
    for attendu in ("A-01", "B-03", "E-13", "H-02"):
        assert attendu in ids, f"Règle {attendu} introuvable dans le cahier"


def test_g03_notes_de_changement_api_existent():
    """[G-03] Le fichier de notes existe avec son titre."""
    texte = lire(NOTES)
    assert texte.lstrip().startswith("# Notes de changement API"), (
        "Le fichier doit commencer par « # Notes de changement API »"
    )


# ----------------------------------------------------------------------------
# Inventaire : structure
# ----------------------------------------------------------------------------
def test_inventaire_contient_toutes_les_sections(inv):
    manquantes = [s for s in SECTIONS_REQUISES if s not in inv]
    assert not manquantes, f"Sections manquantes dans l'inventaire : {manquantes}"


def test_inventaire_sans_hesitation_ni_placeholder():
    """Tout doute va dans questions-ouvertes.md, jamais dans l'inventaire."""
    texte = lire(INVENTAIRE)
    trouves = [m for m in MOTS_INTERDITS if m.lower() in texte.lower()]
    assert not trouves, f"Termes interdits dans l'inventaire (poser une question à la place) : {trouves}"


def test_inventaire_et_questions_ne_citent_que_des_regles_existantes():
    """Aucune règle inventée : tout identifiant cité existe dans le cahier gelé."""
    connus = ids_du_cahier()
    for chemin in (INVENTAIRE, QUESTIONS):
        cites = set(ID_REGLE.findall(lire(chemin)))
        inconnus = cites - connus
        assert not inconnus, f"{chemin.name} cite des règles absentes du cahier : {sorted(inconnus)}"


def test_questions_format_valide():
    """Le fichier de questions existe et chaque question est bien formée."""
    qs = questions()
    ids = [q[0] for q in qs]
    assert len(ids) == len(set(ids)), "Identifiants de questions en double"


# ----------------------------------------------------------------------------
# Inventaire : contenu vérifié contre le code
# ----------------------------------------------------------------------------
def test_i01_niveau_max_liste_exacte_et_complete(inv):
    """[A-12] Toutes les lignes contenant niveau_max sont listées, et seulement elles."""
    declarees = {(c, n) for c, n, _ in entrees(inv["I-01"])}
    reelles = set()
    for p in fichiers_py(production_seulement=False):
        for no, ligne in enumerate(lignes_de(p), start=1):
            if "niveau_max" in ligne:
                reelles.add((p.relative_to(ROOT).as_posix(), no))
    assert declarees == reelles, (
        f"Manquantes : {sorted(reelles - declarees)}\nEn trop : {sorted(declarees - reelles)}"
    )
    assert lire_total(inv["I-01"]) == len(reelles)


def test_i02_conditions_copiees_du_dg(inv):
    """[B-03] Chaque condition citée existe et parle du DG ; le total est déclaré."""
    liste = entrees(inv["I-02"])
    assert liste, "Aucune condition listée"
    for chemin, ligne, _ in liste:
        verifier_ref(chemin, ligne)
        assert "dg" in lignes_de(ROOT / chemin)[ligne - 1].lower(), (
            f"{chemin}:{ligne} ne mentionne pas le DG"
        )
    total = lire_total(inv["I-02"])
    assert total == len(liste)
    if total != 5:
        assert any(q[1] == "B-03" for q in questions()), (
            f"Le cahier annonce 5 conditions, l'inventaire en trouve {total} : "
            "une question B-03 est obligatoire"
        )


@pytest.mark.parametrize(
    "section,cles",
    [("I-03", CLES_I03), ("I-04", CLES_I04), ("I-10", CLES_I10)],
)
def test_i03_i04_i10_constats_references(inv, section, cles):
    """[C-04, H-01, A-14] Chaque constat est soit ABSENT, soit appuyé par des références réelles."""
    kv = cles_valeurs(inv[section])
    for cle in cles:
        assert cle in kv, f"{section} : ligne « - {cle} : <valeur> | <refs ou ABSENT> » manquante"
        valeur, refs = kv[cle]
        assert valeur.strip(), f"{section} / {cle} : valeur vide"
        verifier_refs_ou_absent(refs, f"{section} / {cle}")


def test_i05_statut_critique_caracterise(inv):
    """[E-09] Le comportement actuel est constaté par un test de caractérisation."""
    kv = cles_valeurs(inv["I-05"])
    cle = "Comportement actuel du statut CRITIQUE"
    assert cle in kv, f"Ligne « - {cle} : CONSERVE|ECRASE|STATUT_ABSENT | refs » manquante"
    valeur, refs = kv[cle]
    assert valeur in {"CONSERVE", "ECRASE", "STATUT_ABSENT"}, f"Valeur invalide : {valeur!r}"
    assert refs != "ABSENT", "Des références sont obligatoires"
    verifier_refs_ou_absent(refs, cle)
    if valeur in {"CONSERVE", "ECRASE"}:
        assert any(c.startswith("tests/caracterisation/") for c, _ in REF.findall(refs)), (
            "Le constat doit pointer vers un test dans tests/caracterisation/"
        )


def test_i06_registre_codes_reels_et_complets(inv):
    """[A-01] Les codes listés existent dans le REGISTRE, sans oubli pour les modules listés."""
    kv = cles_valeurs(inv["I-06"])
    assert "Fichier du REGISTRE" in kv, "Ligne « - Fichier du REGISTRE : REGISTRE | chemin:ligne » manquante"
    refs = kv["Fichier du REGISTRE"][1]
    trouvees = REF.findall(refs)
    assert len(trouvees) == 1, "Une seule référence attendue pour le fichier du REGISTRE"
    chemin, ligne = trouvees[0]
    verifier_ref(chemin, int(ligne))
    source = (ROOT / chemin).read_text(encoding="utf-8", errors="replace")

    codes = {}
    for l in inv["I-06"]:
        m = re.match(r"^- ([a-z_]+\.[a-z_]+) \| ([a-z_]+)$", l)
        if m:
            codes[m.group(1)] = m.group(2)
        elif l.startswith("- ") and not CLE_VALEUR.match(l):
            pytest.fail(f"Ligne mal formée en I-06 (attendu « - module.verbe | module ») : {l!r}")
    assert codes, "Aucun code listé (format « - projets.lire | projets »)"
    assert lire_total(inv["I-06"]) == len(codes)
    for code, module in codes.items():
        assert code.split(".")[0] == module, f"{code} : le module doit être le préfixe ({code.split('.')[0]})"
        assert re.search(rf"""["']{re.escape(code)}["']""", source), (
            f"{code} introuvable comme chaîne littérale dans {chemin}"
        )
    modules = set(codes.values())
    litteraux = set(re.findall(r"""["']([a-z_]+\.[a-z_]+)["']""", source))
    oublies = {c for c in litteraux if c.split(".")[0] in modules} - set(codes)
    assert not oublies, f"Codes présents dans le REGISTRE mais non listés : {sorted(oublies)}"


def test_i07_modules_et_portees(inv):
    """[D-04] Chaque module listé en I-06 a une portée proposée ; ged peut s'y ajouter."""
    mods = {}
    for l in inv["I-07"]:
        m = re.match(r"^- ([a-z_]+) \| (PROJET|GLOBALE|A_CONFIRMER)$", l)
        if m:
            mods[m.group(1)] = m.group(2)
        elif l.startswith("- "):
            pytest.fail(f"Ligne mal formée en I-07 (attendu « - module | PROJET|GLOBALE|A_CONFIRMER ») : {l!r}")
    codes_modules = {
        re.match(r"^- ([a-z_]+)\.", l).group(1)
        for l in inv["I-06"]
        if re.match(r"^- [a-z_]+\.[a-z_]+ \| [a-z_]+$", l)
    }
    assert codes_modules <= set(mods), f"Modules sans portée : {sorted(codes_modules - set(mods))}"
    assert set(mods) - codes_modules <= {"ged"}, (
        f"Modules inconnus du REGISTRE : {sorted(set(mods) - codes_modules - {'ged'})}"
    )


def test_i08_tests_existants_a_adapter(inv):
    """[E-08, A-12] Les tests existants concernés sont identifiés, références valides."""
    liste = entrees(inv["I-08"])
    assert liste, "Aucun test existant listé"
    for chemin, ligne, _ in liste:
        verifier_ref(chemin, ligne)
    noms = {Path(c).name for c, _, _ in liste}
    for requis in ("test_statuts_crud.py", "test_statuts_projet.py"):
        assert requis in noms, f"{requis} (cité par E-08) doit figurer dans la liste"
    assert lire_total(inv["I-08"]) == len(liste)


def test_i09_comptages_de_reference(inv):
    """[D-08, F-10, E-06, E-13, A-13] Compteurs de départ, recalculés par le test."""
    declares = {}
    for l in inv["I-09"]:
        m = re.match(r"^- (\w+) : (\d+)\s*$", l)
        if m:
            declares[m.group(1)] = int(m.group(2))
    manquants = [m for m in MOTS_I09 if m not in declares]
    assert not manquants, f"Mots manquants en I-09 : {manquants}"
    reels = {m: 0 for m in MOTS_I09}
    motifs = {m: re.compile(rf"\b{re.escape(m)}\b") for m in MOTS_I09}
    for p in fichiers_py(production_seulement=True):
        for ligne in lignes_de(p):
            for m, motif in motifs.items():
                if motif.search(ligne):
                    reels[m] += 1
    ecarts = {m: (declares[m], reels[m]) for m in MOTS_I09 if declares[m] != reels[m]}
    assert not ecarts, f"Écarts (déclaré, réel) : {ecarts}"


# ----------------------------------------------------------------------------
# Baseline et caractérisation
# ----------------------------------------------------------------------------
def test_baseline_suite_de_tests_enregistree():
    """La sortie de la suite existante, avant toute modification, est conservée."""
    texte = lire(BASELINE)
    assert re.search(r"\b\d+ passed\b", texte), (
        "baseline-tests.txt doit contenir la ligne de résumé pytest (« N passed ... »)"
    )


def test_caracterisation_presente_sans_raccourci():
    """Au moins un test de caractérisation, sans skip ni xfail."""
    fichiers = list(CARACT.rglob("test_*.py")) if CARACT.is_dir() else []
    assert fichiers, "Aucun test dans tests/caracterisation/"
    for f in fichiers:
        texte = f.read_text(encoding="utf-8")
        assert not re.search(r"\b(skip|skipif|xfail)\b", texte), (
            f"{f.relative_to(ROOT)} contient skip/xfail : interdit"
        )


def test_caracterisation_passe_sur_le_code_actuel():
    """Les tests de caractérisation décrivent le comportement ACTUEL : ils passent."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/caracterisation", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    assert r.returncode == 0, f"Caractérisation en échec :\n{r.stdout[-3000:]}"
