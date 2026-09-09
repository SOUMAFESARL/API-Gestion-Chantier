"""Crée l'entreprise de démonstration et son premier administrateur.

    python manage.py creer_tenant_demo

Idempotent : relancer la commande ne casse rien.
Accessible ensuite sur http://demo.localhost:8000/ — les navigateurs
résolvent `*.localhost` vers 127.0.0.1 sans toucher au fichier hosts.
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.core.enums import RoleGlobal, StatutEntreprise, StatutUtilisateur
from apps.tenants.models import Domaine, Entreprise

CODE_SCHEMA = "demo"
DOMAINE = "demo.localhost"

# Compte d'accès à l'admin Django, créé seulement avec `--acces-django`.
EMAIL_TECHNIQUE = "dev@demo.ci"
MOT_DE_PASSE_TECHNIQUE = "Dev1234!"


class Command(BaseCommand):
    help = "Crée l'entreprise de démonstration (schéma `demo`) et son administrateur."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@demo.ci")
        parser.add_argument("--motdepasse", default="Demo1234!")
        parser.add_argument(
            "--acces-django",
            action="store_true",
            help=(
                "Crée en plus un compte technique dev@demo.ci ayant accès à "
                "l'admin Django. Développement uniquement — voir l'encadré."
            ),
        )

    # Pas de `@transaction.atomic` ici — défaut **D-7**, règle R-65 de T-020.
    #
    # `TenantMixin.save()` rattrape un échec de `create_schema` par
    # `self.delete(force_drop=True)`, soit un `DROP SCHEMA` suivi d'un `DELETE`.
    # Si l'échec est une erreur de base — le cas courant, une migration qui
    # casse —, la transaction est déjà avortée : le rattrapage lève
    # `InFailedSqlTransaction`, et c'est cette exception-là qui remonte.
    # L'erreur d'origine, la seule qui dise ce qui n'a pas marché, est perdue.
    def handle(self, *args, **options):
        entreprise, cree = Entreprise.objects.get_or_create(
            schema_name=CODE_SCHEMA,
            defaults={
                "raison_sociale": "Entreprise de démonstration",
                "nom_commercial": "Démo BTP",
                "pays": "CI",
                "ville": "Abidjan",
                "email_contact": options["email"],
                "statut": StatutEntreprise.ESSAI,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"Entreprise {'créée' if cree else 'déjà présente'} : {entreprise}")
        )

        domaine, cree_domaine = Domaine.objects.get_or_create(
            domain=DOMAINE, defaults={"tenant": entreprise, "is_primary": True}
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Domaine {'créé' if cree_domaine else 'déjà présent'} : {domaine.domain}"
            )
        )

        # L'utilisateur vit dans le schéma du tenant, pas dans `public`.
        with schema_context(CODE_SCHEMA):
            from apps.accounts.models import Utilisateur

            utilisateur = Utilisateur.objects.filter(email=options["email"]).first()
            if utilisateur is None:
                # `create_user`, jamais `create_superuser` — règle R-64 de T-020.
                # `AD` est un **rôle métier**, pas un statut technique :
                # `is_superuser = True` court-circuite *toute* vérification de
                # permission Django, y compris celles que le RBAC refuse. Sur un
                # tenant de démonstration c'est sans conséquence ; sur un client,
                # la matrice de permissions deviendrait décorative.
                # **Directeur Général et Propriétaire**, comme un vrai premier
                # inscrit — `services/inscription.provisionner` fait exactement
                # cela. La démonstration servait un simple `AD` sans statut de
                # fondateur : l'immuabilité du propriétaire (T-S1-01) ne s'y
                # observait donc pas, et l'écran des rôles — réservé au DG —
                # restait inaccessible. *Un tenant de démonstration qui ne se
                # comporte pas comme un client ne démontre rien.*
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

            if options["acces_django"]:
                self._creer_compte_technique()

            self._creer_donnees_metier_demo(utilisateur)

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(f"  Ouvrir  http://{DOMAINE}:8000/api/health/"))
        if options["acces_django"]:
            self.stdout.write(self.style.WARNING(f"  Admin   http://{DOMAINE}:8000/admin/"))

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

        Le compte technique d'accès à l'admin Django n'est jamais concerné : il
        appartient à l'éditeur, pas à l'entreprise cliente.
        """
        if utilisateur.email == EMAIL_TECHNIQUE:
            return
        if utilisateur.is_owner and utilisateur.role_global == RoleGlobal.DIRECTEUR_GENERAL:
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

    def _creer_compte_technique(self) -> None:
        """Compte d'accès à l'admin Django — **développement uniquement**.

        Il est séparé de l'administrateur du client, et c'est tout l'intérêt :
        l'admin Django est l'outil de l'éditeur, pas celui de l'entreprise
        cliente. Les confondre donnait au client un accès inconditionnel à ses
        propres tables, RBAC compris.
        """
        from apps.accounts.models import Utilisateur

        if Utilisateur.objects.filter(email=EMAIL_TECHNIQUE).exists():
            self.stdout.write(f"Compte technique déjà présent : {EMAIL_TECHNIQUE}")
            return

        Utilisateur.objects.create_superuser(
            email=EMAIL_TECHNIQUE,
            password=MOT_DE_PASSE_TECHNIQUE,
            nom="Accès",
            prenom="Django",
            role_global=RoleGlobal.ADMIN,
            statut=StatutUtilisateur.ACTIF,
        )
        self.stdout.write(
            self.style.WARNING(
                f"Compte technique créé : {EMAIL_TECHNIQUE} — développement uniquement"
            )
        )

    def _creer_donnees_metier_demo(self, admin_user) -> None:
        """Peuple des données de chantiers, lots, rapports, bons de paiement et réceptions.

        Garantit que le tableau de bord affiche des métriques BTP réelles et vivantes
        (aucun bouchon ou valeur codée en dur).
        """
        from datetime import date
        from decimal import Decimal
        from django.utils import timezone

        from apps.achats.models import ReceptionMateriau
        from apps.chantier.models import RapportJournalier
        from apps.core.enums import (
            Meteo,
            ModeExecution,
            ModePaiement,
            RoleProjet,
            RoleTiersChoix,
            StatutBonPaiement,
            StatutProjet,
            StatutRapport,
            TypeTiers,
        )
        from apps.finance.models import BonPaiement
        from apps.projets.models import AffectationProjet, Lot, Projet
        from apps.tiers.models import RoleTiers, Tiers

        self.stdout.write("  Génération / vérification des données métier démo...")

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
        p1, _ = Projet.objects.get_or_create(
            reference="CHANT-2026-001",
            defaults={
                "nom": "Résidence Les Jardins d'Angré",
                "description": "Construction d'un complexe résidentiel de 12 villas duplex",
                "client": t_client1,
                "ville": "Abidjan",
                "quartier": "Cocody Angré 8ème Tranche",
                "budget_initial_montant": 185_000_000_00,  # 185 M FCFA
                "date_debut_prevue": date(2026, 1, 15),
                "date_fin_prevue": date(2026, 11, 30),
                "date_debut_reelle": date(2026, 1, 15),
                "chef_projet": admin_user,
                "statut": StatutProjet.EN_COURS,
                "avancement_reel": Decimal("68.00"),
                "avancement_theorique": Decimal("65.00"),
                "indice_sante": 85,
            },
        )
        AffectationProjet.objects.get_or_create(
            utilisateur=admin_user, projet=p1, defaults={"role_projet": RoleProjet.CHEF_PROJET}
        )

        p2, _ = Projet.objects.get_or_create(
            reference="CHANT-2026-002",
            defaults={
                "nom": "Immeuble R+5 Le Phare",
                "description": "Bâtiment administratif et commercial R+5 avec sous-sol",
                "client": t_client2,
                "ville": "San-Pédro",
                "quartier": "Zone Portuaire",
                "budget_initial_montant": 320_000_000_00,  # 320 M FCFA
                "date_debut_prevue": date(2026, 2, 1),
                "date_fin_prevue": date(2026, 12, 15),
                "date_debut_reelle": date(2026, 2, 10),
                "chef_projet": admin_user,
                "statut": StatutProjet.EN_COURS,
                "avancement_reel": Decimal("42.00"),
                "avancement_theorique": Decimal("40.00"),
                "indice_sante": 78,
            },
        )
        AffectationProjet.objects.get_or_create(
            utilisateur=admin_user, projet=p2, defaults={"role_projet": RoleProjet.CHEF_PROJET}
        )

        p3, _ = Projet.objects.get_or_create(
            reference="CHANT-2026-003",
            defaults={
                "nom": "Centre Commercial Riviera",
                "description": "Aménagement et réfection galeries marchandes",
                "client": t_client1,
                "ville": "Abidjan",
                "quartier": "Riviera Palmeraie",
                "budget_initial_montant": 95_000_000_00,  # 95 M FCFA
                "date_debut_prevue": date(2025, 10, 1),
                "date_fin_prevue": date(2026, 2, 28),  # Délai dépassé
                "date_debut_reelle": date(2025, 10, 5),
                "chef_projet": admin_user,
                "statut": StatutProjet.EN_RETARD,
                "avancement_reel": Decimal("82.00"),
                "avancement_theorique": Decimal("100.00"),
                "indice_sante": 45,
            },
        )
        AffectationProjet.objects.get_or_create(
            utilisateur=admin_user, projet=p3, defaults={"role_projet": RoleProjet.CHEF_PROJET}
        )

        # 3. Lots
        lot1_p1, _ = Lot.objects.get_or_create(
            projet=p1,
            code="LOT-01",
            defaults={
                "libelle": "Gros Œuvre & Fondations",
                "mode_execution": ModeExecution.SOUS_TRAITANCE_STRUCTUREE,
                "titulaire": t_tacheron1,
                "avancement": Decimal("68.00"),
            },
        )
        Lot.objects.get_or_create(
            projet=p1,
            code="LOT-02",
            defaults={
                "libelle": "Électricité & Courants faibles",
                "mode_execution": ModeExecution.REGIE,
                "avancement": Decimal("45.00"),
            },
        )

        lot1_p2, _ = Lot.objects.get_or_create(
            projet=p2,
            code="LOT-01",
            defaults={
                "libelle": "Terrassement & Voierie",
                "mode_execution": ModeExecution.REGIE,
                "avancement": Decimal("85.00"),
            },
        )
        Lot.objects.get_or_create(
            projet=p2,
            code="LOT-02",
            defaults={
                "libelle": "Second Œuvre & Carrelage",
                "mode_execution": ModeExecution.SOUS_TRAITANCE_INFORMELLE,
                "titulaire": t_tacheron2,
                "avancement": Decimal("30.00"),
            },
        )

        lot1_p3, _ = Lot.objects.get_or_create(
            projet=p3,
            code="LOT-01",
            defaults={
                "libelle": "Menuiserie & Façade Vitrée",
                "mode_execution": ModeExecution.SOUS_TRAITANCE_STRUCTUREE,
                "titulaire": t_tacheron1,
                "avancement": Decimal("82.00"),
            },
        )

        # 4. Rapports Journaliers du jour
        today = timezone.now().date()
        RapportJournalier.objects.get_or_create(
            projet=p1,
            date_rapport=today,
            defaults={
                "auteur": admin_user,
                "meteo": Meteo.ENSOLEILLE,
                "effectif_regie": 12,
                "effectif_tacherons": 20,
                "effectif_present": 32,
                "observations": "Coulage dalle niveau 2 terminé conformément au plan de ferraillage.",
                "blocages_critiques": 0,
                "statut": StatutRapport.APPROUVE,
            },
        )

        RapportJournalier.objects.get_or_create(
            projet=p2,
            date_rapport=today,
            defaults={
                "auteur": admin_user,
                "meteo": Meteo.PLUIE,
                "effectif_regie": 8,
                "effectif_tacherons": 14,
                "effectif_present": 22,
                "observations": "Arrêt temporaire des travaux de terrassement à 14h suite à fortes pluies.",
                "blocages_critiques": 1,
                "statut": StatutRapport.SOUMIS,
            },
        )

        RapportJournalier.objects.get_or_create(
            projet=p3,
            date_rapport=today,
            defaults={
                "auteur": admin_user,
                "meteo": Meteo.ENSOLEILLE,
                "effectif_regie": 4,
                "effectif_tacherons": 10,
                "effectif_present": 14,
                "observations": "Pose des huisseries extérieures en cours.",
                "blocages_critiques": 0,
                "statut": StatutRapport.SOUMIS,
            },
        )

        # 5. Bons de paiement (dont 3 en attente pour un total net de 8.4 M FCFA)
        BonPaiement.objects.get_or_create(
            numero="BDP-2026-001",
            defaults={
                "projet": p1,
                "lot": lot1_p1,
                "beneficiaire": t_tacheron1,
                "corps_etat": "Maçonnerie RDC & 1er étage",
                "montant_brut": 4_500_000_00,
                "deduction_avance": 500_000_00,
                "deduction_penalite": 0,
                "montant_net": 4_000_000_00,  # 4.0 M FCFA
                "statut": StatutBonPaiement.A_SIGNER,
                "mode_paiement": ModePaiement.VIREMENT,
            },
        )

        BonPaiement.objects.get_or_create(
            numero="BDP-2026-002",
            defaults={
                "projet": p2,
                "lot": lot1_p2,
                "beneficiaire": t_tacheron2,
                "corps_etat": "Passage des gaines techniques et coffrets",
                "montant_brut": 2_800_000_00,
                "deduction_avance": 0,
                "deduction_penalite": 0,
                "montant_net": 2_800_000_00,  # 2.8 M FCFA
                "statut": StatutBonPaiement.A_SIGNER,
                "mode_paiement": ModePaiement.CASH,
            },
        )

        BonPaiement.objects.get_or_create(
            numero="BDP-2026-003",
            defaults={
                "projet": p3,
                "lot": lot1_p3,
                "beneficiaire": t_tacheron1,
                "corps_etat": "Menuiserie alu RDC",
                "montant_brut": 1_600_000_00,
                "deduction_avance": 0,
                "deduction_penalite": 0,
                "montant_net": 1_600_000_00,  # 1.6 M FCFA
                "statut": StatutBonPaiement.A_SIGNER,
                "mode_paiement": ModePaiement.VIREMENT,
            },
        )

        BonPaiement.objects.get_or_create(
            numero="BDP-2026-000",
            defaults={
                "projet": p1,
                "lot": lot1_p1,
                "beneficiaire": t_tacheron1,
                "corps_etat": "Fouilles et semelles de fondation",
                "montant_brut": 5_000_000_00,
                "montant_net": 5_000_000_00,
                "statut": StatutBonPaiement.PAYE,
                "mode_paiement": ModePaiement.VIREMENT,
                "paye_le": timezone.now(),
            },
        )

        # 6. Réceptions de Matériaux
        ReceptionMateriau.objects.get_or_create(
            projet=p1,
            designation="400 sacs ciment CPJ 42.5 livrés & contrôlés",
            date_reception=today,
            defaults={
                "fournisseur": t_fourn1,
                "quantite": Decimal("400"),
                "unite": "Sacs",
                "conforme": True,
                "receptionne_par": admin_user,
            },
        )

        ReceptionMateriau.objects.get_or_create(
            projet=p2,
            designation="25 barres fer à béton HA 12 & HA 14",
            date_reception=today,
            defaults={
                "fournisseur": t_fourn2,
                "quantite": Decimal("25"),
                "unite": "Barres",
                "conforme": True,
                "receptionne_par": admin_user,
            },
        )

        ReceptionMateriau.objects.get_or_create(
            projet=p1,
            designation="12 m³ de sable lagunaire lavé",
            date_reception=today,
            defaults={
                "fournisseur": t_fourn1,
                "quantite": Decimal("12"),
                "unite": "m³",
                "conforme": True,
                "receptionne_par": admin_user,
            },
        )

        self.stdout.write(self.style.SUCCESS("  Données métier démo initialisées avec succès."))
