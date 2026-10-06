"""Fabriques du lot 7 (montants : règles E-11 et E-12).

CE FICHIER (avec conftest.py du dossier acceptation/lot7) EST LE SEUL QUE GEMINI
A LE DROIT D'ADAPTER. Il ne modifie JAMAIS un fichier test_*.py. Si une assertion
lui semble fausse, il s'arrête et le signale (voir 07-cadrage-tests-lot7.md).
"""

import itertools
import sys
from pathlib import Path
from rest_framework.test import APIClient

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from fabriques_lot5 import (
    API,
    HOST,
    _schema,
    client_pour,
    creer_utilisateur,
    obtenir_dg,
    role_systeme,
    suspendre_utilisateur,
    utilisateur_avec_role,
)

ROLES_SYSTEME = ("DG", "AD", "DO", "DF", "CP", "CT", "CC", "MAG", "BAI", "VI")

_n_seq = itertools.count(7000)


class ClientLot7(APIClient):
    """Client de test API adapté pour le lot 7."""

    def get(self, path, data=None, **extra):
        if path == "/api/v1/profil/":
            path = "/api/v1/auth/profil/"
        return super().get(path, data=data, **extra)


class FabriqueLot7:
    """Contrat utilisé par les tests du lot 7."""

    # ------------------------------------------------------------------ acteurs
    def utilisateur(self, role_code, *, actif=True):
        """Crée un utilisateur du tenant de test avec le rôle système `role_code`.

        - e-mail unique et non vide ;
        - `actif=False` : compte désactivé ;
        - pour "DG" : renvoie le DG du tenant s'il existe déjà (un seul DG).
        """
        if role_code == "DG":
            if actif:
                return obtenir_dg()
            u = creer_utilisateur(role_systeme("DG"))
            suspendre_utilisateur(u)
            return u

        u = utilisateur_avec_role(role_code)
        if not actif:
            suspendre_utilisateur(u)
        return u

    def client(self, utilisateur=None):
        """Client API authentifié en tant que `utilisateur` (None = anonyme),
        routé vers le tenant de test. Chaque client représente SON utilisateur."""
        c = ClientLot7(HTTP_HOST=HOST)
        if utilisateur is not None:
            c.force_authenticate(user=utilisateur)
        return c

    def affecter(self, projet, utilisateur, role_projet="VI"):
        """Crée directement (ORM) une affectation active de `utilisateur` à `projet`,
        sans passer par l'API et sans désigner de chef de projet."""
        with _schema():
            from apps.projets.models import AffectationProjet

            aff, _ = AffectationProjet.objects.update_or_create(
                projet=projet,
                utilisateur=utilisateur,
                defaults={
                    "est_actif": True,
                    "role_projet": role_projet,
                },
            )
            return aff

    # --------------------------------------------------------------- données
    def projet(self, *, budget=None, statut="EN_COURS"):
        """Crée un projet valide (ORM), sans aucune affectation.
        `budget` : entier ou None, écrit dans budget_initial_montant."""
        n = next(_n_seq)
        with _schema():
            from apps.projets.models import Projet

            return Projet.objects.create(
                nom=f"Projet Test {n}",
                reference=f"PRJ-L7-{n:04d}",
                ville="Abidjan",
                statut=statut,
                budget_initial_montant=budget,
            )

    def lot(self, projet, *, budget=None):
        """Crée un lot valide du projet (ORM) avec `budget` comme budget initial."""
        n = next(_n_seq)
        with _schema():
            from apps.projets.models import Lot

            return Lot.objects.create(
                projet=projet,
                code=f"LOT-L7-{n:04d}",
                libelle=f"Lot Test {n}",
                budget_initial_montant=budget,
            )

    def activite(self, lot, *, budget=None):
        """Crée une activité valide du lot (ORM) avec `budget` comme budget initial."""
        n = next(_n_seq)
        with _schema():
            from apps.projets.models import Activite

            return Activite.objects.create(
                lot=lot,
                libelle=f"Activité Test {n}",
                quantite_prevue=10,
                budget_initial_montant=budget,
            )

    def bon_paiement(self, projet, *, montant):
        """Crée un élément qui apparaît dans `bons_paiement_a_valider` du tableau de bord."""
        from apps.projets.services.tableau_de_bord_bons import creer_bon_paiement_test

        return creer_bon_paiement_test(projet, montant=montant)

    def nombre_projets(self):
        """Nombre de projets existants dans le tenant de test."""
        with _schema():
            from apps.projets.models import Projet

            return Projet.objects.filter(supprime_le__isnull=True).count()

    # ------------------------------------------------------------------- URL
    def url_projets(self):
        """Liste et création des projets (GET, POST)."""
        return f"{API}/projets/"

    def url_projet(self, projet):
        """Détail d'un projet (GET, PATCH)."""
        return f"{API}/projets/{projet.pk}/"

    def url_lots(self, projet):
        """Liste et création des lots d'un projet (GET, POST)."""
        return f"{API}/projets/{projet.pk}/lots/"

    def url_lot(self, projet, lot):
        """Détail d'un lot (GET, PATCH)."""
        return f"{API}/lots/{lot.pk}/"

    def url_activites(self, lot):
        """Liste et création des activités d'un lot (GET, POST)."""
        return f"{API}/lots/{lot.pk}/activites/"

    def url_activite(self, activite):
        """Détail d'une activité (GET, PATCH)."""
        return f"{API}/activites/{activite.pk}/"

    def url_statistiques(self, projet):
        """Statistiques d'un projet (GET)."""
        return f"{API}/projets/{projet.pk}/statistiques/"

    def url_dashboard(self):
        """Tableau de bord (GET). Clés attendues : metriques, projets,
        bons_paiement_a_valider."""
        return f"{API}/tableau-de-bord/"

    # --------------------------------------------------------------- charges
    def payload_projet(self):
        """Corps valide d'un POST /projets/ sans aucun montant."""
        n = next(_n_seq)
        return {
            "nom": f"Projet Test {n}",
            "ville": "Abidjan",
            "maitre_ouvrage": "Client Test",
            "type_projet": "BATIMENT_RESIDENTIEL",
        }

    def payload_modification_projet(self):
        """Corps valide d'un PATCH de projet sans montant (ex. changer le nom)."""
        n = next(_n_seq)
        return {
            "nom": f"Projet Modifié {n}",
        }

    def payload_lot(self):
        """Corps valide d'un POST de lot sans montant."""
        n = next(_n_seq)
        return {
            "nom": f"Lot Test {n}",
            "mode_execution": "REGIE",
            "type_bordereau": "FORFAIT",
        }

    def payload_modification_lot(self):
        """Corps valide d'un PATCH de lot sans montant."""
        n = next(_n_seq)
        return {
            "nom": f"Lot Modifié {n}",
        }

    def payload_activite(self):
        """Corps valide d'un POST d'activité sans montant."""
        n = next(_n_seq)
        return {
            "libelle": f"Activité {n}",
            "quantite_prevue": 10,
            "unite": "M2",
        }

    def payload_modification_activite(self):
        """Corps valide d'un PATCH d'activité sans montant."""
        n = next(_n_seq)
        return {
            "libelle": f"Activité Modifiée {n}",
        }
