"""Équipes de chantier : composition datée, chef unique, affectation aux cases de l'arbre.

Décisions validées le 29/10/2026 :

- **Rattachée à une entreprise** — la nôtre ou un partenaire (sous-traitant, tâcheron). La
  « nature » d'avant (interne / sous-traitante, sans effet) n'est plus saisie : elle se déduit.
- **Un seul chef d'équipe**, membre de l'équipe, avec ou sans compte, **de la même entreprise
  que son équipe**. Le chef de chantier du projet peut lui-même diriger une équipe.
- **Membres choisis dans le registre de main-d'œuvre**, avec une date d'arrivée et une date de
  départ : l'historique de l'équipe se garde.
- **Une personne dans deux équipes le même jour** : permis, avec un avertissement.
- **Affectation à n'importe quelle case**, valable pour tout le sous-arbre ; une case peut
  recevoir plusieurs équipes ; la plus précise l'emporte.
- **Exécutant, mode d'exécution, équipe** : trois questions (qui répond du travail, comment on
  le suit, quelles personnes sont sur place). S'ils se contredisent — une équipe d'un partenaire
  sur une case que nous exécutons nous-mêmes —, le logiciel avertit sans bloquer.

Les fonctions d'écriture rendent `(objet, avertissements)` : la liste dit ce qui mérite
l'attention sans rien refuser.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import ErreurConflit, ErreurMetier
from apps.projets.models import (
    AffectationEquipeElement,
    EquipeChantier,
    MembreEquipeChantier,
    PersonneMainOeuvre,
)
from apps.projets.services.main_oeuvre import verifier_partenaire

__all__ = [
    "affecter_equipe",
    "ajouter_membre",
    "creer_equipe",
    "modifier_equipe",
    "modifier_membre",
    "retirer_affectation_equipe",
    "retirer_membre",
]

FONCTION_CHEF = "CHEF_EQUIPE"


def _nom_entreprise(tiers) -> str:
    return tiers.raison_sociale if tiers is not None else "notre entreprise"


def _avertissement(code: str, message: str, **details) -> dict:
    return {"code": code, "message": message, **details}


def chevauchements(personne, debut: date, fin: date | None, exclure_membre=None) -> list[dict]:
    """Les autres équipes où la personne est présente sur la même période (tous projets)."""
    qs = MembreEquipeChantier.objects.filter(personne=personne, equipe__est_actif=True).filter(
        Q(date_depart__isnull=True) | Q(date_depart__gte=debut)
    )
    if fin is not None:
        qs = qs.filter(date_arrivee__lte=fin)
    if exclure_membre is not None:
        qs = qs.exclude(pk=exclure_membre.pk)
    return [
        {"equipe_id": str(m.equipe_id), "equipe": m.equipe.nom, "projet": m.equipe.projet.nom}
        for m in qs.select_related("equipe", "equipe__projet")
    ]


def _verifier_chef(equipe, personne) -> None:
    if personne.entreprise_partenaire_id != equipe.entreprise_partenaire_id:
        raise ErreurMetier(
            f"Le chef d'équipe appartient à l'entreprise de son équipe : "
            f"{personne.nom_complet} est de {_nom_entreprise(personne.entreprise_partenaire)}, "
            f"l'équipe de {_nom_entreprise(equipe.entreprise_partenaire)}."
        )


def _ceder_la_place_de_chef(equipe, sauf=None) -> None:
    anciens = equipe.membres.filter(est_chef=True)
    if sauf is not None:
        anciens = anciens.exclude(pk=sauf.pk)
    for ancien in anciens:
        ancien.est_chef = False
        if ancien.fonction == FONCTION_CHEF:
            ancien.fonction = "OUVRIER_QUALIFIE"
        ancien.save(update_fields=["est_chef", "fonction", "modifie_le"])


def _avertir_membre(equipe, personne, debut, fin, exclure=None) -> list[dict]:
    avertissements = []
    if personne.entreprise_partenaire_id != equipe.entreprise_partenaire_id:
        avertissements.append(
            _avertissement(
                "MEMBRE_AUTRE_ENTREPRISE",
                f"{personne.nom_complet} est de {_nom_entreprise(personne.entreprise_partenaire)}, "
                f"l'équipe de {_nom_entreprise(equipe.entreprise_partenaire)}.",
            )
        )
    autres = [
        c for c in chevauchements(personne, debut, fin, exclure) if c["equipe_id"] != str(equipe.pk)
    ]
    if autres:
        avertissements.append(
            _avertissement(
                "DEUX_EQUIPES_MEME_JOUR",
                f"{personne.nom_complet} est aussi dans "
                + ", ".join(f"« {c['equipe']} » ({c['projet']})" for c in autres)
                + " sur la même période.",
                equipes=autres,
            )
        )
    return avertissements


@transaction.atomic
def creer_equipe(
    projet,
    *,
    nom: str,
    corps_etat: str = "",
    entreprise_partenaire=None,
    membres: list[dict] | None = None,
    createur=None,
) -> tuple[EquipeChantier, list[dict]]:
    nom = " ".join((nom or "").split())
    if not nom:
        raise ValidationError({"nom": "Le nom de l'équipe est obligatoire."})
    if EquipeChantier.objects.filter(projet=projet, nom__iexact=nom).exists():
        raise ErreurConflit(f"Une équipe « {nom} » existe déjà sur ce projet.")
    verifier_partenaire(entreprise_partenaire)
    equipe = EquipeChantier.objects.create(
        projet=projet,
        nom=nom,
        corps_etat=" ".join((corps_etat or "").split()),
        entreprise_partenaire=entreprise_partenaire,
        cree_par=createur,
    )
    avertissements = []
    if sum(1 for m in membres or [] if m.get("est_chef")) > 1:
        raise ErreurMetier("Une équipe n'a qu'un seul chef.")
    for donnees in membres or []:
        _, avert = ajouter_membre(equipe, createur=createur, **donnees)
        avertissements += avert
    return equipe, avertissements


@transaction.atomic
def modifier_equipe(equipe: EquipeChantier, *, donnees: dict) -> tuple[EquipeChantier, list[dict]]:
    champs = ["modifie_le"]
    avertissements = []
    if "nom" in donnees:
        nom = " ".join((donnees["nom"] or "").split())
        if not nom:
            raise ValidationError({"nom": "Le nom de l'équipe est obligatoire."})
        if (
            EquipeChantier.objects.filter(projet=equipe.projet, nom__iexact=nom)
            .exclude(pk=equipe.pk)
            .exists()
        ):
            raise ErreurConflit(f"Une équipe « {nom} » existe déjà sur ce projet.")
        equipe.nom = nom
        champs.append("nom")
    if "corps_etat" in donnees:
        equipe.corps_etat = " ".join((donnees["corps_etat"] or "").split())
        champs.append("corps_etat")
    if "entreprise_partenaire" in donnees:
        partenaire = donnees["entreprise_partenaire"]
        verifier_partenaire(partenaire)
        chef = (
            equipe.membres.filter(est_chef=True, date_depart__isnull=True)
            .select_related("personne")
            .first()
        )
        if chef is not None and chef.personne.entreprise_partenaire_id != getattr(
            partenaire, "pk", None
        ):
            raise ErreurMetier(
                "Le chef d'équipe appartient à l'entreprise de son équipe : "
                "changez d'abord de chef."
            )
        equipe.entreprise_partenaire = partenaire
        champs.append("entreprise_partenaire")
        etrangers = equipe.membres.filter(date_depart__isnull=True).exclude(
            personne__entreprise_partenaire=partenaire
        )
        if etrangers.exists():
            avertissements.append(
                _avertissement(
                    "MEMBRE_AUTRE_ENTREPRISE",
                    f"{etrangers.count()} membre(s) n'appartiennent pas à "
                    f"{_nom_entreprise(partenaire)}.",
                )
            )
    if "est_actif" in donnees:
        equipe.est_actif = bool(donnees["est_actif"])
        champs.append("est_actif")
    equipe.save(update_fields=champs)
    return equipe, avertissements


@transaction.atomic
def ajouter_membre(
    equipe: EquipeChantier,
    *,
    personne_id=None,
    personne: PersonneMainOeuvre | None = None,
    fonction: str = "OUVRIER",
    est_chef: bool = False,
    date_arrivee: date | None = None,
    date_depart: date | None = None,
    createur=None,
) -> tuple[MembreEquipeChantier, list[dict]]:
    if personne is None:
        personne = PersonneMainOeuvre.objects.filter(pk=personne_id).first()
    if personne is None or not personne.est_actif:
        raise ValidationError({"personne_id": "Cette personne est introuvable dans le registre."})
    debut = date_arrivee or timezone.localdate()
    if date_depart and date_depart < debut:
        raise ValidationError({"date_depart": "Le départ ne précède pas l'arrivée."})
    if equipe.membres.filter(personne=personne, date_depart__isnull=True).exists():
        raise ErreurConflit(f"{personne.nom_complet} fait déjà partie de cette équipe.")
    if fonction == FONCTION_CHEF:
        est_chef = True
    if est_chef:
        _verifier_chef(equipe, personne)
        _ceder_la_place_de_chef(equipe)
        fonction = FONCTION_CHEF
    avertissements = _avertir_membre(equipe, personne, debut, date_depart)
    membre = MembreEquipeChantier.objects.create(
        equipe=equipe,
        personne=personne,
        fonction=fonction,
        est_chef=est_chef,
        date_arrivee=debut,
        date_depart=date_depart,
        cree_par=createur,
    )
    return membre, avertissements


@transaction.atomic
def modifier_membre(
    membre: MembreEquipeChantier, *, donnees: dict
) -> tuple[MembreEquipeChantier, list[dict]]:
    """Fonction, chef d'équipe, dates d'arrivée et de départ. Nommer un chef retire la place à
    l'ancien ; un chef qui part cesse d'être chef."""
    equipe = membre.equipe
    champs = ["modifie_le"]
    if donnees.get("fonction") == FONCTION_CHEF:
        donnees = {**donnees, "est_chef": True}
    if "est_chef" in donnees and bool(donnees["est_chef"]) != membre.est_chef:
        if donnees["est_chef"]:
            if membre.date_depart is not None:
                raise ErreurMetier("Un membre parti ne devient pas chef de l'équipe.")
            _verifier_chef(equipe, membre.personne)
            _ceder_la_place_de_chef(equipe, sauf=membre)
            membre.est_chef = True
            membre.fonction = FONCTION_CHEF
            champs += ["est_chef", "fonction"]
        else:
            membre.est_chef = False
            if membre.fonction == FONCTION_CHEF:
                membre.fonction = "OUVRIER_QUALIFIE"
            champs += ["est_chef", "fonction"]
    if "fonction" in donnees and donnees["fonction"] != FONCTION_CHEF and not membre.est_chef:
        membre.fonction = donnees["fonction"]
        champs.append("fonction")
    for nom in ("date_arrivee", "date_depart"):
        if nom in donnees:
            setattr(membre, nom, donnees[nom])
            champs.append(nom)
    if membre.date_depart and membre.date_depart < membre.date_arrivee:
        raise ValidationError({"date_depart": "Le départ ne précède pas l'arrivée."})
    if membre.date_depart and membre.est_chef:
        membre.est_chef = False
        champs.append("est_chef")
    membre.save(update_fields=list(dict.fromkeys(champs)))
    avertissements = []
    if {"date_arrivee", "date_depart"} & set(donnees):
        avertissements = [
            a
            for a in _avertir_membre(
                equipe, membre.personne, membre.date_arrivee, membre.date_depart, membre
            )
            if a["code"] == "DEUX_EQUIPES_MEME_JOUR"
        ]
    return membre, avertissements


@transaction.atomic
def retirer_membre(
    membre: MembreEquipeChantier,
    *,
    date_depart: date | None = None,
    supprimer: bool = False,
    utilisateur=None,
) -> None:
    """Un départ se date (l'historique de l'équipe le garde) ; une erreur de saisie se supprime."""
    if supprimer:
        membre.delete(utilisateur=utilisateur)
        return
    membre.date_depart = date_depart or timezone.localdate()
    if membre.date_depart < membre.date_arrivee:
        raise ValidationError({"date_depart": "Le départ ne précède pas l'arrivée."})
    membre.est_chef = False
    membre.save(update_fields=["date_depart", "est_chef", "modifie_le"])


@transaction.atomic
def affecter_equipe(
    equipe: EquipeChantier, element, *, createur=None
) -> tuple[AffectationEquipeElement, list[dict]]:
    """Pose l'équipe sur une case : elle vaut pour tout le sous-arbre (§13bis)."""
    if element.projet_id != equipe.projet_id:
        raise ValidationError({"element_id": "Cette case n'appartient pas au projet de l'équipe."})
    if not equipe.est_actif:
        raise ErreurMetier("Cette équipe est désactivée.")
    if AffectationEquipeElement.objects.filter(equipe=equipe, element=element).exists():
        raise ErreurConflit("Cette équipe est déjà affectée à cette case.")
    affectation = AffectationEquipeElement.objects.create(
        equipe=equipe, element=element, cree_par=createur
    )
    from apps.projets.selectors.arbre import charger_arbre

    arbre = charger_arbre(element.projet)
    titulaire = arbre.titulaire_id(arbre.par_id[element.pk])
    avertissements = []
    if titulaire != equipe.entreprise_partenaire_id:
        avertissements.append(
            _avertissement(
                "EXECUTANT_DIFFERENT",
                f"L'équipe est de {_nom_entreprise(equipe.entreprise_partenaire)}, alors que "
                + (
                    "cette case est exécutée par notre entreprise."
                    if titulaire is None
                    else "cette case est exécutée par un autre titulaire."
                ),
            )
        )
    return affectation, avertissements


def retirer_affectation_equipe(affectation: AffectationEquipeElement, utilisateur=None) -> None:
    affectation.delete(utilisateur=utilisateur)
