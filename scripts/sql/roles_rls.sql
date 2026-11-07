-- Rôle de la portée plateforme — D9, règle R-5 (lot 4 de la sortie du multi-schéma).
--
-- À exécuter **en superutilisateur** (seul un superutilisateur accorde BYPASSRLS), une fois par
-- serveur pour le rôle, une fois par base pour les droits :
--
--   psql -U postgres -d ccd_schema_unique -v app=ccd -f scripts/sql/roles_rls.sql
--
-- `app`          : le rôle avec lequel Django se connecte (POSTGRES_USER).
-- `proprietaire` : le rôle propriétaire des tables, celui qui joue les migrations ; par défaut,
--                  `app` (cas local : `ccd` est à la fois propriétaire et applicatif).
--
-- Le rôle `ccd_plateforme` ne se connecte pas (NOLOGIN) : Django le prend par `SET ROLE` le temps
-- d'une `portee_plateforme(...)`, et le rend aussitôt. Il ne fait que lire et écrire des lignes ;
-- il ne crée ni ne modifie aucune table.
--
-- En production (lot 9), la D9 prévoit en plus un rôle applicatif `ccd_app` distinct du
-- propriétaire, ni superutilisateur ni BYPASSRLS : c'est l'objet de la vérification §8.1 du plan.
-- `manage.py verifier_isolation` dit ensuite si tout est en place.

\set ON_ERROR_STOP on

\if :{?app}
\else
  \echo 'Variable manquante : -v app=<rôle de connexion de Django>'
  \quit
\endif
\if :{?proprietaire}
\else
  \set proprietaire :app
\endif

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ccd_plateforme') AS creer \gset
\if :creer
  CREATE ROLE ccd_plateforme NOLOGIN BYPASSRLS;
\endif
ALTER ROLE ccd_plateforme NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;

-- Le rôle de connexion peut prendre ccd_plateforme (SET ROLE).
GRANT ccd_plateforme TO :"app";

-- Droits sur les lignes, dans cette base.
GRANT USAGE ON SCHEMA public TO ccd_plateforme;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ccd_plateforme;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO ccd_plateforme;
ALTER DEFAULT PRIVILEGES FOR ROLE :"proprietaire" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ccd_plateforme;
ALTER DEFAULT PRIVILEGES FOR ROLE :"proprietaire" IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO ccd_plateforme;

-- Garde-fou : le rôle de connexion ne doit être ni superutilisateur ni BYPASSRLS.
SELECT rolname AS role_de_connexion, rolsuper AS superutilisateur, rolbypassrls AS contourne_rls
FROM pg_roles WHERE rolname = :'app';
