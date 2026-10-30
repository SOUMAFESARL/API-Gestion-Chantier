"""Qui tient quelle fonction du journal sur un projet : par les permissions (30/10/2026).

**Le nom du rôle ne compte pas.** Une fonction revient aux personnes **affectées** au projet dont
le rôle tenu sur ce projet porte la permission :

| Fonction                       | Permission                   |
|--------------------------------|------------------------------|
| écrire son rapport du jour     | `chantier.rediger`           |
| valider un rapport             | `chantier.valider`           |
| approuver un rapport           | `chantier.approuver`         |
| rédiger la synthèse            | `chantier.synthese_rediger`  |
| approuver la synthèse          | `chantier.synthese_approuver`|

L'entreprise règle ces permissions sur ses rôles et répond de ses choix ; les valeurs par défaut
donnent rédiger au chef de chantier, valider au conducteur, approuver au chef de projet.

**Le DG ne tient aucune fonction** (décision du 14/10/2026) : il a toutes les permissions mais
n'est affecté à aucun chantier ; il consulte et relance.

**Le périmètre.** Un titulaire sans case affectée a tout le projet. Un rapport parle de la partie
du projet de son rédacteur ; un signataire est attendu sur un rapport quand sa partie et celle du
rapport se recouvrent (l'une contient l'autre, ou l'une des deux est tout le projet).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.core.droits import est_dg, permissions_du_role

__all__ = [
    "APPROUVER",
    "REDIGER",
    "SYNTHESE_APPROUVER",
    "SYNTHESE_REDIGER",
    "VALIDER",
    "Titulaire",
    "affectations_actives",
    "chemins_des_cases",
    "perimetres_se_recouvrent",
    "tient_fonction",
    "titulaire_de",
    "titulaires",
    "verifier_fonction",
]

REDIGER = "chantier.rediger"
VALIDER = "chantier.valider"
APPROUVER = "chantier.approuver"
SYNTHESE_REDIGER = "chantier.synthese_rediger"
SYNTHESE_APPROUVER = "chantier.synthese_approuver"

LIBELLES = {
    REDIGER: "rédiger le journal",
    VALIDER: "valider un rapport",
    APPROUVER: "approuver un rapport",
    SYNTHESE_REDIGER: "rédiger la synthèse",
    SYNTHESE_APPROUVER: "approuver la synthèse",
}


def _aujourdhui():
    from zoneinfo import ZoneInfo

    return timezone.localdate(timezone=ZoneInfo("Africa/Abidjan"))


def affectations_actives(projet_id):
    """Les affectations du projet en vigueur aujourd'hui, de comptes actifs."""
    from apps.projets.models import AffectationProjet

    jour = _aujourdhui()
    return (
        AffectationProjet.objects.filter(
            projet_id=projet_id,
            est_actif=True,
            supprime_le__isnull=True,
            date_debut__lte=jour,
            utilisateur__supprime_le__isnull=True,
            utilisateur__statut="ACTIF",
        )
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        .select_related("utilisateur")
    )


@dataclass(frozen=True)
class Titulaire:
    """Qui tient une fonction sur le projet, et la partie du projet où il la tient."""

    utilisateur: object
    perimetre_ids: tuple[str, ...]
    chemins: tuple[str, ...]

    @property
    def tout_le_projet(self) -> bool:
        return not self.chemins

    def concerne(self, chemins_rapport) -> bool:
        return perimetres_se_recouvrent(self.chemins, chemins_rapport)


def perimetres_se_recouvrent(chemins_a, chemins_b) -> bool:
    """Vide : tout le projet. Deux branches se recouvrent si l'une contient l'autre."""
    if not chemins_a or not chemins_b:
        return True
    return any(a.startswith(b) or b.startswith(a) for a in chemins_a for b in chemins_b)


def chemins_des_cases(ids) -> tuple[str, ...]:
    """Les chemins actuels des cases d'un périmètre (une case déplacée garde sa branche)."""
    if not ids:
        return ()
    from apps.projets.models import Element

    return tuple(Element.objects.filter(pk__in=ids).values_list("chemin", flat=True))


def titulaires(projet, permission: str) -> list[Titulaire]:
    """Les personnes affectées au projet dont le rôle sur le projet porte la permission."""
    from apps.accounts.models import Role

    permissions_par_role: dict[str, set[str]] = {}
    resultat = []
    for affectation in affectations_actives(getattr(projet, "pk", projet)).prefetch_related(
        "perimetres"
    ):
        utilisateur = affectation.utilisateur
        if est_dg(utilisateur):
            continue
        code = (affectation.role_projet or "").upper()
        if code not in permissions_par_role:
            role = Role.objects.filter(code__iexact=code, supprime_le__isnull=True).first()
            permissions_par_role[code] = permissions_du_role(role) if role else set()
        if permission not in permissions_par_role[code]:
            continue
        cases = [c for c in affectation.perimetres.all() if c.supprime_le is None]
        resultat.append(
            Titulaire(
                utilisateur=utilisateur,
                perimetre_ids=tuple(str(c.pk) for c in cases),
                chemins=tuple(c.chemin for c in cases),
            )
        )
    return resultat


def titulaire_de(projet, utilisateur, permission: str) -> Titulaire | None:
    if utilisateur is None:
        return None
    return next(
        (t for t in titulaires(projet, permission) if t.utilisateur.pk == utilisateur.pk), None
    )


def tient_fonction(projet, utilisateur, permission: str) -> bool:
    return titulaire_de(projet, utilisateur, permission) is not None


def verifier_fonction(projet, utilisateur, permission: str) -> Titulaire:
    titulaire = titulaire_de(projet, utilisateur, permission)
    if titulaire is None:
        raise PermissionDenied(
            "Votre rôle sur ce projet n'a pas la permission de "
            f"{LIBELLES.get(permission, permission)}."
        )
    return titulaire
