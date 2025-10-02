#!/usr/bin/env python3
"""
Générateur d'application de pointage avec Claude 4.X
"""

import os
import anthropic

def main():
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    # Spécifications complètes pour l'application de pointage
    specifications = '''
SPÉCIFICATIONS COMPLÈTES - APPLICATION DE POINTAGE

## Contexte et Objectifs
- Application web de gestion du temps de travail pour entreprise
- Interface d'administration pour gérer les pointages des employés
- Sécurité renforcée avec les meilleures pratiques 2024
- Interface moderne, responsive et accessible

## Architecture Technique
- Backend: Flask (Python) avec SQLAlchemy
- Frontend: HTML/CSS/JavaScript vanilla avec sécurité XSS
- Base de données: SQLite (pour simplicité déploiement)
- Déploiement: Compatible avec les plateformes cloud modernes

## Fonctionnalités Principales

### 1. Authentification et Sécurité
- Connexion sécurisée avec numéro d'employé et mot de passe
- Sessions sécurisées avec cookies HttpOnly
- Protection XSS avec DOMPurify
- Validation et sanitisation de toutes les données
- Gestion des erreurs robuste
- Rate limiting sur les API

### 2. Gestion des Employés
- CRUD complet des employés
- Numéros d'employé flexibles (ADMIN001, Munier, EMP001, etc.)
- Rôles: employé standard et administrateur
- Statut actif/inactif

### 3. Système de Pointage
- 4 créneaux par jour: Arrivée matin, Sortie midi, Retour midi, Sortie soir
- Calcul automatique des heures travaillées
- Historique complet des pointages
- Interface intuitive pour les employés

### 4. Interface d'Administration
- Dashboard avec statistiques temps réel
- Gestion complète des pointages (CRUD)
- Filtres avancés (employé, date, période)
- Actions en lot (suppression multiple)
- Export des données
- Interface responsive et accessible

### 5. Sécurité et Performance
- Protection contre les injections SQL
- Validation côté client et serveur
- Gestion d'erreurs gracieuse
- Loading states et feedback utilisateur
- Pagination pour les grandes listes
- Cache intelligent

## Spécifications Techniques Détaillées

### Backend (Flask)
- Structure modulaire avec blueprints
- Modèles SQLAlchemy avec relations
- API REST sécurisée
- Middleware de sécurité
- Logging et monitoring

### Frontend
- Design moderne avec CSS Grid/Flexbox
- JavaScript ES6+ avec modules
- Composants réutilisables
- Accessibilité WCAG 2.1
- Progressive Web App features

### Base de Données
- Modèle Employee: id, employee_number, first_name, last_name, email, password_hash, is_admin, is_active, created_at
- Modèle TimeEntry: id, employee_id, date, morning_in, lunch_out, lunch_in, evening_out, morning_hours, afternoon_hours, total_hours, created_at, updated_at
- Index optimisés pour les requêtes fréquentes
- Contraintes d'intégrité

### API Endpoints
- POST /api/auth/login - Connexion
- POST /api/auth/logout - Déconnexion
- GET /api/employees - Liste employés
- GET /api/admin/timeentries - Liste pointages avec filtres
- POST /api/admin/timeentries - Créer pointage
- PUT /api/admin/timeentries/{id} - Modifier pointage
- DELETE /api/admin/timeentries/{id} - Supprimer pointage
- POST /api/admin/timeentries/bulk - Actions en lot

### Interface Utilisateur
- Page d'accueil avec navigation claire
- Interface de connexion sécurisée
- Dashboard administrateur avec KPI
- Interface de gestion des pointages avec:
  * Tableau paginé et filtrable
  * Modal de création/modification
  * Actions en lot
  * Feedback temps réel
  * Design responsive

## Critères de Qualité
- Code propre et documenté
- Performance optimisée
- Sécurité maximale
- UX/UI moderne
- Accessibilité complète
- Déploiement simple

## Contraintes
- Compatible Python 3.11+
- Pas de dépendances complexes
- Déploiement sur cloud (Manus, Render, Vercel)
- Temps de chargement < 2s
- Support navigateurs modernes

Créer une application complète, robuste et prête pour la production qui respecte toutes ces spécifications.
'''

    response = client.messages.create(
        model='claude-3-5-sonnet-20241022',  # Version la plus récente
        max_tokens=8000,
        messages=[{
            'role': 'user', 
            'content': f'''En tant qu'expert développeur full-stack, créez une application de pointage complète et robuste selon ces spécifications:

{specifications}

Générez le code complet pour:
1. app.py - Application Flask principale avec toutes les routes API
2. models.py - Modèles de données SQLAlchemy
3. static/index.html - Page d'accueil moderne
4. static/admin.html - Interface d'administration complète et sécurisée
5. requirements.txt - Dépendances Python

Le code doit être:
- Prêt pour la production
- Sécurisé contre toutes les vulnérabilités courantes
- Performant et optimisé
- Moderne et maintenable
- Complètement fonctionnel

Utilisez les meilleures pratiques 2024 et assurez-vous que tout fonctionne parfaitement ensemble.

Répondez avec le code complet de chaque fichier, séparé par des marqueurs clairs.'''
        }]
    )

    print('=== RÉPONSE CLAUDE 4.X ===')
    print(response.content[0].text)

if __name__ == '__main__':
    main()
