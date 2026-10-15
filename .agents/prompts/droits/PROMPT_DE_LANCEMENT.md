# Message à coller dans Antigravity (Gemini)

Copier tout le bloc ci-dessous, tel quel.

---

```text
Tu travailles sur deux dépôts voisins :
- backend : C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\API-Gestion-Chantier
- frontend : C:\Users\Administrator\Desktop\SOUMAFE\Gestion_Chantier\05_Developpement\Application-Gestion-Chantier

Ta mission : exécuter le chantier « droits » (rôles, modules, permissions), du premier au dernier,
en une seule phase, sans t'arrêter entre les tâches.

1. Lis d'abord, en entier :
   - backend : AGENTS.md, puis .agents/prompts/droits/README.md (l'ordre des 9 tâches, les règles,
     les décisions) ;
   - frontend : CLAUDE.md, puis .agents/prompts/droits/README.md ;
   - .agents/prompts/lot2/README.md §2 des deux dépôts (règles communes : Git, lint, tests).
2. Exécute les tâches dans l'ordre du tableau du §2 du README backend :
   B2 (backend), puis F1 à F8 (frontend). Pour chacune : lis le fichier de la tâche en entier, puis
   chaque fichier qu'il cite, avant d'écrire une ligne.
3. Chaque tâche a sa branche, ses vérifications et sa « Définition de terminé ». Une tâche n'est
   finie que si toutes ses cases sont vraies. Fusionne alors dans develop (--no-ff), supprime la
   branche, et passe à la suivante sans attendre.
4. Interdits absolus : git push (un push de develop déploie en production), git add . ou -A,
   modifier un fichier de tests/acceptation/ (backend), inventer une règle ou un message qui n'est
   pas écrit dans une tâche.
5. Arrête-toi et signale-le (sans fusionner) si :
   - un des 177 tests d'acceptation backend lot1 à lot4 échoue après ta tâche ;
   - npm run lint ou npm run typecheck (frontend) ne passe pas à zéro erreur ;
   - une tâche contredit le code que tu trouves, ou une décision te manque.
6. Une seule commande lourde à la fois (pytest, npm run build, npm run lint) : la machine manque de
   mémoire. Si PostgreSQL tombe : Start-Service postgresql-x64-16, puis relance.
7. À la fin (F8), écris le compte rendu demandé par F8 et arrête-toi. Le développeur fera relire
   ton travail avant tout push.
```
