"""Résolution de l'en-tête et du pied des documents en lignes prêtes à imprimer.

Le navigateur dessine le PDF ; il ne connaît ni les libellés (« RCCM : … ») ni
l'endroit où l'entreprise range ses téléphones. Le serveur lui rend donc le
réglage ET ce que le réglage donne aujourd'hui, avec les valeurs de l'entreprise.
"""

from __future__ import annotations

from django.core.files.storage import default_storage

from apps.projets.models.parametres_documents import ParametresDocuments

__all__ = ["resoudre_documents", "valeurs_mentions"]


def _telephone_principal(entreprise) -> str:
    """Numéro principal de l'entreprise, à défaut le numéro de contact recopié."""
    principal = (
        entreprise.telephones.filter(est_principal=True, supprime_le__isnull=True)
        .order_by("ordre")
        .first()
    )
    if principal is not None:
        return principal.numero
    return (entreprise.telephone_contact or "").strip()


def valeurs_mentions(entreprise) -> dict[str, str]:
    """Ligne imprimable de chaque code de mention (chaîne vide = rien à imprimer).

    `site_web` n'existe pas sur l'entreprise : sa ligne reste vide, et donc omise,
    tant qu'aucun champ ne le porte.
    """

    def propre(valeur) -> str:
        return " ".join(str(valeur or "").split())

    def avec_libelle(libelle: str, valeur) -> str:
        valeur = propre(valeur)
        return f"{libelle} : {valeur}" if valeur else ""

    return {
        "raison_sociale": propre(entreprise.raison_sociale),
        "nom_commercial": propre(entreprise.nom_commercial),
        "rccm": avec_libelle("RCCM", entreprise.rccm),
        "nif": avec_libelle("NIF", entreprise.nif),
        "adresse": propre(entreprise.adresse),
        "ville": propre(entreprise.ville),
        "telephone": avec_libelle("Tél", _telephone_principal(entreprise)),
        "email": avec_libelle("Email", entreprise.email_contact),
        "site_web": avec_libelle("Site web", getattr(entreprise, "site_web", "")),
    }


def _lignes(codes: list[str], valeurs: dict[str, str], texte_libre: str) -> list[str]:
    lignes = [valeurs.get(code, "") for code in codes]
    lignes.append(" ".join((texte_libre or "").split()))
    return [ligne for ligne in lignes if ligne]


def _url_logo(entreprise, request) -> str | None:
    # L'original recadré sert aux documents (voir `EntrepriseSerializer`).
    cle = entreprise.logo_original or entreprise.logo
    if not cle:
        return None
    url = default_storage.url(cle)
    return request.build_absolute_uri(url) if request is not None else url


def resoudre_documents(
    parametres: ParametresDocuments, entreprise, request=None
) -> dict:
    """`{entete: {logo_url, lignes}, pied: {lignes}}` pour le réglage donné."""
    valeurs = valeurs_mentions(entreprise)
    return {
        "entete": {
            "logo_url": _url_logo(entreprise, request) if parametres.entete_afficher_logo else None,
            "lignes": _lignes(parametres.entete_mentions, valeurs, parametres.entete_texte_libre),
        },
        "pied": {
            "lignes": _lignes(parametres.pied_mentions, valeurs, parametres.pied_texte_libre),
        },
    }
