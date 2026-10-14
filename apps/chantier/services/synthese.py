"""Le circuit de la synthèse périodique : le CT rédige et signe, le CP approuve ou rejette.

Règles arrêtées le 14/10/2026 :

- **seules les semaines et les mois clos se signent** ; une période
  personnalisée se consulte et s'exporte, et une période en cours n'a pas
  encore de synthèse à signer ;
- **signe celui qui tient la fonction sur le chantier** (option 3, comme le
  rapport journalier) : le conducteur de travaux rédige et signe, le chef de
  projet approuve ou rejette ;
- **le CT ne s'approuve pas lui-même** : qui tient les deux fonctions signe
  la première, et laisse la seconde à un autre ;
- **à la signature du CT, le calcul est figé** ; un rejet le libère, et la
  signature suivante figera les rapports tels qu'ils seront alors.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.audit.services import journaliser
from apps.chantier.models import SynthesePeriodique
from apps.chantier.services.journal import aujourdhui, verifier_fonction
from apps.core.enums import ActionAudit
from apps.core.exceptions import ErreurMetier
from apps.projets.models import Projet
from apps.projets.services.machine_etats import verifier_statut_projet_pour_ecriture

#: Une appréciation signée dit quelque chose : comme un motif de rejet.
LONGUEUR_MIN_APPRECIATION = 20
LONGUEUR_MIN_MOTIF = 20

Statut = SynthesePeriodique.Statut


class SyntheseNonModifiable(ErreurMetier):
    code_metier = "regle_metier"
    default_detail = "Cette synthèse est signée : elle ne se modifie plus."


def verifier_signable(type_, fin):
    if type_ not in SynthesePeriodique.Type.values:
        raise ErreurMetier("Une période personnalisée se consulte ; elle ne se signe pas.")
    if fin >= aujourdhui():
        raise ErreurMetier(
            "La période n'est pas close : sa synthèse se rédige à partir du lendemain de son "
            "dernier jour."
        )


def _tracer(synthese, utilisateur, action, evenement, *, avant=None, commentaire=""):
    journaliser(
        action=action,
        type_entite="SynthesePeriodique",
        entite_id=synthese.id,
        utilisateur_id=utilisateur.id,
        valeur_avant=avant,
        valeur_apres={
            "statut": synthese.statut,
            "evenement": evenement,
            "projet": str(synthese.projet_id),
            "periode": f"{synthese.date_debut.isoformat()}/{synthese.date_fin.isoformat()}",
            "commentaire": commentaire,
        },
    )


def _ecrire(*, projet, type_, debut, fin, utilisateur, appreciation, objectifs):
    """Crée ou met à jour la rédaction du CT. À appeler dans une transaction."""
    verifier_signable(type_, fin)
    # Verrou du chantier : deux enregistrements simultanés ne créent pas deux synthèses.
    projet = get_object_or_404(Projet.objects.select_for_update(), pk=projet.pk)
    verifier_statut_projet_pour_ecriture(projet)
    verifier_fonction(projet, utilisateur, "CT")
    synthese = (
        SynthesePeriodique.objects.select_for_update()
        .filter(projet=projet, type=type_, date_debut=debut, date_fin=fin)
        .first()
    )
    creee = synthese is None
    if creee:
        synthese = SynthesePeriodique(
            projet=projet, type=type_, date_debut=debut, date_fin=fin, cree_par=utilisateur
        )
    elif synthese.statut not in (Statut.BROUILLON, Statut.REJETEE):
        raise SyntheseNonModifiable()
    synthese.appreciation = appreciation.strip()
    synthese.objectifs = objectifs
    synthese.redigee_par = utilisateur
    synthese.redigee_le = timezone.now()
    synthese.save()
    return synthese, creee


@transaction.atomic
def enregistrer_synthese(**redaction):
    synthese, creee = _ecrire(**redaction)
    _tracer(
        synthese,
        redaction["utilisateur"],
        ActionAudit.CREATION if creee else ActionAudit.MODIFICATION,
        "REDACTION_CT",
    )
    return synthese


@transaction.atomic
def soumettre_synthese(*, request, **redaction):
    """Enregistre la rédaction et la signe au nom du CT, en figeant le calcul."""
    from apps.chantier.selectors.synthese import calculer

    if len(redaction["appreciation"].strip()) < LONGUEUR_MIN_APPRECIATION:
        raise ErreurMetier(
            "L'appréciation est trop courte pour être signée.",
            details={
                "appreciation": [f"Au moins {LONGUEUR_MIN_APPRECIATION} caractères sont requis."]
            },
        )
    synthese, _ = _ecrire(**redaction)
    avant = {"statut": synthese.statut}
    synthese.photographie = calculer(
        request, synthese.projet, synthese.type, synthese.date_debut, synthese.date_fin
    )
    synthese.statut = Statut.SOUMISE
    synthese.signee_ct_par = redaction["utilisateur"]
    synthese.signee_ct_le = timezone.now()
    synthese.decidee_cp_par = None
    synthese.decidee_cp_le = None
    synthese.commentaire_cp = ""
    synthese.save()
    _tracer(synthese, redaction["utilisateur"], ActionAudit.SIGNATURE, "SIGNATURE_CT", avant=avant)
    return synthese


def _decider(synthese, utilisateur):
    """Le CP du chantier, sur une synthèse signée par le CT — et pas par lui."""
    synthese = get_object_or_404(
        SynthesePeriodique.objects.select_for_update().select_related("projet"), pk=synthese.pk
    )
    verifier_fonction(synthese.projet, utilisateur, "CP")
    verifier_statut_projet_pour_ecriture(synthese.projet)
    if synthese.statut != Statut.SOUMISE:
        raise ErreurMetier("Seule une synthèse signée par le conducteur de travaux se décide.")
    if synthese.signee_ct_par_id == utilisateur.id:
        raise PermissionDenied("Le signataire CT ne peut pas approuver sa propre synthèse.")
    return synthese


@transaction.atomic
def approuver_synthese(*, synthese, utilisateur, commentaire=""):
    synthese = _decider(synthese, utilisateur)
    synthese.statut = Statut.APPROUVEE
    synthese.decidee_cp_par = utilisateur
    synthese.decidee_cp_le = timezone.now()
    synthese.commentaire_cp = commentaire.strip()
    synthese.save()
    _tracer(
        synthese,
        utilisateur,
        ActionAudit.SIGNATURE,
        "SIGNATURE_CP",
        avant={"statut": Statut.SOUMISE},
        commentaire=synthese.commentaire_cp,
    )
    return synthese


@transaction.atomic
def rejeter_synthese(*, synthese, utilisateur, motif):
    if len(motif.strip()) < LONGUEUR_MIN_MOTIF:
        raise ErreurMetier(
            f"Le motif de rejet doit comporter au moins {LONGUEUR_MIN_MOTIF} caractères."
        )
    synthese = _decider(synthese, utilisateur)
    synthese.statut = Statut.REJETEE
    synthese.decidee_cp_par = utilisateur
    synthese.decidee_cp_le = timezone.now()
    synthese.commentaire_cp = motif.strip()
    # Rendue au CT : elle se recalcule, et sa prochaine signature la figera de nouveau.
    synthese.photographie = {}
    synthese.save()
    _tracer(
        synthese,
        utilisateur,
        ActionAudit.VALIDATION,
        "REJET_CP",
        avant={"statut": Statut.SOUMISE},
        commentaire=synthese.commentaire_cp,
    )
    return synthese
