"""Port?e plateforme explicite sans r?le privil?gi? (h?bergement mutualis?).

La RLS reste forc?e. Le wrapper positionne puis r?initialise le r?glage pour
chaque contexte. Comme entreprise_id et SET ROLE, ce r?glage ne prot?ge pas
contre une injection SQL ; il prot?ge des filtres oubli?s.
"""

from django.db import migrations

from apps.core.rls import role_plateforme

TABLES = [
    "role",
    "role_module_permission",
    "utilisateur",
    "invitation",
    "appareil",
    "jeton_reinitialisation",
    "journal_audit",
    "tiers",
    "role_tiers",
    "progression_configuration",
    "etape_configuration",
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
    "blocage",
    "journal_chantier",
    "alerte_journal",
    "rapport_journalier",
    "relance_journal",
    "synthese_periodique",
]

CONDITION = (
    "(current_setting('ccd.portee_plateforme', true) = 'on' "
    "AND nullif(current_setting('ccd.entreprise_id', true), '') IS NULL)"
)


def installer(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(
            f'CREATE POLICY portee_plateforme_session ON "{table}" '
            f"USING {CONDITION} WITH CHECK {CONDITION}"
        )
    schema_editor.execute(
        f"""
CREATE OR REPLACE FUNCTION verifier_immuabilite_historique_date()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND (current_user = '{role_plateforme()}'
            OR (current_setting('ccd.portee_plateforme', true) = 'on'
                AND nullif(current_setting('ccd.entreprise_id', true), '') IS NULL))
       AND OLD.entreprise_id::text = current_setting('ccd.purge_entreprise', true) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'RG-07 : historique_date est immuable. Operation % interdite.', TG_OP;
END;
$$ LANGUAGE plpgsql;
""",
        params=None,
    )


def retirer(apps, schema_editor):
    from importlib import import_module

    for table in TABLES:
        schema_editor.execute(f'DROP POLICY portee_plateforme_session ON "{table}"')
    ancienne = import_module("apps.projets.migrations.0002_isolation_sql")
    schema_editor.execute(ancienne._immuabilite(), params=None)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_planifier_taches")]
    operations = [migrations.RunPython(installer, retirer)]
