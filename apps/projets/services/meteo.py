"""Météo temps réel pour la barre d'application et le tableau de bord.

Interroge l'API gratuite Open-Meteo et met le relevé en cache trente minutes,
pour que la barre s'affiche sans attendre le réseau à chaque page.

**Ce service ne renvoie aucune phrase.** Il renvoie des *codes* — une condition,
une alerte, une raison d'indisponibilité — et l'écran choisit les mots. C'est
la règle du Socle §1.1, et elle a une conséquence pratique ici : les libellés
partaient du serveur en français, l'écran en avait d'autres de son côté, et la
bulle d'aide de la barre affichait les uns pendant que la pastille affichait
les autres. *L'icône, elle, était choisie en cherchant « orage » dans la
phrase du serveur : reformuler un libellé changeait l'icône.*

Les libellés de ces codes vivent dans `messages/fr.json`, et non dans
`/referentiels/enumerations/` : rien de tout cela n'est stocké en base ni
sélectionnable dans un formulaire — c'est une dérivation passagère d'une source
extérieure, pas une énumération du modèle.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.core.cache import cache
from django.utils import timezone

from apps.projets.referentiels.villes import normaliser_chaine, resoudre_coordonnees

logger = logging.getLogger(__name__)

DUREE_CACHE_SECONDES = 1800  # 30 minutes

# **Les pays où la météo s'affiche — une décision de produit, pas une limite
# technique.** Le référentiel des localités couvre les neuf pays de
# l'inscription et sait résoudre leurs coordonnées ; Open-Meteo couvre le monde.
# La couverture reste la Côte d'Ivoire : arbitrage rendu le 09/09/2026.
PAYS_METEO = frozenset({"CI"})


# --- Les codes ------------------------------------------------------------
#
# Chacun a un libellé et une bulle d'aide dans `messages/fr.json`, sous
# `tableauDeBord.navigation.meteo`. Ajouter un code sans son libellé fait
# apparaître la clé brute dans la barre : c'est visible tout de suite, et c'est
# voulu — un code muet vaut mieux qu'un code traduit au hasard.

CONDITION_DEGAGE = "DEGAGE"
CONDITION_ECLAIRCIES = "ECLAIRCIES"
CONDITION_NUAGEUX = "NUAGEUX"
CONDITION_COUVERT = "COUVERT"
CONDITION_BROUILLARD = "BROUILLARD"
CONDITION_BRUINE = "BRUINE"
CONDITION_PLUIE = "PLUIE"
CONDITION_AVERSES = "AVERSES"
CONDITION_ORAGE = "ORAGE"
CONDITION_VARIABLE = "VARIABLE"

# Le degré de gêne pour le chantier, du plus léger au plus grave.
ALERTE_VIGILANCE_PLUIE = "VIGILANCE_PLUIE"
ALERTE_INTEMPERIES = "INTEMPERIES"
ALERTE_ORAGE = "ORAGE"

# Pourquoi il n'y a pas de température à montrer. Quatre situations, quatre
# messages — c'est ce que la barre affichait avant sous une seule phrase,
# « Température non disponible », qui laissait croire à une panne passagère
# alors que le pays n'était pas couvert ou la ville pas répertoriée.
RAISON_PAYS_NON_COUVERT = "PAYS_NON_COUVERT"
RAISON_VILLE_ABSENTE = "VILLE_ABSENTE"
RAISON_VILLE_INCONNUE = "VILLE_INCONNUE"
RAISON_SERVICE_INDISPONIBLE = "SERVICE_INDISPONIBLE"

# D'où vient la ville dont on montre la météo. La barre en a besoin pour
# formuler : la température du siège ne dit rien de la praticabilité d'un
# chantier à quatre cents kilomètres, et l'annoncer comme telle serait faux.
PORTEE_ENTREPRISE = "ENTREPRISE"
PORTEE_CHANTIER = "CHANTIER"


def interpreter_code_wmo(code: int | None) -> tuple[str, bool, str | None]:
    """Code météo WMO -> (condition, praticable, alerte).

    La praticabilité est un jugement BTP, pas une donnée d'Open-Meteo : on
    coupe à la forte averse, parce que c'est là que le béton frais, les
    tranchées et le travail en hauteur deviennent des sujets.
    """
    if code is None:
        return (CONDITION_VARIABLE, True, None)

    if code == 0:
        return (CONDITION_DEGAGE, True, None)
    if code in (1, 2):
        return (CONDITION_ECLAIRCIES, True, None)
    if code == 3:
        return (CONDITION_COUVERT, True, None)
    if code in (45, 48):
        return (CONDITION_BROUILLARD, True, None)
    if code in (51, 53, 55):
        return (CONDITION_BRUINE, True, None)
    if code in (61, 63):
        return (CONDITION_PLUIE, True, ALERTE_VIGILANCE_PLUIE)
    if code in (65, 80, 81, 82):
        return (CONDITION_AVERSES, False, ALERTE_INTEMPERIES)
    if code in (95, 96, 99):
        return (CONDITION_ORAGE, False, ALERTE_ORAGE)

    if code > 50:
        return (CONDITION_PLUIE, code < 65, None)
    return (CONDITION_NUAGEUX, True, None)


def meteo_indisponible(
    raison: str, ville: str = "", portee: str = PORTEE_ENTREPRISE
) -> dict[str, Any]:
    """L'état « pas de température », dans une forme unique.

    Il était écrit à la main en cinq endroits, avec cinq jeux de clés
    légèrement différents : l'écran devait deviner lesquelles seraient là.
    """
    return {
        "disponible": False,
        "raison": raison,
        "ville": ville or "",
        "portee": portee,
        "temperature": None,
        "condition": None,
        "code_wmo": None,
        "praticable": True,
        "alerte": None,
        "releve_le": None,
    }


def obtenir_meteo(ville: str, pays: str = "CI", portee: str = PORTEE_CHANTIER) -> dict[str, Any]:
    """Le relevé d'une localité, ou la raison de son absence.

    Ne lève jamais : une barre d'application ne tombe pas parce qu'un service
    météo ne répond pas.
    """
    code_pays = (pays or "").strip().upper()

    if code_pays not in PAYS_METEO:
        return meteo_indisponible(RAISON_PAYS_NON_COUVERT, ville, portee)

    if not (ville or "").strip():
        return meteo_indisponible(RAISON_VILLE_ABSENTE, "", portee)

    resolution = resoudre_coordonnees(ville, pays=code_pays)
    if resolution is None:
        return meteo_indisponible(RAISON_VILLE_INCONNUE, ville, portee)

    nom_canonique, latitude, longitude = resolution

    # Le code pays est **dans la clé** : « Matam » est à la fois une commune de
    # Conakry et un chef-lieu sénégalais. La portée, en revanche, n'y est pas —
    # la température d'une ville ne dépend pas de qui la regarde.
    cle_cache = f"meteo_{code_pays.lower()}_{normaliser_chaine(nom_canonique).replace(' ', '_')}"

    en_cache = cache.get(cle_cache)
    if isinstance(en_cache, dict):
        return {**en_cache, "portee": portee}

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        f"&timezone=Africa%2FAbidjan"
    )

    try:
        requete = urllib.request.Request(
            url,
            headers={"User-Agent": "CCD-Digital/1.0 (+https://ccd-digital.ci)"},
        )
        with urllib.request.urlopen(requete, timeout=2.5) as reponse:
            if reponse.status != 200:
                logger.warning(
                    "Open-Meteo a répondu avec le statut %s pour %s",
                    reponse.status,
                    nom_canonique,
                )
                return meteo_indisponible(RAISON_SERVICE_INDISPONIBLE, nom_canonique, portee)

            corps = json.loads(reponse.read().decode("utf-8"))

        actuel = corps.get("current", {})
        temperature_brute = actuel.get("temperature_2m")
        code_wmo = actuel.get("weather_code")
        condition, praticable, alerte = interpreter_code_wmo(code_wmo)

        releve: dict[str, Any] = {
            "disponible": True,
            "raison": None,
            "ville": nom_canonique,
            "temperature": (
                round(float(temperature_brute)) if temperature_brute is not None else None
            ),
            "condition": condition,
            "code_wmo": code_wmo,
            "praticable": praticable,
            "alerte": alerte,
            "releve_le": timezone.now().isoformat(),
        }

        cache.set(cle_cache, releve, timeout=DUREE_CACHE_SECONDES)
        return {**releve, "portee": portee}

    except Exception as exc:
        logger.warning(
            "Échec de l'appel météo Open-Meteo pour %s (%s) : %s",
            nom_canonique,
            url,
            exc,
        )
        return meteo_indisponible(RAISON_SERVICE_INDISPONIBLE, nom_canonique, portee)
