#!/usr/bin/env python3
"""
Application de Pointage - Générée par Claude 4.X
Application Flask sécurisée pour la gestion du temps de travail
"""

import os
import logging
from datetime import datetime, date, time, timedelta
from functools import wraps
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import BadRequest
import re

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialisation de l'application
app = Flask(__name__, static_folder='../static', static_url_path='')

# Configuration sécurisée
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-key-change-in-production'),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///timetracking.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={
        'pool_pre_ping': True,
        'pool_recycle': 300,
    },
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_TIME_LIMIT=None,
)

# Initialisation des extensions
db = SQLAlchemy(app)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Modèles de données
class Employee(db.Model):
    """Modèle pour les employés"""
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    time_entries = db.relationship('TimeEntry', backref='employee', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Employee {self.employee_number}: {self.first_name} {self.last_name}>'
    
    def set_password(self, password: str) -> None:
        """Définit le mot de passe hashé"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """Vérifie le mot de passe"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        data = {
            'id': self.id,
            'employee_number': self.employee_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        return data

class TimeEntry(db.Model):
    """Modèle pour les entrées de temps"""
    __tablename__ = 'time_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    
    # Heures de pointage
    morning_in = db.Column(db.Time)
    lunch_out = db.Column(db.Time)
    lunch_in = db.Column(db.Time)
    evening_out = db.Column(db.Time)
    
    # Heures calculées
    morning_hours = db.Column(db.Float, default=0.0)
    afternoon_hours = db.Column(db.Float, default=0.0)
    total_hours = db.Column(db.Float, default=0.0)
    
    # Métadonnées
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Contraintes
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date', name='unique_employee_date'),
        db.Index('idx_employee_date', 'employee_id', 'date'),
    )
    
    def __repr__(self):
        return f'<TimeEntry {self.employee_id} - {self.date}>'
    
    def calculate_hours(self) -> None:
        """Calcule les heures travaillées"""
        self.morning_hours = 0.0
        self.afternoon_hours = 0.0
        
        # Calcul des heures du matin
        if self.morning_in and self.lunch_out:
            morning_delta = datetime.combine(self.date, self.lunch_out) - datetime.combine(self.date, self.morning_in)
            self.morning_hours = round(morning_delta.total_seconds() / 3600, 2)
        
        # Calcul des heures de l'après-midi
        if self.lunch_in and self.evening_out:
            afternoon_delta = datetime.combine(self.date, self.evening_out) - datetime.combine(self.date, self.lunch_in)
            self.afternoon_hours = round(afternoon_delta.total_seconds() / 3600, 2)
        
        # Total
        self.total_hours = round(self.morning_hours + self.afternoon_hours, 2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}" if self.employee else None,
            'employee_number': self.employee.employee_number if self.employee else None,
            'date': self.date.isoformat() if self.date else None,
            'morning_in': self.morning_in.strftime('%H:%M') if self.morning_in else None,
            'lunch_out': self.lunch_out.strftime('%H:%M') if self.lunch_out else None,
            'lunch_in': self.lunch_in.strftime('%H:%M') if self.lunch_in else None,
            'evening_out': self.evening_out.strftime('%H:%M') if self.evening_out else None,
            'morning_hours': self.morning_hours,
            'afternoon_hours': self.afternoon_hours,
            'total_hours': self.total_hours,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

# Utilitaires de sécurité
def validate_employee_number(employee_number: str) -> bool:
    """Valide le format du numéro d'employé"""
    if not employee_number or len(employee_number) > 50:
        return False
    # Permet lettres, chiffres, tirets et underscores
    return re.match(r'^[a-zA-Z0-9_-]+$', employee_number) is not None

def validate_email(email: str) -> bool:
    """Valide le format de l'email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def sanitize_string(value: str, max_length: int = 255) -> str:
    """Nettoie et valide une chaîne"""
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]

# Décorateurs
def login_required(f):
    """Décorateur pour vérifier l'authentification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return jsonify({'success': False, 'error': 'Authentification requise'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Décorateur pour vérifier les droits administrateur"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return jsonify({'success': False, 'error': 'Authentification requise'}), 401
        
        employee = Employee.query.get(session['employee_id'])
        if not employee or not employee.is_admin:
            return jsonify({'success': False, 'error': 'Droits administrateur requis'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# Routes principales
@app.route('/')
def index():
    """Page d'accueil"""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/admin')
def admin():
    """Interface d'administration"""
    return send_from_directory(app.static_folder, 'admin.html')

# API d'authentification
@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """Connexion utilisateur"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        employee_number = sanitize_string(data.get('employee_number', ''))
        password = data.get('password', '')
        
        if not employee_number or not password:
            return jsonify({'success': False, 'error': 'Numéro d\'employé et mot de passe requis'}), 400
        
        if not validate_employee_number(employee_number):
            return jsonify({'success': False, 'error': 'Format de numéro d\'employé invalide'}), 400
        
        # Recherche de l'employé (insensible à la casse)
        employee = Employee.query.filter(
            db.func.lower(Employee.employee_number) == employee_number.lower(),
            Employee.is_active == True
        ).first()
        
        if not employee or not employee.check_password(password):
            logger.warning(f"Tentative de connexion échouée pour: {employee_number}")
            return jsonify({'success': False, 'error': 'Identifiants invalides'}), 401
        
        # Connexion réussie
        session.permanent = True
        session['employee_id'] = employee.id
        session['is_admin'] = employee.is_admin
        
        logger.info(f"Connexion réussie pour: {employee.employee_number}")
        
        return jsonify({
            'success': True,
            'employee': employee.to_dict(),
            'is_admin': employee.is_admin
        })
        
    except Exception as e:
        logger.error(f"Erreur lors de la connexion: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Déconnexion utilisateur"""
    session.clear()
    return jsonify({'success': True, 'message': 'Déconnexion réussie'})

@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    """Vérification de l'état d'authentification"""
    if 'employee_id' in session:
        employee = Employee.query.get(session['employee_id'])
        if employee and employee.is_active:
            return jsonify({
                'authenticated': True,
                'employee': employee.to_dict(),
                'is_admin': employee.is_admin
            })
    
    return jsonify({'authenticated': False})

# API des employés
@app.route('/api/employees', methods=['GET'])
@admin_required
def list_employees():
    """Liste des employés (admin seulement)"""
    try:
        employees = Employee.query.filter_by(is_active=True).order_by(Employee.last_name, Employee.first_name).all()
        
        return jsonify({
            'success': True,
            'employees': [emp.to_dict() for emp in employees]
        })
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des employés: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

# API des pointages
@app.route('/api/timeentries', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def create_timeentry():
    """Créer un pointage"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        employee_id = session['employee_id']
        today = date.today()
        
        # Récupérer ou créer l'entrée du jour
        time_entry = TimeEntry.query.filter_by(employee_id=employee_id, date=today).first()
        if not time_entry:
            time_entry = TimeEntry(employee_id=employee_id, date=today)
            db.session.add(time_entry)
        
        # Mettre à jour les heures de pointage
        for field in ['morning_in', 'lunch_out', 'lunch_in', 'evening_out']:
            if field in data:
                time_str = data[field]
                if time_str:
                    try:
                        # Parser l'heure depuis ISO string ou format HH:MM
                        if 'T' in time_str:
                            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                            time_obj = dt.time()
                        else:
                            time_obj = datetime.strptime(time_str, '%H:%M').time()
                        setattr(time_entry, field, time_obj)
                    except ValueError:
                        return jsonify({'success': False, 'error': f'Format d\'heure invalide pour {field}'}), 400
        
        # Calculer les heures
        time_entry.calculate_hours()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pointage enregistré',
            'timeentry': time_entry.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la création du pointage: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

# API d'administration des pointages
@app.route('/api/admin/timeentries', methods=['GET'])
@admin_required
def admin_list_timeentries():
    """Liste des pointages avec filtres (admin seulement)"""
    try:
        # Paramètres de filtrage
        employee_id = request.args.get('employee_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = min(request.args.get('limit', 50, type=int), 100)
        offset = max(request.args.get('offset', 0, type=int), 0)
        
        # Construction de la requête
        query = TimeEntry.query.join(Employee)
        
        if employee_id:
            query = query.filter(TimeEntry.employee_id == employee_id)
        
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                query = query.filter(TimeEntry.date >= start_dt)
            except ValueError:
                return jsonify({'success': False, 'error': 'Format de date invalide pour start_date'}), 400
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                query = query.filter(TimeEntry.date <= end_dt)
            except ValueError:
                return jsonify({'success': False, 'error': 'Format de date invalide pour end_date'}), 400
        
        # Pagination et tri
        total_count = query.count()
        timeentries = query.order_by(TimeEntry.date.desc(), TimeEntry.id.desc()).offset(offset).limit(limit).all()
        
        return jsonify({
            'success': True,
            'timeentries': [entry.to_dict() for entry in timeentries],
            'total_count': total_count,
            'limit': limit,
            'offset': offset,
            'has_more': (offset + limit) < total_count
        })
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des pointages: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.route('/api/admin/timeentries', methods=['POST'])
@admin_required
def admin_create_timeentry():
    """Créer un pointage (admin seulement)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        employee_id = data.get('employee_id')
        date_str = data.get('date')
        
        if not employee_id or not date_str:
            return jsonify({'success': False, 'error': 'employee_id et date sont requis'}), 400
        
        # Vérifier l'employé
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'error': 'Employé non trouvé'}), 404
        
        # Parser la date
        try:
            entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        # Vérifier l'unicité
        existing = TimeEntry.query.filter_by(employee_id=employee_id, date=entry_date).first()
        if existing:
            return jsonify({'success': False, 'error': 'Un pointage existe déjà pour cette date'}), 409
        
        # Créer l'entrée
        time_entry = TimeEntry(employee_id=employee_id, date=entry_date)
        
        # Ajouter les heures
        for field in ['morning_in', 'lunch_out', 'lunch_in', 'evening_out']:
            time_str = data.get(field)
            if time_str:
                try:
                    time_obj = datetime.strptime(time_str, '%H:%M').time()
                    setattr(time_entry, field, time_obj)
                except ValueError:
                    return jsonify({'success': False, 'error': f'Format d\'heure invalide pour {field}'}), 400
        
        # Calculer les heures
        time_entry.calculate_hours()
        
        db.session.add(time_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pointage créé',
            'timeentry': time_entry.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la création du pointage: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.route('/api/admin/timeentries/<int:timeentry_id>', methods=['PUT'])
@admin_required
def admin_update_timeentry(timeentry_id):
    """Modifier un pointage (admin seulement)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        time_entry = TimeEntry.query.get(timeentry_id)
        if not time_entry:
            return jsonify({'success': False, 'error': 'Pointage non trouvé'}), 404
        
        # Mettre à jour la date si fournie
        if 'date' in data:
            try:
                new_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
                # Vérifier l'unicité
                existing = TimeEntry.query.filter_by(
                    employee_id=time_entry.employee_id,
                    date=new_date
                ).filter(TimeEntry.id != timeentry_id).first()
                
                if existing:
                    return jsonify({'success': False, 'error': 'Un pointage existe déjà pour cette date'}), 409
                
                time_entry.date = new_date
            except ValueError:
                return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        # Mettre à jour les heures
        for field in ['morning_in', 'lunch_out', 'lunch_in', 'evening_out']:
            if field in data:
                time_str = data[field]
                if time_str:
                    try:
                        time_obj = datetime.strptime(time_str, '%H:%M').time()
                        setattr(time_entry, field, time_obj)
                    except ValueError:
                        return jsonify({'success': False, 'error': f'Format d\'heure invalide pour {field}'}), 400
                else:
                    setattr(time_entry, field, None)
        
        # Recalculer les heures
        time_entry.calculate_hours()
        time_entry.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pointage mis à jour',
            'timeentry': time_entry.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la mise à jour du pointage: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.route('/api/admin/timeentries/<int:timeentry_id>', methods=['DELETE'])
@admin_required
def admin_delete_timeentry(timeentry_id):
    """Supprimer un pointage (admin seulement)"""
    try:
        time_entry = TimeEntry.query.get(timeentry_id)
        if not time_entry:
            return jsonify({'success': False, 'error': 'Pointage non trouvé'}), 404
        
        db.session.delete(time_entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pointage supprimé'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la suppression du pointage: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.route('/api/admin/timeentries/bulk', methods=['POST'])
@admin_required
def admin_bulk_timeentries():
    """Actions en lot sur les pointages (admin seulement)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        action = data.get('action')
        timeentry_ids = data.get('timeentry_ids', [])
        
        if not action or not timeentry_ids:
            return jsonify({'success': False, 'error': 'Action et timeentry_ids requis'}), 400
        
        if len(timeentry_ids) > 100:
            return jsonify({'success': False, 'error': 'Maximum 100 opérations en lot'}), 400
        
        if action == 'delete':
            deleted_count = 0
            for timeentry_id in timeentry_ids:
                if isinstance(timeentry_id, int):
                    time_entry = TimeEntry.query.get(timeentry_id)
                    if time_entry:
                        db.session.delete(time_entry)
                        deleted_count += 1
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'{deleted_count} pointage(s) supprimé(s)',
                'deleted_count': deleted_count
            })
        
        return jsonify({'success': False, 'error': 'Action non supportée'}), 400
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de l'opération en lot: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

# Gestion des erreurs
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Ressource non trouvée'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'success': False, 'error': 'Trop de requêtes, veuillez patienter'}), 429

# Initialisation de la base de données
def init_database():
    """Initialise la base de données avec des données par défaut"""
    with app.app_context():
        db.create_all()
        
        # Créer l'administrateur par défaut
        admin = Employee.query.filter_by(employee_number='ADMIN001').first()
        if not admin:
            admin = Employee(
                employee_number='ADMIN001',
                first_name='Admin',
                last_name='Système',
                email='admin@pointage.local',
                is_admin=True,
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Créer un employé de test
            employee = Employee(
                employee_number='EMP001',
                first_name='Jean',
                last_name='Dupont',
                email='jean.dupont@pointage.local',
                is_admin=False,
                is_active=True
            )
            employee.set_password('password123')
            db.session.add(employee)
            
            db.session.commit()
            logger.info("Base de données initialisée avec les utilisateurs par défaut")

if __name__ == '__main__':
    init_database()
    logger.info("🚀 Application de pointage démarrée")
    logger.info("👤 Admin: ADMIN001 / admin123")
    logger.info("👤 Employé: EMP001 / password123")
    app.run(host='0.0.0.0', port=5000, debug=False)
else:
    # Pour le déploiement
    init_database()
