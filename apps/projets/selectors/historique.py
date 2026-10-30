"""L'historique des modifications d'une case, lu dans le journal d'audit (§12.2, §13quinquies).

Chaque geste sur une case écrit une entrée au journal d'audit immuable (`services.arbre._tracer`) :
qui, quand, quel geste, le motif, et les valeurs avant et après quand le geste en a. L'historique
d'une case n'est que la lecture de ces entrées : **aucune table de plus**.

Les reports de dates ont leur propre historique, plus détaillé (motif de la liste, justification,
écart en jours) : `GET /elements/{id}/historique-dates/`.
"""

from __future__ import annotations

from apps.audit.models import JournalAudit

__all__ = ["LIBELLES_GESTES", "entrees_de_case", "representer_entrees"]

TYPE_ENTITE_CASE = "Element"

#: Le nom affiché de chaque geste. Un geste inconnu s'affiche par son code.
LIBELLES_GESTES = {
    "MODIFICATION": "Modification",
    "AJOUT_SOUS_CASE_COMMENCEE": "Ajout sous une case commencée",
    "DEPLACEMENT": "Déplacement",
    "DETAIL": "Détail en sous-tâches",
    "SUPPRESSION": "Suppression",
    "DESACTIVATION": "Désactivation",
    "REACTIVATION": "Réactivation",
    "SUSPENSION": "Suspension",
    "REPRISE": "Reprise",
    "CLOTURE": "Clôture",
    "REOUVERTURE": "Réouverture",
    "DUPLICATION": "Créée par copie",
    "DUPLIQUEE": "Copiée",
    "IMPORT_DQE": "Import du DQE",
}

#: Ce qu'une personne sans `projets.voir_montants` ne voit pas dans les valeurs avant et après.
CHAMPS_MONTANTS = {"montant", "montant_initial", "enveloppe", "poids"}


def entrees_de_case(element):
    """Les entrées du journal pour cette case, de la plus récente à la plus ancienne."""
    return JournalAudit.objects.filter(type_entite=TYPE_ENTITE_CASE, entite_id=element.pk).order_by(
        "-horodatage", "-id"
    )


def _masquer(valeurs, montants_visibles: bool):
    if not isinstance(valeurs, dict) or montants_visibles:
        return valeurs
    return {k: (None if k in CHAMPS_MONTANTS else v) for k, v in valeurs.items()}


def representer_entrees(entrees, *, montants_visibles: bool = True) -> list[dict]:
    """Les entrées d'une page, avec le nom de leur auteur (une requête pour toute la page)."""
    from apps.accounts.models import Utilisateur

    entrees = list(entrees)
    ids = {e.utilisateur_id for e in entrees if e.utilisateur_id}
    auteurs = {
        u.pk: u
        for u in Utilisateur.tous_objets.filter(pk__in=ids).only("id", "prenom", "nom", "email")
    }
    resultat = []
    for entree in entrees:
        apres = dict(entree.valeur_apres or {}) if isinstance(entree.valeur_apres, dict) else {}
        evenement = apres.pop("evenement", None) or entree.action
        motif = apres.pop("motif", "") or ""
        auteur = auteurs.get(entree.utilisateur_id)
        resultat.append(
            {
                "id": entree.pk,
                "horodatage": entree.horodatage,
                "action": entree.action,
                "geste": evenement,
                "geste_libelle": LIBELLES_GESTES.get(evenement, evenement),
                "motif": motif,
                "auteur": {
                    "id": str(auteur.pk),
                    "nom": f"{auteur.prenom} {auteur.nom}".strip() or auteur.email,
                }
                if auteur
                else None,
                "avant": _masquer(entree.valeur_avant, montants_visibles),
                "apres": _masquer(apres, montants_visibles) or None,
            }
        )
    return resultat
