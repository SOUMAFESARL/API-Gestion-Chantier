"""Services du module « tiers ».

Référentiel unique des acteurs externes (décision H3 du MCD).
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.audit.services import journaliser
from apps.core.enums import ActionAudit
from apps.core.exceptions import ErreurConflit
from apps.tiers.models import RoleTiers, Tiers
from apps.tiers.selectors import references_du_tiers

__all__ = [
    "TiersReferenceErreur",
    "creer_tiers",
    "modifier_tiers",
    "supprimer_tiers",
]

_LIBELLES_REFERENCES = {
    "projets": "des projets (client / maître d'ouvrage)",
    "elements": "des lots ou activités du découpage (titulaire)",
    "equipes": "des équipes de chantier (entreprise partenaire)",
    "main_oeuvre": "des personnes du registre de main-d'œuvre",
    "bons_commande": "des bons de commande de stock (fournisseur)",
}


class TiersReferenceErreur(ErreurConflit):
    """Suppression refusée : ce tiers est encore référencé par au moins une entité."""

    code_metier = "tiers_reference"
    default_detail = _(
        "Ce tiers est déjà référencé dans l'application et ne peut pas être supprimé."
    )


def _nettoyer_champs_texte(donnees: dict) -> dict:
    propre = dict(donnees)
    for champ in ("raison_sociale", "telephone", "email", "adresse", "ville", "rccm", "nif"):
        if champ in propre and propre[champ] is not None:
            propre[champ] = str(propre[champ]).strip()
    return propre


def _synchroniser_roles(tiers: Tiers, roles_codes: list[str], *, auteur=None) -> None:
    """Aligne les rôles d'un tiers en respectant la suppression logique et l'unicité."""
    cibles = list(dict.fromkeys(roles_codes))
    actifs = {r.role: r for r in RoleTiers.objects.filter(tiers=tiers)}

    for code, role_obj in actifs.items():
        if code not in cibles:
            role_obj.delete(utilisateur=auteur)

    for code in cibles:
        if code in actifs:
            continue
        supprime = RoleTiers.tous_objets.filter(
            tiers=tiers, role=code, supprime_le__isnull=False
        ).first()
        if supprime is not None:
            supprime.supprime_le = None
            supprime.supprime_par = None
            supprime.modifie_par = auteur
            supprime.save(
                update_fields=["supprime_le", "supprime_par", "modifie_par", "modifie_le"]
            )
        else:
            RoleTiers.objects.create(tiers=tiers, role=code, cree_par=auteur)


def _instantanee_tiers(tiers: Tiers) -> dict:
    return {
        "type_tiers": tiers.type_tiers,
        "raison_sociale": tiers.raison_sociale,
        "telephone": tiers.telephone,
        "email": tiers.email,
        "ville": tiers.ville,
        "est_actif": tiers.est_actif,
        "note_evaluation": (
            str(tiers.note_evaluation) if tiers.note_evaluation is not None else None
        ),
        "roles": sorted(r.role for r in tiers.roles.all() if r.supprime_le is None),
    }


@transaction.atomic
def creer_tiers(
    donnees: dict,
    *,
    auteur=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> Tiers:
    """Crée un tiers et ses rôles associés, avec trace d'audit."""
    propre = _nettoyer_champs_texte(donnees)
    roles_codes = list(dict.fromkeys(propre.pop("roles", [])))

    tiers = Tiers.objects.create(cree_par=auteur, **propre)
    for code in roles_codes:
        RoleTiers.objects.create(tiers=tiers, role=code, cree_par=auteur)

    tiers = Tiers.objects.prefetch_related("roles").get(pk=tiers.pk)
    journaliser(
        action=ActionAudit.CREATION,
        type_entite="tiers",
        entite_id=tiers.pk,
        utilisateur_id=auteur.pk if auteur and getattr(auteur, "is_authenticated", False) else None,
        valeur_apres=_instantanee_tiers(tiers),
        adresse_ip=adresse_ip,
        appareil=(appareil or "")[:255],
    )
    return tiers


@transaction.atomic
def modifier_tiers(
    tiers: Tiers,
    donnees: dict,
    *,
    auteur=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> Tiers:
    """Modifie partiellement un tiers et synchronise ses rôles en suppression logique."""
    tiers = Tiers.objects.select_for_update().prefetch_related("roles").get(pk=tiers.pk)
    avant = _instantanee_tiers(tiers)

    propre = _nettoyer_champs_texte(donnees)
    roles_codes = propre.pop("roles", None)

    for attr, val in propre.items():
        setattr(tiers, attr, val)
    if auteur is not None and getattr(auteur, "is_authenticated", False):
        tiers.modifie_par = auteur
    tiers.save()

    if roles_codes is not None:
        _synchroniser_roles(tiers, roles_codes, auteur=auteur)

    tiers = Tiers.objects.prefetch_related("roles").get(pk=tiers.pk)
    journaliser(
        action=ActionAudit.MODIFICATION,
        type_entite="tiers",
        entite_id=tiers.pk,
        utilisateur_id=auteur.pk if auteur and getattr(auteur, "is_authenticated", False) else None,
        valeur_avant=avant,
        valeur_apres=_instantanee_tiers(tiers),
        adresse_ip=adresse_ip,
        appareil=(appareil or "")[:255],
    )
    return tiers


@transaction.atomic
def supprimer_tiers(
    tiers: Tiers,
    *,
    auteur=None,
    adresse_ip: str | None = None,
    appareil: str = "",
) -> None:
    """Suppression logique d'un tiers, refusée (409) s'il est encore référencé."""
    tiers = Tiers.objects.select_for_update().prefetch_related("roles").get(pk=tiers.pk)
    refs = references_du_tiers(tiers)
    if refs:
        libelles = [_LIBELLES_REFERENCES.get(r, r) for r in refs]
        raise TiersReferenceErreur(
            (
                f"Impossible de supprimer « {tiers.raison_sociale} » : ce tiers est encore lié à "
                f"{', '.join(libelles)}. Désactivez-le plutôt pour conserver l'historique."
            ),
            details={"references": refs, "peut_desactiver": True},
        )

    avant = _instantanee_tiers(tiers)
    utilisateur = auteur if auteur and getattr(auteur, "is_authenticated", False) else None
    tiers.roles.all().supprimer_logiquement(utilisateur=utilisateur)
    tiers.delete(utilisateur=utilisateur)

    journaliser(
        action=ActionAudit.SUPPRESSION,
        type_entite="tiers",
        entite_id=tiers.pk,
        utilisateur_id=utilisateur.pk if utilisateur else None,
        valeur_avant=avant,
        adresse_ip=adresse_ip,
        appareil=(appareil or "")[:255],
    )
