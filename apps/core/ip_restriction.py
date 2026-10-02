"""Module de validation des restrictions d'adresse IP pour le Super Admin.

Gère l'extraction sécurisée de l'adresse IP cliente et l'évaluation contre
une liste blanche pouvant contenir des adresses IPv4/IPv6 isolées ou des
masques de sous-réseau CIDR (ex: 192.168.1.0/24, 10.0.0.0/8).
"""

import functools
import ipaddress
import logging
from typing import Sequence

logger = logging.getLogger("securite.super_admin")


def extraire_ip_client(request) -> str:
    """Extrait l'adresse IP du client à partir de la requête.

    Prend en compte l'en-tête HTTP_X_FORWARDED_FOR si présent,
    en extrayant la première adresse IP (client d'origine),
    sinon utilise REMOTE_ADDR.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip_parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]
        if ip_parts:
            return ip_parts[0]
    return (request.META.get("REMOTE_ADDR") or "").strip()


@functools.lru_cache(maxsize=128)
def _parser_reseau(regle: str):
    """Parse une règle d'adresse ou de sous-réseau avec cache."""
    try:
        return ipaddress.ip_network(regle, strict=False)
    except ValueError:
        return None


def est_ip_autorisee(ip_str: str, autorisees: Sequence[str]) -> bool:
    """Vérifie si l'adresse IP donnée figure dans la liste blanche d'IP ou de sous-réseaux.

    Args:
        ip_str: L'adresse IP à tester (IPv4 ou IPv6).
        autorisees: Séquence de chaînes d'IP ou plages CIDR (ex: ["127.0.0.1", "192.168.1.0/24"]).

    Returns:
        True si l'IP est autorisée, False sinon.
    """
    if not ip_str:
        return False

    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    for regle in autorisees:
        regle = regle.strip()
        if not regle:
            continue
        reseau = _parser_reseau(regle)
        if reseau and ip_obj in reseau:
            return True

    return False
