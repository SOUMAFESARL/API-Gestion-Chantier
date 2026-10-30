"""Enregistrer et retirer les avenants ; tenir les cumuls qui donnent la date contractuelle.

- Un avenant **sans case** porte sur le projet entier : ses jours s'ajoutent à l'origine du
  projet. **Avec des cases**, ses jours s'ajoutent à l'origine de chacune de ces cases.
- Le **montant** de tout avenant s'ajoute au budget contractuel du projet (positif ou négatif).
- Enregistrer ou retirer exige `projets.avenants_gerer` sur tout le projet (le chef de projet
  par défaut ; le DG a toutes les permissions).
"""

from __future__ import annotations

from collections import defaultdict

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import ErreurConflit
from apps.projets.models import Avenant, Element, Projet

__all__ = ["avenant_en_dict", "enregistrer_avenant", "recalculer_avenants", "retirer_avenant"]


def recalculer_avenants(projet: Projet) -> None:
    """Les cumuls du projet et de ses cases, recalculés depuis les avenants vivants."""
    avenants = list(Avenant.objects.filter(projet=projet).prefetch_related("elements"))
    jours_projet, montant, jours_cases = 0, 0, defaultdict(int)
    for avenant in avenants:
        cases = [e for e in avenant.elements.all() if e.supprime_le is None]
        montant += avenant.montant or 0
        if cases:
            for case in cases:
                jours_cases[case.pk] += avenant.jours_accordes
        else:
            jours_projet += avenant.jours_accordes
    Projet.objects.filter(pk=projet.pk).update(
        jours_accordes=jours_projet, montant_avenants=montant
    )
    projet.jours_accordes, projet.montant_avenants = jours_projet, montant
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
    jours_accordes: int = 0,
    montant: int | None = None,
    elements_ids=(),
    document=None,
    auteur=None,
) -> Avenant:
    """Un avenant signé : enregistré tel quel, sans circuit de validation."""
    from apps.core.enums import ActionAudit
    from apps.projets.services.contrats import valider_fichier_contrat

    cases = list(Element.objects.filter(pk__in=elements_ids or [], projet=projet))
    if len(cases) != len(set(map(str, elements_ids or []))):
        raise ValidationError({"elements_ids": "Une case n'appartient pas à ce projet."})
    if document is not None:
        valider_fichier_contrat(document)
    avenant = Avenant(
        projet=projet,
        numero=numero.strip(),
        date_signature=date_signature,
        objet=objet.strip(),
        jours_accordes=jours_accordes or 0,
        montant=montant,
        cree_par=auteur,
    )
    try:
        with transaction.atomic():
            avenant.save()
    except IntegrityError:
        raise ErreurConflit(f"L'avenant n° {numero} existe déjà sur ce projet.") from None
    if document is not None:
        avenant.document_nom = document.name[:255]
        avenant.document_type = getattr(document, "content_type", "") or ""
        avenant.document.save(document.name, document, save=False)
        avenant.save(update_fields=["document", "document_nom", "document_type", "modifie_le"])
    avenant.elements.set(cases)
    recalculer_avenants(projet)
    _tracer(
        avenant,
        auteur,
        ActionAudit.CREATION,
        {
            "numero": avenant.numero,
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
        "cree_le": avenant.cree_le,
    }
