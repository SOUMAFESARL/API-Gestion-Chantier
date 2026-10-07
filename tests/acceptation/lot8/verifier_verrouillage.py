"""Vérifie que les tests d'acceptation du lot 8 n'ont pas été modifiés.

Usage (depuis la racine du dépôt) :
    python tests/acceptation/lot8/verifier_verrouillage.py

Compare l'empreinte SHA-256 de chaque test_*.py (fins de ligne normalisées, donc
insensible à CRLF/LF) à l'empreinte attendue, et refuse skip, xfail et importorskip.
Code de sortie 0 = verrou intact, 1 = violation.
"""

import hashlib
import re
import sys
from pathlib import Path

ATTENDU = {
    "test_00_plomberie_lot8.py": "8dd2e05e659f1a49a360c3949732f5a6ea8d3ba2c5758d5afc04cdb76d43a607",
    "test_c01_c05_invitations_lectures.py": "2328afd758e748e9d4fc6195cdb4b7f4e4e6777f91e16ce389d97f6b8a8ba989",
    "test_c02_depart_collaborateur.py": "809bed6c5440a788f121e5f4b75983186d87562167a07dc49af91ce92966bfad",
    "test_c03_registre_global.py": "36908bcad5873cbaf02526fcf53c9f15ca39e67e5d5d9cb0d2de2066f55f8ea2",
    "test_c04_quotas_expiration.py": "ef88a109477152aecb2642295e6795efed3bf8a63ea274df9617a38c4576b41d",
    "test_f03_f08_lectures_vues.py": "2943301201542fce2bd3cda385f4d513f138e0804f37ffe4104939450ff19bdb",
    "test_statiques_lot8.py": "b1407026a337310bbd90ce9cd209b82639c0ac26b619ed91b46e4289349c0401",
}
INTERDITS = re.compile(r"\b(skip|skipif|xfail|importorskip)\b")


def empreinte(chemin):
    donnees = chemin.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(donnees).hexdigest()


def main():
    dossier = Path(__file__).resolve().parent
    problemes = []
    presents = {f.name for f in dossier.glob("test_*.py")}
    for nom, attendu in ATTENDU.items():
        chemin = dossier / nom
        if not chemin.exists():
            problemes.append(f"MANQUANT : {nom}")
            continue
        if empreinte(chemin) != attendu:
            problemes.append(f"MODIFIÉ : {nom}")
        if INTERDITS.search(chemin.read_text(encoding="utf-8")):
            problemes.append(f"skip/xfail interdit dans {nom}")
    for nom in sorted(presents - set(ATTENDU)):
        problemes.append(f"FICHIER DE TEST NON PRÉVU : {nom}")
    if problemes:
        print("VERROU VIOLÉ")
        for p in problemes:
            print(" -", p)
        return 1
    print(f"Verrou intact ({len(ATTENDU)} fichiers de tests).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
