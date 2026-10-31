"""Importer le registre de main-d'œuvre depuis Excel (décision du 31/10/2026).

Même circuit que l'import du découpage : **lire ne crée rien**. Le fichier devient des lignes
vérifiées une à une ; l'écran les montre, l'utilisateur corrige sur place (l'entreprise se choisit
parmi les tiers partenaires), puis on applique.

- **Colonnes** : Nom, Prénom (obligatoires), Téléphone, Métier, Entreprise — reconnues par leur nom,
  sans accents ni majuscules, dans n'importe quel ordre.
- **Entreprise** : vide, c'est notre entreprise ; sinon un tiers sous-traitant, tâcheron ou
  prestataire, retrouvé par sa raison sociale. Un nom inconnu met la ligne en erreur : on le
  choisit alors dans la liste à l'écran.
- **Doublons** (règle du registre : même nom, même prénom, même entreprise), contre le registre et
  à l'intérieur du fichier : la ligne est sautée et signalée.
- **Erreurs** : seules les lignes valides s'enregistrent ; les autres reviennent avec leur raison.
- **Téléphone** : un numéro sans indicatif reçoit celui du pays de l'entreprise ; le zéro de tête
  qu'Excel mange et le « + » qu'il retire se rattrapent quand la longueur ne laisse pas de doute.
"""

from __future__ import annotations

import io

from django.db import connection, transaction
from rest_framework.exceptions import APIException, ValidationError

from apps.catalogue.models.referentiel import cle_comparaison
from apps.projets.models import PersonneMainOeuvre
from apps.projets.services import main_oeuvre
from apps.projets.services.import_export import lire_fichier
from apps.tenants.services.telephones import est_e164, normaliser_telephone

__all__ = [
    "appliquer_import",
    "lire_import",
    "modele_import",
    "partenaires_eligibles",
    "telephone_importe",
    "verifier_lignes",
]

VALIDE, DOUBLON, ERREUR = "VALIDE", "DOUBLON", "ERREUR"

#: Les colonnes reconnues, par leur nom comparé sans accents ni majuscules.
COLONNES = {
    "nom": {"nom", "nom de famille", "noms"},
    "prenom": {"prenom", "prenoms"},
    "telephone": {"telephone", "tel", "tel.", "contact", "numero", "numero de telephone"},
    "metier": {"metier", "fonction", "qualification", "specialite"},
    "entreprise": {"entreprise", "societe", "employeur", "sous-traitant", "partenaire"},
}
ENTETES_MODELE = ["Nom", "Prénom", "Téléphone", "Métier", "Entreprise"]

#: Indicatif, longueur nationale usuelle, et si le numéro national commence par un zéro.
#: Alignée sur `features/referentiels/telephone.ts` (les neuf pays de l'inscription).
PAYS = {
    "CI": ("+225", 10, True),
    "SN": ("+221", 9, False),
    "CM": ("+237", 9, False),
    "BF": ("+226", 8, False),
    "ML": ("+223", 8, False),
    "TG": ("+228", 8, False),
    "BJ": ("+229", 10, True),
    "GN": ("+224", 9, False),
    "GA": ("+241", 8, False),
}


def _texte(valeur) -> str:
    return " ".join(str(valeur or "").split())


def _pays_entreprise() -> str:
    pays = (getattr(getattr(connection, "tenant", None), "pays", "") or "").upper()
    return pays if pays in PAYS else "CI"


def telephone_importe(valeur, pays: str) -> tuple[str, str | None]:
    """(numéro E.164, erreur). Vide reste vide ; l'indicatif du pays complète un numéro national."""
    brut = normaliser_telephone(_texte(valeur))
    if not brut:
        return "", None
    indicatif, longueur, zero_initial = PAYS.get(pays, PAYS["CI"])
    if brut.startswith("+"):
        return (brut, None) if est_e164(brut) else (brut, "Numéro international invalide.")
    if not brut.isdigit():
        return brut, "Le numéro ne doit contenir que des chiffres."
    chiffres_indicatif = indicatif[1:]
    # « +225 07… » saisi dans une cellule numérique : Excel a retiré le « + ».
    if brut.startswith(chiffres_indicatif) and len(brut) == len(chiffres_indicatif) + longueur:
        return f"+{brut}", None
    # « 07 00… » devenu 700… : Excel a mangé le zéro de tête.
    if zero_initial and len(brut) == longueur - 1 and not brut.startswith("0"):
        brut = f"0{brut}"
    numero = f"{indicatif}{brut}"
    if len(brut) != longueur or not est_e164(numero):
        return brut, f"Numéro attendu sur {longueur} chiffres, ou avec l'indicatif (+…)."
    return numero, None


def partenaires_eligibles():
    """Les tiers à qui l'on peut rattacher une personne : sous-traitant, tâcheron, prestataire."""
    from apps.tiers.models import Tiers

    return (
        Tiers.objects.filter(
            est_actif=True,
            roles__role__in=[str(r) for r in main_oeuvre.ROLES_PARTENAIRES],
        )
        .distinct()
        .order_by("raison_sociale")
    )


def _colonnes(entetes: list[str]) -> dict[str, int]:
    positions = {}
    for index, entete in enumerate(entetes):
        cle = cle_comparaison(entete)
        for champ, noms in COLONNES.items():
            if cle in noms and champ not in positions:
                positions[champ] = index
    manquantes = [nom for nom in ("nom", "prenom") if nom not in positions]
    if manquantes:
        raise ValidationError(
            {
                "fichier": "Colonnes obligatoires absentes : "
                + ", ".join("Nom" if m == "nom" else "Prénom" for m in manquantes)
                + ". Partez du modèle à télécharger."
            }
        )
    return positions


def lire_import(fichier) -> dict:
    """Le fichier devient des lignes vérifiées. Rien n'est écrit."""
    lignes_fichier = lire_fichier(fichier)
    if not lignes_fichier:
        raise ValidationError({"fichier": "Le fichier est vide."})
    positions = _colonnes(lignes_fichier[0])
    if len(lignes_fichier) < 2:
        raise ValidationError({"fichier": "Le fichier ne contient aucune personne."})
    partenaires = list(partenaires_eligibles())
    par_nom = {cle_comparaison(t.raison_sociale): t for t in partenaires}

    def cellule(ligne, champ):
        index = positions.get(champ)
        return ligne[index] if index is not None and index < len(ligne) else ""

    lignes = []
    for numero, ligne in enumerate(lignes_fichier[1:], start=2):
        entreprise = _texte(cellule(ligne, "entreprise"))
        tiers = par_nom.get(cle_comparaison(entreprise)) if entreprise else None
        lignes.append(
            {
                "numero": numero,
                "nom": _texte(cellule(ligne, "nom")),
                "prenom": _texte(cellule(ligne, "prenom")),
                "telephone": _texte(cellule(ligne, "telephone")),
                "metier": _texte(cellule(ligne, "metier")),
                "entreprise_partenaire_id": str(tiers.pk) if tiers else None,
                # Le nom lu dans le fichier : il dit à l'écran ce qui n'a pas été reconnu.
                "entreprise_saisie": "" if tiers else entreprise,
            }
        )
    return {
        "lignes": verifier_lignes(lignes, partenaires=partenaires),
        "partenaires": [{"id": str(t.pk), "nom": t.raison_sociale} for t in partenaires],
    }


def verifier_lignes(lignes: list[dict], *, partenaires=None) -> list[dict]:
    """Chaque ligne reçoit un statut (VALIDE, DOUBLON, ERREUR), ses erreurs par champ et son
    téléphone normalisé. Les lignes sont rendues dans l'ordre reçu."""
    pays = _pays_entreprise()
    partenaires = list(partenaires if partenaires is not None else partenaires_eligibles())
    ids_partenaires = {str(t.pk) for t in partenaires}
    vus: dict[tuple, int] = {}
    resultat = []
    for ligne in lignes:
        nom, prenom = _texte(ligne.get("nom")), _texte(ligne.get("prenom"))
        metier = _texte(ligne.get("metier"))
        partenaire_id = ligne.get("entreprise_partenaire_id") or None
        partenaire_id = str(partenaire_id) if partenaire_id else None
        entreprise_saisie = _texte(ligne.get("entreprise_saisie")) if not partenaire_id else ""
        erreurs: dict[str, str] = {}
        if not nom:
            erreurs["nom"] = "Le nom est obligatoire."
        elif len(nom) > 150:
            erreurs["nom"] = "150 caractères au plus."
        if not prenom:
            erreurs["prenom"] = "Le prénom est obligatoire."
        elif len(prenom) > 150:
            erreurs["prenom"] = "150 caractères au plus."
        if len(metier) > 100:
            erreurs["metier"] = "100 caractères au plus."
        telephone, erreur_telephone = telephone_importe(ligne.get("telephone"), pays)
        if erreur_telephone:
            erreurs["telephone"] = erreur_telephone
        if partenaire_id and partenaire_id not in ids_partenaires:
            erreurs["entreprise"] = (
                "Cette entreprise n'est ni sous-traitant, ni tâcheron, ni prestataire."
            )
        elif entreprise_saisie:
            erreurs["entreprise"] = (
                f"« {entreprise_saisie} » n'est pas parmi les tiers partenaires : choisissez "
                "l'entreprise dans la liste."
            )
        message_doublon = ""
        if not erreurs:
            cle = (nom.lower(), prenom.lower(), partenaire_id)
            if cle in vus:
                message_doublon = f"Déjà présent dans le fichier (ligne {vus[cle]})."
            elif PersonneMainOeuvre.objects.filter(
                nom__iexact=nom, prenom__iexact=prenom, entreprise_partenaire_id=partenaire_id
            ).exists():
                message_doublon = "Figure déjà dans le registre pour cette entreprise."
            else:
                vus[cle] = ligne.get("numero")
        resultat.append(
            {
                "numero": ligne.get("numero"),
                "nom": nom,
                "prenom": prenom,
                "telephone": telephone,
                "metier": metier,
                "entreprise_partenaire_id": partenaire_id,
                "entreprise_saisie": entreprise_saisie,
                "statut": ERREUR if erreurs else (DOUBLON if message_doublon else VALIDE),
                "erreurs": erreurs,
                "message": message_doublon,
            }
        )
    return resultat


def _message(exc: APIException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return " ".join(
            str(m)
            for valeurs in detail.values()
            for m in (valeurs if isinstance(valeurs, list) else [valeurs])
        )
    if isinstance(detail, list):
        return " ".join(str(m) for m in detail)
    return str(detail)


def appliquer_import(lignes: list[dict], *, createur=None) -> dict:
    """Crée les lignes valides, une par une ; un refus au dernier moment (une saisie concurrente)
    n'empêche pas les autres. Les doublons sont sautés, les erreurs rendues."""
    from apps.tiers.models import Tiers

    verifiees = verifier_lignes(lignes)
    tiers = {
        str(t.pk): t
        for t in Tiers.objects.filter(
            pk__in={
                ligne["entreprise_partenaire_id"]
                for ligne in verifiees
                if ligne["entreprise_partenaire_id"]
            }
        )
    }
    creees = 0
    for ligne in verifiees:
        if ligne["statut"] != VALIDE:
            continue
        try:
            with transaction.atomic():
                main_oeuvre.creer_personne(
                    nom=ligne["nom"],
                    prenom=ligne["prenom"],
                    telephone=ligne["telephone"],
                    metier=ligne["metier"],
                    entreprise_partenaire=tiers.get(ligne["entreprise_partenaire_id"] or ""),
                    createur=createur,
                )
        except APIException as exc:
            ligne["statut"], ligne["message"] = ERREUR, _message(exc)
            continue
        ligne["statut"] = "CREEE"
        creees += 1
    return {
        "creees": creees,
        "doublons": sum(1 for ligne in verifiees if ligne["statut"] == DOUBLON),
        "erreurs": sum(1 for ligne in verifiees if ligne["statut"] == ERREUR),
        "lignes": verifiees,
    }


def modele_import() -> bytes:
    """Le fichier Excel à remplir : les bons en-têtes, une ligne d'exemple, la colonne Téléphone en
    texte (Excel n'y mange plus le zéro de tête), et la liste des entreprises partenaires."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    pays = _pays_entreprise()
    indicatif, longueur, zero_initial = PAYS[pays]
    exemple_national = ("07" if zero_initial else "7").ljust(longueur, "0")

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Main-d'œuvre"
    feuille.append(ENTETES_MODELE)
    feuille.append(["KONÉ", "Moussa", f"{indicatif} {exemple_national}", "Maçon", ""])
    for cellule in feuille[1]:
        cellule.font = Font(bold=True)
    for lettre, largeur in zip("ABCDE", (22, 22, 20, 20, 32), strict=True):
        feuille.column_dimensions[lettre].width = largeur
    for ligne in range(2, 1002):
        feuille.cell(row=ligne, column=3).number_format = "@"
    feuille.freeze_panes = "A2"

    entreprises = classeur.create_sheet("Entreprises")
    entreprises.append(["Entreprises partenaires (laisser vide pour notre entreprise)"])
    entreprises["A1"].font = Font(bold=True)
    entreprises.column_dimensions["A"].width = 60
    for tiers in partenaires_eligibles():
        entreprises.append([tiers.raison_sociale])

    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()
