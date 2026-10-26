# F1 — Découpage d'un projet en arbre : décisions v1.2

| | |
|---|---|
| Concerne | F1 (lots et activités), F3 (calcul de l'avancement), MLD (tables `lot`, `activite` et référentiels) |
| Dates | v1.0 le 23/10/2026 (création) ; v1.1 le 26/10/2026 (modification d'un projet, F3, corrections) ; v1.2 le 26/10/2026 (affectations, équipes, permissions) |
| Décision | ZANFACK Durel |
| Statut | Décisions de conception prises **avant** toute implémentation. **À valider par le Product Owner** (§17) |
| Raison | Le découpage figé Lot → Activité ne s'adapte pas aux chantiers réels : il faut pouvoir découper par phase, ouvrage, lot, activité ou toute autre unité, sur autant de niveaux que nécessaire |
| Prototype | `F1_prototype_decoupage.html`, dans ce dossier : création, modification d'un projet de démonstration, règles en images |

Ce document remplace, pour le découpage d'un projet, tout ce que F1 et F3 disent des lots et
des activités. Là où il les contredit, c'est lui qui s'applique.

**Ce qui change en v1.1.** Les parents ont leurs propres dates (§11) ; le poids d'un élément est
le montant connu le plus précis (§8) ; le statut d'un parent ne dépend plus de celui de ses
enfants (§10) ; plus de code automatique (A-4) ; deux frères ne portent pas le même nom (A-6) ;
la modification d'un projet (§12) et F3 sur l'arbre (§9) sont décidées.

**Ce qui change en v1.2.** Les affectations, les équipes et les permissions sur l'arbre (§13bis) :
le périmètre d'une affectation devient un ou plusieurs éléments, une permission s'exerce dans ce
périmètre, et plus aucune règle ne dépend du nom d'un rôle. Le §11.2 et le §7 en sont corrigés.
Le journal de chantier (§13ter) et les modes d'exécution (§13quater) sont décidés. Les engagements
initiaux et courants, les avenants (§11bis) et la visibilité par périmètre (§13bis) aussi ; le
mot « avenant » est réservé à l'acte signé, le reste devient une « modification tracée ». Les
compléments du suivi (§13quinquies) ferment les trous relevés : saisie en masse, dépassement,
réouverture, dates réelles, dépendances, jalons, historique de l'avancement. Le journal hors
connexion et les alertes de retard sont décidés (§13quater-bis et §13quater-ter).

---

## 1. Le principe : un seul objet, l'élément

Phase, ouvrage, lot, activité **sont le même objet** : un **élément de découpage**. Ils ne
diffèrent que par leur parent. « Ouvrage » ou « Lot » n'est que le **libellé du niveau** où se
trouve l'élément.

```
élément : projet, parent, niveau, intitulé, code libre, ordre
```

**Conséquence acceptée : aucun comportement ne dépend d'un nom.** Le code ne teste jamais
« est-ce un lot ? ». Ce qui doit varier d'un élément à l'autre dépend de sa position (feuille ou
parent) ou d'un réglage explicite, jamais d'un libellé.

**Une feuille** est un élément sans enfant. Ce statut n'est pas fixe : découper une feuille en
fait un parent.

**Un élément est commencé** quand au moins une feuille en dessous de lui porte une mesure
(quantité réalisée, pourcentage déclaré, clôture). Cette notion remplace le marqueur
`premier_rapport_soumis` des lots.

## 2. Le gabarit : les niveaux d'un projet

1. Un **gabarit** est une liste ordonnée de niveaux. Chaque niveau a un libellé et, au plus, une
   liste de valeurs (§4). On définit autant de niveaux que l'on veut.
2. **La récursion est permise à tout niveau, sans profondeur maximale.** Une activité peut
   contenir des activités, un lot des lots. Le niveau n'est donc plus la profondeur.
3. Le même libellé ne figure pas sur deux niveaux. « Un lot dans un lot », c'est de la récursion
   sur le niveau Lot, pas un second niveau Lot.

**Règles de l'arbre.**

| # | Règle |
|---|---|
| A-1 | Un enfant est **soit au niveau de son parent** (récursion), **soit au niveau suivant**. On ne saute pas de niveau : un projet qui n'a pas besoin d'un niveau le retire de son gabarit |
| A-2 | Les enfants d'un élément sont **tous du même niveau** : tous de son niveau, ou tous du niveau suivant, jamais un mélange |
| A-3 | Renommer un niveau est toujours permis, en ajouter un à la fin aussi. Insérer un niveau au milieu d'un projet rempli passe par le geste « Insérer un niveau » (§12.6) |
| A-4 | **Pas de code automatique stocké.** La numérotation 1, 1.2, 1.2.3 n'est qu'un **affichage** de la vue en arbre, recalculé à l'écran, sans valeur d'identifiant. Seul existe un **code libre facultatif**, pour reprendre la numérotation du bordereau du client (DQE, BPU) ; il ne change que si on le modifie. Le `code` obligatoire actuel des lots (« L-01 ») disparaît |
| A-5 | **Une feuille commencée ne se découpe pas directement** : on passe par le geste « Détailler » (§12.5) |
| A-6 | **Deux frères ne portent pas le même intitulé**, comparés sans accents, majuscules ni espaces superflus (`cle_comparaison`). Refusé à la création, au renommage et au déplacement |

## 3. Les modèles de découpage

1. Un **modèle** est un gabarit (ses niveaux et la liste de chacun) accompagné de **lignes
   types** (§5). Le modèle de pré-remplissage et le modèle réutilisable sont une seule et même chose.
2. **Le super admin crée des modèles plateforme**, autant qu'il veut. Ils sont fournis par défaut
   pour le BTP.
3. **Un modèle plateforme est visible par toutes les entreprises sans être copié chez elles.** Il
   existe une seule fois, dans le schéma `public`, et chaque entreprise le lit, comme
   `ReferentielPlateforme`. Une correction du super admin est donc vue partout immédiatement.
4. **Une entreprise crée ses propres modèles.** Elle ne modifie ni ne supprime un modèle
   plateforme (même règle que les référentiels, arbitrage du 16/10/2026).
5. **Personnaliser** un modèle plateforme en crée une copie dans l'entreprise, **liée à son
   original par identifiant**, et non par son nom. La copie s'affiche « Nom (personnalisé) ».
   **L'original reste visible** à côté d'elle.
6. Une copie personnalisée **ne suit plus son original**. Si le super admin modifie l'original
   ensuite, la copie le signale sans rien appliquer.
7. **Homonymie.** Une entreprise qui crée de zéro un modèle portant le nom d'un modèle plateforme
   le voit affiché « Nom (entreprise) ». Deux modèles d'une même origine ne portent pas le même nom.
8. **Un modèle plateforme ne puise que dans des listes plateforme.** Un modèle d'entreprise puise
   dans les deux.
9. **Type de projet.** Un modèle déclare les types de projet pour lesquels il est conçu. À la
   création d'un projet, **tous les modèles sont proposés**, ceux du type choisi en tête.
10. **Le contenu d'un modèle se construit avec le tableau du §5**, chez le super admin comme dans
    l'entreprise : « Enregistrer comme nouveau modèle », « Mettre à jour ce modèle » (sur ses
    propres modèles), « Personnaliser ce modèle ».
11. **Un projet reçoit une copie de son modèle.** Modifier ou supprimer un modèle ne change aucun
    projet déjà créé.

## 4. Les listes de valeurs

1. **Les listes sont des données, pas une énumération codée.** Le super admin crée des listes
   plateforme (Phases, Lots…), l'entreprise crée les siennes et ajoute ses valeurs aux listes
   plateforme, sans pouvoir retirer celles de la plateforme.
2. La catégorie `LOT` du référentiel actuel devient la liste « Lots ». `TYPE_PROJET` et
   `MODE_EXECUTION` restent des catégories codées : le code s'en sert pour décider de comportements.
3. **Chaque niveau du gabarit choisit librement la liste où il puise ses propositions, ou aucune.**
   Le lien passe par l'identifiant de la liste, jamais par le nom. **Une seule liste par niveau.**
4. Le choix se fait **dans le modèle**, et le projet peut le changer comme le reste du gabarit.
5. **La liste est ouverte** : on choisit une valeur proposée ou on tape librement.
6. Une valeur tapée hors liste **n'entre pas** dans la liste.
7. Dans un projet, les valeurs **déjà saisies** à un niveau sont proposées en plus de la liste.
8. **Changer la liste d'un niveau déjà rempli ne modifie aucune valeur existante.**
9. Un niveau récursif propose la même liste à tous ses étages.

Les valeurs réelles des phases, des lots supplémentaires et des modèles seront fournies par le
Product Owner. Le prototype utilise des exemples, sauf la liste des lots, qui reprend le
référentiel actuel (`catalogue/migrations/0011_peupler_referentiels.py`).

## 5. Le tableau de démarrage d'un projet

Au démarrage d'un projet, le découpage se saisit dans **un tableau pré-rempli**, à partir d'un
modèle ou d'un fichier Excel. On y modifie, ajoute ou supprime des lignes.

1. **Une ligne = une feuille.** Ses colonnes sont les niveaux du gabarit, dans l'ordre.
2. **Les cellules identiques se regroupent** sous un même parent. Le même intitulé sous deux
   parents différents donne deux éléments distincts.
3. **Renommer un parent** propose de le faire sur toutes les lignes de son groupe ou sur cette
   ligne seulement (ce qui la rattache à un autre parent).
4. **Une cellule vide en fin de ligne est permise** : son dernier élément rempli est la feuille.
5. **Une cellule vide au milieu d'une ligne est interdite** : c'est un niveau sauté (A-1).
6. **Seule la première cellule est obligatoire.** Une ligne entièrement vide est ignorée.
7. **Ligne sans effet** : une ligne dont le dernier élément a des enfants sur d'autres lignes est
   signalée, non bloquante, et ignorée.
8. Une ligne **porte la structure seulement**, sans unité, quantité, montant ni date.
9. **La récursion ne se saisit pas dans le tableau** : elle se fait après la création, dans la vue
   en arbre.
10. **Excel.** Import (ajout ou remplacement) et export, la première ligne portant les libellés
    des niveaux.
11. **Retirer un niveau** se fait par ✕, avec confirmation s'il porte des valeurs. Il n'y a pas de
    niveau « facultatif » à cocher.

## 6. Les règles de cohérence du tableau

| # | Règle | Effet |
|---|---|---|
| C-1 | Cellule vide au milieu d'une ligne | **Bloquant** |
| C-2 | Ligne en double (même chemin complet) | **Bloquant** |
| C-3 | Niveau sans libellé | **Bloquant** |
| C-4 | Deux niveaux au même libellé | **Bloquant** |
| C-5 | Valeur qui appartient à la liste d'un **autre** niveau et pas à la sienne : colonnes inversées ? | Avertissement |
| C-6 | Enfant portant le même nom que son parent | Avertissement |
| C-7 | Valeur hors de la liste de son niveau : coquille ? | Avertissement discret |

Avant la création, un récapitulatif liste les avertissements : on corrige ou on crée quand même.
C-1 à C-4 s'appliquent aussi à l'enregistrement d'un modèle.

## 7. Ce que porte un élément

| Groupe | Champs | Feuille | Parent |
|---|---|---|---|
| Identité | intitulé, code libre, ordre, statut, motif | saisi | saisi (statut : §10) |
| Mesure | mode de mesure, unité, quantités, pourcentage | saisi | — |
| Avancement | physique, temporel, écart | calculé (§9) | calculé (§9) |
| Montant | montant (feuille), enveloppe (parent) | saisi | enveloppe saisie, plus la somme de ses enfants (§8) |
| Dates | dates prévues, baseline, dates réelles | saisies | **saisies aussi** : un parent a ses propres dates et sa propre baseline (§11) |
| Exécution | mode d'exécution, type de bordereau, titulaire | **défini sur n'importe quel élément, hérité par ses descendants**, redéfinissable sur un descendant | |

Le chef de chantier et les équipes ne sont **pas** des champs de l'élément : ils viennent des
affectations (§13bis), pour qu'il n'existe qu'une seule source de vérité.

- `Activite.poids` disparaît : le poids est le montant.
- `Lot.phase`, texte libre, disparaît : la phase est désormais un niveau.
- `Lot.code`, obligatoire, disparaît au profit du code libre facultatif (A-4).

## 8. Les montants et le poids

Un parent porte **deux montants** : une **enveloppe** facultative et saisie (par exemple le
montant du marché d'un lot), et la **somme** des montants de ses enfants, calculée. L'écart entre
les deux est affiché, signalé quand la somme dépasse l'enveloppe, **jamais bloquant**.

**Le poids d'un élément est le montant connu le plus précis :**

| Situation | Poids | Physique du parent |
|---|---|---|
| Feuille avec un montant | son montant | — |
| Parent dont **tous** les enfants ont un poids | la **somme** de ses enfants | moyenne des enfants pondérée par leur poids |
| Parent aux enfants **partiellement** chiffrés, **avec** enveloppe | son **enveloppe** | (somme des physiques × poids des enfants chiffrés) ÷ enveloppe : la part non chiffrée compte pour 0 % |
| Parent aux enfants partiellement chiffrés, **sans** enveloppe | aucun | calculé sur les enfants chiffrés seulement, et signalé « partiel » |
| Aucun montant connu | aucun | **« avancement indisponible »** |

- Un élément sans poids ne pèse rien au-dessus de lui, et il est compté parmi les « exclus ».
- **Quand on découpe une feuille, son montant devient l'enveloppe du nouveau parent.** À
  l'inverse, un parent qui perd son dernier enfant redevient une feuille, et son enveloppe
  devient son montant.
- Modifier un montant affiche son effet sur l'avancement du projet avant de confirmer.

*Options écartées : la somme seule (on perd l'enveloppe contractuelle), la répartition imposée
de l'enveloppe (bloquante pendant la construction du détail), les parts égales entre frères
quand aucun montant n'est connu (un chiffre trompeur plutôt qu'un aveu d'ignorance).*

## 9. L'avancement : F3 sur l'arbre

On saisit l'avancement **sur les feuilles seulement**, et il remonte jusqu'au projet. Les
formules de F3 sont conservées et généralisées :

| F3 | Aujourd'hui | Avec l'arbre |
|---|---|---|
| **1. Physique de la feuille** | quantité réalisée / quantité prévue ; 100 % si clôturée | inchangée en mode **quantité** ; nouveau mode **pourcentage déclaré**, pour ce qui ne se mesure pas en quantité (études, démarches, réception) |
| **2. Physique d'un parent** | lot : moyenne des activités **pondérée par la quantité prévue** | **tout parent** : moyenne des enfants **pondérée par le poids** du §8. Les quantités ne s'additionnent pas entre unités |
| **3. Physique du projet** | moyenne des lots pondérée par le budget ; 0 % sans budget | la règle de tout parent ; **« indisponible »** au lieu de 0 % |
| **4. Temporel** | lot : jours ouvrés écoulés / total, sur sa baseline ; projet : moyenne des temporels des lots pondérée par le budget | **feuille** : sur ses propres dates (baseline contractuelle, §11bis, sinon prévues) ; **parent** : moyenne des temporels de ses enfants, **avec les mêmes poids que le physique** ; sur ses propres dates si ses enfants sont incomplètement chiffrés |
| **5. Écart** | temporel − physique, du lot et du projet | même formule, pour **chaque élément** |
| **6. Indice de santé** | délais 40 % + rapports 25 % + blocages 20 % + incidents 15 % | inchangé ; si l'écart est indisponible, calculé sur les trois autres scores, pondérations redistribuées, et affiché **« partiel »** |

**Règles de saisie.**
- **Aucune mesure sur une feuille en mode quantité sans unité ni quantité prévue** : « renseignez
  la quantité prévue ». La feuille est signalée « à compléter ». Tant qu'elle n'a rien de mesuré,
  son physique vaut 0 %.
- La quantité réalisée est alimentée par les rapports journaliers approuvés et par la mise à jour
  tracée, comme aujourd'hui. Chaque saisie garde son auteur, sa date, ses valeurs avant et après
  et son commentaire.

## 10. Statuts et suppression

**Chaque élément est jugé sur lui-même** : son propre écart (§9) et la date de fin de ses propres
dates. Un enfant en retard ne met pas son parent en retard ; le parent le **signale** (« 3 en
retard »).

| Situation | Statut |
|---|---|
| L'élément ou un de ses ancêtres est suspendu | Suspendu |
| Feuille clôturée ; parent dont tous les enfants sont clôturés | Clôturé |
| Fin prévue dépassée, ou écart au-delà du seuil de retard | En retard |
| Commencé, ou date de début atteinte | En cours |
| Sinon | Planifié |

Le seuil de retard reprend celui du score de délais de F3. Le prototype utilise 10 points pour
l'illustration.

- **Suspendre** se fait sur n'importe quel élément et descend vers tous ses descendants.
- **Clôturer** ne se fait que sur une feuille, et met son avancement à 100 %. Pas de clôture en cascade.

**Suppression**, toujours logique (Socle commun) :

| Cas | Règle |
|---|---|
| Élément sans mesure en dessous | Suppression de l'élément et de son sous-arbre |
| Élément commencé | Suppression interdite : on le **désactive** (`est_actif`) ; il sort des calculs et garde son historique. Motif obligatoire |
| Dernier enfant retiré | Le parent redevient une feuille (§8) |

## 11. Les dates

Chaque élément a **ses propres dates prévues et sa baseline**, parents compris. La baseline est
posée à la première saisie des dates et **ne bouge jamais**.

**Vers le bas, le parent encadre.** Les dates d'un parent bornent celles de ses enfants, du projet
jusqu'à la feuille. On ne peut pas resserrer un parent en deçà d'un de ses enfants.

**Vers le haut, l'enfant peut prolonger.** Si la saisie d'un enfant dépasse son parent, à la
planification comme à la reprogrammation, une **alerte** liste les éléments qu'il faudrait
prolonger. Si on confirme, le parent est prolongé, puis son propre parent si besoin, **jusqu'au
projet**.

1. Une prolongation est une **reprogrammation du parent** : elle entre dans l'historique avec le
   motif de l'enfant (« Prolongé par le report de Murs RDC »). La dérive par rapport à la baseline
   contractuelle (§11bis) apparaît à chaque niveau, et l'**alerte au DG au-delà de 30 jours**
   s'applique à chacun.
2. **Prolonger le projet, ou un élément commencé, exige la permission `projets.prolonger`**
   (donnée par défaut au chef de projet ; le DG a toutes les permissions), avec
   un motif. Les autres utilisateurs voient l'alerte et ne peuvent qu'annuler.
3. **Un parent ne rétrécit jamais tout seul** : si un enfant finit plus tôt, le parent garde ses
   dates.
4. Une fois fixées, les dates ne changent que par **reprogrammation** (RG-11) : motif choisi dans
   la liste et justification d'au moins 30 caractères.

## 11bis. Engagements initiaux, courants et avenants

**Vocabulaire.** Une **modification tracée** est un choix interne, avec motif (§12.2). Un
**avenant** est un **acte signé avec le client**, qui change l'engagement envers lui.

**Trois couches de dates par élément.**

| Couche | Ce que c'est | Qui la change |
|---|---|---|
| Baseline v0 | l'engagement initial, posé à la première saisie | personne, jamais |
| **Baseline contractuelle** | l'engagement en vigueur ; elle part de v0 | **seulement un avenant signé** |
| Dates prévues | le planning de travail | la reprogrammation (RG-11) |

- **L'alerte au DG** (au-delà de 30 jours) mesure la dérive des dates prévues **sur la baseline
  contractuelle** : un délai accordé par le client n'est plus compté comme un retard.
- **Le temporel de F3** (formule 4, §9) se calcule sur la baseline contractuelle.
- **La dérive totale sur v0** reste affichée pour information : « +45 j sur l'initial, dont 30
  accordés par avenant ».

**Le même principe vaut pour les autres engagements.**

| Engagement | Initiale (jamais modifiée) | Courante | Change par |
|---|---|---|---|
| Dates | baseline v0 | baseline contractuelle | avenant signé |
| Montant | montant initial | montant courant | modification tracée ou avenant |
| Quantité prévue | quantité initiale | quantité courante | modification tracée ou avenant |

La pondération utilise le **montant courant**, l'avancement la **quantité courante** ; les valeurs
initiales servent à l'historique et à l'analyse des écarts.

**Un avenant** a un numéro, une date de signature, un objet, le document signé, et la liste des
éléments concernés avec leurs nouvelles valeurs contractuelles (dates, montants, quantités). Il suit
les règles du §11 : il encadre vers le bas, prolonge vers le haut, avec l'aperçu des effets. Il
exige la permission **`projets.avenants_gerer`** (nouvelle).

**Quantité prévue d'une feuille commencée.**
1. Aperçu de l'effet sur la feuille et sur le projet, puis motif : c'est une modification tracée,
   rattachée à un avenant s'il y en a un.
2. **Refusée en dessous du réalisé** : soit le réalisé est faux et on le corrige, soit la feuille
   est terminée et on la clôture.
3. **L'unité ne change plus** une fois la feuille commencée ; pour changer d'unité, on détaille la
   feuille ou on en crée une autre.
4. Permission : `projets.chiffrer`, élargie à « chiffrer et métrer ».

## 12. Modifier un projet

**12.1 La vue en arbre.** Le tableau à plat reste l'outil de **création** et de l'**ajout en
masse** de nouvelles branches (y compris par Excel, rapproché par chemin). La **modification** se
fait dans la vue en arbre, par des gestes explicites : renommer, ajouter, déplacer, détailler,
insérer un niveau, clôturer, suspendre, désactiver. Modifier une cellule du tableau serait
ambigu : renommer ou déplacer ?

**12.2 Modification tracée.** Toute modification qui touche un **élément commencé** (ajout sous
lui, déplacement, changement de montant ou de quantité prévue, désactivation, détail) est une
**modification tracée** : motif obligatoire et entrée dans l'historique. *Le mot « avenant » est
réservé à l'acte signé avec le client (§11bis).*

**12.3 Renommer, ajouter.** Libres, dans le respect de A-1, A-2 et A-6. Ajouter un enfant sous une
feuille non commencée en fait un parent : son montant devient son enveloppe.

**12.4 Déplacer.** On ne déplace un élément que sous un parent du **niveau juste au-dessus** ou du
**même niveau** (récursion), sans enfreindre A-2 ni A-6. Avant de confirmer, un **aperçu des
effets** liste :
- les feuilles qui changent de **déclarant** (périmètre, §13) ou de **titulaire** hérité ;
- l'avancement de l'ancien et du nouveau parent, avant et après ;
- l'ancien parent qui redevient une feuille, le nouveau qui devient un parent ;
- les prolongations qu'imposent les dates de l'élément déplacé (règles du §11).

**12.5 Détailler une feuille commencée.** La feuille devient un parent ; un premier enfant,
**« Réalisé avant détail »**, reçoit ses mesures, est clôturé à 100 % et reçoit un montant
**égal à ce qui a été réalisé** : montant × avancement. Le reste du montant devient l'enveloppe à
répartir sur les nouveaux enfants. L'avancement du parent est **identique avant et après**
(4 M acquis sur une enveloppe de 10 M = 40 %).

**12.6 Insérer un niveau dans un projet rempli.** Un élément intermédiaire (« Général » par
défaut) est créé sous chaque parent concerné ; les anciens enfants passent dessous. L'arbre reste
valide à chaque instant ; on renomme ou on scinde ensuite.

**12.7 Modifier un montant ou l'exécution.** L'effet est affiché avant de confirmer : avancement
du projet avant et après pour un montant, feuilles touchées pour un chef ou un titulaire.

## 13. Ce qui se rattache à l'arbre

**La mesure pointe vers une feuille** : lignes de quantités du journal, mise à jour manuelle de
l'avancement, historique des dates, équipe affectée, dépendance entre tâches.

**Le périmètre pointe vers n'importe quel élément** et vaut pour tout ce qui est en dessous :
rapport journalier, chef de chantier affecté, blocage, alerte de retard.

1. **Le périmètre le plus précis l'emporte.** Un chef a « Bâtiment A », un autre « Maçonnerie »,
   sous Bâtiment A : le chef de Maçonnerie déclare « Murs RDC », celui de Bâtiment A ne le peut
   pas. Une quantité n'est jamais déclarée deux fois.
2. **Le rapport global du projet** couvre tout ce qu'aucun périmètre ne couvre.
3. Le déclarant d'une feuille est celui **du jour du rapport**. Les anciens rapports gardent leur
   photographie de la structure.

## 13bis. Affectations, équipes et permissions

Les **droits** (qui peut faire quoi) et les **équipes** (qui travaille où) restent deux choses
distinctes, comme aujourd'hui.

**Affectation d'un collaborateur.**
1. Une affectation relie un collaborateur à un projet, avec un **rôle** et des dates.
2. **Le rôle est propre à l'affectation** : il prend par défaut le rôle de plateforme du
   collaborateur, mais peut différer d'un projet à l'autre (conducteur de travaux ici, chef de
   chantier là). *Cela revient sur l'arbitrage du 16/10/2026, qui alignait toujours le rôle sur le
   projet sur le rôle de plateforme.*
3. **Son périmètre est un ou plusieurs éléments de l'arbre** ; aucun signifie tout le projet. Les
   champs `lot` et `zone` disparaissent.

**Une permission s'exerce dans le périmètre.** Un collaborateur peut faire une action sur un
élément **si le rôle de son affectation a la permission ET si l'élément est dans son périmètre**
(l'élément lui-même ou un de ses ancêtres). Les rôles de portée Entreprise ont tout le projet pour
périmètre.

**Le déclarant d'une feuille se déduit des affectations** : parmi les collaborateurs qui ont
`chantier.rediger` sur un périmètre contenant la feuille, le périmètre le plus précis l'emporte.
Le rapport est tenu **par périmètre et par jour**, pas par personne : un chef et son adjoint qui
partagent un périmètre écrivent le même rapport.

**Plus aucune règle ne dépend du nom d'un rôle.** Les exceptions codées deviennent des permissions :

| Exception codée aujourd'hui | Permission | Par défaut |
|---|---|---|
| Prolonger le projet ou un élément commencé « CP et DG » | `projets.prolonger` | CP |
| Le CT peut retirer un membre (`PeutRetirerDuProjet`) | `projets.retirer_membres` | CP, CT |
| Le CC est refusé sur la mise à jour d'avancement | `projets.mesurer` (saisie hors rapport) | CP, CT |
| *(nouveau)* ajouter, déplacer, détailler, insérer un niveau, désactiver | `projets.decouper` | CP |
| *(nouveau)* fixer les montants et les enveloppes | `projets.chiffrer` | CP |
| *(nouveau)* planifier et reprogrammer les dates | `projets.planifier` | CP, CT |

Le DG a toutes les permissions. Une entreprise qui veut, par exemple, que ses conducteurs
prolongent les délais coche une case.

**Ce que chacun voit.** Les permissions ci-dessus disent ce qu'on peut **faire** ; la lecture suit
la même logique.
- **`projets.voir_tout`** (nouvelle) donne la vue de **tout le projet**. Par défaut : CP, CT, MOA,
  MOE, consultant.
- **Sans elle**, on voit **son périmètre** et le **chemin** qui y mène (les intitulés des ancêtres,
  sans leurs données), rien d'autre. C'est le cas par défaut du chef de chantier, et d'un futur
  rôle de sous-traitant.
- **`projets.voir_montants`** reste indépendante : elle s'applique à ce que l'on voit.
- **Le journal** suit la même règle : sans `voir_tout`, on lit les parties de son périmètre et les
  parties communes.

**Équipes.**
1. Une équipe reste propre au projet : nature (interne ou sous-traitante), corps d'état, chef
   d'équipe, membres avec ou sans compte.
2. **Elle s'affecte à n'importe quel élément** et vaut pour tout le sous-arbre.
   `AffectationEquipeActivite` devient une affectation d'équipe à un élément.
3. **Une affectation posée plus bas remplace celle d'en haut** pour cette branche : même règle
   « le plus précis l'emporte » que pour les périmètres et le titulaire.
4. `Activite.colaborateur` et `Activite.equipe`, en double avec les affectations et les équipes,
   disparaissent.

## 13ter. Le journal de chantier

**Un seul journal par projet et par jour**, écrit à plusieurs mains, qui monte une seule fois en
approbation. Les périmètres disent **qui écrit quelle partie**.

1. **Parties.** Chaque feuille appartient à la partie du rédacteur dont le périmètre est le plus
   précis (§13bis) ; personne n'écrit la ligne d'un autre. Les feuilles non couvertes forment la
   partie du rapport global.
2. **Feuilles proposées** : celles **actives ce jour-là** (leurs dates couvrent le jour, ou elles
   sont commencées et non clôturées). Une feuille cochée comme travaillée sans quantité exige une
   observation.
3. **Parties communes** (météo, horaires, arrêt) : remplies une fois, par n'importe quel rédacteur.
   Les effectifs se déclarent par équipe, pré-remplis par les équipes affectées.
4. **Photographie** : la tranche de l'arbre du jour (identifiant, chemin, niveau, unité, prévu,
   cumul de la veille, théorique, mode, titulaire, équipes).
5. **Chef absent** : sa partie n'est pas renseignée ; on passe par une **suppléance**, une
   affectation datée au même périmètre.

**Circuit, par permissions.**

| Étape | Unité | Qui |
|---|---|---|
| Rédiger, marquer « prête » | partie | `chantier.rediger`, périmètre le plus précis |
| Soumettre | journal | n'importe quel rédacteur, quand les parties attendues sont prêtes ou signalées absentes |
| Viser | **partie** | `chantier.viser` (nouvelle) sur un périmètre qui contient **toute** la partie ; à défaut, ou passé 24 h, sur tout le projet |
| Journal visé | journal | automatiquement, quand toutes les parties sont visées |
| Approuver | journal | `chantier.valider` sur tout le projet ; les quantités remontent dans F3 et toute la chaîne d'ancêtres est recalculée |

- Les parties communes ne sont pas visées séparément : l'approbation les couvre.
- **Rejet d'une partie** : seule cette partie est rouverte pour son rédacteur ; les autres gardent
  leur visa. Une partie visée est verrouillée.
- **Partie vide** : visée comme constat d'absence, sans bloquer le journal.
- Un bouton « Viser toutes mes parties » garde un seul geste quand un seul conducteur couvre tout
  le projet.
- Rapports attendus et relance de 17 h 30 : un journal par projet et par jour ouvré, comme
  aujourd'hui ; la relance vise les rédacteurs dont la partie manque.

## 13quater. Les modes d'exécution

Aujourd'hui, trois modes de base sont codés (régie, sous-traitance structurée, informelle) et une
entreprise ne crée que des libellés qui s'y rattachent. **Un mode devient une donnée**, que
l'entreprise définit librement **dans un cadre** : elle choisit le nom et l'assemblage, parmi des
options que la plateforme sait traiter.

**Un mode, c'est trois réglages.**

| Réglage | Options (codées par la plateforme) |
|---|---|
| Mesure d'une feuille | quantité du jour (une ligne par feuille) ; production par intervenant (plusieurs lignes : intervenant, quantité, tarif) |
| Briques du journal | effectifs, matériaux, livraisons, équipements, présence du titulaire : chacune **obligatoire**, **facultative** ou **absente** |
| Rémunération (module 3) | au temps passé ; à la tâche (quantité × tarif) ; au forfait, par situations |

La mesure vaut pour chaque feuille ; les briques valent pour la partie du journal. Une partie qui
mêle plusieurs modes prend l'union de leurs briques, « obligatoire » l'emportant.

**Règles de cohérence d'un mode.**

| Rémunération | Exige |
|---|---|
| Au temps passé | brique Effectifs obligatoire |
| À la tâche | mesure « production par intervenant » (le tarif est sur la ligne) |
| Au forfait | mesure « quantité du jour » |

*Pas de prix unitaire sur la feuille (décision du 26/10/2026) : il confondrait le prix du bordereau
du client (vente) et le tarif du tâcheron (achat). Le tarif d'exécution relève du contrat passé
avec le titulaire, donc du module 3.*

**Ce que l'entreprise peut faire.**
- Créer autant de modes qu'elle veut, sous ses propres noms (uniques, comparés par `cle_comparaison`).
- Personnaliser un mode plateforme (copie liée à l'original), sans le modifier ni le supprimer.
- Choisir le mode par défaut de ses projets.
- Désactiver un mode utilisé, plutôt que le supprimer.
- Le tout avec la permission **`projets.modes_gerer`** (nouvelle) : un mode change ce que le
  journal exige, c'est plus lourd que d'ajouter un nom de lot.

Elle ne peut pas inventer une mesure, une brique ou une rémunération : elles sont ajoutées par la
plateforme quand un besoin réel apparaît. Un générateur de formulaires est écarté.

**Irréversibilité (RG-03) sur l'arbre.**
1. Le mode **effectif** d'une feuille commencée ne change plus, ni directement, ni par héritage.
   Changer le mode d'un parent est refusé si une de ses feuilles commencées en hérite ; l'aperçu
   des effets les liste.
2. Un mode utilisé par une feuille commencée garde sa mesure et sa rémunération ; seules ses
   briques peuvent encore passer d'obligatoire à facultative ou l'inverse. Pour changer davantage,
   on crée un nouveau mode. Les anciens journaux restent intacts grâce à leur photographie.

## 13quater-bis. Le journal hors connexion

Aujourd'hui, le web recopie le journal en cours dans le navigateur, sur une copie unique par
projet et par jour, et « la copie la plus récente l'emporte » ; l'application Android utilisera un
SQLite chiffré. Avec un journal à plusieurs mains (§13ter), cette règle écraserait les parties des
autres. Elle est remplacée :

1. **Synchronisation par partie**, pas par journal : chacun n'envoie que les lignes de ses feuilles
   et les effectifs de ses équipes. Une feuille n'ayant qu'un rédacteur, deux personnes ne
   modifient jamais la même ligne.
2. **Parties communes** (météo, horaires, arrêt) : synchronisées champ par champ, la dernière
   saisie l'emporte, avec trace dans l'historique.
3. **Le serveur est la référence.** Chaque envoi porte la version de la partie sur laquelle il a été
   écrit. Si personne n'y a touché, il est accepté. Si la partie a été visée ou le journal approuvé
   pendant la coupure, il est **refusé** ; la copie locale est conservée et signalée (« non
   envoyée : partie déjà visée par … »). Rien n'est fusionné en silence.
4. **Feuille sortie de la partie pendant la coupure** (déplacée, désactivée, détaillée) : seule sa
   ligne est refusée, avec la raison ; le reste passe.
5. **Préparation en cache** : à chaque connexion, l'application télécharge la préparation du jour et
   du lendemain (feuilles actives de la partie, cumuls de la veille, équipes). Sans elle, la
   saisie hors ligne est impossible : « connectez-vous une fois pour préparer la journée ».
6. **Soumettre hors ligne** est une intention en attente, exécutée au retour du réseau si les
   conditions tiennent toujours, sinon signalée. Les alertes immédiates et les photos partent au
   retour du réseau.

## 13quater-ter. Les alertes de retard

Aujourd'hui, les alertes sont calculées par lot (seuils de 5, 15 et 25 points d'écart), dédupliquées
avec escalade, et adressées par nom de rôle (CT et CP, puis DO, puis DG). Sur l'arbre, alerter sur
chaque élément en retard multiplierait les alertes d'une même cause.

1. **Où naît une alerte : réglage du gabarit.** Chaque niveau porte une case **« Alerter à ce
   niveau »** ; par défaut, le niveau qui joue le rôle du lot. Le projet garde son alerte globale,
   déclenchée par l'indice de santé. C'est un réglage explicite, pas un nom.
2. **Un jalon** dont la date passe sans qu'il soit atteint alerte **toujours**, quel que soit son
   niveau.
3. **Les feuilles en retard** d'une branche n'ont pas leur propre alerte : elles figurent parmi les
   **causes** de l'alerte du niveau suivi, classées par leur poids dans le retard (montant ×
   écart), avec les absences, blocages et incidents du périmètre.
4. **Inchangés** : les trois seuils, la déduplication avec escalade, le cycle Ouverte, En cours,
   Résolue, Ignorée.
5. **Destinataires, sans nom de rôle** : la permission **`projets.alertes_voir`**, exercée dans le
   périmètre, et un **seuil personnel** (« me prévenir à partir de Modéré, Élevé ou Critique »).
   Par défaut : CT et CP à Modéré, DO à Élevé, DG à Critique. Une alerte part vers ceux qui ont la
   permission sur un périmètre contenant l'élément et dont le seuil est atteint.
6. Traiter une alerte exige **`projets.alertes_traiter`**.

## 13quinquies. Compléments du suivi

**1. Saisie en masse.**
- **Import des quantités et montants (DQE)** sur un projet existant : colonnes des niveaux, puis au
  choix Unité, Quantité, Montant, Début, Fin. Une colonne « Prix unitaire » sert seulement à
  calculer le montant (Q × PU) à l'import ; elle n'est pas conservée (§13quater).
- Rapprochement **par chemin** : une ligne reconnue met la feuille à jour selon le §11bis
  (modification tracée si commencée, refus sous le réalisé, unité figée) ; une ligne inconnue est
  proposée comme nouvelle branche ; une feuille absente du fichier n'est jamais touchée.
- Un **bilan** précède l'application : mises à jour, nouvelles feuilles, refus motivés.
- **Dupliquer une branche** : copie la structure, les unités, les quantités, les montants, le mode
  et le titulaire ; ni mesures, ni dates, ni baselines, ni affectations, ni équipes. La copie se
  pose sous un parent autorisé (§12.4) et se nomme aussitôt (A-6).

**2. Dépassement.** Réalisé supérieur au prévu : le calcul reste plafonné à 100 %, la feuille
affiche « dépassement +N % ». Le journal avertit (« dépasse le prévu de 30 m² : confirmer »), sans
jamais bloquer. Atteindre 100 % ne clôture pas : la feuille propose « Clôturer ? ».

**3. Réouverture.** Rouvrir une feuille clôturée exige **`projets.rouvrir`** (nouvelle) et un
motif. L'avancement redevient mesuré, la fin réelle est effacée, les statuts des parents sont
recalculés ; l'historique garde la clôture et la réouverture.

**4. Dates réelles**, calculées et corrigeables par modification tracée :
- début réel = date du premier journal portant une mesure sur la feuille (date du chantier, pas de
  l'approbation) ;
- fin réelle = date de la clôture ;
- parent : le plus tôt des débuts réels de ses enfants ; fin réelle quand tous sont clôturés.

**5. Dépendances.** Un seul type de lien (B commence après la fin de A), **plusieurs
prédécesseurs** possibles, entre feuilles ; les boucles sont refusées. Reprogrammer A liste dans
l'aperçu les successeurs qui commenceraient trop tôt, avec **« décaler aussi »** coché par défaut ;
le décalage suit les règles du §11. Jamais de décalage silencieux.

**6. Jalons.** Une feuille **sans durée** (début = fin) dont la mesure est **« atteint / non
atteint »** ; l'atteindre, c'est la clôturer. Elle pèse son montant (nul pour une réception, non
nul pour un jalon de paiement), est en retard si sa date passe sans qu'elle soit atteinte, et ne
bouge contractuellement que par avenant.

**7. Historique de l'avancement.** À chaque approbation de journal et chaque semaine, chaque
élément est photographié (physique, temporel, écart, montant courant) : courbe en S, tendance,
**fin estimée** (reste à faire ÷ vitesse des quatre dernières semaines). La fin estimée est
affichée seulement ; elle ne modifie jamais une date.

**8. La ligne du journal s'adapte à la feuille.** Trois formes de mesure par feuille (§9) :
quantité, pourcentage déclaré, jalon. Le journal demande respectivement la quantité du jour,
l'**avancement cumulé déclaré (%)**, ou **« atteint aujourd'hui »**. Le mode d'exécution (§13quater)
ne règle la forme de la ligne — quantité du jour ou production par intervenant — que pour les
feuilles en quantité.

## 14. Reprise de l'existant

L'application n'a **pas d'utilisateurs en production** : aucune donnée n'est à préserver. On
**remplace** `Lot` et `Activite` par les nouvelles tables, sans migration de reprise ; les données
de test du serveur sont vidées ; `creer_tenant_demo` est reconstruit sur le nouveau modèle, avec
plusieurs niveaux et au moins une récursion.

## 15. Ce qui reste à traiter

| Sujet | Contenu |
|---|---|
| Module 3 (rémunération) | Contrats avec les titulaires, tarifs d'exécution, prix du bordereau client |
| Contrat d'API | Remplacement de `/lots/` et `/activites/` |
| Écrans | Vue en arbre, tableau de démarrage, gestion des listes et des modèles |
| Données réelles | Phases, lots supplémentaires et modèles, à fournir par le Product Owner |

## 16. Documents à mettre à jour

- **MLD** : tables `element`, `niveau` (gabarit du projet), `modele_decoupage` et ses niveaux et
  lignes, `liste_valeurs` et ses valeurs ; retrait de `lot` et `activite` ; liens vers l'élément
  des tables qui pointaient vers eux.
- **SFD F3** : formules 2 à 6 remplacées par le §9 ; statuts par le §10.
- **SFD F1** : lots et activités remplacés par le découpage en arbre.
- **MCD**, conventions d'API et maquettes, une fois le §15 traité.

## 17. Avant l'implémentation

1. **Confrontation aux sources du client.** Le CDC est une **base**, pas une limite : le produit
   peut aller au-delà (décision du 26/10/2026). La relecture du CDC, du MVP et du backlog sert
   donc à vérifier que **rien de ce qu'ils exigent n'est perdu**, et à consigner chaque écart avec
   sa raison. Le **Socle commun**, lui, reste non négociable : langue, formats, suppression
   logique, journal d'audit immuable, performance, charte des messages.
2. **Validation par le Product Owner** de ce document.
3. **Chiffrage.** Découper la refonte en chantiers (modèle de données, tableau de démarrage, vue en
   arbre, calculs F3, journal, équipes, frontend), estimer chacun, puis décider **quand** la
   faire au regard de l'échéance du 31/12/2026.
