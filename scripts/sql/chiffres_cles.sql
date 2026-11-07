-- Chiffres clés d'une entreprise peuplée par `peupler_donnees_test` (D9, lot 6).
--
-- Sert à comparer l'ancien modèle (un schéma par entreprise) et le nouveau (schéma unique) :
-- les UUID sont régénérés, on compare les contenus. Même requête des deux côtés, seul le
-- contexte change :
--
--   ancien : SET search_path TO demo, public;
--   nouveau : SELECT set_config('ccd.entreprise_id', '<uuid de demo>', false);  -- la RLS filtre
--
-- Une ligne par fait, triée : deux sorties se comparent avec `diff`.

WITH p AS (SELECT * FROM projet WHERE supprime_le IS NULL)
SELECT * FROM (
    -- Projets : statut, avancement, santé
    SELECT 'projet ' || reference || ' : ' || statut || ' | reel ' || avancement_reel
           || ' | theorique ' || avancement_theorique || ' | sante ' || coalesce(indice_sante::text, '-')
           || ' | badge ' || coalesce(badge_sante, '-') AS fait
    FROM p
    UNION ALL
    -- Contenu de chaque projet
    SELECT 'projet ' || p.reference || ' : elements ' || (SELECT count(*) FROM element e WHERE e.projet_id = p.id AND e.supprime_le IS NULL)
           || ' | points ' || (SELECT count(*) FROM point_avancement x WHERE x.projet_id = p.id)
           || ' | affectations ' || (SELECT count(*) FROM affectation_projet x WHERE x.projet_id = p.id AND x.supprime_le IS NULL)
           || ' | equipes ' || (SELECT count(*) FROM equipe_chantier x WHERE x.projet_id = p.id AND x.supprime_le IS NULL)
           || ' | alertes ' || (SELECT count(*) FROM alerte_retard x WHERE x.projet_id = p.id)
           || ' | arrets ' || (SELECT count(*) FROM arret_chantier x WHERE x.projet_id = p.id)
    FROM p
    UNION ALL
    -- Journaux par statut
    SELECT 'journaux ' || p.reference || ' ' || r.statut || ' : ' || count(*)
    FROM rapport_journalier r JOIN p ON p.id = r.projet_id
    WHERE r.supprime_le IS NULL GROUP BY p.reference, r.statut
    UNION ALL
    SELECT 'journaux detailles : ' || count(*) FROM journal_chantier WHERE supprime_le IS NULL
    UNION ALL
    -- Blocages par statut
    SELECT 'blocages ' || p.reference || ' ' || b.statut || ' : ' || count(*)
    FROM blocage b JOIN p ON p.id = b.projet_id
    WHERE b.supprime_le IS NULL GROUP BY p.reference, b.statut
    UNION ALL
    -- Volumes du référentiel de l'entreprise
    SELECT 'tiers : ' || count(*) FROM tiers WHERE supprime_le IS NULL
    UNION ALL
    SELECT 'main-d''oeuvre : ' || count(*) FROM personne_main_oeuvre WHERE supprime_le IS NULL
    UNION ALL
    -- Droits par compte (partie locale de l'adresse : le domaine change d'une entreprise à l'autre)
    SELECT 'compte ' || split_part(u.email, '@', 1) || ' : ' || coalesce(ro.code, '-') || ' | '
           || coalesce((
               SELECT string_agg(cp.code, ',' ORDER BY cp.code)
               FROM role_module_permission rmp
               JOIN role_module_permission_permissions_catalogue l ON l.rolemodulepermission_id = rmp.id
               JOIN catalogue_permission cp ON cp.id = l.cataloguepermission_id
               WHERE rmp.role_id = ro.id AND rmp.supprime_le IS NULL
           ), '-')
    FROM utilisateur u LEFT JOIN role ro ON ro.id = u.role_id
    -- Les seize collaborateurs du jeu (une base de développement en a souvent d'autres)
    WHERE split_part(u.email, '@', 1) IN (
        'cp.kone', 'cp.bamba', 'ct.yao', 'ct.ouattara', 'ct.nguessan', 'cc.coulibaly',
        'cc.traore', 'cc.kouassi', 'cc.diabate', 'cc.gnamien', 'it.soro', 'df.aka', 'qse.konan',
        'moe.kacou', 'moa.palmiers', 'vi.audit'
    )
) faits
ORDER BY fait;
