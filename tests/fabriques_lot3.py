"""
FABRIQUES DU LOT 3.

Adapté avec les noms réels et précis du dépôt (champs obligatoires, routes, modèles).
"""
import itertools
import uuid
from datetime import date, timedelta

SCHEMA = "demo"
HOST = "demo.localhost"
API = "/api/v1"
_n = itertools.count(1)


def _schema():
    from django_tenants.utils import schema_context

    return schema_context(SCHEMA)


# --------------------------------------------------------------------------- routes
def url_projets():
    return f"{API}/projets/"


def url_projet(projet):
    return f"{API}/projets/{projet.pk}/"


def url_lots(projet):
    return f"{API}/projets/{projet.pk}/lots/"


def url_journal_reports():
    return f"{API}/projets/journal-reports/"


def url_motifs_report():
    return f"{API}/projets/motifs-report/"


def corps_lot():
    """Corps minimal d'un POST de lot. Une réponse 400 reste un « passage de la garde »."""
    return {
        "nom": f"Lot {next(_n)}",
        "mode_execution": "DIRECT",
        "type_bordereau": "PRIX_UNITAIRES",
    }


# --------------------------------------------------------------------------- rôles
def role_systeme(code):
    from apps.accounts.models import Role

    with _schema():
        return Role.objects.get(code=code, supprime_le__isnull=True)


def creer_role_personnalise(portee="PROJET", code=None):
    """Rôle personnalisé SANS aucune permission (aucune ligne de matrice)."""
    from apps.accounts.models import Role

    code = code or f"PERSO_{next(_n)}"
    with _schema():
        return Role.objects.create(
            code=code,
            libelle=code,
            portee=portee,
            est_systeme=False,
            est_actif=True,
        )


def changer_portee(role, portee):
    with _schema():
        role.portee = portee
        role.save(update_fields=["portee"])
    return role


def definir_permissions(role, codes):
    """Donne EXACTEMENT ces codes au rôle."""
    from apps.accounts.models import Module, RoleModulePermission
    from apps.catalogue.models import CatalogueModule, CataloguePermission
    from apps.core.registre_permissions import REGISTRE

    with _schema():
        RoleModulePermission.objects.filter(role=role).delete()
        codes_par_module = {}
        for c in codes:
            def_p = REGISTRE.get(c)
            mod_code = def_p.module if def_p else c.split(".")[0]
            codes_par_module.setdefault(mod_code.lower(), []).append(c)

        for mod_code, m_codes in codes_par_module.items():
            cat_mod = CatalogueModule.objects.filter(code=mod_code, supprime_le__isnull=True).first()
            mod_local = Module.objects.filter(code=mod_code, supprime_le__isnull=True).first()
            rmp = RoleModulePermission.objects.create(
                role=role,
                module=mod_local,
                module_catalogue=cat_mod,
                niveau=1,
            )
            perms = list(CataloguePermission.objects.filter(code__in=m_codes, supprime_le__isnull=True))
            rmp.permissions_catalogue.set(perms)


def corps_permissions(codes):
    """Corps d'un PATCH de rôle qui coche ces codes."""
    return {"permissions": list(codes), "confirmer": True}


# --------------------------------------------------------------------------- personnes
def creer_utilisateur(role):
    from apps.accounts.models import Utilisateur

    n = next(_n)
    with _schema():
        u = Utilisateur(
            email=f"u{n}-{uuid.uuid4().hex[:6]}@test.local",
            nom=f"Nom{n}",
            prenom="Test",
            role=role,
            role_global=role.code,
            statut="ACTIF",
        )
        u.set_password("MotDePasse!123")
        u.save()
        return u


def utilisateur_avec_role(code):
    return creer_utilisateur(role_systeme(code))


def obtenir_dg():
    from apps.accounts.models import Utilisateur

    with _schema():
        existant = Utilisateur.objects.filter(role__code="DG", supprime_le__isnull=True).first()
    return existant or utilisateur_avec_role("DG")


# --------------------------------------------------------------------------- projets et affectations
def creer_projet():
    from apps.projets.models import Projet

    n = next(_n)
    with _schema():
        return Projet.objects.create(
            nom=f"Projet test {n}",
            reference=f"PRJ-{n:04d}",
            ville="Abidjan",
        )


def affecter(utilisateur, projet):
    from apps.projets.models import AffectationProjet

    with _schema():
        aff, _ = AffectationProjet.objects.update_or_create(
            projet=projet,
            utilisateur=utilisateur,
            defaults={
                "est_actif": True,
                "role_projet": "CP",
            },
        )
        return aff


def desactiver_affectation(affectation):
    from django.utils import timezone

    with _schema():
        affectation.est_actif = False
        affectation.supprime_le = timezone.now()
        affectation.save(update_fields=["est_actif", "supprime_le", "modifie_le"])
    return affectation


def creer_report(projet):
    """Un enregistrement d'historique de report rattaché au projet (HistoriqueDate)."""
    from apps.accounts.models import Utilisateur
    from apps.projets.models import HistoriqueDate, MotifReport

    with _schema():
        motif, _ = MotifReport.objects.get_or_create(
            code="INTEMPERIES",
            defaults={"libelle": "Intempéries", "est_actif": True},
        )
        auteur = Utilisateur.objects.filter(supprime_le__isnull=True).first() or obtenir_dg()
        return HistoriqueDate.objects.create(
            type_objet="PROJET",
            projet=projet,
            champ="date_fin_prevue",
            valeur_avant=date.today(),
            valeur_apres=date.today() + timedelta(days=14),
            motif=motif,
            justification="Justification obligatoire de report de plus de 30 caractères pour test.",
            auteur=auteur,
            ecart_jours=14,
        )


# --------------------------------------------------------------------------- HTTP
def client_pour(utilisateur):
    from rest_framework.test import APIClient

    c = APIClient(HTTP_HOST=HOST)
    c.force_authenticate(user=utilisateur)
    return c


def liste_de(reponse):
    """Normalise une réponse de liste (paginée ou non)."""
    data = reponse.json() if hasattr(reponse, "json") else reponse.data
    if isinstance(data, dict):
        if "resultats" in data:
            return data["resultats"]
        if "results" in data:
            return data["results"]
    return data


def ids_de(reponse):
    return {str(ligne["id"]) for ligne in liste_de(reponse)}
