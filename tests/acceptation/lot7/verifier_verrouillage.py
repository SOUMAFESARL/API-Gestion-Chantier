"""Vérifie que les tests d'acceptation du lot 7 n'ont pas été modifiés.

Usage (depuis la racine du dépôt) :
    python tests/acceptation/lot7/verifier_verrouillage.py

Compare l'empreinte SHA-256 de chaque test_*.py (fins de ligne normalisées, donc
insensible à CRLF/LF) à l'empreinte attendue, et refuse skip, xfail et importorskip.
Code de sortie 0 = verrou intact, 1 = violation.
"""

import hashlib
import re
import sys
from pathlib import Path

ATTENDU = {
    "test_00_plomberie_lot7.py": "1786656da1abcddbc5f12af76c0bc60bbd86c4eeece0080f3502b935b094cf81",
    "test_e11_masquage_montants_lecture.py": "0349e313373c4a10816fd9603bbac1bed0a0a2eff3fe9ad6f3f98b61316ff5d2",
    "test_e11_refus_ecriture_montants_sans_droit.py": "2651a6c293a297c40cf38dd3828f52de64fea57eb51925e3e000e924593c9b48",
    "test_e12_retrait_champs_sans_source.py": "61f13ac76ec7be423f14c4bbf51435284f58c1d638f5d3ef27baca05f89ea725"
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
