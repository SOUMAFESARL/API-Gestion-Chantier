"""Outils de la suite d'étanchéité (D9, plan §4.3, lot 7) : routes, identifiants, témoin.

**Les routes viennent de l'URLconf**, par introspection : une route ajoutée demain est éprouvée
sans qu'on y pense. Ce qu'on écrit à la main, c'est seulement **quel modèle désigne chaque
paramètre d'URL** (`CIBLES`) — et une route dont un paramètre n'y figure pas fait échouer la
suite, plutôt que d'être sautée en silence.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from django.apps import apps
from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.resolvers import RegexPattern

METHODES = ("get", "post", "put", "patch", "delete")

# Paramètre d'URL → modèle dont on essaie l'identifiant d'une ligne de B. La clé est le segment
# d'URL qui précède le paramètre, et le nom du paramètre : `projets/<uuid:pk>` → `Projet`.
CIBLES: dict[tuple[str, str], str] = {
    ("projets", "pk"): "projets.Projet",
    ("projets", "projet_id"): "projets.Projet",
    ("elements", "pk"): "projets.Element",
    ("avenants", "pk"): "projets.Avenant",
    ("dependances", "pk"): "projets.Dependance",
    ("niveaux", "niveau_id"): "projets.NiveauProjet",
    ("equipes", "equipe_id"): "projets.EquipeChantier",
    ("membres", "membre_id"): "projets.MembreEquipeChantier",
    ("affectations", "affectation_id"): "projets.AffectationEquipeElement",
    ("affectations", "pk"): "projets.AffectationProjet",
    ("arrets-chantier", "pk"): "projets.ArretChantier",
    ("alertes-retard", "pk"): "projets.AlerteRetard",
    ("exceptions", "pk"): "projets.ExceptionCalendrier",
    ("main-oeuvre", "pk"): "projets.PersonneMainOeuvre",
    ("listes", "pk"): "projets.ListeValeursEntreprise",
    ("valeurs", "pk"): "projets.ValeurListeEntreprise",
    ("modeles", "pk"): "projets.ModeleDecoupageEntreprise",
    # `rapports/<pk>` comme `chantier/rapports/<pk>` : l'identifiant du rapport journalier (le
    # journal se charge par `rapport_id`).
    ("rapports", "pk"): "chantier.RapportJournalier",
    ("blocages", "pk"): "chantier.Blocage",
    ("syntheses", "pk"): "chantier.SynthesePeriodique",
    ("journal", "identifiant"): "chantier.JournalChantier",
    ("tiers", "pk"): "tiers.Tiers",
    ("collaborateurs", "pk"): "accounts.Utilisateur",
    ("invitations", "pk"): "accounts.Utilisateur",
    ("comptes", "pk"): "accounts.Utilisateur",
    ("roles", "pk"): "accounts.Role",
    ("clients", "client_id"): "tenants.Entreprise",
    ("entreprises", "entreprise_id"): "tenants.Entreprise",
    ("inscriptions", "pk"): "tenants.DemandeInscription",
    ("factures", "pk"): "billing.Facture",
    ("statut", "transaction_id"): "billing.PaiementAbonnement.reference_transaction",
}

# Paramètres qui ne désignent pas une ligne : une valeur fixe, valable pour toute entreprise.
# Une route qui n'a que ceux-là est éprouvée comme une liste.
VALEURS_FIXES = {
    "categorie": "types-projet",
    "origine": "ENTREPRISE",
    # Codes d'un espace de noms propre à chaque entreprise (étapes de configuration,
    # référentiels) : A n'atteint que les siens, quel que soit le code.
    "code": "INEXISTANT",
}

# Routes d'administration de la plateforme : le catalogue n'appartient à aucune entreprise. Le
# DG de A doit y être refusé ; l'identifiant essayé est quelconque.
PREFIXES_PLATEFORME = ("api/v1/admins/", "api/v1/admin/")
PARAMETRES_PLATEFORME = {"pk", "module_id"}

# Corps envoyés aux routes d'écriture qui valident le corps **avant** de vérifier les droits :
# un corps vide y obtient un 400, et la frontière n'est jamais atteinte.
CORPS = {
    "api/v1/admins/entreprises/<uuid:entreprise_id>/assistance/": {
        "motif": "Suite d'étanchéité : le DG d'une autre entreprise ne doit pas entrer."
    },
}

# Refus sous un autre code que 403/404, sans rien laisser voir de B : tolérés, chacun avec sa
# raison. Le corps et le témoin restent vérifiés.
REFUS_ATYPIQUES = {
    "api/v1/^decoupage/listes/(?P<origine>PLATEFORME|ENTREPRISE|plateforme|entreprise)/"
    "(?P<pk>[0-9a-fA-F-]{36})/$": (
        {400},
        "la liste de l'URL passe par `resoudre_liste`, qui répond 400 « Cette liste est "
        "introuvable » (elle valide aussi les références envoyées dans un corps)",
    ),
    "api/v1/^decoupage/listes/(?P<origine>PLATEFORME|ENTREPRISE|plateforme|entreprise)/"
    "(?P<pk>[0-9a-fA-F-]{36})/valeurs/$": (
        {400},
        "le corps est validé avant la liste, puis `resoudre_liste` répond 400",
    ),
    "api/v1/^decoupage/listes/(?P<origine>PLATEFORME|ENTREPRISE|plateforme|entreprise)/"
    "(?P<pk>[0-9a-fA-F-]{36})/valeurs/importer/$": (
        {415},
        "import de fichier : un corps JSON est refusé par l'analyseur avant la vue",
    ),
}

# Routes dont le contrôle positif (B lit sa propre ligne) est sans objet.
CONTROLE_SANS_OBJET = {
    "api/v1/avenants/<uuid:pk>/document/": "l'avenant de test n'a pas de document joint",
    "api/v1/factures/<uuid:pk>/": "réservée au personnel de l'éditeur (403 pour un client)",
    "api/v1/factures/<uuid:pk>/pdf/": "réservée au personnel de l'éditeur (403 pour un client)",
}

# Routes retirées de la suite, chacune avec sa raison.
EXCLUSIONS = {
    "^media/(?P<path>.*)$": "fichiers servis par Django en développement seulement (DEBUG)",
    "api/v1/inscription/etat/<uuid:suivi>/": (
        "sonde publique de l'inscription : l'identifiant de suivi, tiré au hasard, est le secret"
    ),
}


@dataclass(frozen=True)
class Route:
    gabarit: str  # tel que l'URLconf l'écrit : api/v1/projets/<uuid:pk>/
    morceaux: tuple[tuple[bool, str], ...]  # (est_une_regex, texte) de chaque niveau
    parametres: tuple[str, ...]
    methodes: tuple[str, ...]
    vue: str

    def __str__(self) -> str:
        return self.gabarit

    @property
    def plateforme(self) -> bool:
        return self.gabarit.replace("^", "").startswith(PREFIXES_PLATEFORME)

    @property
    def identifiants(self) -> tuple[str, ...]:
        """Les paramètres qui désignent une ligne (hors valeurs fixes)."""
        return tuple(p for p in self.parametres if p not in VALEURS_FIXES)

    def url(self, valeurs: dict[str, str]) -> str:
        morceaux = []
        for est_regex, texte in self.morceaux:
            if est_regex:
                texte = _remplir_regex(texte, valeurs)
                texte = texte.removeprefix("^").removesuffix("$").replace("\\", "")
            else:
                texte = re.sub(r"<(?:\w+:)?(\w+)>", lambda m: str(valeurs[m.group(1)]), texte)
            morceaux.append(texte)
        return "/" + "".join(morceaux)

    def segment(self, parametre: str) -> str:
        """Le segment d'URL qui nomme `parametre` : le dernier segment littéral qui le précède,
        sans compter les autres paramètres ni les constantes (`PLATEFORME`) — dans
        `decoupage/listes/<origine>/<pk>`, c'est `listes`."""
        gabarit = "".join(
            _remplir_regex(texte, _Nommer()) if est_regex else texte
            for est_regex, texte in self.morceaux
        )
        avant = re.split(rf"<(?:\w+:)?{parametre}>", gabarit)[0]
        for morceau in reversed([m for m in avant.split("/") if m]):
            if not morceau.startswith("<") and not morceau.isupper():
                return morceau.lstrip("^")
        return ""


class _Nommer(dict):
    """Pour `_remplir_regex` : chaque groupe nommé redevient `<nom>`."""

    def __missing__(self, nom):
        return f"<{nom}>"


def _remplir_regex(texte: str, valeurs: dict[str, str]) -> str:
    """Remplace chaque groupe nommé `(?P<nom>…)` par sa valeur, parenthèses imbriquées comprises."""
    sortie, i = [], 0
    while (debut := texte.find("(?P<", i)) != -1:
        nom = texte[debut + 4 : texte.index(">", debut)]
        profondeur, j = 0, debut
        while True:
            if texte[j] == "(" and texte[j - 1 : j] != "\\":
                profondeur += 1
            elif texte[j] == ")" and texte[j - 1 : j] != "\\":
                profondeur -= 1
                if profondeur == 0:
                    break
            j += 1
        sortie.append(texte[i:debut])
        sortie.append(str(valeurs[nom]))
        i = j + 1
    sortie.append(texte[i:])
    return "".join(sortie)


def _methodes(rappel) -> tuple[str, ...]:
    actions = getattr(rappel, "actions", None)
    if actions:
        return tuple(m for m in METHODES if m in actions)
    classe = getattr(rappel, "cls", None) or getattr(rappel, "view_class", None)
    if classe is None:
        return ("get",)
    return tuple(m for m in METHODES if hasattr(classe, m))


def _parcourir(resolveur, morceaux=()):
    for motif in resolveur.url_patterns:
        morceau = (isinstance(motif.pattern, RegexPattern), str(motif.pattern))
        if isinstance(motif, URLResolver):
            yield from _parcourir(motif, (*morceaux, morceau))
        elif isinstance(motif, URLPattern):
            yield (*morceaux, morceau), motif


def toutes_les_routes() -> list[Route]:
    """Chaque route de l'URLconf, une fois (les variantes `.json` des routeurs DRF exceptées)."""
    routes, vus = [], set()
    for morceaux, motif in _parcourir(get_resolver()):
        gabarit = "".join(texte for _, texte in morceaux)
        if "(?P<format>" in gabarit or "<drf_format_suffix:format>" in gabarit:
            continue
        rappel = motif.callback
        classe = getattr(rappel, "cls", None) or getattr(rappel, "view_class", None)
        route = Route(
            gabarit=gabarit,
            morceaux=morceaux,
            parametres=tuple(motif.pattern.regex.groupindex),
            methodes=_methodes(rappel),
            vue=(classe or rappel).__name__,
        )
        if (gabarit, route.methodes) not in vus:
            vus.add((gabarit, route.methodes))
            routes.append(route)
    return routes


def cible(route: Route, parametre: str) -> str | None:
    """Le modèle (`app.Modele` ou `app.Modele.champ`) qu'un paramètre désigne, ou `None`."""
    return CIBLES.get((route.segment(parametre), parametre))


# --------------------------------------------------------------------------
# Ce qui appartient à une entreprise
# --------------------------------------------------------------------------
def modeles_d_entreprise():
    """Tout modèle qui rattache ses lignes à une entreprise : les `ModeleEntreprise` (sous RLS),
    et les tables de la plateforme qui portent une clé `entreprise` (abonnement, factures,
    demandes d'inscription…) — celles-là, seule la vue les protège."""
    from apps.tenants.models import Entreprise

    for modele in apps.get_models():
        if not modele._meta.managed or modele is Entreprise:
            continue
        champ = next(
            (
                f
                for f in modele._meta.concrete_fields
                if f.attname == "entreprise_id" or (f.is_relation and f.related_model is Entreprise)
            ),
            None,
        )
        if champ is not None:
            yield modele, champ.attname


def est_uuid(valeur) -> bool:
    return isinstance(valeur, uuid.UUID)


UUID_DANS_TEXTE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
