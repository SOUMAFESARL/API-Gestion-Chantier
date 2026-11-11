"""Crée une entreprise de démonstration et son premier administrateur.

    python manage.py creer_entreprise_demo                       # entreprise `demo`, admin@demo.ci
    python manage.py creer_entreprise_demo --entreprise beta     # entreprise `beta`, admin@beta.ci

Idempotent : relancer la commande ne casse rien. Les adresses prennent le domaine de
l'entreprise (`@<slug>.ci`) : l'adresse est unique sur toute la plateforme (D9), et la suite
d'étanchéité a besoin de deux entreprises peuplées dans la même base.
"""

from django.core.management.base import BaseCommand

from apps.core.contexte import contexte_entreprise
from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.entreprises.models import Entreprise

SLUG_PAR_DEFAUT = "demo"


class Command(BaseCommand):
    help = "Crée une entreprise de démonstration (`demo` par défaut) et son administrateur."

    def add_arguments(self, parser):
        parser.add_argument("--entreprise", default=SLUG_PAR_DEFAUT, help="Slug de l'entreprise.")
        parser.add_argument("--email", default=None, help="Par défaut : admin@<slug>.ci.")
        parser.add_argument("--motdepasse", default="Demo1234!")

    def handle(self, *args, **options):
        slug = options["entreprise"]
        self.slug = slug
        options["email"] = options["email"] or f"admin@{slug}.ci"
        entreprise = Entreprise.objects.filter(slug=slug).first()
        cree = entreprise is None
        if cree:
            entreprise = Entreprise.objects.create(
                slug=slug,
                raison_sociale="Entreprise de démonstration"
                + ("" if slug == SLUG_PAR_DEFAUT else f" {slug.capitalize()}"),
                nom_commercial="Démo BTP"
                if slug == SLUG_PAR_DEFAUT
                else f"{slug.capitalize()} BTP",
                pays="CI",
                ville="Abidjan",
                email_contact=options["email"],
                statut=StatutEntreprise.ESSAI,
            )
        self.stdout.write(
            self.style.SUCCESS(f"Entreprise {'créée' if cree else 'déjà présente'} : {entreprise}")
        )

        # Les comptes et les données de démonstration appartiennent à l'entreprise (D9, R-8).
        with contexte_entreprise(entreprise):
            from apps.accounts.models import Utilisateur
            from apps.accounts.services.roles import initialiser_roles_par_defaut

            # Les rôles avant le fondateur : `Utilisateur.save` ne rattache le rôle `DG` que
            # s'il existe déjà (même ordre que `services/inscription.activer`).
            initialiser_roles_par_defaut()
            from apps.projets.services.reprogrammation import initialiser_motifs_report_par_defaut

            initialiser_motifs_report_par_defaut()
            utilisateur = Utilisateur.objects.filter(email=options["email"]).first()
            if utilisateur is None:
                # `create_user`, jamais `create_superuser` — règle R-64 de T-020.
                # `AD` est un **rôle métier**, pas un statut technique :
                # `is_superuser = True` court-circuite *toute* vérification de
                # permission Django, y compris celles que le RBAC refuse. Sur une
                # entreprise de démonstration c'est sans conséquence ; sur un client,
                # la matrice de permissions deviendrait décorative.
                # **Directeur Général et Propriétaire**, comme un vrai premier
                # inscrit — `services/inscription.provisionner` fait exactement
                # cela. La démonstration servait un simple `AD` sans statut de
                # fondateur : l'immuabilité du propriétaire (T-S1-01) ne s'y
                # observait donc pas, et l'écran des rôles — réservé au DG —
                # restait inaccessible. *Une démonstration qui ne se comporte
                # pas comme un client ne démontre rien.*
                utilisateur = Utilisateur.objects.create_user(
                    email=options["email"],
                    password=options["motdepasse"],
                    nom="Administrateur",
                    prenom="Démo",
                    role_global=RoleGlobal.DIRECTEUR_GENERAL,
                    statut=StatutUtilisateur.ACTIF,
                )
                utilisateur.is_owner = True
                utilisateur.save(update_fields=["is_owner", "modifie_le"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Directeur Général et propriétaire créé : {utilisateur.email}"
                    )
                )
            else:
                self.stdout.write(f"Administrateur déjà présent : {utilisateur.email}")
                self._retirer_privileges_techniques(utilisateur)
                self._promouvoir_fondateur(utilisateur)

            self._creer_donnees_metier_demo(options["motdepasse"])

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(f"  Connexion  {options['email']} sur http://localhost:3000/")
        )

    def _retirer_privileges_techniques(self, utilisateur) -> None:
        """Répare un administrateur créé avant la correction de **R-64**.

        Une commande idempotente ne se contente pas de ne rien casser quand on
        la rejoue : elle **converge vers l'état spécifié**. Sans cela, la
        correction ne vaudrait que pour les installations neuves, et les bases
        de développement existantes garderaient un `is_superuser` que plus
        personne ne penserait à retirer.
        """
        if not (utilisateur.is_staff or utilisateur.is_superuser):
            return

        utilisateur.is_staff = False
        utilisateur.is_superuser = False
        utilisateur.save(update_fields=["is_staff", "is_superuser", "modifie_le"])
        self.stdout.write(
            self.style.WARNING(
                "  privilèges techniques retirés — R-64 : `AD` est un rôle "
                "métier, pas un statut technique"
            )
        )

    def _promouvoir_fondateur(self, utilisateur) -> None:
        """Répare une démonstration créée avant que le fondateur soit posé.

        Même doctrine que `_retirer_privileges_techniques` : une commande
        idempotente **converge vers l'état spécifié** au lieu de se contenter de
        ne rien casser. Sans cela, la correction ne vaudrait que pour les bases
        neuves, et les démonstrations existantes garderaient un administrateur
        que rien ne protège — celui-là même sur lequel on veut vérifier que la
        protection existe.
        """
        if utilisateur.is_owner and utilisateur.role_global == RoleGlobal.DIRECTEUR_GENERAL:
            if utilisateur.role_id is None:
                # Démonstration montée avant la correction du lot 7 : `save` rattache le rôle.
                utilisateur.save(update_fields=["role", "role_global", "modifie_le"])
                self.stdout.write(self.style.WARNING("  rôle DG rattaché au fondateur"))
            return

        utilisateur.role_global = RoleGlobal.DIRECTEUR_GENERAL
        utilisateur.is_owner = True
        utilisateur.save(update_fields=["role_global", "is_owner", "modifie_le"])
        self.stdout.write(
            self.style.WARNING(
                "  promu Directeur Général et propriétaire — la démonstration se "
                "comporte désormais comme un vrai premier inscrit"
            )
        )

    def _collaborateur_demo(self, email, nom, prenom, role_global, mot_de_passe):
        """Un collaborateur de démonstration, créé une fois et laissé tel quel ensuite."""
        from apps.accounts.models import Role, Utilisateur

        utilisateur = Utilisateur.objects.filter(email=email).first()
        if utilisateur is None:
            utilisateur = Utilisateur.objects.create_user(
                email=email,
                password=mot_de_passe,
                nom=nom,
                prenom=prenom,
                role=Role.objects.filter(code=role_global).first(),
                role_global=role_global,
                statut=StatutUtilisateur.ACTIF,
            )
            self.stdout.write(self.style.SUCCESS(f"  Collaborateur créé : {email}"))
        return utilisateur

    def _remettre_en_conformite(self, projet, debut, fin) -> None:
        """Aligne un chantier de démonstration sur la règle : pas de suivi sans découpage.

        Une commande idempotente converge vers l'état spécifié au lieu de se contenter de ne rien
        casser : les bases montées avant la règle portaient des chantiers « En cours » à 68 % ou
        42 % **sans aucun découpage**, avec un rapport de l'ancien modèle — la fiche annonçait un
        avancement que l'onglet « Avancement » ne pouvait pas expliquer.

        - **Jamais démarré** (aucun journal : un chantier ne passe « En cours » qu'avec un rapport
          soumis) : « En attente », sans avancement ni santé, début réel effacé, dates devant soi
          (`debut` et `fin`) si les siennes sont passées. Ses rapports de l'ancien modèle (sans
          journal) sont retirés.
        - **Avec découpage** : on ne touche pas à l'arbre ; les valeurs dérivées (avancement,
          théorique, santé, statut) sont recalculées par l'application, qui les écrit à partir de
          l'arbre au lieu de garder celles saisies à la main.
        """
        from django.db import transaction
        from django.utils import timezone

        from apps.chantier.models import JournalChantier, RapportJournalier
        from apps.core.enums import StatutProjet
        from apps.projets.models import Element
        from apps.projets.services.avancement import recalculer_apres_quantites

        retires = (
            RapportJournalier.tous_objets.filter(projet=projet, supprime_le__isnull=True)
            .exclude(pk__in=JournalChantier.objects.values("rapport_id"))
            .update(supprime_le=timezone.now())
        )

        decoupe = Element.objects.filter(projet=projet).exists()
        demarre = JournalChantier.objects.filter(rapport__projet=projet).exists()
        if not demarre:
            champs = {
                "statut": StatutProjet.EN_ATTENTE,
                "avancement_reel": 0,
                "avancement_theorique": 0,
                "indice_sante": None,
                "date_debut_reelle": None,
            }
            if projet.date_debut_prevue is None or projet.date_debut_prevue < timezone.localdate():
                champs |= {"date_debut_prevue": debut, "date_fin_prevue": fin}
            if retires or any(getattr(projet, nom) != valeur for nom, valeur in champs.items()):
                for nom, valeur in champs.items():
                    setattr(projet, nom, valeur)
                projet.save(update_fields=[*champs, "modifie_le"])
                self.stdout.write(
                    self.style.WARNING(
                        f"  {projet.reference} : jamais démarré — remis « En attente », sans "
                        f"avancement ni santé ({retires} rapport(s) de l'ancien modèle retiré(s))"
                    )
                )
        if decoupe:
            with transaction.atomic():
                recalculer_apres_quantites([], projet=projet, declencheur_type="JEU_DE_DEMO")
            projet.refresh_from_db()
            self.stdout.write(
                f"  {projet.reference} : découpage présent — statut {projet.statut}, "
                f"avancement {projet.avancement_reel} %, santé {projet.indice_sante}"
            )

    def _creer_donnees_metier_demo(self, mot_de_passe) -> None:
        """Peuple des données de chantiers, lots, rapports, bons de paiement et réceptions.

        Garantit que le tableau de bord affiche des métriques BTP réelles et vivantes
        (aucun bouchon ou valeur codée en dur).

        **Le DG ne tient aucune fonction sur les chantiers** (décision du
        14/10/2026) : un chef de projet et un chef de chantier de démonstration
        les tiennent à sa place. Ils se connectent avec le même mot de passe.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.core.enums import (
            RoleProjet,
            RoleTiersChoix,
            StatutProjet,
            TypeTiers,
        )
        from apps.projets.models import AffectationProjet, Projet
        from apps.tiers.models import RoleTiers, Tiers

        self.stdout.write("  Génération / vérification des données métier démo...")

        from apps.accounts.services.roles import initialiser_roles_par_defaut

        initialiser_roles_par_defaut()
        chef_projet = self._collaborateur_demo(
            f"cp@{self.slug}.ci", "Kouamé", "Djatchi", RoleGlobal.CHEF_PROJET, mot_de_passe
        )
        chef_chantier = self._collaborateur_demo(
            f"cc@{self.slug}.ci", "Sidibé", "Gbané", RoleGlobal.CHEF_CHANTIER, mot_de_passe
        )

        # 1. Tiers
        t_client1, _ = Tiers.objects.get_or_create(
            raison_sociale="SCI Les Palmiers",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+22507000001",
                "email": "contact@palmiers-ci.com",
                "ville": "Abidjan",
                "adresse": "Cocody Ambassades",
            },
        )
        RoleTiers.objects.get_or_create(tiers=t_client1, role=RoleTiersChoix.CLIENT_MOA)

        t_client2, _ = Tiers.objects.get_or_create(
            raison_sociale="Groupe Immobilier Ivoire",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+22507000002",
                "email": "direction@immo-ivoire.ci",
                "ville": "San-Pédro",
                "adresse": "Zone Industrielle",
            },
        )
        RoleTiers.objects.get_or_create(tiers=t_client2, role=RoleTiersChoix.CLIENT_MOA)

        t_tacheron1, _ = Tiers.objects.get_or_create(
            raison_sociale="Kouamé Bâtiment SARL",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+22505000010",
                "email": "kouame.bat@gmail.com",
                "ville": "Abidjan",
            },
        )
        RoleTiers.objects.get_or_create(tiers=t_tacheron1, role=RoleTiersChoix.TACHERON)

        t_tacheron2, _ = Tiers.objects.get_or_create(
            raison_sociale="Diallo Électricité & Plomberie",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+22505000020",
                "email": "diallo.ep@gmail.com",
                "ville": "Abidjan",
            },
        )
        RoleTiers.objects.get_or_create(tiers=t_tacheron2, role=RoleTiersChoix.TACHERON)

        t_fourn1, _ = Tiers.objects.get_or_create(
            raison_sociale="Sococim Ciments CI",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+22521000030",
                "email": "ventes@sococim.ci",
                "ville": "Abidjan",
            },
        )
        RoleTiers.objects.get_or_create(tiers=t_fourn1, role=RoleTiersChoix.FOURNISSEUR)

        t_fourn2, _ = Tiers.objects.get_or_create(
            raison_sociale="SOTICI Tuyaux & Aciers",
            defaults={
                "type_tiers": TypeTiers.ENTREPRISE,
                "telephone": "+22521000040",
                "email": "commandes@sotici.ci",
                "ville": "Abidjan",
            },
        )
        RoleTiers.objects.get_or_create(tiers=t_fourn2, role=RoleTiersChoix.FOURNISSEUR)

        # 2. Projets
        #
        # Trois chantiers **à découper** : en attente, sans avancement, sans santé, sans rapport.
        # Le suivi d'avancement naît du découpage — l'arbre du projet — et le découpage ne
        # s'applique qu'une fois le tableau de démarrage validé, depuis l'onglet « Découpage » :
        # le parcours de démonstration commence donc là, comme celui d'un vrai chantier. Aucune
        # valeur d'avancement, de santé ou de statut n'est écrite à la main ici (le jeu
        # `peupler_donnees_test` donne, lui, des chantiers déjà suivis, calculés par l'application).
        # Les dates se prennent à partir d'aujourd'hui pour que la démonstration ne vieillisse pas.
        aujourdhui = timezone.localdate()
        p1, cree_p1 = Projet.objects.get_or_create(
            reference="CHANT-2026-001",
            defaults={
                "nom": "Résidence Les Jardins d'Angré",
                "description": "Construction d'un complexe résidentiel de 12 villas duplex",
                "client": t_client1,
                "ville": "Abidjan",
                "quartier": "Cocody Angré 8ème Tranche",
                "budget_initial_montant": 185_000_000_00,  # 185 M FCFA
                "date_debut_prevue": aujourdhui + timedelta(days=14),
                "date_fin_prevue": aujourdhui + timedelta(days=14 + 320),
                "chef_projet": chef_projet,
                "statut": StatutProjet.EN_ATTENTE,
            },
        )

        p2, cree_p2 = Projet.objects.get_or_create(
            reference="CHANT-2026-002",
            defaults={
                "nom": "Immeuble R+5 Le Phare",
                "description": "Bâtiment administratif et commercial R+5 avec sous-sol",
                "client": t_client2,
                "ville": "San-Pédro",
                "quartier": "Zone Portuaire",
                "budget_initial_montant": 320_000_000_00,  # 320 M FCFA
                "date_debut_prevue": aujourdhui + timedelta(days=21),
                "date_fin_prevue": aujourdhui + timedelta(days=21 + 300),
                "chef_projet": chef_projet,
                "statut": StatutProjet.EN_ATTENTE,
            },
        )

        p3, cree_p3 = Projet.objects.get_or_create(
            reference="CHANT-2026-003",
            defaults={
                "nom": "Centre Commercial Riviera",
                "description": "Aménagement et réfection galeries marchandes",
                "client": t_client1,
                "ville": "Abidjan",
                "quartier": "Riviera Palmeraie",
                "budget_initial_montant": 95_000_000_00,  # 95 M FCFA
                "date_debut_prevue": aujourdhui + timedelta(days=30),
                "date_fin_prevue": aujourdhui + timedelta(days=30 + 150),
                "chef_projet": chef_projet,
                "statut": StatutProjet.EN_ATTENTE,
            },
        )

        # L'encadrement d'un chantier neuf. Un chantier déjà présent garde le sien :
        # `retirer_dg_des_chantiers` remet en conformité les données antérieures.
        for projet, cree in ((p1, cree_p1), (p2, cree_p2), (p3, cree_p3)):
            if cree:
                AffectationProjet.objects.create(
                    utilisateur=chef_projet, projet=projet, role_projet=RoleProjet.CHEF_PROJET
                )
                AffectationProjet.objects.create(
                    utilisateur=chef_chantier, projet=projet, role_projet=RoleProjet.CHEF_CHANTIER
                )

        # 3. Une démonstration montée avant cette règle converge vers l'état spécifié.
        for projet, jours, duree in ((p1, 14, 320), (p2, 21, 300), (p3, 30, 150)):
            debut = aujourdhui + timedelta(days=jours)
            self._remettre_en_conformite(projet, debut, debut + timedelta(days=duree))

        self.stdout.write(self.style.SUCCESS("  Données métier démo initialisées avec succès."))
