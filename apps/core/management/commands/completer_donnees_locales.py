"""Complète la base locale pour tester l'application de bout en bout, rôle par rôle.

    python manage.py completer_donnees_locales                       # `demo` et `beta`
    python manage.py completer_donnees_locales --entreprise demo

**Développement uniquement** (refusé quand `DEBUG` est faux). À lancer après
`creer_entreprise_demo` et `peupler_donnees_test`, qui fournissent les chantiers, les rapports et
l'avancement ; `monter_base --demo` l'enchaîne.

Ce que cette commande ajoute, et que ces deux-là ne créent pas :

- **le personnel de l'éditeur** : un SUPERVISEUR (lecture et écriture) et un agent SUPPORT
  (lecture seule), sans entreprise — sans eux, le back-office est inatteignable ;
- **un compte pour chacun des dix rôles du socle** (DG, AD, DO, DF, CP, CT, CC, MAG, BAI, VI) :
  `peupler_donnees_test` n'en créait que six ; AD, DO, MAG et BAI manquaient ;
- **de quoi remplir les écrans qui restaient vides** : téléphones de l'entreprise, invitation en
  attente, avenants, contrat, dépendances entre tâches, exceptions de calendrier, synthèse
  hebdomadaire, liste de valeurs et types de projet propres à l'entreprise, abonnement d'essai,
  factures et paiement, demandes d'inscription à valider.

Idempotente : chaque ligne est cherchée avant d'être créée ; relancer la commande ne duplique rien.
Une section qui échoue est signalée et n'empêche pas les suivantes ; la commande se termine alors
en erreur, pour que l'échec ne passe pas inaperçu.

Les mots de passe sont ceux de `--motdepasse` (le même que `peupler_donnees_test`).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.contexte import contexte_entreprise, portee_plateforme

def pdf_minimal() -> bytes:
    """Un PDF d'une page blanche, assez valide pour passer `valider_fichier_contrat`."""
    import io

    from pypdf import PdfWriter

    ecrivain = PdfWriter()
    ecrivain.add_blank_page(width=210, height=297)
    tampon = io.BytesIO()
    ecrivain.write(tampon)
    return tampon.getvalue()


# (adresse, prénom, nom, code du rôle, téléphone). Le domaine devient `@<slug>.ci`.
COMPTES_DU_SOCLE = [
    ("ad.sylla@demo.ci", "Aïssatou", "Sylla", "AD", "+2250701020321"),
    ("do.diallo@demo.ci", "Mamadou", "Diallo", "DO", "+2250701020322"),
    ("mag.camara@demo.ci", "Sékou", "Camara", "MAG", "+2250701020323"),
    ("bai.fofana@demo.ci", "Salimata", "Fofana", "BAI", "+2250701020324"),
]
# Rôles de portée Projet à affecter : (adresse, rôle), sur les deux premiers chantiers de test.
AFFECTATIONS = [("mag.camara@demo.ci", "MAG"), ("bai.fofana@demo.ci", "BAI")]

PERSONNEL_EDITEUR = [
    # (adresse, prénom, nom, superviseur ?)
    ("test.superviseur@ccd-digital.ci", "Superviseur", "CCD Digital", True),
    ("test.support@ccd-digital.ci", "Support", "CCD Digital", False),
]


def adresse(cle: str, slug: str) -> str:
    return cle.replace("@demo.ci", f"@{slug}.ci")


class Command(BaseCommand):
    help = "Complète la base locale : comptes de chaque rôle, back-office, écrans restés vides."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entreprise",
            nargs="*",
            default=["demo", "beta"],
            help="Slugs à compléter (défaut : demo beta).",
        )
        parser.add_argument("--motdepasse", default="Demo1234!")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Réservé au développement : refusé quand DEBUG est faux.")
        self.motdepasse = options["motdepasse"]
        self.echecs: list[str] = []

        self._section("Personnel de l'éditeur", self._personnel_editeur)
        self._section("Demandes d'inscription à valider", self._demandes_inscription)

        from apps.entreprises.models import Entreprise

        for slug in options["entreprise"]:
            with portee_plateforme(motif=f"completer_donnees_locales : {slug}"):
                entreprise = Entreprise.objects.filter(slug=slug).first()
            if entreprise is None:
                raise CommandError(f"Aucune entreprise « {slug} » : lancez creer_entreprise_demo.")
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n— Entreprise « {slug} »"))
            self.entreprise, self.slug = entreprise, slug
            with contexte_entreprise(entreprise):
                self._section("Abonnement d'essai", self._abonnement)
                self._section("Comptes des rôles manquants", self._comptes_du_socle)
                self._section("Affectations MAG et BAI", self._affectations)
                self._section("Téléphones de l'entreprise", self._telephones)
                self._section("Invitation en attente", self._invitation)
                self._section("Types de projet et liste de l'entreprise", self._referentiels)
                self._section("Exceptions de calendrier", self._exceptions_calendrier)
                self._section("Avenants et contrat", self._avenants_et_contrat)
                self._section("Dépendances entre tâches", self._dependances)
                self._section("Synthèse hebdomadaire", self._synthese)
            self._section("Factures et paiement", self._factures)

        self.stdout.write("")
        if self.echecs:
            for echec in self.echecs:
                self.stderr.write(self.style.ERROR(f"  ÉCHEC {echec}"))
            raise CommandError(f"{len(self.echecs)} section(s) en échec.")
        self.stdout.write(self.style.SUCCESS("Base locale complétée."))

    # ------------------------------------------------------------------ outils
    def _section(self, titre, fonction):
        try:
            with transaction.atomic():
                resultat = fonction()
            self.stdout.write(f"  {titre} : {resultat or 'ok'}")
        except Exception as exc:  # noqa: BLE001 — outil de développement : on continue et on signale
            self.echecs.append(f"{getattr(self, 'slug', 'plateforme')} / {titre} : {exc!r}")
            self.stderr.write(self.style.ERROR(f"  {titre} : ÉCHEC {exc!r}"))

    def _projet(self, reference):
        from apps.projets.models import Projet

        return Projet.objects.filter(reference=reference).first()

    def _dg(self):
        from apps.accounts.models import Utilisateur

        return Utilisateur.objects.filter(is_owner=True).first()

    # ------------------------------------------------------------- plateforme
    def _personnel_editeur(self):
        from apps.accounts.models import Utilisateur
        from apps.core.enums import RoleGlobal, StatutUtilisateur

        crees = 0
        with portee_plateforme(motif="completer_donnees_locales : personnel de l'éditeur"):
            for email, prenom, nom, superviseur in PERSONNEL_EDITEUR:
                if Utilisateur.objects.filter(email__iexact=email).exists():
                    continue
                Utilisateur.objects.create_user(
                    email=email,
                    password=self.motdepasse,
                    nom=nom,
                    prenom=prenom,
                    role_global=RoleGlobal.ADMIN,
                    statut=StatutUtilisateur.ACTIF,
                    is_staff=True,
                    is_superuser=superviseur,
                )
                crees += 1
        return f"{crees} créé(s)"

    def _demandes_inscription(self):
        from apps.entreprises.models import DemandeInscription

        maintenant = timezone.now()
        lot = [
            ("Bâtiments du Nord SARL", "direction@batiments-nord.ci", "batiments_du_nord_sarl"),
            ("Sahel Travaux Publics", "direction@sahel-tp.sn", "sahel_travaux_publics"),
        ]
        crees = 0
        with portee_plateforme(motif="completer_donnees_locales : demandes d'inscription"):
            for raison, email, slug in lot:
                if DemandeInscription.objects.filter(email=email).exists():
                    continue
                DemandeInscription.objects.create(
                    raison_sociale=raison,
                    pays="SN" if email.endswith(".sn") else "CI",
                    email=email,
                    slug_reserve=slug,
                    empreinte=DemandeInscription.empreinte_de(uuid.uuid4()),
                    expire_le=maintenant + timedelta(days=2),
                    cgu_version="2026-09",
                    cgu_acceptees_le=maintenant,
                )
                crees += 1
        return f"{crees} créée(s)"

    # ------------------------------------------------------------- entreprise
    def _abonnement(self):
        from apps.billing.models import Abonnement, Plan

        if Abonnement.objects.filter(entreprise=self.entreprise).exists():
            return "déjà présent"
        plan = Plan.objects.filter(code="MAITRE_OEUVRE").first() or Plan.objects.first()
        debut = timezone.localdate()
        fin = debut + timedelta(days=14)
        Abonnement.objects.create(
            entreprise=self.entreprise,
            plan=plan,
            statut=Abonnement.Statut.ESSAI,
            date_debut=debut,
            date_fin=fin,
            fin_essai=fin,
            renouvellement_auto=False,
        )
        return "créé (essai de 14 jours)"

    def _comptes_du_socle(self):
        from apps.accounts.models import Role, Utilisateur
        from apps.core.enums import StatutUtilisateur

        crees = 0
        for cle, prenom, nom, code, telephone in COMPTES_DU_SOCLE:
            email = adresse(cle, self.slug)
            if Utilisateur.objects.filter(email=email).exists():
                continue
            role = Role.objects.get(code=code, supprime_le__isnull=True)
            Utilisateur.objects.create_user(
                email=email,
                password=self.motdepasse,
                nom=nom,
                prenom=prenom,
                telephone=telephone,
                role=role,
                role_global=code,
                statut=StatutUtilisateur.ACTIF,
            )
            crees += 1
        return f"{crees} créé(s)"

    def _affectations(self):
        from apps.accounts.models import Utilisateur
        from apps.projets.models import AffectationProjet
        from apps.projets.services.affectations import affecter_collaborateur_projet

        chef = Utilisateur.objects.filter(email=adresse("cp.kone@demo.ci", self.slug)).first()
        faits = 0
        for reference in ("TEST-2026-002", "TEST-2026-003"):
            projet = self._projet(reference)
            if projet is None:
                continue
            for cle, role in AFFECTATIONS:
                utilisateur = Utilisateur.objects.get(email=adresse(cle, self.slug))
                if AffectationProjet.objects.filter(
                    projet=projet, utilisateur=utilisateur, est_actif=True
                ).exists():
                    continue
                affecter_collaborateur_projet(
                    projet=projet,
                    utilisateur=utilisateur,
                    role_projet=role,
                    date_debut=timezone.localdate() - timedelta(days=10),
                    fonction_membre="",
                    perimetres_ids=None,
                    modifie_par=chef,
                )
                faits += 1
        return f"{faits} affectation(s)"

    def _telephones(self):
        from apps.entreprises.models import TelephoneEntreprise

        if TelephoneEntreprise.objects.filter(entreprise=self.entreprise).exists():
            return "déjà présents"
        lot = [
            (TelephoneEntreprise.Libelle.FIXE, "Siège du Plateau", "+22527213344", True),
            (TelephoneEntreprise.Libelle.MOBILE, "Responsable QSE", "+2250512345678", False),
        ]
        for ordre, (libelle, nom, numero, principal) in enumerate(lot):
            TelephoneEntreprise.objects.create(
                entreprise=self.entreprise,
                libelle=libelle,
                nom=nom,
                numero=numero,
                est_principal=principal,
                ordre=ordre,
            )
        return f"{len(lot)} créé(s)"

    def _invitation(self):
        from apps.accounts.models import Invitation
        from apps.accounts.services.invitations import creer_invitation

        email = f"kader.zoungrana@{self.slug}.ci"
        if Invitation.objects.filter(email=email).exists():
            return "déjà présente"
        creer_invitation(
            email=email,
            role_propose="CT",
            nom="Kader Zoungrana",
            emetteur=self._dg(),
            verifier_quota=False,
        )
        return f"créée pour {email}"

    def _referentiels(self):
        from apps.projets.models import ListeValeursEntreprise, ReferentielEntreprise
        from apps.projets.services import listes_modeles as lm

        faits = 0
        for categorie, code, libelle, groupe in [
            ("TYPE_PROJET", "CENTRE_SANTE", "Centre de santé communautaire", ""),
            ("LOT", "DESENFUMAGE", "Désenfumage et sécurité incendie", "Lots techniques"),
        ]:
            _, cree = ReferentielEntreprise.objects.get_or_create(
                categorie=categorie,
                code=code,
                defaults={"libelle": libelle, "groupe": groupe},
            )
            faits += cree
        if not ListeValeursEntreprise.objects.filter(libelle="Matériaux de gros œuvre").exists():
            lm.creer_liste(
                "Matériaux de gros œuvre",
                "Liste de l'entreprise, pour les essais de saisie.",
                ["Ciment CPJ 42,5", "Acier HA 12", "Sable lagunaire", "Gravier 15/25"],
            )
            faits += 1
        return f"{faits} créé(s)"

    def _exceptions_calendrier(self):
        from apps.projets.models import ExceptionCalendrier

        aujourdhui = timezone.localdate()
        faits = 0
        for decalage, ouvre, motif in [
            (21, False, "Fermeture de l'entreprise — inventaire annuel"),
            (28, True, "Samedi travaillé pour rattraper un retard de coulage"),
        ]:
            jour = aujourdhui + timedelta(days=decalage)
            _, cree = ExceptionCalendrier.objects.get_or_create(
                date=jour, defaults={"ouvre": ouvre, "motif": motif}
            )
            faits += cree
        return f"{faits} créée(s)"

    def _avenants_et_contrat(self):
        from apps.projets.models import Avenant, ProjetContrat
        from apps.projets.services.avenants import enregistrer_avenant

        projet = self._projet("TEST-2026-002")
        if projet is None:
            return "chantier TEST-2026-002 absent"
        faits = 0
        if not Avenant.objects.filter(projet=projet).exists():
            for numero, objet, jours, montant in [
                ("AV-001", "Travaux supplémentaires de terrassement", 12, 8_500_000),
                ("AV-002", "Prolongation pour intempéries exceptionnelles", 20, None),
            ]:
                enregistrer_avenant(
                    projet,
                    numero=numero,
                    date_signature=timezone.localdate() - timedelta(days=15),
                    objet=objet,
                    jours_accordes=jours,
                    montant=montant,
                    document=ContentFile(pdf_minimal(), name=f"{numero}.pdf"),
                    auteur=self._dg(),
                )
                faits += 1
        if not ProjetContrat.objects.filter(projet=projet).exists():
            contenu = pdf_minimal()
            ProjetContrat.objects.create(
                projet=projet,
                nom="Contrat de marché.pdf",
                taille=len(contenu),
                type_contenu="application/pdf",
                fichier=ContentFile(contenu, name="contrat-marche.pdf"),
            )
            faits += 1
        return f"{faits} créé(s)"

    def _dependances(self):
        from apps.projets.models import Dependance, Element

        projet = self._projet("TEST-2026-002")
        if projet is None:
            return "chantier TEST-2026-002 absent"
        if Dependance.objects.filter(projet=projet).exists():
            return "déjà présentes"
        feuilles = list(
            Element.objects.filter(projet=projet, est_actif=True, enfants__isnull=True).order_by(
                "ordre", "cree_le"
            )[:6]
        )
        faits = 0
        for pred, succ in zip(feuilles, feuilles[1:]):
            Dependance.objects.create(projet=projet, predecesseur=pred, successeur=succ)
            faits += 1
        return f"{faits} lien(s)"

    def _synthese(self):
        from apps.chantier.models import SynthesePeriodique
        from apps.chantier.services.synthese import enregistrer_synthese
        from apps.projets.models import AffectationProjet

        projet = self._projet("TEST-2026-002")
        if projet is None:
            return "chantier TEST-2026-002 absent"
        if SynthesePeriodique.objects.filter(projet=projet).exists():
            return "déjà présente"
        affectation = AffectationProjet.objects.filter(
            projet=projet, role_projet="CT", est_actif=True
        ).select_related("utilisateur").first()
        if affectation is None:
            return "aucun conducteur affecté à TEST-2026-002"
        conducteur = affectation.utilisateur
        aujourdhui = timezone.localdate()
        fin = aujourdhui - timedelta(days=aujourdhui.weekday() + 1)  # dimanche écoulé
        debut = fin - timedelta(days=6)
        enregistrer_synthese(
            projet=projet,
            type_="HEBDOMADAIRE",
            debut=debut,
            fin=fin,
            utilisateur=conducteur,
            appreciation="Semaine conforme au planning ; coulage des poteaux achevé.",
            objectifs="Lancer les planchers du niveau suivant.",
        )
        return f"créée (du {debut} au {fin})"

    def _factures(self):
        from apps.billing.models import Abonnement, Facture, PaiementAbonnement

        abonnement = Abonnement.objects.filter(entreprise=self.entreprise).first()
        if abonnement is None:
            return "pas d'abonnement"
        if Facture.objects.filter(entreprise=self.entreprise).exists():
            return "déjà présentes"
        aujourdhui = timezone.localdate()
        faits = 0
        for rang, (statut, mois) in enumerate(
            [(Facture.Statut.PAYEE, 2), (Facture.Statut.IMPAYEE, 1)], start=1
        ):
            ht = 49_000 * 100
            tva = int(Decimal(ht) * Decimal("0.18"))
            debut = aujourdhui - timedelta(days=30 * mois)
            facture = Facture.objects.create(
                numero=f"FAC-{aujourdhui.year}-{aujourdhui.month:02d}-{self.slug[:3].upper()}{rang:03d}",
                abonnement=abonnement,
                entreprise=self.entreprise,
                periode_debut=debut,
                periode_fin=debut + timedelta(days=29),
                montant_ht=ht,
                taux_tva=Decimal("18.00"),
                montant_tva=tva,
                montant_ttc=ht + tva,
                statut=statut,
                date_echeance=debut + timedelta(days=30),
            )
            if statut == Facture.Statut.PAYEE:
                PaiementAbonnement.objects.create(
                    facture=facture,
                    mode=PaiementAbonnement.Mode.AUTRE,
                    reference_commande=f"CMD-LOCAL-{self.slug[:3].upper()}-{rang:03d}",
                    montant=facture.montant_ttc,
                    statut=PaiementAbonnement.Statut.CONFIRME,
                    paye_le=timezone.now() - timedelta(days=30 * mois - 2),
                )
            faits += 1
        return f"{faits} facture(s)"
