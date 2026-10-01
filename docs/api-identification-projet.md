# Nouveau projet : identification seule

Une entreprise authentifiée crée son projet au clic sur « Créer le projet ».
La connexion seule ne crée aucun projet automatiquement.
Le jeton Bearer détermine le créateur et le schéma de l'entreprise ; ne pas
envoyer d'identifiant d'entreprise. Les permissions du module PROJETS restent requises.
La direction (propriétaire, DG, administrateur) peut créer sans chef ;
la création par un collaborateur conserve l'obligation de sélectionner un chef.

```http
POST /api/v1/projets/
Authorization: Bearer <access>
Content-Type: application/json
```

```json
{
  "nom": "Immeuble Les Palmiers R+5",
  "type_projet": "BATIMENT_RESIDENTIEL",
  "ville": "Abidjan",
  "maitre_ouvrage": "Entreprise cliente",
  "maitre_oeuvre": "Cabinet d'études"
}
```

Réponse 201 : projet avec UUID, référence automatique PRJ-AAAA-NNN,
créateur et entreprise. Sans planning ni équipe, dates et chef valent null.
Nom, ville et maître d'ouvrage ne peuvent être vides. Le type utilise les
choix de GET `/api/v1/projets/contexte-creation/` ; le contrat historique
conserve BATIMENT_RESIDENTIEL comme valeur par défaut si le type est omis.
Maître d'œuvre facultatif. Un UUID `client` existant peut remplacer le texte
`maitre_ouvrage`, sans envoyer les deux.

| Action | Route | Statut |
| --- | --- | --- |
| Créer | POST /api/v1/projets/ | 201 |
| Lister | GET /api/v1/projets/ | 200 |
| Consulter | GET /api/v1/projets/{id}/ | 200 |
| Modifier | PATCH /api/v1/projets/{id}/ | 200 |
| Supprimer logiquement | DELETE /api/v1/projets/{id}/ | 204 |

Compléter ensuite par PATCH avec les dates prévues, le budget et
`chef_projet_id`. Ne pas envoyer `chef_projet_id: null` : omettre ce champ
tant qu'aucun chef n'est choisi. Les invitations et affectations utilisent
leurs routes existantes. Les dates doivent être ordonnées si toutes deux renseignées.

Migration additive : `python manage.py migrate_schemas` pour appliquer
les changements à tous les schémas. Aucun planning fictif ni affectation
automatique du dirigeant. Le formulaire complet existant reste accepté.

Pour apprendre : visualiser le flux, prédire les réponses, vérifier les tests,
puis expliquer à un pair la différence entre créateur et responsable.
Les champs nullable sont documentés par [Django](https://docs.djangoproject.com/en/5.2/ref/models/fields/),
la validation et la modification partielle par [DRF](https://www.django-rest-framework.org/api-guide/serializers/).
