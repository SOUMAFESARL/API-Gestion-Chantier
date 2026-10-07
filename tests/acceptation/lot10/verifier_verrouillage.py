#!/usr/bin/env python3
"""Verrou SHA-256 du lot 10.

Usage :
    python tests/acceptation/lot10/verifier_verrouillage.py            vérifie (code 0 = conforme)
    python tests/acceptation/lot10/verifier_verrouillage.py --generer  affiche le dictionnaire à coller
                                                                       dans EMPREINTES_ATTENDUES

Procédure : après le branchement de fabriques_lot10.py et la relecture de Durel, lancer
--generer, coller le résultat ci-dessous, committer, poser le tag verrouille-lot10.
Le script ne se contrôle pas lui-même ; les fichiers __pycache__ et *.pyc sont ignorés.
"""
import hashlib
import sys
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
NOM_SCRIPT = Path(__file__).name

EMPREINTES_ATTENDUES = {
    "conftest.py": "0acad078f4899b809e733f5a276b9a1c3a5b7be6d8ba3a7069486120bbecc2a7",
    "fabriques_lot10.py": "4e5d421a9a8f6ffbbb68add33fe1af1599f4d69208873c4dd005aed5fd8545bc",
    "test_00_plomberie_lot10.py": "42372794e926af6e7a90ba45a9e98ba12b9cc17f9b6c52155195fb1e51087c5f",
    "test_f09_meteo_villes_invariance.py": "6581763c6aa73c39523e10892fe705438adc713417e5958f12b0d9db5dda3690",
    "test_f10_nettoyage_docstrings_constantes.py": "c2ad5f017c55c79d6fdb0cf47e45f265d1373b66694dc6568a1d77816ba279ac",
    "test_g02_compatibilite_contrat_front.py": "b23400cc34c784741ec9ae02dbed23d48eb67ed079846a75e83cdbb723f3cf9a",
    "test_g03_notes_changement_api.py": "70ddf8a7c94583482c81ceb5f6aae27d912aa0d542e9bdcb5b8e9f3d923b6454",
    "test_statiques_cloture_refonte.py": "b1f082516902d3153f30f04455cf2607159a0703f0d2012a369f0beddb1ee263",
}


def _empreinte(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


def _fichiers() -> list[Path]:
    return sorted(
        p for p in DOSSIER.iterdir()
        if p.is_file() and p.name != NOM_SCRIPT and p.suffix != ".pyc"
    )


def main(argv: list[str]) -> int:
    actuelles = {p.name: _empreinte(p) for p in _fichiers()}

    if "--generer" in argv:
        print("EMPREINTES_ATTENDUES = {")
        for nom, valeur in actuelles.items():
            print(f'    "{nom}": "{valeur}",')
        print("}")
        return 0

    if not EMPREINTES_ATTENDUES:
        print("ECHEC : aucune empreinte enregistrée (lancer --generer puis coller le résultat).")
        return 1

    modifies = [n for n, v in EMPREINTES_ATTENDUES.items() if n in actuelles and actuelles[n] != v]
    manquants = [n for n in EMPREINTES_ATTENDUES if n not in actuelles]
    en_trop = [n for n in actuelles if n not in EMPREINTES_ATTENDUES]

    conformes = len(EMPREINTES_ATTENDUES) - len(modifies) - len(manquants)
    print(f"Lot 10 : {conformes} / {len(EMPREINTES_ATTENDUES)} fichiers conformes")
    for titre, liste in (("MODIFIÉS", modifies), ("MANQUANTS", manquants), ("NON PRÉVUS", en_trop)):
        for nom in liste:
            print(f"  {titre} : {nom}")
    return 0 if not (modifies or manquants or en_trop) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
