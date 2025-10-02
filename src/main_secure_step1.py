#!/usr/bin/env python3
"""
Application de Pointage - Version Sécurisée Étape 1
Améliorations de sécurité prioritaires selon Claude 4.X
"""

import os
import logging
import secrets
import io
import re
import html
from datetime import datetime, date, time, timedelta
from functools import wraps
from typing import Optional, Dict, Any, List
from calendar import monthrange
import hashlib
import time as time_module

from flask import Flask, request, jsonify, session, render_template_string, redirect, url_for, send_file, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import validate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SelectField, DateField, FloatField, BooleanField, TextAreaField, TimeField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional as OptionalValidator
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Configuration du logging sécurisé
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('security.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
security_logger = logging.getLogger('security')

# Initialisation de l'application
app = Flask(__name__)

# Configuration sécurisée renforcée
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', secrets.token_urlsafe(32)),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///timetracking_secure.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,  # HTTPS uniquement
    SESSION_COOKIE_SAMESITE='Strict',  # Protection CSRF
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),  # Session plus courte
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_TIME_LIMIT=3600,  # Token CSRF expire en 1h
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # Limite upload 16MB
)

# Initialisation des extensions de sécurité
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Classe pour la journalisation de sécurité
class SecurityAudit:
    @staticmethod
    def log_login_attempt(employee_number: str, success: bool, ip_address: str):
        """Journalise les tentatives de connexion"""
        status = "SUCCESS" if success else "FAILED"
        security_logger.warning(f"LOGIN_{status}: {employee_number} from {ip_address}")
    
    @staticmethod
    def log_admin_action(admin_id: int, action: str, target: str, ip_address: str):
        """Journalise les actions administratives"""
        security_logger.info(f"ADMIN_ACTION: User {admin_id} performed {action} on {target} from {ip_address}")
    
    @staticmethod
    def log_data_access(user_id: int, resource: str, ip_address: str):
        """Journalise l'accès aux données sensibles"""
        security_logger.info(f"DATA_ACCESS: User {user_id} accessed {resource} from {ip_address}")
    
    @staticmethod
    def log_security_event(event_type: str, details: str, ip_address: str):
        """Journalise les événements de sécurité"""
        security_logger.warning(f"SECURITY_EVENT: {event_type} - {details} from {ip_address}")

# Fonctions de validation et sanitisation
class DataValidator:
    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        """Nettoie et valide une chaîne de caractères"""
        if not value:
            return ""
        
        # Supprime les caractères dangereux
        value = html.escape(value.strip())
        
        # Limite la longueur
        if len(value) > max_length:
            value = value[:max_length]
        
        return value
    
    @staticmethod
    def validate_employee_number(employee_number: str) -> bool:
        """Valide le format du numéro d'employé"""
        pattern = r'^[A-Z]{2,5}\d{3,6}$'
        return bool(re.match(pattern, employee_number))
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Valide le format de l'email"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """Valide la force du mot de passe"""
        if len(password) < 8:
            return False, "Le mot de passe doit contenir au moins 8 caractères"
        
        if not re.search(r'[A-Z]', password):
            return False, "Le mot de passe doit contenir au moins une majuscule"
        
        if not re.search(r'[a-z]', password):
            return False, "Le mot de passe doit contenir au moins une minuscule"
        
        if not re.search(r'\d', password):
            return False, "Le mot de passe doit contenir au moins un chiffre"
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Le mot de passe doit contenir au moins un caractère spécial"
        
        return True, "Mot de passe valide"

# Formulaires WTF avec validation CSRF
class LoginForm(FlaskForm):
    employee_number = StringField('Numéro d\'employé', 
                                validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Mot de passe', 
                           validators=[DataRequired(), Length(min=8, max=128)])

class EmployeeForm(FlaskForm):
    employee_number = StringField('Numéro d\'employé', 
                                validators=[DataRequired(), Length(min=3, max=20)])
    first_name = StringField('Prénom', 
                           validators=[DataRequired(), Length(min=1, max=100)])
    last_name = StringField('Nom', 
                          validators=[DataRequired(), Length(min=1, max=100)])
    email = StringField('Email', 
                       validators=[DataRequired(), Email(), Length(max=255)])
    department = StringField('Département', 
                           validators=[OptionalValidator(), Length(max=100)])
    position = StringField('Poste', 
                         validators=[OptionalValidator(), Length(max=100)])
    hourly_rate = FloatField('Taux horaire', 
                           validators=[OptionalValidator(), NumberRange(min=0, max=1000)])
    hire_date = DateField('Date d\'embauche', 
                         validators=[OptionalValidator()])
    is_admin = BooleanField('Administrateur')
    password = PasswordField('Mot de passe', 
                           validators=[DataRequired(), Length(min=8, max=128)])

class TimeEntryForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    morning_in = TimeField('Arrivée matin', validators=[OptionalValidator()])
    lunch_out = TimeField('Sortie midi', validators=[OptionalValidator()])
    lunch_in = TimeField('Retour midi', validators=[OptionalValidator()])
    evening_out = TimeField('Sortie soir', validators=[OptionalValidator()])
    notes = TextAreaField('Notes', validators=[OptionalValidator(), Length(max=500)])

# Modèles de données (identiques mais avec validation renforcée)
class Employee(db.Model):
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_number = db.Column(db.String(50), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    department = db.Column(db.String(100))
    position = db.Column(db.String(100))
    hire_date = db.Column(db.Date)
    hourly_rate = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        """Définit le mot de passe avec validation"""
        is_valid, message = DataValidator.validate_password_strength(password)
        if not is_valid:
            raise ValueError(message)
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Vérifie le mot de passe"""
        return check_password_hash(self.password_hash, password)
    
    def is_locked(self):
        """Vérifie si le compte est verrouillé"""
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False
    
    def lock_account(self, duration_minutes=30):
        """Verrouille le compte"""
        self.locked_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        self.failed_login_attempts = 0
        db.session.commit()
    
    def record_failed_login(self):
        """Enregistre une tentative de connexion échouée"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.lock_account()
        db.session.commit()
    
    def record_successful_login(self):
        """Enregistre une connexion réussie"""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def get_hours_stats(self, start_date=None, end_date=None):
        """Calcule les statistiques d'heures pour l'employé"""
        if not start_date:
            start_date = date.today().replace(day=1)
        if not end_date:
            end_date = date.today()
        
        entries = TimeEntry.query.filter(
            TimeEntry.employee_id == self.id,
            TimeEntry.date >= start_date,
            TimeEntry.date <= end_date
        ).all()
        
        total_hours = sum(entry.total_hours for entry in entries)
        days_worked = len([e for e in entries if e.total_hours > 0])
        
        return {
            'total_hours': round(total_hours, 2),
            'days_worked': days_worked,
            'average_hours_per_day': round(total_hours / max(days_worked, 1), 2),
            'entries': entries
        }
    
    def to_dict(self):
        """Convertit en dictionnaire (sans données sensibles)"""
        return {
            'id': self.id,
            'employee_number': self.employee_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'department': self.department,
            'position': self.position,
            'hire_date': self.hire_date.isoformat() if self.hire_date else None,
            'hourly_rate': self.hourly_rate,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class TimeEntry(db.Model):
    __tablename__ = 'time_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    morning_in = db.Column(db.Time)
    lunch_out = db.Column(db.Time)
    lunch_in = db.Column(db.Time)
    evening_out = db.Column(db.Time)
    total_hours = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    modified_by = db.Column(db.Integer, db.ForeignKey('employees.id'))  # Audit trail
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='time_entries')
    modifier = db.relationship('Employee', foreign_keys=[modified_by])
    
    def calculate_hours(self):
        """Calcule les heures travaillées avec validation"""
        total = 0.0
        
        # Validation de cohérence des horaires
        times = [self.morning_in, self.lunch_out, self.lunch_in, self.evening_out]
        valid_times = [t for t in times if t is not None]
        
        if len(valid_times) > 1:
            # Vérifier que les horaires sont dans l'ordre chronologique
            for i in range(len(valid_times) - 1):
                if valid_times[i] >= valid_times[i + 1]:
                    raise ValueError("Les horaires doivent être dans l'ordre chronologique")
        
        if self.morning_in and self.lunch_out:
            morning_delta = datetime.combine(self.date, self.lunch_out) - datetime.combine(self.date, self.morning_in)
            total += morning_delta.total_seconds() / 3600
        
        if self.lunch_in and self.evening_out:
            afternoon_delta = datetime.combine(self.date, self.evening_out) - datetime.combine(self.date, self.lunch_in)
            total += afternoon_delta.total_seconds() / 3600
        
        # Validation des heures (max 24h par jour)
        if total > 24:
            raise ValueError("Le total d'heures ne peut pas dépasser 24h par jour")
        
        self.total_hours = round(total, 2)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'date': self.date.isoformat() if self.date else None,
            'morning_in': self.morning_in.strftime('%H:%M') if self.morning_in else None,
            'lunch_out': self.lunch_out.strftime('%H:%M') if self.lunch_out else None,
            'lunch_in': self.lunch_in.strftime('%H:%M') if self.lunch_in else None,
            'evening_out': self.evening_out.strftime('%H:%M') if self.evening_out else None,
            'total_hours': self.total_hours,
            'notes': self.notes,
            'modified_by': self.modified_by
        }

# Décorateurs de sécurité renforcés
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            SecurityAudit.log_security_event("UNAUTHORIZED_ACCESS", f"Attempted access to {request.endpoint}", request.remote_addr)
            flash('Connexion requise', 'error')
            return redirect(url_for('index'))
        
        # Vérifier la validité de la session
        employee = Employee.query.get(session['employee_id'])
        if not employee or not employee.is_active:
            session.clear()
            flash('Session invalide', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            SecurityAudit.log_security_event("UNAUTHORIZED_ADMIN_ACCESS", f"Attempted admin access to {request.endpoint}", request.remote_addr)
            flash('Connexion requise', 'error')
            return redirect(url_for('index'))
        
        employee = Employee.query.get(session['employee_id'])
        if not employee or not employee.is_admin or not employee.is_active:
            SecurityAudit.log_security_event("UNAUTHORIZED_ADMIN_ACCESS", f"User {session.get('employee_id')} attempted admin access", request.remote_addr)
            flash('Accès administrateur requis', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

def validate_csrf_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            validate_csrf(request.form.get('csrf_token'))
        except:
            SecurityAudit.log_security_event("CSRF_VIOLATION", f"Invalid CSRF token on {request.endpoint}", request.remote_addr)
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Middleware de sécurité
@app.before_request
def security_headers():
    """Ajoute les headers de sécurité"""
    # Protection contre le clickjacking
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; font-src 'self' cdnjs.cloudflare.com; connect-src 'self';"
        return response

# Fonctions utilitaires (identiques)
def get_week_dates(target_date=None):
    if not target_date:
        target_date = date.today()
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def get_month_dates(target_date=None):
    if not target_date:
        target_date = date.today()
    start_of_month = target_date.replace(day=1)
    _, last_day = monthrange(target_date.year, target_date.month)
    end_of_month = target_date.replace(day=last_day)
    return start_of_month, end_of_month

# Routes sécurisées
@app.route('/')
def index():
    if 'employee_id' in session:
        return redirect(url_for('employee_dashboard'))
    
    form = LoginForm()
    return render_template_string('''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connexion Sécurisée - Système de Pointage</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            max-width: 400px;
            width: 100%;
        }
        .security-badge {
            background: linear-gradient(45deg, #27ae60, #2ecc71);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.8em;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="card-header bg-primary text-white text-center p-4">
            <h2><i class="fas fa-shield-alt"></i> Système de Pointage</h2>
            <p class="mb-0">Version Sécurisée</p>
            <div class="mt-2">
                <span class="security-badge">
                    <i class="fas fa-lock"></i> Sécurité Renforcée
                </span>
            </div>
        </div>
        <div class="card-body p-4">
            <form method="POST" action="/login">
                {{ form.hidden_tag() }}
                <div class="mb-3">
                    {{ form.employee_number.label(class="form-label") }}
                    {{ form.employee_number(class="form-control", placeholder="Ex: ADMIN001, EMP001...") }}
                    {% if form.employee_number.errors %}
                        <div class="text-danger small">{{ form.employee_number.errors[0] }}</div>
                    {% endif %}
                </div>
                <div class="mb-3">
                    {{ form.password.label(class="form-label") }}
                    {{ form.password(class="form-control") }}
                    {% if form.password.errors %}
                        <div class="text-danger small">{{ form.password.errors[0] }}</div>
                    {% endif %}
                </div>
                <div class="d-grid">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-sign-in-alt"></i> Connexion Sécurisée
                    </button>
                </div>
            </form>
            
            <div class="mt-4">
                <div class="alert alert-info">
                    <h6><i class="fas fa-info-circle"></i> Comptes de test</h6>
                    <small>
                        <strong>Admin:</strong> ADMIN001 / Admin123!<br>
                        <strong>Employé:</strong> EMP001 / Password123!
                    </small>
                </div>
                
                <div class="alert alert-warning">
                    <h6><i class="fas fa-exclamation-triangle"></i> Sécurité</h6>
                    <small>
                        • Protection CSRF activée<br>
                        • Rate limiting en place<br>
                        • Audit trail complet<br>
                        • Verrouillage après 5 échecs
                    </small>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Messages flash -->
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            <div class="position-fixed top-0 end-0 p-3" style="z-index: 1050">
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            </div>
        {% endif %}
    {% endwith %}

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>''', form=form)

@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limiting sur la connexion
def login():
    form = LoginForm()
    
    if not form.validate_on_submit():
        flash('Données invalides', 'error')
        return redirect(url_for('index'))
    
    employee_number = DataValidator.sanitize_string(form.employee_number.data, 20)
    password = form.password.data
    
    # Validation du format
    if not DataValidator.validate_employee_number(employee_number):
        SecurityAudit.log_login_attempt(employee_number, False, request.remote_addr)
        flash('Format de numéro d\'employé invalide', 'error')
        return redirect(url_for('index'))
    
    employee = Employee.query.filter_by(employee_number=employee_number, is_active=True).first()
    
    if not employee:
        SecurityAudit.log_login_attempt(employee_number, False, request.remote_addr)
        flash('Identifiants invalides', 'error')
        return redirect(url_for('index'))
    
    # Vérifier si le compte est verrouillé
    if employee.is_locked():
        SecurityAudit.log_security_event("LOCKED_ACCOUNT_ACCESS", f"Attempt to access locked account {employee_number}", request.remote_addr)
        flash('Compte temporairement verrouillé. Réessayez plus tard.', 'error')
        return redirect(url_for('index'))
    
    if not employee.check_password(password):
        employee.record_failed_login()
        SecurityAudit.log_login_attempt(employee_number, False, request.remote_addr)
        flash('Identifiants invalides', 'error')
        return redirect(url_for('index'))
    
    # Connexion réussie
    employee.record_successful_login()
    session['employee_id'] = employee.id
    session.permanent = True
    
    SecurityAudit.log_login_attempt(employee_number, True, request.remote_addr)
    flash(f'Connexion sécurisée réussie ! Bienvenue {employee.first_name}', 'success')
    
    if employee.is_admin:
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('employee_dashboard'))

@app.route('/logout')
@login_required
def logout():
    employee_id = session.get('employee_id')
    SecurityAudit.log_security_event("LOGOUT", f"User {employee_id} logged out", request.remote_addr)
    session.clear()
    flash('Déconnexion sécurisée réussie', 'success')
    return redirect(url_for('index'))

# Initialisation de la base de données
def init_database():
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
                department='Administration',
                position='Administrateur',
                hire_date=date.today(),
                is_admin=True,
                is_active=True
            )
            admin.set_password('Admin123!')
            db.session.add(admin)
            
            # Créer un employé de test
            employee = Employee(
                employee_number='EMP001',
                first_name='Jean',
                last_name='Dupont',
                email='jean.dupont@pointage.local',
                department='Production',
                position='Technicien',
                hire_date=date.today() - timedelta(days=30),
                hourly_rate=15.50,
                is_admin=False,
                is_active=True
            )
            employee.set_password('Password123!')
            db.session.add(employee)
            
            db.session.commit()
            logger.info("Base de données sécurisée initialisée")

if __name__ == '__main__':
    init_database()
    logger.info("🔒 Application de pointage SÉCURISÉE démarrée - Étape 1")
    app.run(host='0.0.0.0', port=5000, debug=False)
else:
    init_database()
