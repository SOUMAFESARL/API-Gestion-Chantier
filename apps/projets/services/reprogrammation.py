"""Service métier de reprogrammation des dates prévisionnelles (US-033, RG-11).

Schéma : tenant.
Module CDC : 1 (Gestion des Projets).
"""

from datetime import date
from django.db import connection, transaction
from rest_framework import serializers

from apps.projets.models import (
    Activite,
    HistoriqueDate,
    Lot,
    MotifReport,
    Projet,
    TypeObjetHistorique,
)
from apps.projets.tasks import notifier_dg_derive_delai

__all__ = ["reprogrammer_date_instance"]


@transaction.atomic
def reprogrammer_date_instance(
    instance: Projet | Lot | Activite,
    nouvelle_date_fin: date,
    nouvelle_date_debut: date | None = None,
    motif_id: str | None = None,
    justification: str = "",
    auteur=None,
) -> dict:
    """Reprogramme les dates prévisionnelles d'un projet, d'un lot ou d'une activité.

    Garantit :
    1. Justification obligatoire >= 30 caractères (RG-11).
    2. Motif obligatoire parmi les motifs actifs (liste dynamique).
    3. Respect absolu de la hiérarchie temporelle (Activité <= Lot <= Projet).
    4. Traçabilité complète dans HistoriqueDate (avant / après / auteur / justification).
    5. Préservation immuable de la Baseline v0.
    6. Déclenchement d'une alerte Celery au DG si le cumul de dérive > 30 jours par rapport à la Baseline v0.
    """
    # 1. Validation de la justification (RG-11)
    justif_propre = (justification or "").strip()
    if len(justif_propre) < 30:
        raise serializers.ValidationError(
            {"justification": "La justification doit comporter au moins 30 caractères (RG-11)."}
        )

    # 2. Validation du motif
    if not motif_id:
        raise serializers.ValidationError({"motif_id": "Le motif de report est obligatoire."})

    try:
        motif = MotifReport.objects.get(id=motif_id, supprime_le__isnull=True)
    except (MotifReport.DoesNotExist, ValueError):
        raise serializers.ValidationError({"motif_id": "Le motif de report spécifié est introuvable."})

    if not motif.est_actif:
        raise serializers.ValidationError(
            {"motif_id": f"Le motif '{motif.libelle}' est inactif et ne peut plus être utilisé."}
        )

    # 3. Dates prévisionnelles cibles
    debut_cible = nouvelle_date_debut or instance.date_debut_prevue
    fin_cible = nouvelle_date_fin

    if not debut_cible or not fin_cible:
        raise serializers.ValidationError(
            {"date_fin_prevue": "Les dates de début et de fin prévisionnelles sont requises."}
        )

    if fin_cible <= debut_cible:
        raise serializers.ValidationError(
            {"date_fin_prevue": "La date de fin prévisionnelle doit être strictement postérieure à la date de début."}
        )

    # 4. Validation hiérarchique temporelle stricte
    if isinstance(instance, Activite):
        type_objet = TypeObjetHistorique.ACTIVITE
        lot = instance.lot
        if lot.date_debut_prevue and debut_cible < lot.date_debut_prevue:
            raise serializers.ValidationError(
                {
                    "date_debut_prevue": (
                        f"L'activité ne peut pas débuter avant son lot "
                        f"({lot.date_debut_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
        if lot.date_fin_prevue and fin_cible > lot.date_fin_prevue:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": (
                        f"L'activité ne peut pas se terminer après son lot "
                        f"({lot.date_fin_prevue.strftime('%d/%m/%Y')}). "
                        "Reprogrammez d'abord le lot parent."
                    )
                }
            )

    elif isinstance(instance, Lot):
        type_objet = TypeObjetHistorique.LOT
        projet = instance.projet
        if projet.date_debut_prevue and debut_cible < projet.date_debut_prevue:
            raise serializers.ValidationError(
                {
                    "date_debut_prevue": (
                        f"Le lot ne peut pas débuter avant le projet "
                        f"({projet.date_debut_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
        if projet.date_fin_prevue and fin_cible > projet.date_fin_prevue:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": (
                        f"Le lot ne peut pas se terminer après le projet "
                        f"({projet.date_fin_prevue.strftime('%d/%m/%Y')}). "
                        "Reprogrammez d'abord le projet."
                    )
                }
            )

        # Contrôle sur les activités enfants
        act_avant = instance.activites.filter(
            supprime_le__isnull=True,
            date_debut_prevue__lt=debut_cible,
        ).first()
        if act_avant:
            raise serializers.ValidationError(
                {
                    "date_debut_prevue": (
                        f"Le lot ne peut pas débuter après son activité '{act_avant.libelle}' "
                        f"({act_avant.date_debut_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
        act_apres = instance.activites.filter(
            supprime_le__isnull=True,
            date_fin_prevue__gt=fin_cible,
        ).first()
        if act_apres:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": (
                        f"Le lot ne peut pas se terminer avant son activité '{act_apres.libelle}' "
                        f"({act_apres.date_fin_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )

    elif isinstance(instance, Projet):
        type_objet = TypeObjetHistorique.PROJET
        # Contrôle sur les lots enfants
        lot_avant = instance.lots.filter(
            supprime_le__isnull=True,
            date_debut_prevue__lt=debut_cible,
        ).first()
        if lot_avant:
            raise serializers.ValidationError(
                {
                    "date_debut_prevue": (
                        f"Le projet ne peut pas débuter après son lot '{lot_avant.libelle}' "
                        f"({lot_avant.date_debut_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
        lot_apres = instance.lots.filter(
            supprime_le__isnull=True,
            date_fin_prevue__gt=fin_cible,
        ).first()
        if lot_apres:
            raise serializers.ValidationError(
                {
                    "date_fin_prevue": (
                        f"Le projet ne peut pas se terminer avant son lot '{lot_apres.libelle}' "
                        f"({lot_apres.date_fin_prevue.strftime('%d/%m/%Y')})."
                    )
                }
            )
    else:
        raise ValueError(f"Type d'entité non pris en charge pour la reprogrammation : {type(instance)}")

    # 5. Détection des changements réels
    ancien_debut = instance.date_debut_prevue
    ancienne_fin = instance.date_fin_prevue

    debut_modifie = (ancien_debut != debut_cible)
    fin_modifiee = (ancienne_fin != fin_cible)

    if not debut_modifie and not fin_modifiee:
        raise serializers.ValidationError(
            {"non_field_errors": ["Aucun décalage de date n'a été spécifié."]}
        )

    # 6. Historisation
    historiques_crees = []

    kwargs_lien = {
        "projet": instance if type_objet == TypeObjetHistorique.PROJET else (
            instance.projet if type_objet == TypeObjetHistorique.LOT else instance.lot.projet
        ),
        "lot": instance if type_objet == TypeObjetHistorique.LOT else (
            instance.lot if type_objet == TypeObjetHistorique.ACTIVITE else None
        ),
        "activite": instance if type_objet == TypeObjetHistorique.ACTIVITE else None,
    }

    if debut_modifie:
        h_debut = HistoriqueDate.objects.create(
            type_objet=type_objet,
            champ="date_debut_prevue",
            valeur_avant=ancien_debut,
            valeur_apres=debut_cible,
            ecart_jours=(debut_cible - ancien_debut).days,
            motif=motif,
            justification=justif_propre,
            auteur=auteur,
            **kwargs_lien,
        )
        historiques_crees.append(h_debut)

    if fin_modifiee:
        h_fin = HistoriqueDate.objects.create(
            type_objet=type_objet,
            champ="date_fin_prevue",
            valeur_avant=ancienne_fin,
            valeur_apres=fin_cible,
            ecart_jours=(fin_cible - ancienne_fin).days,
            motif=motif,
            justification=justif_propre,
            auteur=auteur,
            **kwargs_lien,
        )
        historiques_crees.append(h_fin)

    # 7. Sauvegarde des nouvelles dates prévisionnelles (Baseline v0 INTACTE)
    instance.date_debut_prevue = debut_cible
    instance.date_fin_prevue = fin_cible
    champs_maj = ["date_debut_prevue", "date_fin_prevue", "modifie_le"]

    from apps.projets.services.machine_etats import retablir_statut_apres_decalage_si_necessaire
    statut_retabli = retablir_statut_apres_decalage_si_necessaire(instance, nouvelle_date_fin=fin_cible)
    if statut_retabli:
        champs_maj.append("statut")

    instance.save(update_fields=champs_maj)

    # 8. Mesure de la dérive par rapport à la Baseline v0 & Alerte Celery
    baseline_fin = instance.date_fin_baseline or ancienne_fin
    jours_derive = (fin_cible - baseline_fin).days
    alerte_declenchee = False

    if jours_derive > 30:
        schema = getattr(connection, "schema_name", None)
        notifier_dg_derive_delai.delay(
            schema_name=schema,
            type_objet=type_objet,
            objet_id=str(instance.id),
            jours_derive=jours_derive,
            motif_libelle=motif.libelle,
            justification=justif_propre,
        )
        alerte_declenchee = True

    return {
        "instance": instance,
        "date_debut_prevue": debut_cible,
        "date_fin_prevue": fin_cible,
        "date_debut_baseline": instance.date_debut_baseline,
        "date_fin_baseline": instance.date_fin_baseline,
        "jours_derive_baseline": jours_derive,
        "alerte_dg_declenchee": alerte_declenchee,
        "statut_retabli": statut_retabli,
        "statut": getattr(instance, "statut", None),
        "historiques": historiques_crees,
    }
