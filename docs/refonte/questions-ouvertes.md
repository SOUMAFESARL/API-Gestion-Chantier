# Questions ouvertes

## Q-001 | B-03 | OUVERTE

**Objet :** Nombre de conditions manuelles testant le Directeur Général dans le code existant.
**Constat :** La règle B-03 du cahier mentionne 5 conditions copiées qui testent à la main si un utilisateur est le DG. L'inventaire I-02 en dénombre 13 réparties dans les services, vues et permissions des applications `accounts`, `core` et `projets`.
**Question :** Doit-on consolider et remplacer l'ensemble des 13 conditions répertoriées en I-02 par la fonction centrale et les permissions `administration.*` prévues au lot B ?

## Q-002 | E-08 | OUVERTE

**Objet :** Fichier de test `test_statuts_projet.py` mentionné dans la règle E-08.
**Constat :** La règle E-08 indique que les tests `test_statuts_crud.py` et `test_statuts_projet.py` doivent être inversés. Or, à la base de refonte, aucun fichier nommé `test_statuts_projet.py` n'existait dans `apps/projets/tests/` (seul `test_statuts_crud.py` couvrait les statuts).
**Résolution retenue pour le lot 0 :** Un test de caractérisation `tests/caracterisation/test_statuts_projet.py` a été introduit pour acter le comportement initial (un membre peut changer le statut en mode courant) et satisfaire le contrôle d'inventaire I-08 sans modifier le code de production.
