"""Mesure le coût SQL des principaux endpoints, et le compare à une mesure précédente.

    python manage.py mesurer_requetes --sortie tmp/perf/mesure_schema_unique.json
    python manage.py mesurer_requetes --reference tmp/perf/mesure_avant.json --ignorer-empreintes

**Développement uniquement.** Pour chaque compte et chaque endpoint : le nombre de requêtes SQL,
la durée médiane de trois appels, une **empreinte** de la réponse JSON, et le nombre de requêtes
de **réglage** de la session, qui ne font pas de travail mais coûtent un aller-retour :

- dans l'ancien modèle (django-tenants), les `SET search_path`, que Django compte parmi les
  requêtes (colonne `search_path` des anciennes mesures) ;
- dans le schéma unique (D9), le `set_config` de la RLS (`apps.core.rls`), envoyé par le curseur
  brut, que Django ne voit pas (colonne `rls`).

La comparaison porte donc sur trois nombres : les requêtes **utiles** (hors réglage), les
**réglages**, et les **allers-retours** (la somme), seul chiffre qui se compare d'un modèle à
l'autre.

Avec `--reference`, une empreinte différente fait échouer la commande : une optimisation réussie
baisse le nombre de requêtes **sans changer une seule réponse**. Entre l'ancien modèle et le
schéma unique, les identifiants sont régénérés et toutes les empreintes diffèrent :
`--ignorer-empreintes` ne compare alors que les coûts.

Les appels passent par le client de test de Django, dans le processus : la mesure porte sur le
serveur seul. Les jetons sont émis comme à la connexion (`emettre_jetons`), sans mot de passe.

Prérequis : le jeu de `peupler_donnees_test` (chantiers `TEST-2026-0xx`) dans l'entreprise.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

# Les clés des comptes restent en `@demo.ci` : ce sont celles des mesures de référence. Pour une
# autre entreprise, l'adresse prend son domaine (`adresse_entreprise`).
COMPTES_PAR_DEFAUT = ["proprietaire", "cp.kone@demo.ci", "cc.kouassi@demo.ci"]

ENDPOINTS = [
    "/api/v1/auth/profil/",
    "/api/v1/utilisateurs/moi/",
    "/api/v1/referentiels/droits/",
    "/api/v1/projets/",
    "/api/v1/tableau-de-bord/",
    "/api/v1/projets/{TEST-2026-002}/",
    "/api/v1/projets/{TEST-2026-002}/decoupage/",
    "/api/v1/projets/{TEST-2026-002}/courbe/",
    "/api/v1/projets/{TEST-2026-003}/",
    "/api/v1/projets/{TEST-2026-003}/decoupage/",
]

# Clés qui changent d'un appel à l'autre sans que la réponse change de sens.
CLES_VOLATILES = {"trace_id", "genere_le", "calcule_le", "maintenant", "serveur_heure"}


def _normaliser(valeur):
    if isinstance(valeur, dict):
        return {k: _normaliser(v) for k, v in sorted(valeur.items()) if k not in CLES_VOLATILES}
    if isinstance(valeur, list):
        return [_normaliser(v) for v in valeur]
    return valeur


def _empreinte(reponse) -> str:
    try:
        contenu = json.loads(reponse.content or b"null")
    except ValueError:
        contenu = reponse.content.decode("utf-8", "replace")
    texte = json.dumps(_normaliser(contenu), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


def couts(mesure: dict) -> tuple[int, int, int]:
    """`(utiles, réglages, allers-retours)` d'une mesure, quel que soit le modèle qui l'a prise."""
    reglages_comptes = mesure.get("search_path", 0)  # inclus dans `requetes` (ancien modèle)
    reglages_hors_compte = mesure.get("rls", 0)  # absents de `requetes` (schéma unique)
    utiles = mesure["requetes"] - reglages_comptes
    reglages = reglages_comptes + reglages_hors_compte
    return utiles, reglages, utiles + reglages


class Command(BaseCommand):
    help = "Mesure le nombre de requêtes SQL et la durée des principaux endpoints."

    def add_arguments(self, parser):
        parser.add_argument("--entreprise", default="demo", help="Slug de l'entreprise mesurée.")
        parser.add_argument(
            "--comptes",
            nargs="*",
            default=COMPTES_PAR_DEFAUT,
            help="Emails des comptes ; « proprietaire » désigne le fondateur (DG).",
        )
        parser.add_argument("--sortie", help="Fichier JSON où écrire la mesure.")
        parser.add_argument("--reference", help="Mesure précédente à laquelle comparer.")
        parser.add_argument(
            "--ignorer-empreintes",
            action="store_true",
            help="Ne compare que les coûts (référence prise dans un autre modèle de données).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.DEBUG:
            raise CommandError("Commande de développement : refusée quand DEBUG est faux.")

        jetons, endpoints = self._preparer(options["entreprise"], options["comptes"])
        client = Client(HTTP_HOST="localhost")
        mesures = {}
        for compte, jeton in jetons.items():
            entetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}
            for gabarit, url in endpoints:
                client.get(url, **entetes)  # échauffement : imports, caches de module
                durees = []
                for _ in range(3):
                    # Le réglage RLS n'est renvoyé que si le contexte change : on oublie l'état
                    # mémorisé, comme le ferait la première requête d'une nouvelle requête HTTP
                    # arrivant après une autre entreprise sur la même connexion.
                    connection.etat_rls = None
                    connection.reglages_rls = 0
                    with CaptureQueriesContext(connection) as capture:
                        debut = time.perf_counter()
                        reponse = client.get(url, **entetes)
                        durees.append((time.perf_counter() - debut) * 1000)
                    requetes = capture.captured_queries
                    rls = connection.reglages_rls
                mesures[f"{compte} {gabarit}"] = {
                    "statut": reponse.status_code,
                    "requetes": len(requetes),
                    "search_path": sum(
                        1 for q in requetes if q["sql"].startswith("SET search_path")
                    ),
                    "rls": rls,
                    "ms": round(statistics.median(durees), 1),
                    "empreinte": _empreinte(reponse),
                }

        reference = self._lire(options["reference"]) if options["reference"] else None
        self._afficher(mesures, reference, options["ignorer_empreintes"])
        if options["sortie"]:
            chemin = Path(options["sortie"])
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_text(json.dumps(mesures, ensure_ascii=False, indent=1), encoding="utf-8")
            self.stdout.write(f"Mesure écrite dans {chemin}")
        if reference and not options["ignorer_empreintes"]:
            changees = [
                c
                for c in mesures
                if c in reference and mesures[c]["empreinte"] != reference[c]["empreinte"]
            ]
            if changees:
                raise CommandError("Au moins une réponse a changé par rapport à la référence.")
        if reference:
            statuts = [
                c
                for c in mesures
                if c in reference and mesures[c]["statut"] != reference[c]["statut"]
            ]
            if statuts:
                raise CommandError(f"Statut HTTP différent de la référence : {', '.join(statuts)}")

    def _preparer(self, slug, comptes):
        from apps.accounts.models import Utilisateur
        from apps.accounts.services.authentification import emettre_jetons
        from apps.core.contexte import contexte_entreprise, portee_plateforme
        from apps.projets.management.commands.peupler_donnees_test import adresse_entreprise
        from apps.projets.models import Projet
        from apps.tenants.models import Entreprise

        with portee_plateforme(motif="mesurer_requetes : entreprise mesurée"):
            entreprise = Entreprise.objects.filter(schema_name=slug).first()
        if entreprise is None:
            raise CommandError(f"Aucune entreprise « {slug} ».")

        jetons, endpoints = {}, []
        with contexte_entreprise(entreprise):
            for compte in comptes:
                if compte == "proprietaire":
                    utilisateur = Utilisateur.objects.filter(is_owner=True).first()
                else:
                    utilisateur = Utilisateur.objects.filter(
                        email=adresse_entreprise(compte, slug)
                    ).first()
                if utilisateur is None:
                    raise CommandError(f"Compte introuvable dans « {slug} » : {compte}")
                jetons[compte] = emettre_jetons(utilisateur)["access"]
            references = dict(
                Projet.objects.filter(reference__startswith="TEST-2026-").values_list(
                    "reference", "pk"
                )
            )
        for gabarit in ENDPOINTS:
            url = gabarit
            for reference, pk in references.items():
                url = url.replace(f"{{{reference}}}", str(pk))
            if "{" in url:
                raise CommandError("Jeu de test absent : lancez `peupler_donnees_test`.")
            endpoints.append((gabarit, url))
        return jetons, endpoints

    def _lire(self, chemin):
        return json.loads(Path(chemin).read_text(encoding="utf-8"))

    def _afficher(self, mesures, reference, ignorer_empreintes):
        entete = (
            f"{'compte / endpoint':<62} {'st':>3} {'utiles':>6} {'régl.':>5} {'a/r':>5} {'ms':>7}"
        )
        self.stdout.write(
            entete + ("  référence (utiles/régl./a-r)" if reference else "  empreinte")
        )
        total = [0, 0, 0]
        total_ref = [0, 0, 0]
        for cle, m in mesures.items():
            utiles, reglages, allers = couts(m)
            total = [total[0] + utiles, total[1] + reglages, total[2] + allers]
            ligne = (
                f"{cle[:62]:<62} {m['statut']:>3} {utiles:>6} {reglages:>5} {allers:>5} "
                f"{m['ms']:>7}"
            )
            if reference and cle in reference:
                r = reference[cle]
                r_utiles, r_reglages, r_allers = couts(r)
                total_ref = [
                    total_ref[0] + r_utiles,
                    total_ref[1] + r_reglages,
                    total_ref[2] + r_allers,
                ]
                identique = ignorer_empreintes or m["empreinte"] == r["empreinte"]
                regression = utiles > r_utiles or m["statut"] != r["statut"]
                ligne += f"  {r_utiles}/{r_reglages}/{r_allers}  ({allers - r_allers:+d} a/r)"
                if not identique:
                    ligne += "  RÉPONSE DIFFÉRENTE"
                style = self.style.ERROR if (regression or not identique) else self.style.SUCCESS
                self.stdout.write(style(ligne))
            else:
                self.stdout.write(f"{ligne}  {m['empreinte']}")
        self.stdout.write(
            f"Total : {total[0]} requêtes utiles, {total[1]} réglages, {total[2]} allers-retours."
        )
        if reference:
            self.stdout.write(
                f"Référence : {total_ref[0]} requêtes utiles, {total_ref[1]} réglages, "
                f"{total_ref[2]} allers-retours."
            )
