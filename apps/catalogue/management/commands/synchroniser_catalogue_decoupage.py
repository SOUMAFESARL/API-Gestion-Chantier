"""Synchronise les listes de valeurs et modèles de découpage plateforme de façon idempotente.

    python manage.py synchroniser_catalogue_decoupage
    python manage.py synchroniser_catalogue_decoupage --dry-run

Contrairement à `ensemencer_plateforme`, cette commande :
- fonctionne même lorsque des entreprises existent déjà en base ;
- ne charge que les 5 modèles du découpage plateforme (`ListeValeursPlateforme`,
  `ValeurListePlateforme`, `ModeleDecoupagePlateforme`, `NiveauModelePlateforme`,
  `LigneModelePlateforme`) depuis `apps/catalogue/fixtures/plateforme_initiale.json` ;
- est strictement non destructrice : si une liste ou un modèle existe déjà dans
  `_base_manager` (par `pk` ou par `cle_comparaison`, y compris supprimé logiquement),
  elle ne l'écrase pas et ne le ressuscite pas afin de préserver les choix du Super Admin.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogue.models.decoupage import (
    LigneModelePlateforme,
    ListeValeursPlateforme,
    ModeleDecoupagePlateforme,
    NiveauModelePlateforme,
    ValeurListePlateforme,
)
from apps.catalogue.models.referentiel import cle_comparaison

CHEMIN_FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "plateforme_initiale.json"
)


class Command(BaseCommand):
    help = (
        "Insère de façon idempotente et non destructrice les listes et modèles "
        "de découpage plateforme absents de la base."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les éléments qui seraient insérés sans modifier la base.",
        )

    def handle(self, *args, **options):
        dry_run: bool = bool(options.get("dry_run"))
        if not CHEMIN_FIXTURE.exists():
            raise CommandError(f"Fixture introuvable : {CHEMIN_FIXTURE}")

        donnees = json.loads(CHEMIN_FIXTURE.read_text(encoding="utf-8"))

        entrees_listes = [
            e for e in donnees if e.get("model") == "catalogue.listevaleursplateforme"
        ]
        entrees_valeurs = [
            e for e in donnees if e.get("model") == "catalogue.valeurlisteplateforme"
        ]
        entrees_modeles = [
            e for e in donnees if e.get("model") == "catalogue.modeledecoupageplateforme"
        ]
        entrees_niveaux = [
            e for e in donnees if e.get("model") == "catalogue.niveaumodeleplateforme"
        ]
        entrees_lignes = [
            e for e in donnees if e.get("model") == "catalogue.lignemodeleplateforme"
        ]

        compteurs = {
            "listes": 0,
            "valeurs": 0,
            "modeles": 0,
            "niveaux": 0,
            "lignes": 0,
        }

        with transaction.atomic():
            # 1. Listes de valeurs plateforme
            listes_par_pk = {
                str(lst.pk): lst for lst in ListeValeursPlateforme._base_manager.all()
            }
            listes_par_cle = {
                (lst.cle_comparaison or cle_comparaison(lst.libelle)): lst
                for lst in listes_par_pk.values()
            }
            # Associe le pk de la fixture à l'instance réelle en base (existante ou créée)
            correspondance_listes: dict[str, ListeValeursPlateforme] = {}
            listes_nouvelles_pks: set[str] = set()

            for entree in entrees_listes:
                pk = str(entree["pk"])
                champs = entree["fields"]
                libelle = champs["libelle"]
                cle = (champs.get("cle_comparaison") or cle_comparaison(libelle))[:120]

                existante = listes_par_pk.get(pk) or listes_par_cle.get(cle)
                if existante is not None:
                    correspondance_listes[pk] = existante
                    continue

                nouvelle_liste = ListeValeursPlateforme(
                    id=pk,
                    libelle=libelle,
                    cle_comparaison=cle,
                    description=champs.get("description", ""),
                    ordre=champs.get("ordre", 0),
                    est_actif=bool(champs.get("est_actif", True)),
                    supprime_le=champs.get("supprime_le"),
                )
                if not dry_run:
                    nouvelle_liste.save(force_insert=True)
                correspondance_listes[pk] = nouvelle_liste
                listes_par_pk[pk] = nouvelle_liste
                listes_par_cle[cle] = nouvelle_liste
                listes_nouvelles_pks.add(pk)
                compteurs["listes"] += 1

            # 2. Valeurs des listes plateforme
            valeurs_existantes = list(ValeurListePlateforme._base_manager.all())
            valeurs_pks = {str(v.pk) for v in valeurs_existantes}
            valeurs_cles = {
                (str(v.liste_id), v.cle_comparaison or cle_comparaison(v.libelle))
                for v in valeurs_existantes
            }
            listes_ayant_deja_valeurs = {str(v.liste_id) for v in valeurs_existantes}

            for entree in entrees_valeurs:
                pk = str(entree["pk"])
                champs = entree["fields"]
                fixture_liste_pk = str(champs["liste"])
                liste_cible = correspondance_listes.get(fixture_liste_pk)
                if liste_cible is None or liste_cible.supprime_le is not None:
                    continue

                cible_liste_pk = str(liste_cible.pk)
                # Si la liste existait déjà et possédait déjà ses valeurs (éventuellement
                # modifiées ou supprimées par le Super Admin), on ne la ré-ensemence pas.
                if (
                    fixture_liste_pk not in listes_nouvelles_pks
                    and cible_liste_pk in listes_ayant_deja_valeurs
                ):
                    continue

                libelle = champs["libelle"]
                cle = (champs.get("cle_comparaison") or cle_comparaison(libelle))[:200]
                if pk in valeurs_pks or (cible_liste_pk, cle) in valeurs_cles:
                    continue

                nouvelle_valeur = ValeurListePlateforme(
                    id=pk,
                    liste=liste_cible,
                    libelle=libelle,
                    groupe=champs.get("groupe", ""),
                    cle_comparaison=cle,
                    ordre=champs.get("ordre", 0),
                    supprime_le=champs.get("supprime_le"),
                )
                if not dry_run:
                    nouvelle_valeur.save(force_insert=True)
                valeurs_pks.add(pk)
                valeurs_cles.add((cible_liste_pk, cle))
                compteurs["valeurs"] += 1

            # 3. Modèles de découpage plateforme
            modeles_par_pk = {
                str(m.pk): m for m in ModeleDecoupagePlateforme._base_manager.all()
            }
            modeles_par_cle = {
                (m.cle_comparaison or cle_comparaison(m.nom)): m
                for m in modeles_par_pk.values()
            }
            modeles_ayant_niveaux = {
                str(mid)
                for mid in NiveauModelePlateforme._base_manager.values_list(
                    "modele_id", flat=True
                ).distinct()
            }
            correspondance_modeles: dict[str, ModeleDecoupagePlateforme] = {}
            modeles_a_peupler: set[str] = set()

            for entree in entrees_modeles:
                pk = str(entree["pk"])
                champs = entree["fields"]
                nom = champs["nom"]
                cle = (champs.get("cle_comparaison") or cle_comparaison(nom))[:160]

                existant = modeles_par_pk.get(pk) or modeles_par_cle.get(cle)
                if existant is not None:
                    correspondance_modeles[pk] = existant
                    if (
                        existant.supprime_le is None
                        and str(existant.pk) not in modeles_ayant_niveaux
                    ):
                        modeles_a_peupler.add(pk)
                    continue

                nouveau_modele = ModeleDecoupagePlateforme(
                    id=pk,
                    nom=nom,
                    cle_comparaison=cle,
                    description=champs.get("description", ""),
                    types_projet=champs.get("types_projet", []),
                    par_defaut_pour=champs.get("par_defaut_pour", []),
                    version=champs.get("version", 1),
                    est_actif=bool(champs.get("est_actif", True)),
                    supprime_le=champs.get("supprime_le"),
                )
                if not dry_run:
                    nouveau_modele.save(force_insert=True)
                correspondance_modeles[pk] = nouveau_modele
                modeles_par_pk[pk] = nouveau_modele
                modeles_par_cle[cle] = nouveau_modele
                modeles_a_peupler.add(pk)
                compteurs["modeles"] += 1

            # 4. Niveaux des modèles de découpage plateforme nouvellement insérés
            niveaux_existants = list(NiveauModelePlateforme._base_manager.all())
            niveaux_pks = {str(n.pk) for n in niveaux_existants}
            niveaux_ordres = {(str(n.modele_id), n.ordre) for n in niveaux_existants}

            for entree in entrees_niveaux:
                pk = str(entree["pk"])
                champs = entree["fields"]
                fixture_modele_pk = str(champs["modele"])
                if fixture_modele_pk not in modeles_a_peupler:
                    continue

                modele_cible = correspondance_modeles[fixture_modele_pk]
                cible_modele_pk = str(modele_cible.pk)
                ordre = champs["ordre"]
                if pk in niveaux_pks or (cible_modele_pk, ordre) in niveaux_ordres:
                    continue

                fixture_liste_pk = champs.get("liste")
                liste_cible = (
                    correspondance_listes.get(str(fixture_liste_pk))
                    if fixture_liste_pk
                    else None
                )
                if liste_cible is not None and liste_cible.supprime_le is not None:
                    liste_cible = None
                nouveau_niveau = NiveauModelePlateforme(
                    id=pk,
                    modele=modele_cible,
                    ordre=ordre,
                    libelle=champs["libelle"],
                    liste=liste_cible,
                    alerter=bool(champs.get("alerter", False)),
                    supprime_le=champs.get("supprime_le"),
                )
                if not dry_run:
                    nouveau_niveau.save(force_insert=True)
                niveaux_pks.add(pk)
                niveaux_ordres.add((cible_modele_pk, ordre))
                compteurs["niveaux"] += 1

            # 5. Lignes types des modèles de découpage plateforme nouvellement insérés
            lignes_pks = {
                str(lid)
                for lid in LigneModelePlateforme._base_manager.values_list("id", flat=True)
            }
            for entree in entrees_lignes:
                pk = str(entree["pk"])
                champs = entree["fields"]
                fixture_modele_pk = str(champs["modele"])
                if fixture_modele_pk not in modeles_a_peupler or pk in lignes_pks:
                    continue

                modele_cible = correspondance_modeles[fixture_modele_pk]
                nouvelle_ligne = LigneModelePlateforme(
                    id=pk,
                    modele=modele_cible,
                    ordre=champs.get("ordre", 0),
                    valeurs=champs.get("valeurs", []),
                    supprime_le=champs.get("supprime_le"),
                )
                if not dry_run:
                    nouvelle_ligne.save(force_insert=True)
                lignes_pks.add(pk)
                compteurs["lignes"] += 1

        prefixe = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            f"  {prefixe}Listes insérées : {compteurs['listes']} | "
            f"Valeurs insérées : {compteurs['valeurs']} | "
            f"Modèles insérés : {compteurs['modeles']} | "
            f"Niveaux insérés : {compteurs['niveaux']} | "
            f"Lignes insérées : {compteurs['lignes']}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixe}Synchronisation du catalogue de découpage plateforme terminée."
            )
        )
