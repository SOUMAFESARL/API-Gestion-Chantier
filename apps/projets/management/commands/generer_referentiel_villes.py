"""Recopie le référentiel des villes vers le frontend, sous forme TypeScript.

**Pourquoi une recopie plutôt qu'un appel d'API.** La liste des villes s'ouvre
dans une liste déroulante, au moment où quelqu'un clique dessus. Une liste qui
attend une réponse réseau est une liste vide à cet instant précis — et sur un
chantier, le réseau est la première chose qui manque. Elle est donc dans le
*bundle*, comme la liste des pays de l'inscription l'est déjà.

**Le prix de cette recopie, c'est la divergence** : deux listes que rien ne
tient ensemble finissent par ne plus dire la même chose, et personne ne le voit
puisque chacune fonctionne. D'où cette commande, et le test qui la rejoue en
mode `--verifier` : la même mécanique que `makemigrations --check`.

    python manage.py generer_referentiel_villes             # écrit le fichier
    python manage.py generer_referentiel_villes --verifier   # échoue s'il a divergé

Ce qui traverse la frontière, ce sont les **noms** et le découpage en groupes.
Les coordonnées GPS restent côté serveur : aucun écran ne les lit, et une donnée
recopiée sans lecteur est une donnée qui se périme en silence.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.projets.referentiels.villes import AGGLOMERATION_PRINCIPALE, LOCALITES

RACINE = Path(__file__).resolve().parents[5]
CIBLE_FRONTEND = RACINE / "frontend" / "src" / "features" / "referentiels" / "villes.ts"
CIBLE_APP = RACINE / "Application-Gestion-Chantier" / "src" / "features" / "referentiels" / "villes.ts"
CIBLE = CIBLE_APP if CIBLE_APP.exists() else CIBLE_FRONTEND

ENTETE = """/**
 * Référentiel des villes des neuf pays où une entreprise peut s'inscrire.
 *
 * **Ce fichier est généré.** Sa source est
 * `backend/apps/projets/referentiels/villes.py`, où la même liste porte les
 * coordonnées GPS dont la météo a besoin. Ne pas l'éditer à la main :
 *
 *     python manage.py generer_referentiel_villes
 *
 * `test_le_referentiel_typescript_ne_derive_pas` rejoue la commande en mode
 * vérification et casse la suite si les deux listes ne disent plus la même
 * chose.
 *
 * Il est **statique** : une liste déroulante qui attend une réponse d'API est
 * une liste déroulante vide au moment où on l'ouvre.
 */

"""

PIED = """
export interface ListeVilles {
  /** Le nom de l'agglomération, vide quand le pays n'en découpe pas. */
  agglomeration: string;
  /** Les communes de cette agglomération — vide dans le même cas. */
  communes: string[];
  /** Toutes les autres villes du pays. */
  autres: string[];
}

/**
 * Les villes d'un pays, prêtes à grouper.
 *
 * Un pays sans référentiel renvoie trois listes vides : l'écran bascule alors
 * sur sa saisie libre, ce qui est le comportement voulu — mieux vaut un champ
 * texte qu'une liste déroulante vide.
 */
export function listerVilles(pays: string): ListeVilles {
  const code = (pays || "").trim().toUpperCase();
  return {
    agglomeration: AGGLOMERATION[code] ?? "",
    communes: COMMUNES_AGGLOMERATION[code] ?? [],
    autres: VILLES_HORS_AGGLOMERATION[code] ?? [],
  };
}

/** La ville figure-t-elle au référentiel de ce pays. */
export function villeConnue(pays: string, nom: string): boolean {
  if (!nom) return false;
  const { communes, autres } = listerVilles(pays);
  return communes.includes(nom) || autres.includes(nom);
}
"""


def _liste(noms: list[str]) -> str:
    """Une ville par ligne : c'est ce qui rend le diff lisible en relecture."""
    return "\n".join(f'    "{nom}",' for nom in noms)


def rendre_typescript() -> str:
    """Le contenu attendu du fichier TypeScript."""
    morceaux = [ENTETE]

    morceaux.append(
        "/** Le nom de l'agglomération principale, pour les pays qui en découpent une. */\n"
        "export const AGGLOMERATION: Record<string, string> = {\n"
    )
    for pays, nom in sorted(AGGLOMERATION_PRINCIPALE.items()):
        morceaux.append(f'  {pays}: "{nom}",\n')
    morceaux.append("};\n\n")

    morceaux.append(
        "/** Les communes de l'agglomération principale — un groupe à part dans la liste. */\n"
        "export const COMMUNES_AGGLOMERATION: Record<string, string[]> = {\n"
    )
    for pays in sorted(LOCALITES):
        communes = sorted(loc["nom"] for loc in LOCALITES[pays] if loc["agglomeration"])
        if communes:
            morceaux.append(f"  {pays}: [\n{_liste(communes)}\n  ],\n")
    morceaux.append("};\n\n")

    morceaux.append(
        "/** Les autres villes du pays, par ordre alphabétique. */\n"
        "export const VILLES_HORS_AGGLOMERATION: Record<string, string[]> = {\n"
    )
    for pays in sorted(LOCALITES):
        autres = sorted(loc["nom"] for loc in LOCALITES[pays] if not loc["agglomeration"])
        morceaux.append(f"  {pays}: [\n{_liste(autres)}\n  ],\n")
    morceaux.append("};\n")

    morceaux.append(PIED)
    return "".join(morceaux)


class Command(BaseCommand):
    help = "Génère le référentiel TypeScript des villes depuis le référentiel Python."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verifier",
            action="store_true",
            help="N'écrit rien : échoue si le fichier a divergé de sa source.",
        )

    def handle(self, *args, **options):
        attendu = rendre_typescript()

        if options["verifier"]:
            if not CIBLE.exists():
                raise CommandError(f"{CIBLE} est absent — lancer la commande sans --verifier.")
            actuel = CIBLE.read_text(encoding="utf-8")
            if actuel != attendu:
                raise CommandError(
                    "Le référentiel TypeScript a divergé du référentiel Python. "
                    "Relancer « python manage.py generer_referentiel_villes »."
                )
            self.stdout.write(self.style.SUCCESS("Les deux référentiels concordent."))
            return

        CIBLE.parent.mkdir(parents=True, exist_ok=True)
        # `newline="\n"` explicitement : sous Windows, Python écrirait des CRLF,
        # et le fichier différerait de lui-même d'une machine à l'autre — le
        # mode vérification échouerait alors sans qu'aucune ville ait bougé.
        with CIBLE.open("w", encoding="utf-8", newline="\n") as fichier:
            fichier.write(attendu)

        total = sum(len(v) for v in LOCALITES.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"{total} localités dans {len(LOCALITES)} pays écrites vers {CIBLE.name}."
            )
        )
