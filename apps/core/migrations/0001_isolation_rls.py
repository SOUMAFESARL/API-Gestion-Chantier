"""Sécurité au niveau des lignes sur toutes les tables d'entreprise (D9, lot 4, règle R-5).

Chaque table d'entreprise reçoit `ENABLE` puis `FORCE ROW LEVEL SECURITY` et la politique
`isolation_entreprise` (`apps.core.rls`). Les tables de plateforme (catalogue, plans, facturation
de l'éditeur, entreprises, inscriptions) n'en ont pas : elles se lisent sans contexte (R-1).

**Restent hors RLS** les neuf tables de liaison que Django crée pour les `ManyToManyField`
(`alerte_retard_destinataires`, `avenant_element`…) : elles n'ont pas de colonne `entreprise_id`.
Elles ne contiennent que des paires d'identifiants, sans contenu ; les lignes qu'elles relient
restent, elles, filtrées.

Une nouvelle table d'entreprise ajoute `isolation_entreprise("<table>")` à sa propre migration ;
`manage.py verifier_isolation` signale celle qu'on aurait oubliée.
"""

from django.db import migrations

from apps.core.rls import isolation_entreprise, role_plateforme

TABLES = [
    # accounts
    "role",
    "role_module_permission",
    "utilisateur",
    "invitation",
    "appareil",
    "jeton_reinitialisation",
    # audit
    "journal_audit",
    # tiers
    "tiers",
    "role_tiers",
    # onboarding
    "progression_configuration",
    "etape_configuration",
    # projets
    "alerte_retard",
    "arret_chantier",
    "avenant",
    "semaine_type",
    "exception_calendrier",
    "projet_contrat",
    "point_avancement",
    "liste_valeurs_entreprise",
    "valeur_liste_entreprise",
    "modele_decoupage_entreprise",
    "niveau_modele_entreprise",
    "ligne_modele_entreprise",
    "niveau_projet",
    "element",
    "dependance_element",
    "personne_main_oeuvre",
    "equipe_chantier",
    "membre_equipe_chantier",
    "affectation_equipe_element",
    "motif_report",
    "projet",
    "affectation_projet",
    "historique_date",
    "mise_a_jour_inline",
    "parametres_documents",
    "referentiel_entreprise",
    "sante_projet_snapshot",
    # chantier
    "blocage",
    "journal_chantier",
    "alerte_journal",
    "rapport_journalier",
    "relance_journal",
    "synthese_periodique",
]


def _droits_du_role_plateforme() -> migrations.RunSQL:
    """Les droits du rôle de la portée plateforme, s'il existe déjà.

    Le rôle est global au serveur, mais les droits sont propres à chaque base : la base de test,
    recréée à chaque passe, doit les recevoir ici. Les tables créées plus tard par le même rôle
    les reçoivent d'office (`ALTER DEFAULT PRIVILEGES`). Si le rôle n'existe pas encore,
    `scripts/sql/roles_rls.sql` les accorde en le créant.
    """
    role = role_plateforme()
    return migrations.RunSQL(
        sql=f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO "{role}"';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"';
    EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "{role}"';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public
             GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public
             GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "{role}"';
  END IF;
END $$;
""",
        reverse_sql=migrations.RunSQL.noop,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
        ("audit", "0001_initial"),
        ("tiers", "0001_initial"),
        ("onboarding", "0001_initial"),
        ("projets", "0002_isolation_sql"),
        ("chantier", "0002_isolation_sql"),
    ]

    operations = [
        *(isolation_entreprise(table) for table in TABLES),
        _droits_du_role_plateforme(),
    ]
