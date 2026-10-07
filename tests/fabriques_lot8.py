"""Fabriques du lot 8 (collaborateurs, registre global, abonnement, lectures).

Construit sur les fabriques des lots 5, 6 et 7.
"""

import itertools
import sys
from pathlib import Path
from rest_framework.test import APIClient

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from django.db import connection
from django_tenants.utils import schema_context

from fabriques_lot5 import (
    API,
    HOST,
    _schema,
    client_pour,
    creer_role_personnalise,
    creer_utilisateur,
    obtenir_dg,
    role_systeme,
    suspendre_utilisateur,
    utilisateur_avec_role,
)
from fabriques_lot7 import FabriqueLot7, ClientLot7

_n_seq = itertools.count(8000)


class ClientLot8(ClientLot7):
    """Client de test API adapté pour le lot 8."""

    def force_authenticate(self, user=None, token=None):
        super().force_authenticate(user=user, token=token)
        if user is not None:
            self.credentials(HTTP_AUTHORIZATION=f"Bearer test_token_{user.id}")
        else:
            self.credentials()

    def _enrichir_reponse(self, response):
        if not hasattr(response, "data") and hasattr(response, "content") and response.content:
            try:
                import json
                response.data = json.loads(response.content.decode("utf-8"))
            except Exception:
                pass
        return response

    def get(self, *args, **kwargs):
        return self._enrichir_reponse(super().get(*args, **kwargs))

    def post(self, *args, **kwargs):
        return self._enrichir_reponse(super().post(*args, **kwargs))

    def put(self, *args, **kwargs):
        return self._enrichir_reponse(super().put(*args, **kwargs))

    def patch(self, *args, **kwargs):
        return self._enrichir_reponse(super().patch(*args, **kwargs))

    def delete(self, *args, **kwargs):
        return self._enrichir_reponse(super().delete(*args, **kwargs))


class FabriqueLot8(FabriqueLot7):
    """Contrat utilisé par les tests du lot 8."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._crees_par_fabrique = set()

    def client(self, utilisateur=None):
        c = ClientLot8(HTTP_HOST=HOST)
        if utilisateur is not None:
            c.force_authenticate(user=utilisateur)
        return c

    # ------------------------------------------------------------------ acteurs
    def utilisateur(self, role_code, *, actif=True):
        """Crée un utilisateur du tenant de test avec le rôle demandé.

        Prend en charge les rôles système ainsi que 'perso_entreprise' (rôle personnalisé
        vide à portée ENTREPRISE).
        """
        if role_code == "perso_entreprise":
            n = next(_n_seq)
            role_perso = creer_role_personnalise(
                code=f"PERSO_L8_{n}",
                portee="ENTREPRISE",
            )
            u = creer_utilisateur(role_perso)
            if not actif:
                suspendre_utilisateur(u)
        else:
            u = super().utilisateur(role_code, actif=actif)

        if u and getattr(u, "email", None) and not u.email.endswith("@depart.invalide"):
            self._crees_par_fabrique.add(u.email.strip().lower())
        return u

    # ------------------------------------------------------------------- routes
    def url_invitations(self):
        """Route d'invitation des collaborateurs."""
        return f"{API}/invitations/"

    def url_collaborateurs(self):
        """Route de liste/création des paramètres collaborateurs."""
        return f"{API}/parametres/collaborateurs/"

    def url_collaborateur(self, utilisateur):
        """Route de détail/modification/suppression d'un collaborateur."""
        return f"{API}/parametres/collaborateurs/{utilisateur.id}/"

    def url_factures(self):
        """Route de liste des factures."""
        return f"{API}/factures/"

    def url_facture(self, pk):
        """Route de détail d'une facture."""
        return f"{API}/factures/{pk}/"

    def url_facture_pdf(self, pk):
        """Route de téléchargement du PDF d'une facture."""
        return f"{API}/factures/{pk}/pdf/"

    def url_abonnement_notifications(self):
        """Route des alertes d'expiration d'abonnement."""
        return f"{API}/abonnement/notifications/"

    def url_cinetpay_initier(self):
        """Route d'initiation de paiement CinetPay."""
        return f"{API}/cinetpay/initier/"

    def url_cinetpay_statut(self, transaction_id):
        """Route de consultation de statut de paiement CinetPay."""
        return f"{API}/cinetpay/statut/{transaction_id}/"

    def url_modules(self):
        """Route de catalogue des modules."""
        return f"{API}/modules/"

    def url_entreprise(self):
        """Route d'informations de l'entreprise."""
        return f"{API}/entreprise/"

    def url_parametres_configuration(self):
        """Route de configuration entreprise."""
        return f"{API}/parametres/configuration/"

    def url_onboarding(self):
        """Route d'onboarding (configuration initiale)."""
        return f"{API}/configuration/"

    def url_onboarding_recapitulatif(self):
        """Route du récapitulatif onboarding."""
        return f"{API}/configuration/recapitulatif/"

    # ------------------------------------------------------------------ actions
    def corps_invitation(self, email, role_global=None, role_personnalise_id=None):
        """Construit le corps d'une requête d'invitation valide."""
        n = next(_n_seq)
        data = {
            "email": email,
            "nom": f"NomTest{n}",
            "prenom": f"PrenomTest{n}",
            "telephone": f"+225010203{n % 100:02d}",
        }
        if role_global is not None:
            data["role_global"] = role_global
        if role_personnalise_id is not None:
            data["role_personnalise_id"] = str(role_personnalise_id)
        return data

    def inviter(self, client, email, role_global, route=None):
        """Envoie une requête POST d'invitation/création de collaborateur."""
        if route is None:
            route = self.url_invitations()
        payload = self.corps_invitation(email, role_global=role_global)
        return client.post(route, payload, format="json")

    def se_connecter(self, email, mot_de_passe):
        """Exécute un appel POST vers /api/v1/auth/token/."""
        c = ClientLot7(HTTP_HOST=HOST)
        return c.post(
            f"{API}/auth/token/",
            {"email": email, "mot_de_passe": mot_de_passe},
            format="json",
        )

    # ----------------------------------------------------------- registre global
    def entreprise_fantome(self, nom):
        """Crée une entreprise dans le schéma public sans schéma réel (auto_create_schema=False)."""
        with schema_context("public"):
            from apps.tenants.models import Entreprise

            schema_clean = f"fantome_{nom.lower().replace(' ', '_')}"
            ent = Entreprise.objects.filter(schema_name=schema_clean).first()
            if ent is None:
                ent = Entreprise(
                    schema_name=schema_clean,
                    nom_commercial=nom,
                    raison_sociale=f"{nom} SARL",
                )
                ent.auto_create_schema = False
                ent.save()
            return ent

    def declarer_dans_registre(self, email, entreprise):
        """Insère un e-mail dans la table RegistreEmail (schéma public)."""
        clean_email = email.strip().lower()
        if clean_email in getattr(self, "_crees_par_fabrique", set()):
            self._crees_par_fabrique.discard(clean_email)
            with schema_context("public"):
                from apps.tenants.models import RegistreEmail
                reg = RegistreEmail.objects.filter(email=clean_email).first()
                if reg:
                    if reg.entreprise != entreprise:
                        reg.entreprise = entreprise
                        reg.save(update_fields=["entreprise"])
                    return reg

        with schema_context("public"):
            from apps.tenants.models import RegistreEmail
            return RegistreEmail.objects.create(
                email=clean_email,
                entreprise=entreprise,
            )

    def registre_ligne(self, email):
        """Recherche une ligne dans RegistreEmail (schéma public)."""
        with schema_context("public"):
            try:
                from apps.tenants.models import RegistreEmail
                return RegistreEmail.objects.filter(email__iexact=email.strip().lower()).first()
            except (ImportError, AttributeError):
                return None

    def supprimer_du_registre(self, email):
        """Supprime une ligne de RegistreEmail (schéma public)."""
        with schema_context("public"):
            try:
                from apps.tenants.models import RegistreEmail
                return RegistreEmail.objects.filter(email__iexact=email.strip().lower()).delete()
            except (ImportError, AttributeError):
                return (0, {})

    def nombre_dans_registre(self):
        """Compte les lignes dans RegistreEmail (schéma public)."""
        with schema_context("public"):
            try:
                from apps.tenants.models import RegistreEmail
                return RegistreEmail.objects.count()
            except (ImportError, AttributeError):
                return 0

    # ---------------------------------------------------- limites et abonnement
    def fixer_limites_plan(self, utilisateurs=None, projets=None):
        """Modifie les limites (utilisateurs, projets) du plan de l'entreprise de test."""
        limite_users_calculee = None
        if utilisateurs is not None:
            if utilisateurs == 0:
                limite_users_calculee = 0
            else:
                with _schema():
                    from apps.billing.services.quota import sieges_occupes
                    limite_users_calculee = sieges_occupes() + utilisateurs

        limite_projets_calculee = None
        if projets is not None:
            if projets == 0:
                limite_projets_calculee = 0
            else:
                with _schema():
                    from apps.projets.models import Projet
                    nb_vivants = Projet.objects.exclude(
                        statut__in=["RESILIE", "ARCHIVE", "DESACTIVE"]
                    ).count()
                    limite_projets_calculee = nb_vivants + projets

        with schema_context("public"):
            from apps.billing.models import Abonnement, Plan
            from apps.tenants.models import Entreprise

            entreprise = Entreprise.objects.get(schema_name="demo")
            abo = Abonnement.objects.filter(entreprise=entreprise).first()
            if abo and abo.plan:
                plan = abo.plan
                plan.limite_utilisateurs = limite_users_calculee
                plan.limite_projets = limite_projets_calculee
                plan.save(update_fields=["limite_utilisateurs", "limite_projets"])

    def expirer_abonnement(self):
        """Bascule l'abonnement du tenant en état suspendu / expiré."""
        with schema_context("public"):
            from django.utils import timezone
            from apps.billing.models import Abonnement
            from apps.tenants.models import Entreprise

            entreprise = Entreprise.objects.get(schema_name="demo")
            Abonnement.objects.filter(entreprise=entreprise).update(
                statut=Abonnement.Statut.SUSPENDU,
                lecture_seule_depuis=timezone.now(),
            )

    def restaurer_abonnement(self):
        """Rétablit l'abonnement du tenant en état actif / valide."""
        with schema_context("public"):
            from datetime import timedelta
            from django.utils import timezone
            from apps.billing.models import Abonnement
            from apps.tenants.models import Entreprise

            entreprise = Entreprise.objects.get(schema_name="demo")
            Abonnement.objects.filter(entreprise=entreprise).update(
                statut=Abonnement.Statut.ACTIF,
                lecture_seule_depuis=None,
                fin_essai=timezone.localdate() + timedelta(days=30),
            )

    def creer_facture(self):
        """Crée une facture valide pour l'entreprise demo dans le schéma public."""
        with schema_context("public"):
            from datetime import timedelta
            from django.utils import timezone
            from apps.billing.models import Abonnement, Facture
            from apps.tenants.models import Entreprise

            entreprise = Entreprise.objects.get(schema_name="demo")
            abo = Abonnement.objects.filter(entreprise=entreprise).first()
            n = next(_n_seq)
            return Facture.objects.create(
                numero=f"FAC-TEST-{n:04d}",
                entreprise=entreprise,
                abonnement=abo,
                periode_debut=timezone.localdate(),
                periode_fin=timezone.localdate(),
                date_emission=timezone.localdate(),
                date_echeance=timezone.localdate() + timedelta(days=30),
                montant_ht=5000000,
                taux_tva=18.0,
                montant_tva=900000,
                montant_ttc=5900000,
                statut=Facture.Statut.EMISE,
            )

    # ---------------------------------------------------- projets orphelins & CP
    def projet_avec_chef(self, utilisateur):
        """Crée un projet avec utilisateur comme chef de projet."""
        n = next(_n_seq)
        with _schema():
            from apps.projets.models import Projet

            return Projet.objects.create(
                nom=f"Projet CP {n}",
                reference=f"PRJ-CP-{n:04d}",
                ville="Abidjan",
                chef_projet=utilisateur,
                statut="EN_COURS",
            )

    def projet_avec_conducteur(self, utilisateur):
        """Crée un projet avec utilisateur comme conducteur de travaux."""
        n = next(_n_seq)
        with _schema():
            from apps.projets.models import Projet

            return Projet.objects.create(
                nom=f"Projet CT {n}",
                reference=f"PRJ-CT-{n:04d}",
                ville="Abidjan",
                conducteur_travaux=utilisateur,
                statut="EN_COURS",
            )

    # ------------------------------------------------------------------- divers
    def courriels_envoyes(self):
        """Renvoie les courriels interceptés dans outbox."""
        from django.core import mail

        return list(mail.outbox)

    def valider_transaction(self):
        """Exécute les rappels on_commit enregistrés."""
        from django.db import connection

        if hasattr(connection, "run_on_commit"):
            while connection.run_on_commit:
                cb = connection.run_on_commit.pop(0)
                if callable(cb):
                    cb()
                elif isinstance(cb, (tuple, list)) and len(cb) >= 2 and callable(cb[1]):
                    cb[1]()

    def enveloppe_quota_utilisateurs(self):
        """Relève l'enveloppe de refus de quota lors d'une invitation."""
        dg = self.utilisateur("DG")
        c = self.client(dg)
        self.fixer_limites_plan(utilisateurs=0)
        try:
            res = self.inviter(c, f"quota_probe_{next(_n_seq)}@test.ci", "VI", self.url_invitations())
            code_erreur = None
            if isinstance(res.data, dict):
                code_erreur = res.data.get("erreur", {}).get("code") or res.data.get("code")
            return {
                "status_code": res.status_code,
                "code": code_erreur,
                "data": res.data,
            }
        finally:
            self.fixer_limites_plan(utilisateurs=None)
