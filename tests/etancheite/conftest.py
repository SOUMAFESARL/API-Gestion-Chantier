"""Troisième couche de l'isolation : deux entreprises peuplées, et ce qu'il faut pour les opposer.

`demo` (A) et `beta` (B) sont créées par les commandes de développement — `creer_tenant_demo`,
puis `peupler_donnees_test` sur deux chantiers (`TEST-2026-002` : blocages, journaux manquants ;
`TEST-2026-006` : arrêt de chantier) —, puis complétées (`completer`) des lignes que le jeu ne crée
pas et que des routes désignent. Le peuplement se fait **une fois par session**, hors des
transactions des tests ; chaque test tourne ensuite dans une transaction annulée à la fin.

Localement, `pytest --reuse-db` garde la base de test d'une exécution à l'autre : le peuplement,
idempotent, ne refait alors rien.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from outils_etancheite import UUID_DANS_TEXTE, est_uuid, modeles_d_entreprise

SLUG_A, SLUG_B = "demo", "beta"
CHANTIERS = ["TEST-2026-002", "TEST-2026-006"]


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    from apps.core.contexte import reinitialiser_contexte

    silence = io.StringIO()
    with django_db_blocker.unblock(), override_settings(DEBUG=True):
        reinitialiser_contexte()
        from apps.catalogue.models import CatalogueModule

        if not CatalogueModule._base_manager.exists():
            call_command("ensemencer_plateforme", stdout=silence)
        annee = timezone.localdate().year
        call_command("charger_jours_feries", annees=[annee, annee + 1], stdout=silence)
        for slug in (SLUG_A, SLUG_B):
            call_command("creer_tenant_demo", entreprise=slug, stdout=silence)
            call_command(
                "peupler_donnees_test", entreprise=slug, chantiers=CHANTIERS, stdout=silence
            )
            from completement import completer

            completer(slug)
        reinitialiser_contexte()


@dataclass
class Monde:
    """Les deux entreprises, et de quoi agir au nom de chacune."""

    a: object
    b: object
    jeton_a: str
    jeton_b: str
    # Un identifiant de B par modèle (`app.Modele`), et pour quelques champs (`app.Modele.champ`).
    exemples_b: dict[str, str] = field(default_factory=dict)
    # Tous les identifiants des lignes de B : aucun ne doit apparaître dans une réponse à A.
    identifiants_b: frozenset[str] = frozenset()
    marqueurs_b: tuple[str, ...] = ()

    def fuites(self, contenu: bytes) -> list[str]:
        """Ce qui, dans une réponse, appartient à B."""
        texte = contenu.decode("utf-8", "replace")
        trouves = {u.lower() for u in UUID_DANS_TEXTE.findall(texte)} & self.identifiants_b
        return sorted(trouves) + [m for m in self.marqueurs_b if m in texte]


# Les routes imbriquées (`projets/<pk>/equipes/<equipe_id>/`) veulent un enfant **de ce
# parent** : les exemples se prennent dans un même chantier, puis dans une même équipe.
PROJET_DE_REFERENCE = "TEST-2026-002"


def _exemple(modele, lignes, reference, exemples):
    """L'identifiant d'une ligne de B qui servira d'exemple pour `modele`."""
    from apps.projets.models import EquipeChantier, Projet

    champs = {f.name for f in modele._meta.concrete_fields}
    if modele is Projet:
        return reference.pk
    if "equipe" in champs and "projets.EquipeChantier" in exemples:
        lignes = lignes.filter(equipe_id=exemples["projets.EquipeChantier"])
    elif "projet" in champs and lignes.filter(projet=reference).exists():
        lignes = lignes.filter(projet=reference)
    elif "rapport" in champs and lignes.filter(rapport__projet=reference).exists():
        lignes = lignes.filter(rapport__projet=reference)
    if modele is EquipeChantier and lignes.filter(membres__isnull=False).exists():
        # Une équipe qui a des membres : ses enfants servent d'exemples.
        lignes = lignes.filter(membres__isnull=False).distinct()
    return lignes.order_by("pk").values_list("pk", flat=True).first()


def _jeton(entreprise):
    from apps.accounts.models import Utilisateur
    from apps.accounts.services.authentification import emettre_jetons
    from apps.core.contexte import contexte_entreprise

    with contexte_entreprise(entreprise):
        fondateur = Utilisateur.objects.get(is_owner=True)
        return emettre_jetons(fondateur)["access"]


@pytest.fixture(scope="session")
def monde(django_db_setup, django_db_blocker) -> Monde:
    from apps.core.contexte import portee_plateforme
    from apps.tenants.models import Entreprise

    with django_db_blocker.unblock():
        with portee_plateforme(motif="suite d'étanchéité : inventaire de B"):
            a = Entreprise.objects.get(schema_name=SLUG_A)
            b = Entreprise.objects.get(schema_name=SLUG_B)
            exemples, identifiants = {"tenants.Entreprise": str(b.pk)}, {str(b.pk)}
            from apps.projets.models import Projet

            reference = Projet._base_manager.get(entreprise=b, reference=PROJET_DE_REFERENCE)
            for modele, colonne in modeles_d_entreprise():
                lignes = modele._base_manager.filter(**{colonne: b.pk})
                cles = [cle for cle in lignes.values_list("pk", flat=True) if est_uuid(cle)]
                identifiants.update(str(cle) for cle in cles)
                exemple = _exemple(modele, lignes, reference, exemples)
                if exemple is not None:
                    exemples[modele._meta.label] = str(exemple)
            from apps.billing.models import PaiementAbonnement

            paiement = PaiementAbonnement._base_manager.filter(facture__entreprise=b).first()
            if paiement is not None:
                exemples["billing.PaiementAbonnement.reference_transaction"] = (
                    paiement.reference_transaction
                )
                identifiants.add(str(paiement.pk))
        jeton_a, jeton_b = _jeton(a), _jeton(b)
    return Monde(
        a=a,
        b=b,
        jeton_a=jeton_a,
        jeton_b=jeton_b,
        exemples_b=exemples,
        identifiants_b=frozenset(i.lower() for i in identifiants),
        marqueurs_b=(f"@{SLUG_B}.ci", b.raison_sociale),
    )


def temoin(entreprise_id) -> dict[str, tuple]:
    """L'état des lignes d'une entreprise, table par table : leur nombre et l'empreinte de leur
    contenu. Toute création, modification ou suppression (logique ou physique) le change. Une
    seule requête, en portée plateforme."""
    from apps.core.contexte import portee_plateforme

    morceaux, params = [], []
    for modele, colonne in modeles_d_entreprise():
        table = modele._meta.db_table
        morceaux.append(
            "SELECT %s, count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) "
            f'FROM "{table}" t WHERE t."{colonne}" = %s'
        )
        params += [table, entreprise_id]
    morceaux.append(
        "SELECT 'entreprise_cliente', count(*), md5(string_agg(t::text, ',')) "
        "FROM entreprise_cliente t WHERE t.id = %s"
    )
    params.append(entreprise_id)
    with (
        portee_plateforme(motif="suite d'étanchéité : témoin des lignes de B"),
        connection.cursor() as curseur,
    ):
        curseur.execute(" UNION ALL ".join(morceaux), params)
        return {table: tuple(reste) for table, *reste in curseur.fetchall()}
