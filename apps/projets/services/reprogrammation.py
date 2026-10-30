"""Service métier de reprogrammation des dates prévisionnelles (US-033, RG-11).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from datetime import date

from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db import connection, transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.core.exceptions import ErreurMetier
from apps.projets.models import (
    Element,
    HistoriqueDate,
    MotifReport,
    Projet,
    TypeObjetHistorique,
)
from apps.projets.tasks import notifier_dg_derive_delai

__all__ = [
    "ProlongationRequise",
    "planifier_element",
    "reprogrammer_date_instance",
]


class ProlongationRequise(ErreurMetier):
    """Les nouvelles dates débordent du parent : l'écran montre qui prolonger, puis confirme."""

    code_metier = "prolongation_requise"
    default_detail = (
        "Ces dates dépassent celles d'une case parente. Confirmez la prolongation des cases "
        "listées, ou choisissez d'autres dates."
    )


def _motif_valide(motif_id, justification: str) -> tuple[MotifReport, str]:
    justif_propre = (justification or "").strip()
    if len(justif_propre) < 30:
        raise serializers.ValidationError(
            {"justification": "La justification doit comporter au moins 30 caractères (RG-11)."}
        )
    if not motif_id:
        raise serializers.ValidationError({"motif_id": "Le motif de report est obligatoire."})
    try:
        motif = MotifReport.objects.get(id=motif_id, supprime_le__isnull=True)
    except (MotifReport.DoesNotExist, ValueError, ValidationErrorDjango):
        raise serializers.ValidationError(
            {"motif_id": "Le motif de report spécifié est introuvable."}
        ) from None
    if not motif.est_actif:
        raise serializers.ValidationError(
            {"motif_id": f"Le motif '{motif.libelle}' est inactif et ne peut plus être utilisé."}
        )
    return motif, justif_propre


def _tracer(instance, type_objet, champ, avant, apres, motif, justification, auteur):
    if avant is None or avant == apres:
        return None
    projet = instance if type_objet == TypeObjetHistorique.PROJET else instance.projet
    return HistoriqueDate.objects.create(
        type_objet=type_objet,
        champ=champ,
        valeur_avant=avant,
        valeur_apres=apres,
        ecart_jours=(apres - avant).days,
        motif=motif,
        justification=justification,
        auteur=auteur,
        projet=projet,
        element=instance if type_objet == TypeObjetHistorique.ELEMENT else None,
    )


def _appliquer_prolongations(
    element, debut, fin, *, prolonger, autorise_a_prolonger, motif, justification, auteur
):
    """Élargit les parents qui doivent l'être, ou refuse en les listant (§11)."""
    from apps.projets.selectors.arbre import charger_arbre
    from apps.projets.services.calendrier import prolongations_necessaires

    arbre = charger_arbre(element.projet)
    prolongations = prolongations_necessaires(element, debut, fin, arbre)
    if not prolongations:
        return []
    if not prolonger:
        raise ProlongationRequise(details={"prolongations": [p.en_dict() for p in prolongations]})
    # Prolonger le projet, ou une case déjà commencée, exige `projets.prolonger` (§11.2).
    sensibles = [
        p
        for p in prolongations
        if p.est_projet or arbre.commence(arbre.par_id.get(p.cible.pk, p.cible))
    ]
    if sensibles and not autorise_a_prolonger:
        raise PermissionDenied(
            "Prolonger le projet, ou une case déjà commencée, exige la permission "
            "« projets.prolonger »."
        )
    justif = f"Prolongé par le report de « {element.libelle} » : {justification}"
    for p in prolongations:
        type_objet = TypeObjetHistorique.PROJET if p.est_projet else TypeObjetHistorique.ELEMENT
        _tracer(
            p.cible,
            type_objet,
            "date_debut_prevue",
            p.debut_avant,
            p.debut_apres,
            motif,
            justif,
            auteur,
        )
        _tracer(
            p.cible, type_objet, "date_fin_prevue", p.fin_avant, p.fin_apres, motif, justif, auteur
        )
        p.cible.date_debut_prevue = p.debut_apres
        p.cible.date_fin_prevue = p.fin_apres
        p.cible.save(update_fields=["date_debut_prevue", "date_fin_prevue", "modifie_le"])
    return [p.en_dict() for p in prolongations]


@transaction.atomic
def planifier_element(
    element: Element,
    *,
    date_debut: date | None,
    date_fin: date | None,
    prolonger: bool = False,
    autorise_a_prolonger: bool = False,
    motif_id=None,
    justification: str = "",
    auteur=None,
) -> dict:
    """Première saisie des dates d'une case (planification) — sans motif, sauf s'il faut
    prolonger un parent déjà daté : c'est alors une reprogrammation du parent (§11.1)."""
    if date_debut and date_fin and date_fin < date_debut:
        raise serializers.ValidationError(
            {"date_fin_prevue": "La date de fin ne peut pas précéder la date de début."}
        )
    from apps.projets.selectors.arbre import charger_arbre
    from apps.projets.services.calendrier import (
        prolongations_necessaires,
        verifier_enfants_contenus,
    )

    verifier_enfants_contenus(element, date_debut, date_fin)
    prolongations = []
    if prolongations_necessaires(element, date_debut, date_fin, charger_arbre(element.projet)):
        motif, justif = (None, "")
        if prolonger:
            motif, justif = _motif_valide(motif_id, justification)
        prolongations = _appliquer_prolongations(
            element,
            date_debut,
            date_fin,
            prolonger=prolonger,
            autorise_a_prolonger=autorise_a_prolonger,
            motif=motif,
            justification=justif,
            auteur=auteur,
        )
    element.date_debut_prevue = date_debut
    element.date_fin_prevue = date_fin
    element.save()
    return {"instance": element, "prolongations": prolongations}


@transaction.atomic
def reprogrammer_date_instance(
    instance: Projet | Element,
    nouvelle_date_fin: date,
    nouvelle_date_debut: date | None = None,
    motif_id: str | None = None,
    justification: str = "",
    auteur=None,
    prolonger: bool = False,
    autorise_a_prolonger: bool = False,
) -> dict:
    """Reprogramme les dates prévisionnelles d'un projet ou d'une case de son découpage.

    Garantit :
    1. Justification obligatoire >= 30 caractères (RG-11).
    2. Motif obligatoire parmi les motifs actifs (liste dynamique).
    3. Le parent encadre : on ne resserre pas une case en deçà de ses enfants ; une case qui
       déborde de son parent le prolonge, sur confirmation (`prolonger`), jusqu'au projet (§11).
    4. Traçabilité complète dans HistoriqueDate (avant / après / auteur / justification).
    5. Préservation immuable de la Baseline v0.
    6. Alerte Celery au DG si la dérive sur la date contractuelle (origine + avenants) > 30 jours.
    """
    motif, justif_propre = _motif_valide(motif_id, justification)

    # Dates prévisionnelles cibles
    debut_cible = nouvelle_date_debut or instance.date_debut_prevue
    fin_cible = nouvelle_date_fin

    if not debut_cible or not fin_cible:
        raise serializers.ValidationError(
            {"date_fin_prevue": "Les dates de début et de fin prévisionnelles sont requises."}
        )

    if fin_cible <= debut_cible:
        raise serializers.ValidationError(
            {
                "date_fin_prevue": "La date de fin prévisionnelle doit être strictement postérieure à la date de début."
            }
        )

    from apps.projets.services.calendrier import verifier_enfants_contenus

    if isinstance(instance, Projet):
        type_objet = TypeObjetHistorique.PROJET
    elif isinstance(instance, Element):
        type_objet = TypeObjetHistorique.ELEMENT
    else:
        raise ValueError(
            f"Type d'entité non pris en charge pour la reprogrammation : {type(instance)}"
        )
    verifier_enfants_contenus(instance, debut_cible, fin_cible)

    ancien_debut = instance.date_debut_prevue
    ancienne_fin = instance.date_fin_prevue
    if ancien_debut == debut_cible and ancienne_fin == fin_cible:
        raise serializers.ValidationError(
            {"non_field_errors": ["Aucun décalage de date n'a été spécifié."]}
        )

    prolongations = []
    if type_objet == TypeObjetHistorique.ELEMENT:
        prolongations = _appliquer_prolongations(
            instance,
            debut_cible,
            fin_cible,
            prolonger=prolonger,
            autorise_a_prolonger=autorise_a_prolonger,
            motif=motif,
            justification=justif_propre,
            auteur=auteur,
        )

    historiques_crees = [
        h
        for h in (
            _tracer(
                instance,
                type_objet,
                "date_debut_prevue",
                ancien_debut,
                debut_cible,
                motif,
                justif_propre,
                auteur,
            ),
            _tracer(
                instance,
                type_objet,
                "date_fin_prevue",
                ancienne_fin,
                fin_cible,
                motif,
                justif_propre,
                auteur,
            ),
        )
        if h is not None
    ]

    # Sauvegarde des nouvelles dates prévisionnelles (Baseline v0 INTACTE)
    instance.date_debut_prevue = debut_cible
    instance.date_fin_prevue = fin_cible
    champs_maj = ["date_debut_prevue", "date_fin_prevue", "modifie_le"]

    from apps.projets.services.machine_etats import retablir_statut_apres_decalage_si_necessaire

    statut_retabli = retablir_statut_apres_decalage_si_necessaire(
        instance, nouvelle_date_fin=fin_cible
    )
    if statut_retabli:
        champs_maj.append("statut")

    instance.save(update_fields=champs_maj)

    # La dérive se lit sur l'origine (baseline v0) ; l'alerte au DG, elle, se mesure sur la date
    # contractuelle : un délai accordé par avenant n'est pas un retard (30/10/2026).
    baseline_fin = instance.date_fin_baseline or ancienne_fin or fin_cible
    jours_derive = (fin_cible - baseline_fin).days
    jours_accordes = getattr(instance, "jours_accordes", 0) or 0
    jours_derive_contractuelle = jours_derive - jours_accordes
    alerte_declenchee = False

    if jours_derive_contractuelle > 30:
        schema = getattr(connection, "schema_name", None)
        notifier_dg_derive_delai.delay(
            schema_name=schema,
            type_objet=type_objet,
            objet_id=str(instance.id),
            jours_derive=jours_derive_contractuelle,
            motif_libelle=motif.libelle,
            justification=justif_propre,
        )
        alerte_declenchee = True

    # Déclenchement réactif du recalcul de santé (C8)
    projet_cible = instance if type_objet == TypeObjetHistorique.PROJET else instance.projet
    from apps.projets.services.sante_declencheur import declencher_recalcul_sante

    dernier_h_id = historiques_crees[-1].id if historiques_crees else None
    declencher_recalcul_sante(
        projet_id=projet_cible.id,
        declencheur_type="REPROGRAMMATION_DATE",
        declencheur_id=dernier_h_id,
    )

    return {
        "instance": instance,
        "date_debut_prevue": debut_cible,
        "date_fin_prevue": fin_cible,
        "date_debut_baseline": instance.date_debut_baseline,
        "date_fin_baseline": instance.date_fin_baseline,
        "jours_derive_baseline": jours_derive,
        "jours_accordes": jours_accordes,
        "date_fin_contractuelle": getattr(instance, "date_fin_contractuelle", None),
        "jours_derive_contractuelle": jours_derive_contractuelle,
        "alerte_dg_declenchee": alerte_declenchee,
        "statut_retabli": statut_retabli,
        "statut": getattr(instance, "statut", None),
        "historiques": historiques_crees,
        "prolongations": prolongations,
    }
