"""Le registre de main-d'œuvre de l'entreprise (décision validée le 29/10/2026).

Chaque personne qui peut entrer dans une équipe de chantier y figure une fois : **nom et prénom
obligatoires, téléphone facultatif**. Elle appartient à notre entreprise ou à un partenaire
(sous-traitant, tâcheron), et peut avoir un compte sur la plateforme — un chef de chantier qui
dirige aussi une équipe, par exemple. Une personne sans compte ne se convertit pas en compte
plus tard : un collaborateur avec compte a sa propre fiche, liée à son compte.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.core.enums import RoleTiersChoix
from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.projets.models import MembreEquipeChantier, PersonneMainOeuvre

__all__ = [
    "ROLES_PARTENAIRES",
    "creer_personne",
    "fiche_du_collaborateur",
    "lister_personnes",
    "modifier_personne",
    "retirer_personne",
    "verifier_partenaire",
]

# Les tiers dont les personnes et les équipes peuvent travailler sur nos chantiers.
ROLES_PARTENAIRES = {
    RoleTiersChoix.SOUS_TRAITANT,
    RoleTiersChoix.TACHERON,
    RoleTiersChoix.PRESTATAIRE,
}


def verifier_partenaire(tiers) -> None:
    """Une entreprise partenaire est un tiers sous-traitant, tâcheron ou prestataire."""
    if tiers is None:
        return
    roles = set(tiers.roles.values_list("role", flat=True))
    if not roles & {str(r) for r in ROLES_PARTENAIRES}:
        raise ErreurMetier(
            f"« {tiers.raison_sociale} » n'est ni sous-traitant, ni tâcheron, ni prestataire : "
            "ajoutez-lui ce rôle dans les tiers pour lui rattacher des personnes ou des équipes."
        )


def _texte(valeur) -> str:
    return " ".join((valeur or "").split())


def _telephone(valeur) -> str:
    if not valeur:
        return ""
    from apps.tenants.services.telephones import normaliser_telephone

    return normaliser_telephone(valeur) or _texte(valeur)


def _verifier_doublon(nom, prenom, entreprise_partenaire, exclure=None) -> None:
    doublons = PersonneMainOeuvre.objects.filter(
        nom__iexact=nom, prenom__iexact=prenom, entreprise_partenaire=entreprise_partenaire
    )
    if exclure is not None:
        doublons = doublons.exclude(pk=exclure.pk)
    if doublons.exists():
        raise ErreurConflit(
            f"{prenom} {nom} figure déjà dans le registre pour cette entreprise.",
            details={"existant": str(doublons.first().pk)},
        )


@transaction.atomic
def creer_personne(
    *,
    nom: str,
    prenom: str,
    telephone: str = "",
    entreprise_partenaire=None,
    utilisateur=None,
    metier: str = "",
    createur=None,
) -> PersonneMainOeuvre:
    nom, prenom = _texte(nom), _texte(prenom)
    erreurs = {}
    if not nom:
        erreurs["nom"] = "Le nom est obligatoire."
    if not prenom:
        erreurs["prenom"] = "Le prénom est obligatoire."
    if erreurs:
        raise ValidationError(erreurs)
    verifier_partenaire(entreprise_partenaire)
    if (
        utilisateur is not None
        and PersonneMainOeuvre.objects.filter(utilisateur=utilisateur).exists()
    ):
        raise ErreurConflit("Ce collaborateur a déjà sa fiche dans le registre.")
    _verifier_doublon(nom, prenom, entreprise_partenaire)
    return PersonneMainOeuvre.objects.create(
        nom=nom,
        prenom=prenom,
        telephone=_telephone(telephone),
        entreprise_partenaire=entreprise_partenaire,
        utilisateur=utilisateur,
        metier=_texte(metier),
        cree_par=createur,
    )


def fiche_du_collaborateur(utilisateur, createur=None) -> PersonneMainOeuvre:
    """La fiche d'un collaborateur avec compte — créée à la volée, de notre entreprise."""
    fiche = PersonneMainOeuvre.objects.filter(utilisateur=utilisateur).first()
    if fiche is not None:
        return fiche
    return PersonneMainOeuvre.objects.create(
        nom=_texte(utilisateur.nom) or utilisateur.email,
        prenom=_texte(utilisateur.prenom) or "-",
        telephone=getattr(utilisateur, "telephone", "") or "",
        utilisateur=utilisateur,
        cree_par=createur,
    )


@transaction.atomic
def modifier_personne(personne: PersonneMainOeuvre, *, donnees: dict) -> PersonneMainOeuvre:
    champs = ["modifie_le"]
    for nom in ("nom", "prenom", "metier"):
        if nom in donnees:
            valeur = _texte(donnees[nom])
            if nom in ("nom", "prenom") and not valeur:
                raise ValidationError({nom: "Ce champ est obligatoire."})
            setattr(personne, nom, valeur)
            champs.append(nom)
    if "telephone" in donnees:
        personne.telephone = _telephone(donnees["telephone"])
        champs.append("telephone")
    if "entreprise_partenaire" in donnees:
        partenaire = donnees["entreprise_partenaire"]
        verifier_partenaire(partenaire)
        if (
            partenaire != personne.entreprise_partenaire
            and MembreEquipeChantier.objects.filter(
                personne=personne, date_depart__isnull=True
            ).exists()
        ):
            raise ErreurMetier(
                "Cette personne est membre d'une équipe en cours : enregistrez d'abord son départ "
                "avant de changer son entreprise."
            )
        personne.entreprise_partenaire = partenaire
        champs.append("entreprise_partenaire")
    if "est_actif" in donnees:
        personne.est_actif = bool(donnees["est_actif"])
        champs.append("est_actif")
    _verifier_doublon(
        personne.nom, personne.prenom, personne.entreprise_partenaire, exclure=personne
    )
    personne.save(update_fields=champs)
    return personne


@transaction.atomic
def retirer_personne(personne: PersonneMainOeuvre, *, utilisateur=None) -> None:
    """Une personne qui a fait partie d'une équipe se désactive (l'historique la garde) ; une
    personne jamais affectée se supprime."""
    if MembreEquipeChantier.objects.filter(personne=personne, date_depart__isnull=True).exists():
        raise ErreurMetier(
            "Cette personne est membre d'une équipe en cours : enregistrez d'abord son départ."
        )
    if MembreEquipeChantier.tous_objets.filter(personne=personne).exists():
        personne.est_actif = False
        personne.save(update_fields=["est_actif", "modifie_le"])
        return
    personne.delete(utilisateur=utilisateur)


def lister_personnes(*, recherche: str = "", entreprise: str = "", actives: bool = True):
    """`entreprise` : vide (toutes), « INTERNE » (la nôtre) ou l'identifiant d'un partenaire."""
    qs = PersonneMainOeuvre.objects.select_related("entreprise_partenaire", "utilisateur")
    if actives:
        qs = qs.filter(est_actif=True)
    if recherche:
        qs = qs.filter(
            Q(nom__icontains=recherche)
            | Q(prenom__icontains=recherche)
            | Q(telephone__icontains=recherche)
        )
    if entreprise == "INTERNE":
        qs = qs.filter(entreprise_partenaire__isnull=True)
    elif entreprise:
        qs = qs.filter(entreprise_partenaire_id=entreprise)
    return qs.order_by("nom", "prenom")
