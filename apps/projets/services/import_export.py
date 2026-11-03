"""Le découpage depuis et vers Excel (décision du 30/10/2026).

**Le fichier reprend les colonnes du tableau de démarrage** : une colonne par niveau, dans l'ordre,
puis, facultatives et dans n'importe quel ordre, Unité, Quantité, Montant, Début, Fin. La première
ligne donne le nom des colonnes ; chaque ligne suivante est une tâche, comme dans le tableau.

- **Les montants du fichier sont en FCFA** (comme dans un DQE) ; l'API et la base les tiennent en
  centimes : la conversion se fait ici, à l'entrée comme à la sortie.
- **Une colonne « Prix unitaire »**, facultative, sert seulement à calculer le montant d'une
  ligne qui n'en porte pas : Montant = Quantité x Prix unitaire. Elle n'est pas conservée
  (décisions v1.2, §13quinquies.1) ; un montant présent l'emporte, et un écart est signalé.

- **Importer ne crée rien** : le fichier devient un tableau, vérifié comme celui qu'on saisit
  (C-1 à C-7). L'écran le montre ; on l'applique ensuite par la même route que le tableau, à la
  création comme plus tard pour ajouter des branches.
- **Exporter** donne l'arbre au même format, une ligne par tâche : le fichier exporté se
  réimporte tel quel. Les montants n'y figurent que pour qui peut les voir.

Formats : `.xlsx` et `.csv` (séparateur `;` ou `,`, encodage UTF-8 ou Windows-1252).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError

from apps.catalogue.models.referentiel import cle_comparaison
from apps.core.enums import UniteMesure
from apps.projets.models import NiveauProjet
from apps.projets.selectors.arbre import charger_arbre
from apps.projets.services import listes_modeles as lm
from apps.projets.services.tableau_demarrage import proposer_tableau, verifier_tableau

__all__ = [
    "exporter_arbre",
    "generer_modele_excel_decoupage",
    "generer_modele_excel_projet",
    "importer_modele_fichier",
    "importer_tableau",
    "lire_fichier",
    "lire_tableau",
]

TAILLE_MAX = 5 * 1024 * 1024
LIGNES_MAX = 5000

#: Les colonnes de données, reconnues par leur nom (sans accents ni majuscules).
COLONNES_DONNEES = {
    "unite": {"unite", "unites", "u"},
    "quantite": {"quantite", "quantite prevue", "qte", "quantites"},
    "montant": {"montant", "montant (fcfa)", "montant fcfa", "montants", "valeur", "montant ht"},
    "prix_unitaire": {
        "prix unitaire",
        "prix unitaire (fcfa)",
        "prix unitaire fcfa",
        "prix unitaire ht",
        "pu",
        "p.u",
        "p.u.",
        "p. u.",
        "prix u",
    },
    "date_debut": {"debut", "date de debut", "date debut", "debut prevu"},
    "date_fin": {"fin", "date de fin", "date fin", "fin prevue"},
}
ENTETES_EXPORT = {
    "unite": "Unité",
    "quantite": "Quantité",
    "montant": "Montant (FCFA)",
    "date_debut": "Début",
    "date_fin": "Fin",
}
UNITES = {
    **{cle_comparaison(v): v for v in UniteMesure.values},
    **{cle_comparaison(label): v for v, label in UniteMesure.choices},
    "m2": "M2",
    "m3": "M3",
    "m": "ML",
    "ml": "ML",
    "kg": "KG",
    "u": "U",
    "unite": "U",
    "ens": "FORFAIT",
    "ff": "FORFAIT",
}


def _cellule(valeur) -> str:
    if valeur is None:
        return ""
    if isinstance(valeur, datetime):
        return valeur.date().isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return " ".join(str(valeur).split())


class _PointVirgule(csv.excel):
    delimiter = ";"


def lire_fichier(fichier) -> list[list[str]]:
    """Les lignes du fichier, en texte, lignes vides retirées."""
    nom = (getattr(fichier, "name", "") or "").lower()
    if getattr(fichier, "size", 0) and fichier.size > TAILLE_MAX:
        raise ValidationError({"fichier": "Le fichier dépasse 5 Mo."})
    contenu = fichier.read()
    if nom.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            classeur = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
        except Exception:
            raise ValidationError({"fichier": "Ce fichier Excel ne s'ouvre pas."}) from None
        feuille = classeur.worksheets[0]
        lignes = [[_cellule(v) for v in ligne] for ligne in feuille.iter_rows(values_only=True)]
    elif nom.endswith(".csv"):
        for encodage in ("utf-8-sig", "cp1252"):
            try:
                texte = contenu.decode(encodage)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialecte = csv.Sniffer().sniff(texte[:4096], delimiters=";,\t")
        except csv.Error:
            dialecte = _PointVirgule
        lignes = [
            [_cellule(v) for v in ligne] for ligne in csv.reader(io.StringIO(texte), dialecte)
        ]
    else:
        raise ValidationError({"fichier": "Formats acceptés : .xlsx et .csv."})
    lignes = [ligne for ligne in lignes if any(c for c in ligne)]
    if len(lignes) > LIGNES_MAX + 1:
        raise ValidationError({"fichier": f"Au plus {LIGNES_MAX} lignes de tâches."})
    return lignes


def _type_colonne(entete: str) -> str | None:
    cle = cle_comparaison(entete)
    return next((champ for champ, noms in COLONNES_DONNEES.items() if cle in noms), None)


def _nombre(valeur: str):
    if not valeur:
        return None
    propre = valeur.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(propre)
    except InvalidOperation:
        return valeur  # la vérification dira que la valeur est invalide


def _centimes(fcfa: Decimal) -> int:
    """1 234 567,50 FCFA → 123 456 750 centimes (arrondi au centime le plus proche)."""
    return int((fcfa * 100).quantize(Decimal("1"), ROUND_HALF_UP))


def _fcfa(centimes: int):
    """L'inverse, pour l'export : un entier quand le montant tombe juste."""
    valeur = Decimal(centimes) / 100
    return int(valeur) if valeur == valeur.to_integral_value() else float(valeur)


def _date(valeur: str):
    if not valeur:
        return None
    for format_date in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(valeur[:10], format_date).date().isoformat()
        except ValueError:
            continue
    return valeur


def _niveaux_pour(projet, libelles: list[str]) -> list[dict]:
    """Les niveaux des colonnes : ceux du projet s'il est découpé, sinon ceux du modèle du type
    de projet quand le nom correspond (avec sa liste), sinon un niveau libre."""
    existants = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
    if existants:
        attendus = [cle_comparaison(n.libelle) for n in existants]
        if [cle_comparaison(lib) for lib in libelles] != attendus:
            raise ValidationError(
                {
                    "fichier": "Les colonnes doivent reprendre les niveaux du projet, dans "
                    "l'ordre : " + ", ".join(n.libelle for n in existants) + "."
                }
            )
        return [
            {
                "libelle": n.libelle,
                "liste": lm.reference_liste(n.liste_plateforme or n.liste_entreprise),
                "alerter": n.alerter,
            }
            for n in existants
        ]
    modele = {cle_comparaison(n["libelle"]): n for n in proposer_tableau(projet)["niveaux"]}
    niveaux = []
    for libelle in libelles:
        connu = modele.get(cle_comparaison(libelle))
        niveaux.append(
            {
                "libelle": libelle,
                "liste": connu.get("liste") if connu else None,
                "alerter": bool(connu and connu.get("alerter")),
            }
        )
    return niveaux


def lire_tableau(projet, fichier) -> dict:
    """Le fichier, lu au format du tableau : `{niveaux, lignes, avertissements}`.

    Chaque ligne est un objet `{"cellules": [...], "unite", "quantite", "montant", "date_debut",
    "date_fin"}` (les champs absents du fichier sont omis), le montant en centimes. Les
    avertissements propres au fichier (montant différent de Quantité x Prix unitaire) ont la
    règle `PU`. Rien n'est écrit.
    """
    lignes = lire_fichier(fichier)
    if len(lignes) < 2:
        raise ValidationError(
            {"fichier": "Le fichier n'a pas de ligne de tâche sous les en-têtes."}
        )
    entetes = lignes[0]
    colonnes_niveaux, colonnes_donnees = [], {}
    for index, entete in enumerate(entetes):
        champ = _type_colonne(entete) if entete else None
        if champ:
            colonnes_donnees[champ] = index
        elif entete:
            colonnes_niveaux.append(index)
    if not colonnes_niveaux:
        raise ValidationError({"fichier": "Aucune colonne de niveau (Phase, Lot, Activité…)."})
    niveaux = _niveaux_pour(projet, [entetes[i] for i in colonnes_niveaux])
    tableau, avertissements = [], []
    for numero, ligne in enumerate(lignes[1:], start=1):

        def valeur(i, ligne=ligne):
            return ligne[i] if i is not None and i < len(ligne) else ""

        objet = {"cellules": [valeur(i) for i in colonnes_niveaux]}
        unite = valeur(colonnes_donnees.get("unite"))
        if unite:
            objet["unite"] = UNITES.get(cle_comparaison(unite), unite)
        quantite = _nombre(valeur(colonnes_donnees.get("quantite")))
        if quantite is not None:
            objet["quantite"] = str(quantite) if isinstance(quantite, Decimal) else quantite
        montant = _nombre(valeur(colonnes_donnees.get("montant")))
        prix = _nombre(valeur(colonnes_donnees.get("prix_unitaire")))
        calcule = (
            quantite * prix if isinstance(quantite, Decimal) and isinstance(prix, Decimal) else None
        )
        if isinstance(montant, Decimal):
            objet["montant"] = _centimes(montant)
            if calcule is not None and abs(calcule - montant) >= 1:
                avertissements.append(
                    {
                        "regle": "PU",
                        "ligne": numero,
                        "message": f"Ligne {numero} : le montant ({montant} FCFA) diffère de "
                        f"quantité x prix unitaire ({calcule} FCFA) ; le montant est retenu.",
                    }
                )
        elif montant is not None:
            objet["montant"] = montant  # la vérification dira que la valeur est invalide
        elif calcule is not None:
            objet["montant"] = _centimes(calcule)
        for champ in ("date_debut", "date_fin"):
            jour = _date(valeur(colonnes_donnees.get(champ)))
            if jour:
                objet[champ] = jour
        tableau.append(objet)
    return {"niveaux": niveaux, "lignes": tableau, "avertissements": avertissements}


def importer_tableau(projet, fichier) -> dict:
    """Le fichier devient un tableau de démarrage, vérifié ; rien n'est écrit."""
    lu = lire_tableau(projet, fichier)
    verdict = verifier_tableau(lu["niveaux"], lu["lignes"])
    verdict.pop("_lignes", None)
    verdict.pop("lignes_retenues", None)
    verdict["avertissements"] = [*verdict["avertissements"], *lu["avertissements"]]
    return {"niveaux": lu["niveaux"], "lignes": lu["lignes"], "verification": verdict}


def _lignes_export(projet, montants_visibles: bool) -> tuple[list[str], list[list]]:
    arbre = charger_arbre(projet, actifs_seulement=True)
    niveaux = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
    colonnes = [
        "unite",
        "quantite",
        *(["montant"] if montants_visibles else []),
        "date_debut",
        "date_fin",
    ]
    entetes = [n.libelle for n in niveaux] + [ENTETES_EXPORT[c] for c in colonnes]
    libelles_unites = dict(UniteMesure.choices)
    lignes = []
    numeros = arbre.numerotation()

    def rang(feuille):
        return tuple(int(n) for n in (numeros.get(feuille.pk) or "0").split(".") if n.isdigit())

    for feuille in sorted(arbre.feuilles(), key=rang):
        cellules = arbre.chemin_libelles(feuille)
        cellules += [""] * (len(niveaux) - len(cellules))
        donnees = {
            "unite": libelles_unites.get(feuille.unite, feuille.unite or ""),
            "quantite": float(feuille.quantite_prevue)
            if feuille.quantite_prevue is not None
            else "",
            "montant": _fcfa(feuille.montant) if feuille.montant is not None else "",
            "date_debut": feuille.date_debut_prevue or "",
            "date_fin": feuille.date_fin_prevue or "",
        }
        lignes.append(cellules + [donnees[c] for c in colonnes])
    return entetes, lignes


def _styliser_feuille_decoupage(feuille, nb_niveaux: int) -> None:
    """Applique la mise en forme (en-têtes figés, couleurs, largeurs de colonnes) sur la feuille."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    remplissage_niveau = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    remplissage_donnee = PatternFill(start_color="2C5282", end_color="2C5282", fill_type="solid")
    police_entete = Font(bold=True, color="FFFFFF", size=11)

    for index, cellule in enumerate(feuille[1], start=1):
        cellule.fill = remplissage_niveau if index <= nb_niveaux else remplissage_donnee
        cellule.font = police_entete
        cellule.alignment = Alignment(vertical="center")
    feuille.row_dimensions[1].height = 24
    feuille.freeze_panes = "A2"

    for index_col, colonne in enumerate(feuille.columns, start=1):
        lettre = get_column_letter(index_col)
        longueur_max = max(
            (len(str(c.value or "")) for c in colonne[:200]),
            default=14,
        )
        feuille.column_dimensions[lettre].width = max(16, min(42, longueur_max + 4))


def exporter_arbre(projet, format_fichier: str, *, montants_visibles: bool) -> tuple[bytes, str]:
    """L'arbre au format du tableau : (contenu, type MIME). Le fichier se réimporte tel quel."""
    entetes, lignes = _lignes_export(projet, montants_visibles)
    if format_fichier == "csv":
        tampon = io.StringIO()
        ecrivain = csv.writer(tampon, delimiter=";")
        ecrivain.writerow(entetes)
        for ligne in lignes:
            ecrivain.writerow([c.isoformat() if isinstance(c, date) else c for c in ligne])
        return tampon.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    from openpyxl import Workbook

    nb_niveaux = NiveauProjet.objects.filter(projet=projet).count()
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Découpage"
    feuille.append(entetes)
    for ligne in lignes:
        feuille.append(ligne)
    _styliser_feuille_decoupage(feuille, nb_niveaux)
    tampon = io.BytesIO()
    classeur.save(tampon)
    return (
        tampon.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _valeurs_liste_pour_niveau(ref_liste: dict | None) -> list[str]:
    """Les valeurs d'une liste rattachée à un niveau, pour pré-remplir et valider l'Excel."""
    if not ref_liste or not ref_liste.get("id"):
        return []
    try:
        objet = lm.resoudre_liste(ref_liste)
        donnees = lm.liste_en_dict(objet, avec_valeurs=True)
        return [v["libelle"] for v in donnees.get("valeurs", []) if v.get("libelle")]
    except Exception:
        return []


def generer_modele_excel_decoupage(
    niveaux: list[dict] | None = None,
    lignes_exemple: list | None = None,
) -> bytes:
    """Construit un classeur Excel (.xlsx) type à remplir pour importer un découpage ou un modèle.

    - Feuille 1 (« Découpage ») : colonnes des niveaux suivies de Unité, Quantité, Prix unitaire (FCFA),
      Montant (FCFA), Début, Fin, avec lignes d'exemple et listes déroulantes Excel non bloquantes.
    - Feuille 2 (« Valeurs et mode d emploi ») : consignes et valeurs de référence par niveau.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    niveaux_effectifs = list(niveaux or [])
    if not niveaux_effectifs:
        niveaux_effectifs = [
            {"libelle": "Phase", "liste": None, "alerter": False},
            {"libelle": "Lot", "liste": None, "alerter": True},
            {"libelle": "Tâche", "liste": None, "alerter": False},
        ]
    nb_niveaux = len(niveaux_effectifs)
    colonnes_donnees = [
        "Unité",
        "Quantité",
        "Prix unitaire (FCFA)",
        "Montant (FCFA)",
        "Début",
        "Fin",
    ]
    entetes = [n.get("libelle") or f"Niveau {i + 1}" for i, n in enumerate(niveaux_effectifs)] + colonnes_donnees

    valeurs_par_niveau: list[list[str]] = [
        _valeurs_liste_pour_niveau(n.get("liste")) for n in niveaux_effectifs
    ]

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Découpage"
    feuille.append(entetes)

    lignes_a_ecrire: list[list] = []
    if lignes_exemple:
        for idx, brute in enumerate(lignes_exemple[:50]):
            cellules = brute.get("cellules", []) if isinstance(brute, dict) else list(brute)
            cellules = [str(c or "") for c in cellules[:nb_niveaux]]
            while len(cellules) < nb_niveaux:
                cellules.append("")
            if isinstance(brute, dict) and any(
                brute.get(k) is not None for k in ("unite", "quantite", "montant", "date_debut", "date_fin")
            ):
                montant_fcfa = (
                    _fcfa(brute["montant"])
                    if isinstance(brute.get("montant"), int)
                    else (brute.get("montant") or "")
                )
                lignes_a_ecrire.append(
                    cellules
                    + [
                        brute.get("unite") or "",
                        brute.get("quantite") if brute.get("quantite") is not None else "",
                        "",
                        montant_fcfa,
                        brute.get("date_debut") or "",
                        brute.get("date_fin") or "",
                    ]
                )
            elif idx == 0:
                lignes_a_ecrire.append(cellules + ["FORFAIT", 1, 1500000, 1500000, "2026-01-15", "2026-01-31"])
            elif idx == 1:
                lignes_a_ecrire.append(cellules + ["M3", 120, 25000, 3000000, "2026-02-01", "2026-02-20"])
            else:
                lignes_a_ecrire.append(cellules + ["", "", "", "", "", ""])
    else:
        exemples_defaut = [
            (["Préparation", "Installation de chantier", "Implantation et clôture"], ["FORFAIT", 1, 1500000, 1500000, "2026-01-15", "2026-01-31"]),
            (["Exécution", "Gros œuvre", "Fouilles en rigoles"], ["M3", 120, 15000, 1800000, "2026-02-01", "2026-02-15"]),
            (["Exécution", "Gros œuvre", "Béton armé pour fondations"], ["M3", 45, 110000, 4950000, "2026-02-16", "2026-03-10"]),
        ]
        for idx_ex, (chemin_defaut, donnees_ex) in enumerate(exemples_defaut):
            cellules = []
            for rang in range(nb_niveaux):
                valeurs_liste = valeurs_par_niveau[rang]
                if valeurs_liste:
                    cellules.append(valeurs_liste[min(idx_ex, len(valeurs_liste) - 1)])
                elif rang < len(chemin_defaut):
                    cellules.append(chemin_defaut[rang])
                else:
                    cellules.append(f"Élément {rang + 1}.{idx_ex + 1}")
            lignes_a_ecrire.append(cellules + donnees_ex)

    police_exemple = Font(italic=True, color="334E68")
    for ligne in lignes_a_ecrire:
        feuille.append(ligne)
    for ligne_cellules in feuille.iter_rows(min_row=2, max_row=len(lignes_a_ecrire) + 1):
        for cellule in ligne_cellules:
            cellule.font = police_exemple

    _styliser_feuille_decoupage(feuille, nb_niveaux)

    # Feuille 2 : Mode d'emploi + valeurs de référence pour les listes déroulantes
    notice = classeur.create_sheet(title="Valeurs et mode d emploi")
    notice["A1"] = "Mode d'emploi — Import Excel du découpage de projet ou de modèle"
    notice["A1"].font = Font(bold=True, size=12, color="1B365D")
    instructions = [
        "1. Les premières colonnes de la feuille « Découpage » représentent les niveaux de découpage de votre projet (ex. : Phase, Lot, Activité).",
        "2. Vous pouvez renommer ces colonnes de niveaux, en ajouter ou en retirer avant la colonne « Unité ».",
        "3. Chaque ligne représente une tâche (feuille de l'arbre). Les cellules parentes identiques d'une ligne à l'autre sont automatiquement regroupées.",
        "4. Colonnes de données facultatives : Unité (M2, ML, M3, KG, U, FORFAIT), Quantité, Prix unitaire (FCFA), Montant (FCFA), Début, Fin (AAAA-MM-JJ ou JJ/MM/AAAA).",
        "5. Si « Montant (FCFA) » est laissé vide mais que « Quantité » et « Prix unitaire (FCFA) » sont renseignés, le montant est calculé automatiquement.",
    ]
    for idx_inst, texte_inst in enumerate(instructions, start=3):
        notice[f"A{idx_inst}"] = texte_inst
    notice.column_dimensions["A"].width = 45

    ligne_depart_ref = 10
    notice.cell(row=ligne_depart_ref, column=1, value="Unités autorisées").font = Font(bold=True, color="1B365D")
    unites_codes = list(UniteMesure.values)
    for i, code_u in enumerate(unites_codes, start=ligne_depart_ref + 1):
        notice.cell(row=i, column=1, value=code_u)

    col_unite_decoupage = get_column_letter(nb_niveaux + 1)
    validation_unite = DataValidation(
        type="list",
        formula1=f"='Valeurs et mode d emploi'!$A${ligne_depart_ref + 1}:$A${ligne_depart_ref + len(unites_codes)}",
        allow_blank=True,
    )
    validation_unite.showErrorMessage = False
    feuille.add_data_validation(validation_unite)
    validation_unite.add(f"{col_unite_decoupage}2:{col_unite_decoupage}500")

    col_ref = 2
    for idx_niv, valeurs_niv in enumerate(valeurs_par_niveau):
        if not valeurs_niv:
            continue
        libelle_niv = niveaux_effectifs[idx_niv].get("libelle") or f"Niveau {idx_niv + 1}"
        lettre_ref = get_column_letter(col_ref)
        lettre_decoupage = get_column_letter(idx_niv + 1)
        entete_ref = notice.cell(row=ligne_depart_ref, column=col_ref, value=f"Liste : {libelle_niv}")
        entete_ref.font = Font(bold=True, color="1B365D")
        entete_ref.alignment = Alignment(vertical="center")
        notice.column_dimensions[lettre_ref].width = 32
        valeurs_bornees = valeurs_niv[:300]
        for offset, val in enumerate(valeurs_bornees, start=1):
            notice.cell(row=ligne_depart_ref + offset, column=col_ref, value=val)
        fin_ref = ligne_depart_ref + len(valeurs_bornees)
        validation_niv = DataValidation(
            type="list",
            formula1=f"='Valeurs et mode d emploi'!${lettre_ref}${ligne_depart_ref + 1}:${lettre_ref}${fin_ref}",
            allow_blank=True,
        )
        validation_niv.showErrorMessage = False
        feuille.add_data_validation(validation_niv)
        validation_niv.add(f"{lettre_decoupage}2:{lettre_decoupage}500")
        col_ref += 1

    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()


def generer_modele_excel_projet(projet, reference: dict | None = None) -> bytes:
    """Construit l'exemple type Excel (.xlsx) adapté aux niveaux du projet ou du modèle choisi."""
    existants = list(NiveauProjet.objects.filter(projet=projet).order_by("ordre"))
    if existants:
        niveaux = [
            {
                "libelle": n.libelle,
                "liste": lm.reference_liste(n.liste_plateforme or n.liste_entreprise),
                "alerter": n.alerter,
            }
            for n in existants
        ]
        return generer_modele_excel_decoupage(niveaux=niveaux)
    proposition = proposer_tableau(projet, reference)
    return generer_modele_excel_decoupage(
        niveaux=proposition.get("niveaux") or [],
        lignes_exemple=proposition.get("lignes") or None,
    )


def importer_modele_fichier(fichier, *, pour_plateforme: bool = False) -> dict:
    """Extrait `{niveaux, lignes}` d'un fichier Excel (.xlsx) ou CSV pour créer/éditer un modèle."""
    lignes = lire_fichier(fichier)
    if not lignes:
        raise ValidationError({"fichier": "Le fichier est vide."})
    entetes = lignes[0]
    colonnes_niveaux = []
    for index, entete in enumerate(entetes):
        if not entete:
            continue
        if _type_colonne(entete) is None:
            colonnes_niveaux.append(index)
    if not colonnes_niveaux:
        raise ValidationError({"fichier": "Aucune colonne de niveau (Phase, Lot, Activité…)."})
    if len(colonnes_niveaux) > 5:
        raise ValidationError({"fichier": "Un modèle compte au plus 5 niveaux."})

    if pour_plateforme:
        from apps.catalogue.models import ListeValeursPlateforme

        listes_connues = {
            cle_comparaison(l.libelle): {"origine": "PLATEFORME", "id": str(l.pk), "libelle": l.libelle}
            for l in ListeValeursPlateforme.objects.filter(est_actif=True)
        }
    else:
        listes_connues = {
            cle_comparaison(l["libelle"]): {
                "origine": l["origine"],
                "id": str(l["id"]),
                "libelle": l["libelle"],
            }
            for l in lm.listes_disponibles(avec_valeurs=False)
        }

    niveaux = []
    for rang, index_col in enumerate(colonnes_niveaux):
        libelle = entetes[index_col].strip()
        niveaux.append(
            {
                "libelle": libelle,
                "liste": listes_connues.get(cle_comparaison(libelle)),
                "alerter": rang == (1 if len(colonnes_niveaux) >= 2 else 0),
            }
        )

    lignes_modele = []
    vus = set()
    for ligne in lignes[1:]:
        cellules = [
            (ligne[i].strip() if i < len(ligne) and ligne[i] else "")
            for i in colonnes_niveaux
        ]
        while cellules and not cellules[-1]:
            cellules.pop()
        if not cellules or any(not c for c in cellules):
            continue
        cle_chemin = tuple(cle_comparaison(c) for c in cellules)
        if cle_chemin in vus:
            continue
        vus.add(cle_chemin)
        lignes_modele.append(cellules)

    return {"niveaux": niveaux, "lignes": lignes_modele}
