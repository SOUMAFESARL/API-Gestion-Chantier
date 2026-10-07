#!/usr/bin/env python3
"""Script de vérification de l'intégrité des fichiers de tests du LOT 9.

Garantit que Gemini ne modifie aucune assertion ni aucun test d'acceptation (G-05).
"""
import hashlib
import sys
from pathlib import Path

EMPREINTES_ATTENDUES = {
    "conftest.py": "37ef15b767e03175d7160924fda01fca8a25c80f3e3edacf523c25c6c5882034",
    "test_00_plomberie_lot9.py": "25f340dad9c754e1a351e957fe69c8550fbddb3bea5a21f96f00b6385a68ef66",
    "test_a05_a06_permissions_catalogue.py": "93129845c64a28c0e6ac0544a61bf5951b29c934e45338b446dee5e3db3d2772",
    "test_a07_a08_propagation_roles_systeme.py": "8af772db76c2d51071ff8ba5f0a3a8bd6bf8153d2dbe5124f821af496823356c",
    "test_a09_conflits_roles_systeme.py": "88359368268ca541d9376c9534e82a719caf0cebb347295b9a975e90916bd074",
    "test_a10_a11_modules_activation_desactivation.py": "1ba1343b43c40da2cb146b65cee8876af786e198a81ec022a8b7e4ffec73ba73",
    "test_a14_notifications_dg.py": "5531c4bf1d064c6d42a782436ec59210118978fc6539c6bee3d2a31b0b27b8b2",
    "test_h01_impersonation.py": "6599d0c402eccc16d0c4d01951300b9dbd0d0a29842677e59fd9bb8311718337",
    "test_h02_super_admin_journalisation.py": "7f1b46e624cc199bced37110139c3cdbc161d99d84d786fc63348b9c607865ff",
    "test_statiques_lot9.py": "eaab4bf0de522fadf287b8453798c18901974ffd3245779c67eca50fe498e085",
}


def calculer_sha256(chemin: Path) -> str:
    """Calcule le hash SHA-256 d'un fichier."""
    hasheur = hashlib.sha256()
    with open(chemin, "rb") as f:
        while chunk := f.read(8192):
            hasheur.update(chunk)
    return hasheur.hexdigest()


def verifier() -> bool:
    """Vérifie tous les fichiers verrouillés du lot 9."""
    dossier = Path(__file__).resolve().parent
    succes = True

    print(f"--- Vérification du verrouillage du LOT 9 ({len(EMPREINTES_ATTENDUES)} fichiers) ---")
    for nom_fichier, hash_attendu in EMPREINTES_ATTENDUES.items():
        chemin = dossier / nom_fichier
        if not chemin.exists():
            print(f"[MANQUANT] {nom_fichier}")
            succes = False
            continue

        hash_calcule = calculer_sha256(chemin)
        if hash_calcule != hash_attendu:
            print(f"[ALTÉRÉ]   {nom_fichier}")
            print(f"           Attendu : {hash_attendu}")
            print(f"           Obtenu  : {hash_calcule}")
            succes = False
        else:
            print(f"[INTACT]   {nom_fichier}")

    if succes:
        print("\n--> SUCCÈS : Tous les fichiers de tests du lot 9 sont intacts et conformes au verrou.")
    else:
        print("\n--> ÉCHEC : Au moins un fichier de test a été altéré ou manque !")

    return succes


if __name__ == "__main__":
    if not verifier():
        sys.exit(1)
