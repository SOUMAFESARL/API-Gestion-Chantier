"""Enregistrer et retirer les avenants ; tenir les cumuls qui donnent le cadre contractuel.

- Un avenant exige qu'au moins un contrat du marché soit déposé sur le projet.
- L'avenant signé (`document`) et l'ordre de service (`ordre_service`) sont tous deux obligatoires.
- Aucune valeur négative n'est acceptée (prolongation en années/mois/jours >= 0, montant >= 0).
- Un avenant **sans case** porte sur le projet entier : ses prolongations s'ajoutent à la durée
  contractuelle du projet. **Avec des cases**, ses prolongations s'ajoutent aux jours accordés
  des cases visées, sans modifier leur budget.
- Le **montant** de tout avenant s'ajoute au budget contractuel du projet (jamais aux cases).
- Enregistrer ou retirer exige `projets.avenants_gerer` sur tout le projet (le chef de projet
  par défaut ; le DG a toutes les permissions).
"""

from __future__ import annotations

from collections import defaultdict

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import ErreurConflit
from apps.projets.models import Avenant, Element, Projet
from apps.projets.services.durees import duree_en_jours_approx

__all__ = ["avenant_en_dict", "enregistrer_avenant", "recalculer_avenants", "retirer_avenant"]


def recalculer_avenants(projet: Projet) -> None:
    """Les cumuls du projet et de ses cases, recalculés depuis les avenants vivants."""
    avenants = list(Avenant.objects.filter(projet=projet).prefetch_related("elements"))
    prol_annees, prol_mois, prol_jours = 0, 0, 0
    jours_projet, montant, jours_cases = 0, 0, defaultdict(int)
    for avenant in avenants:
        cases = [e for e in avenant.elements.all() if e.supprime_le is None]
        montant += avenant.montant or 0
        annees_a = avenant.annees_accordees or 0
        mois_a = avenant.mois_accordes or 0
        jours_a = avenant.jours_accordes or 0
        jours_equiv = duree_en_jours_approx(annees=annees_a, mois=mois_a, jours=jours_a)
        if cases:
            for case in cases:
                jours_cases[case.pk] += jours_equiv
        else:
            prol_annees += annees_a
            prol_mois += mois_a
            prol_jours += jours_a
            jours_projet += jours_equiv
    Projet.objects.filter(pk=projet.pk).update(
        jours_accordes=jours_projet,
        prolongation_annees=prol_annees,
        prolongation_mois=prol_mois,
        prolongation_jours=prol_jours,
        montant_avenants=montant,
    )
    projet.jours_accordes = jours_projet
    projet.prolongation_annees = prol_annees
    projet.prolongation_mois = prol_mois
    projet.prolongation_jours = prol_jours
    projet.montant_avenants = montant
    Element.objects.filter(projet=projet).exclude(pk__in=jours_cases).exclude(
        jours_accordes=0
    ).update(jours_accordes=0)
    for pk, jours in jours_cases.items():
        Element.objects.filter(pk=pk).update(jours_accordes=jours)


def _tracer(avenant, auteur, action, valeur):
    from apps.audit.services import journaliser

    journaliser(
        action=action,
        type_entite="Avenant",
        entite_id=avenant.pk,
        utilisateur_id=getattr(auteur, "pk", None),
        valeur_apres=valeur,
    )


@transaction.atomic
def enregistrer_avenant(
    projet: Projet,
    *,
    numero: str,
    date_signature,
    objet: str,
    annees_accordees: int = 0,
    mois_accordes: int = 0,
    jours_accordes: int = 0,
    montant: int | None = None,
    elements_ids=(),
    document=None,
    ordre_service=None,
    auteur=None,
) -> Avenant:
    """Un avenant signé : enregistré tel quel, avec contrat préalable, avenant signé et OS."""
    from pathlib import Path

    from apps.core.enums import ActionAudit
    from apps.projets.services.contrats import FORMATS, valider_fichier_contrat

    if not projet.contrats.exists():
        raise ValidationError(
            {
                "contrat": _(
                    "Déposez d'abord le contrat du marché sur ce projet "
                    "avant d'enregistrer un avenant."
                )
            }
        )

    erreurs = {}
    if document is None:
        erreurs["document"] = _("Le document d'avenant signé est obligatoire.")
    if ordre_service is None:
        erreurs["ordre_service"] = _("L'ordre de service lié à l'avenant est obligatoire.")
    if (annees_accordees or 0) < 0:
        erreurs["annees_accordees"] = _(
            "Le nombre d'années de prolongation ne peut pas être négatif."
        )
    if (mois_accordes or 0) < 0:
        erreurs["mois_accordes"] = _(
            "Le nombre de mois de prolongation ne peut pas être négatif."
        )
    if (jours_accordes or 0) < 0:
        erreurs["jours_accordes"] = _(
            "Le nombre de jours de prolongation ne peut pas être négatif."
        )
    if montant is not None and montant < 0:
        erreurs["montant"] = _("Le montant d'un avenant ne peut pas être négatif.")
    if erreurs:
        raise ValidationError(erreurs)

    cases = list(Element.objects.filter(pk__in=elements_ids or [], projet=projet))
    if len(cases) != len(set(map(str, elements_ids or []))):
        raise ValidationError({"elements_ids": _("Une case n'appartient pas à ce projet.")})
    valider_fichier_contrat(document)
    valider_fichier_contrat(ordre_service)

    avenant = Avenant(
        projet=projet,
        numero=numero.strip(),
        date_signature=date_signature,
        objet=objet.strip(),
        annees_accordees=annees_accordees or 0,
        mois_accordes=mois_accordes or 0,
        jours_accordes=jours_accordes or 0,
        montant=montant,
        cree_par=auteur,
    )
    try:
        with transaction.atomic():
            avenant.save()
    except IntegrityError:
        raise ErreurConflit(_(f"L'avenant n° {numero} existe déjà sur ce projet.")) from None

    ext_doc = Path(document.name).suffix.lower()
    avenant.document_nom = document.name[:255]
    avenant.document_type = FORMATS.get(
        ext_doc, getattr(document, "content_type", "") or "application/octet-stream"
    )
    avenant.document.save(document.name, document, save=False)

    ext_os = Path(ordre_service.name).suffix.lower()
    avenant.ordre_service_nom = ordre_service.name[:255]
    avenant.ordre_service_type = FORMATS.get(
        ext_os, getattr(ordre_service, "content_type", "") or "application/octet-stream"
    )
    avenant.ordre_service.save(ordre_service.name, ordre_service, save=False)

    avenant.save(
        update_fields=[
            "document",
            "document_nom",
            "document_type",
            "ordre_service",
            "ordre_service_nom",
            "ordre_service_type",
            "modifie_le",
        ]
    )
    avenant.elements.set(cases)
    recalculer_avenants(projet)
    _tracer(
        avenant,
        auteur,
        ActionAudit.CREATION,
        {
            "numero": avenant.numero,
            "annees_accordees": avenant.annees_accordees,
            "mois_accordes": avenant.mois_accordes,
            "jours_accordes": avenant.jours_accordes,
            "montant": avenant.montant,
            "cases": [str(c.pk) for c in cases],
        },
    )
    return avenant


@transaction.atomic
def retirer_avenant(avenant: Avenant, auteur=None) -> None:
    """Un avenant enregistré par erreur se retire ; l'historique garde sa trace."""
    from apps.core.enums import ActionAudit

    projet = avenant.projet
    avenant.delete(utilisateur=auteur)
    recalculer_avenants(projet)
    _tracer(avenant, auteur, ActionAudit.SUPPRESSION, {"numero": avenant.numero})


def avenant_en_dict(avenant: Avenant, *, montants_visibles: bool) -> dict:
    return {
        "id": str(avenant.pk),
        "numero": avenant.numero,
        "date_signature": avenant.date_signature,
        "objet": avenant.objet,
        "annees_accordees": avenant.annees_accordees,
        "mois_accordes": avenant.mois_accordes,
        "jours_accordes": avenant.jours_accordes,
        "montant": avenant.montant if montants_visibles else None,
        "porte_sur": "CASES" if avenant.elements.exists() else "PROJET",
        "cases": [
            {"id": str(e.pk), "libelle": e.libelle}
            for e in avenant.elements.all()
            if e.supprime_le is None
        ],
        "document": {"nom": avenant.document_nom, "type": avenant.document_type}
        if avenant.document
        else None,
        "ordre_service": {
            "nom": avenant.ordre_service_nom,
            "type": avenant.ordre_service_type,
        }
        if avenant.ordre_service
        else None,
        "cree_le": avenant.cree_le,
    }
