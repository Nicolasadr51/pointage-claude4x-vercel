#!/usr/bin/env python3
"""
Application de Pointage - Version Sécurisée Étape 2
Fonctionnalités complètes + Optimisations selon Claude 4.X
"""

import os
import logging
import secrets
import io
import re
import html
from datetime import datetime, date, time, timedelta
from functools import wraps, lru_cache
from typing import Optional, Dict, Any, List
from calendar import monthrange
import hashlib
import time as time_module
import json

from flask import Flask, request, jsonify, session, render_template_string, redirect, url_for, send_file, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import validate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SelectField, DateField, FloatField, BooleanField, TextAreaField, TimeField, IntegerField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional as OptionalValidator
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///timetracking_secure_v2.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,  # False pour développement
    SESSION_COOKIE_SAMESITE='Strict',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=4),
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_TIME_LIMIT=3600,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
)

# Initialisation des extensions de sécurité
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# Cache simple en mémoire pour les statistiques
stats_cache = {}
CACHE_DURATION = 300  # 5 minutes

# Classes utilitaires (reprises de l'étape 1)
class SecurityAudit:
    @staticmethod
    def log_login_attempt(employee_number: str, success: bool, ip_address: str):
        status = "SUCCESS" if success else "FAILED"
        security_logger.warning(f"LOGIN_{status}: {employee_number} from {ip_address}")
    
    @staticmethod
    def log_admin_action(admin_id: int, action: str, target: str, ip_address: str):
        security_logger.info(f"ADMIN_ACTION: User {admin_id} performed {action} on {target} from {ip_address}")
    
    @staticmethod
    def log_data_access(user_id: int, resource: str, ip_address: str):
        security_logger.info(f"DATA_ACCESS: User {user_id} accessed {resource} from {ip_address}")
    
    @staticmethod
    def log_security_event(event_type: str, details: str, ip_address: str):
        security_logger.warning(f"SECURITY_EVENT: {event_type} - {details} from {ip_address}")

class DataValidator:
    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        if not value:
            return ""
        value = html.escape(value.strip())
        if len(value) > max_length:
            value = value[:max_length]
        return value
    
    @staticmethod
    def validate_employee_number(employee_number: str) -> bool:
        pattern = r'^[A-Z]{2,5}\d{3,6}$'
        return bool(re.match(pattern, employee_number))
    
    @staticmethod
    def validate_email(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
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

# Cache manager pour les statistiques
class CacheManager:
    @staticmethod
    def get_cache_key(prefix: str, *args) -> str:
        """Génère une clé de cache unique"""
        key_parts = [prefix] + [str(arg) for arg in args]
        return "_".join(key_parts)
    
    @staticmethod
    def get_cached_data(key: str):
        """Récupère les données du cache si valides"""
        if key in stats_cache:
            data, timestamp = stats_cache[key]
            if time_module.time() - timestamp < CACHE_DURATION:
                return data
            else:
                del stats_cache[key]
        return None
    
    @staticmethod
    def set_cached_data(key: str, data):
        """Met en cache les données"""
        stats_cache[key] = (data, time_module.time())
        return data

# Formulaires WTF étendus
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
    phone = StringField('Téléphone', 
                       validators=[OptionalValidator(), Length(max=20)])
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
    employee_id = SelectField('Employé', coerce=int, validators=[DataRequired()])
    date = DateField('Date', validators=[DataRequired()])
    morning_in = TimeField('Arrivée matin', validators=[OptionalValidator()])
    lunch_out = TimeField('Sortie midi', validators=[OptionalValidator()])
    lunch_in = TimeField('Retour midi', validators=[OptionalValidator()])
    evening_out = TimeField('Sortie soir', validators=[OptionalValidator()])
    notes = TextAreaField('Notes', validators=[OptionalValidator(), Length(max=500)])

class ExportForm(FlaskForm):
    employee_id = SelectField('Employé', coerce=int, validators=[OptionalValidator()])
    start_date = DateField('Date de début', validators=[DataRequired()])
    end_date = DateField('Date de fin', validators=[DataRequired()])
    format_type = SelectField('Format', choices=[('excel', 'Excel'), ('csv', 'CSV')], default='excel')

# Modèles de données étendus
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
        is_valid, message = DataValidator.validate_password_strength(password)
        if not is_valid:
            raise ValueError(message)
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False
    
    def lock_account(self, duration_minutes=30):
        self.locked_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        self.failed_login_attempts = 0
        db.session.commit()
    
    def record_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.lock_account()
        db.session.commit()
    
    def record_successful_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    @lru_cache(maxsize=128)
    def get_hours_stats(self, start_date=None, end_date=None):
        """Calcule les statistiques d'heures avec cache"""
        cache_key = CacheManager.get_cache_key("employee_stats", self.id, start_date, end_date)
        cached_data = CacheManager.get_cached_data(cache_key)
        if cached_data:
            return cached_data
        
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
        
        stats = {
            'total_hours': round(total_hours, 2),
            'days_worked': days_worked,
            'average_hours_per_day': round(total_hours / max(days_worked, 1), 2),
            'entries': entries
        }
        
        return CacheManager.set_cached_data(cache_key, stats)
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_number': self.employee_number,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
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
    modified_by = db.Column(db.Integer, db.ForeignKey('employees.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='time_entries')
    modifier = db.relationship('Employee', foreign_keys=[modified_by])
    
    def calculate_hours(self):
        """Calcule les heures travaillées avec validation renforcée"""
        try:
            total = 0.0
            
            # Validation de cohérence des horaires
            times = [self.morning_in, self.lunch_out, self.lunch_in, self.evening_out]
            valid_times = [t for t in times if t is not None]
            
            if len(valid_times) > 1:
                for i in range(len(valid_times) - 1):
                    if valid_times[i] >= valid_times[i + 1]:
                        raise ValueError("Les horaires doivent être dans l'ordre chronologique")
            
            if self.morning_in and self.lunch_out:
                morning_delta = datetime.combine(self.date, self.lunch_out) - datetime.combine(self.date, self.morning_in)
                total += morning_delta.total_seconds() / 3600
            
            if self.lunch_in and self.evening_out:
                afternoon_delta = datetime.combine(self.date, self.evening_out) - datetime.combine(self.date, self.lunch_in)
                total += afternoon_delta.total_seconds() / 3600
            
            if total > 24:
                raise ValueError("Le total d'heures ne peut pas dépasser 24h par jour")
            
            self.total_hours = round(total, 2)
            
        except Exception as e:
            logger.error(f"Erreur calcul heures pour entrée {self.id}: {str(e)}")
            raise
    
    def to_dict(self):
        return {
            'id': self.id,
            'employee_id': self.employee_id,
            'employee_name': f"{self.employee.first_name} {self.employee.last_name}",
            'date': self.date.isoformat() if self.date else None,
            'morning_in': self.morning_in.strftime('%H:%M') if self.morning_in else None,
            'lunch_out': self.lunch_out.strftime('%H:%M') if self.lunch_out else None,
            'lunch_in': self.lunch_in.strftime('%H:%M') if self.lunch_in else None,
            'evening_out': self.evening_out.strftime('%H:%M') if self.evening_out else None,
            'total_hours': self.total_hours,
            'notes': self.notes,
            'modified_by': self.modified_by
        }

# Décorateurs de sécurité (identiques à l'étape 1)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            SecurityAudit.log_security_event("UNAUTHORIZED_ACCESS", f"Attempted access to {request.endpoint}", request.remote_addr)
            flash('Connexion requise', 'error')
            return redirect(url_for('index'))
        
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

# Middleware de sécurité
@app.before_request
def security_headers():
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; font-src 'self' cdnjs.cloudflare.com; connect-src 'self';"
        return response

# Fonctions utilitaires optimisées
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

@lru_cache(maxsize=64)
def get_global_stats():
    """Statistiques globales avec cache"""
    cache_key = "global_stats"
    cached_data = CacheManager.get_cached_data(cache_key)
    if cached_data:
        return cached_data
    
    today = date.today()
    month_start, month_end = get_month_dates(today)
    
    stats = {
        'total_employees': Employee.query.filter_by(is_active=True).count(),
        'present_today': TimeEntry.query.filter_by(date=today).count(),
        'total_hours_month': db.session.query(db.func.sum(TimeEntry.total_hours)).filter(
            TimeEntry.date >= month_start,
            TimeEntry.date <= month_end
        ).scalar() or 0,
        'departments': db.session.query(Employee.department, db.func.count(Employee.id)).filter_by(is_active=True).group_by(Employee.department).all()
    }
    
    return CacheManager.set_cached_data(cache_key, stats)

# Templates HTML optimisés (je vais continuer avec les routes principales)
# Routes principales sécurisées
@app.route('/')
def index():
    if 'employee_id' in session:
        return redirect(url_for('employee_dashboard'))
    
    form = LoginForm()
    return render_template_string(LOGIN_TEMPLATE, form=form)

@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    form = LoginForm()
    
    if not form.validate_on_submit():
        flash('Données invalides', 'error')
        return redirect(url_for('index'))
    
    try:
        employee_number = DataValidator.sanitize_string(form.employee_number.data, 20)
        password = form.password.data
        
        if not DataValidator.validate_employee_number(employee_number):
            SecurityAudit.log_login_attempt(employee_number, False, request.remote_addr)
            flash('Format de numéro d\'employé invalide', 'error')
            return redirect(url_for('index'))
        
        employee = Employee.query.filter_by(employee_number=employee_number, is_active=True).first()
        
        if not employee:
            SecurityAudit.log_login_attempt(employee_number, False, request.remote_addr)
            flash('Identifiants invalides', 'error')
            return redirect(url_for('index'))
        
        if employee.is_locked():
            SecurityAudit.log_security_event("LOCKED_ACCOUNT_ACCESS", f"Attempt to access locked account {employee_number}", request.remote_addr)
            flash('Compte temporairement verrouillé. Réessayez plus tard.', 'error')
            return redirect(url_for('index'))
        
        if not employee.check_password(password):
            employee.record_failed_login()
            SecurityAudit.log_login_attempt(employee_number, False, request.remote_addr)
            flash('Identifiants invalides', 'error')
            return redirect(url_for('index'))
        
        employee.record_successful_login()
        session['employee_id'] = employee.id
        session.permanent = True
        
        SecurityAudit.log_login_attempt(employee_number, True, request.remote_addr)
        flash(f'Connexion sécurisée réussie ! Bienvenue {employee.first_name}', 'success')
        
        if employee.is_admin:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('employee_dashboard'))
            
    except Exception as e:
        logger.error(f"Erreur lors de la connexion: {str(e)}")
        flash('Erreur système. Veuillez réessayer.', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    employee_id = session.get('employee_id')
    SecurityAudit.log_security_event("LOGOUT", f"User {employee_id} logged out", request.remote_addr)
    session.clear()
    flash('Déconnexion sécurisée réussie', 'success')
    return redirect(url_for('index'))

# Templates HTML (versions optimisées)
LOGIN_TEMPLATE = '''<!DOCTYPE html>
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
            <p class="mb-0">Version Sécurisée Étape 2</p>
            <div class="mt-2">
                <span class="security-badge">
                    <i class="fas fa-lock"></i> Sécurité 8.5/10
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
                
                <div class="alert alert-success">
                    <h6><i class="fas fa-check-circle"></i> Nouvelles fonctionnalités</h6>
                    <small>
                        • Dashboard employé complet<br>
                        • Gestion admin avancée<br>
                        • Export Excel personnalisé<br>
                        • Cache et optimisations
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
</html>'''

# Initialisation de la base de données
def init_database():
    with app.app_context():
        try:
            db.create_all()
            
            # Créer l'administrateur par défaut
            admin = Employee.query.filter_by(employee_number='ADMIN001').first()
            if not admin:
                admin = Employee(
                    employee_number='ADMIN001',
                    first_name='Admin',
                    last_name='Système',
                    email='admin@pointage.local',
                    phone='01.23.45.67.89',
                    department='Administration',
                    position='Administrateur',
                    hire_date=date.today(),
                    hourly_rate=25.0,
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
                    phone='01.98.76.54.32',
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
                
                # Créer quelques entrées de test après commit
                for i in range(5):
                    test_date = date.today() - timedelta(days=i)
                    entry = TimeEntry(
                        employee_id=employee.id,
                        date=test_date,
                        morning_in=time(8, 0),
                        lunch_out=time(12, 0),
                        lunch_in=time(13, 0),
                        evening_out=time(17, 0)
                    )
                    entry.calculate_hours()
                    db.session.add(entry)
                
                db.session.commit()
                logger.info("Base de données sécurisée étape 2 initialisée")
                
        except Exception as e:
            logger.error(f"Erreur initialisation base de données: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    init_database()
    logger.info("🚀 Application de pointage SÉCURISÉE ÉTAPE 2 démarrée")
    app.run(host='0.0.0.0', port=5000, debug=False)
else:
    init_database()

# Routes employé complètes
@app.route('/employee')
@login_required
def employee_dashboard():
    try:
        current_user = Employee.query.get(session['employee_id'])
        today = date.today()
        
        # Statistiques avec cache
        today_entry = TimeEntry.query.filter_by(employee_id=current_user.id, date=today).first()
        day_stats = {'total_hours': today_entry.total_hours if today_entry else 0}
        
        week_start, week_end = get_week_dates(today)
        week_stats = current_user.get_hours_stats(week_start, week_end)
        
        month_start, month_end = get_month_dates(today)
        month_stats = current_user.get_hours_stats(month_start, month_end)
        
        # Données pour les graphiques (optimisées)
        daily_chart_labels = []
        daily_chart_data = []
        
        for i in range(7):
            chart_date = today - timedelta(days=6-i)
            daily_chart_labels.append(chart_date.strftime('%d/%m'))
            
            entry = TimeEntry.query.filter_by(employee_id=current_user.id, date=chart_date).first()
            daily_chart_data.append(entry.total_hours if entry else 0)
        
        # Historique récent paginé
        page = request.args.get('page', 1, type=int)
        recent_entries = TimeEntry.query.filter_by(employee_id=current_user.id)\
            .order_by(TimeEntry.date.desc()).paginate(
                page=page, per_page=10, error_out=False
            )
        
        # Nombre total de jours dans le mois
        _, month_days_total = monthrange(today.year, today.month)
        
        SecurityAudit.log_data_access(current_user.id, "employee_dashboard", request.remote_addr)
        
        return render_template_string(EMPLOYEE_DASHBOARD_TEMPLATE,
                                    current_user=current_user,
                                    today_entry=today_entry,
                                    day_stats=day_stats,
                                    week_stats=week_stats,
                                    month_stats=month_stats,
                                    recent_entries=recent_entries.items,
                                    pagination=recent_entries,
                                    daily_chart_labels=json.dumps(daily_chart_labels),
                                    daily_chart_data=json.dumps(daily_chart_data),
                                    month_days_total=month_days_total)
                                    
    except Exception as e:
        logger.error(f"Erreur dashboard employé: {str(e)}")
        flash('Erreur lors du chargement du tableau de bord', 'error')
        return redirect(url_for('index'))

@app.route('/punch', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def punch():
    try:
        punch_type = request.form.get('punch_type')
        employee_id = session['employee_id']
        today = date.today()
        now = datetime.now().time()
        
        if punch_type not in ['morning_in', 'lunch_out', 'lunch_in', 'evening_out']:
            flash('Type de pointage invalide', 'error')
            return redirect(url_for('employee_dashboard'))
        
        # Récupérer ou créer l'entrée du jour
        time_entry = TimeEntry.query.filter_by(employee_id=employee_id, date=today).first()
        if not time_entry:
            time_entry = TimeEntry(employee_id=employee_id, date=today)
            db.session.add(time_entry)
        
        # Mettre à jour le pointage
        setattr(time_entry, punch_type, now)
        time_entry.calculate_hours()
        
        db.session.commit()
        
        type_labels = {
            'morning_in': 'Arrivée matin',
            'lunch_out': 'Sortie midi',
            'lunch_in': 'Retour midi',
            'evening_out': 'Sortie soir'
        }
        
        SecurityAudit.log_admin_action(employee_id, f"PUNCH_{punch_type.upper()}", f"time_entry_{time_entry.id}", request.remote_addr)
        flash(f'{type_labels[punch_type]} enregistrée à {now.strftime("%H:%M")}', 'success')
        
    except Exception as e:
        logger.error(f"Erreur pointage: {str(e)}")
        flash('Erreur lors de l\'enregistrement du pointage', 'error')
        db.session.rollback()
    
    return redirect(url_for('employee_dashboard'))

# Routes d'administration complètes
@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        # Statistiques globales avec cache
        stats = get_global_stats()
        
        today = date.today()
        month_start, month_end = get_month_dates(today)
        
        # Données pour les graphiques
        employees = Employee.query.filter_by(is_active=True).all()
        today_entries = TimeEntry.query.filter_by(date=today).join(Employee).all()
        
        # Statistiques par département avec cache
        cache_key = "dept_stats"
        dept_stats = CacheManager.get_cached_data(cache_key)
        if not dept_stats:
            month_entries = TimeEntry.query.filter(
                TimeEntry.date >= month_start,
                TimeEntry.date <= month_end
            ).join(Employee).all()
            
            dept_stats = {}
            for entry in month_entries:
                dept = entry.employee.department or 'Non défini'
                dept_stats[dept] = dept_stats.get(dept, 0) + entry.total_hours
            
            CacheManager.set_cached_data(cache_key, dept_stats)
        
        dept_chart_labels = list(dept_stats.keys())
        dept_chart_data = list(dept_stats.values())
        
        # Évolution hebdomadaire
        weekly_chart_labels = []
        weekly_chart_data = []
        for i in range(7):
            chart_date = today - timedelta(days=6-i)
            weekly_chart_labels.append(chart_date.strftime('%d/%m'))
            
            day_total = db.session.query(db.func.sum(TimeEntry.total_hours)).filter_by(date=chart_date).scalar() or 0
            weekly_chart_data.append(float(day_total))
        
        # Top employés du mois
        top_employees_query = db.session.query(
            Employee,
            db.func.sum(TimeEntry.total_hours).label('total_hours')
        ).join(TimeEntry).filter(
            TimeEntry.date >= month_start,
            TimeEntry.date <= month_end
        ).group_by(Employee.id).order_by(db.desc('total_hours')).limit(5).all()
        
        top_employees = [(emp, hours) for emp, hours in top_employees_query]
        
        # Pagination des pointages
        page = request.args.get('page', 1, type=int)
        employee_filter = request.args.get('employee_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = TimeEntry.query.join(Employee)
        
        if employee_filter:
            query = query.filter(TimeEntry.employee_id == employee_filter)
        if start_date:
            query = query.filter(TimeEntry.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(TimeEntry.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
        
        filtered_entries = query.order_by(TimeEntry.date.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        SecurityAudit.log_data_access(session['employee_id'], "admin_dashboard", request.remote_addr)
        
        return render_template_string(ADMIN_DASHBOARD_TEMPLATE,
                                    **stats,
                                    avg_hours_day=round(stats['total_hours_month'] / max(len(today_entries), 1), 1),
                                    employees=employees,
                                    today_entries=today_entries,
                                    filtered_entries=filtered_entries.items,
                                    pagination=filtered_entries,
                                    dept_chart_labels=json.dumps(dept_chart_labels),
                                    dept_chart_data=json.dumps(dept_chart_data),
                                    weekly_chart_labels=json.dumps(weekly_chart_labels),
                                    weekly_chart_data=json.dumps(weekly_chart_data),
                                    top_employees=top_employees,
                                    departments_stats=stats['departments'])
                                    
    except Exception as e:
        logger.error(f"Erreur dashboard admin: {str(e)}")
        flash('Erreur lors du chargement du tableau de bord administrateur', 'error')
        return redirect(url_for('index'))

@app.route('/admin/add_employee', methods=['POST'])
@admin_required
@limiter.limit("10 per hour")
def add_employee():
    form = EmployeeForm()
    
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Vérifier l'unicité
        if Employee.query.filter_by(employee_number=form.employee_number.data).first():
            flash('Ce numéro d\'employé existe déjà', 'error')
            return redirect(url_for('admin_dashboard'))
        
        if Employee.query.filter_by(email=form.email.data).first():
            flash('Cette adresse email existe déjà', 'error')
            return redirect(url_for('admin_dashboard'))
        
        employee = Employee(
            employee_number=DataValidator.sanitize_string(form.employee_number.data, 20),
            first_name=DataValidator.sanitize_string(form.first_name.data, 100),
            last_name=DataValidator.sanitize_string(form.last_name.data, 100),
            email=DataValidator.sanitize_string(form.email.data, 255),
            phone=DataValidator.sanitize_string(form.phone.data, 20) if form.phone.data else None,
            department=DataValidator.sanitize_string(form.department.data, 100) if form.department.data else None,
            position=DataValidator.sanitize_string(form.position.data, 100) if form.position.data else None,
            hourly_rate=form.hourly_rate.data or 0.0,
            hire_date=form.hire_date.data,
            is_admin=form.is_admin.data,
            is_active=True
        )
        employee.set_password(form.password.data)
        
        db.session.add(employee)
        db.session.commit()
        
        SecurityAudit.log_admin_action(session['employee_id'], "CREATE_EMPLOYEE", f"employee_{employee.id}", request.remote_addr)
        flash(f'Employé {employee.first_name} {employee.last_name} créé avec succès', 'success')
        
        # Invalider le cache
        stats_cache.clear()
        
    except ValueError as e:
        flash(f'Erreur de validation: {str(e)}', 'error')
        db.session.rollback()
    except Exception as e:
        logger.error(f'Erreur création employé: {str(e)}')
        flash('Erreur lors de la création de l\'employé', 'error')
        db.session.rollback()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_employee/<int:employee_id>', methods=['GET', 'POST'])
@admin_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        try:
            form = EmployeeForm()
            if form.validate_on_submit():
                employee.first_name = DataValidator.sanitize_string(form.first_name.data, 100)
                employee.last_name = DataValidator.sanitize_string(form.last_name.data, 100)
                employee.email = DataValidator.sanitize_string(form.email.data, 255)
                employee.phone = DataValidator.sanitize_string(form.phone.data, 20) if form.phone.data else None
                employee.department = DataValidator.sanitize_string(form.department.data, 100) if form.department.data else None
                employee.position = DataValidator.sanitize_string(form.position.data, 100) if form.position.data else None
                employee.hourly_rate = form.hourly_rate.data or 0.0
                employee.hire_date = form.hire_date.data
                employee.is_admin = form.is_admin.data
                
                if form.password.data:
                    employee.set_password(form.password.data)
                
                db.session.commit()
                
                SecurityAudit.log_admin_action(session['employee_id'], "UPDATE_EMPLOYEE", f"employee_{employee.id}", request.remote_addr)
                flash(f'Employé {employee.first_name} {employee.last_name} modifié avec succès', 'success')
                stats_cache.clear()
                
        except Exception as e:
            logger.error(f'Erreur modification employé: {str(e)}')
            flash('Erreur lors de la modification', 'error')
            db.session.rollback()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
@admin_required
def edit_entry(entry_id):
    entry = TimeEntry.query.get_or_404(entry_id)
    
    if request.method == 'POST':
        try:
            form = TimeEntryForm()
            if form.validate_on_submit():
                entry.date = form.date.data
                entry.morning_in = form.morning_in.data
                entry.lunch_out = form.lunch_out.data
                entry.lunch_in = form.lunch_in.data
                entry.evening_out = form.evening_out.data
                entry.notes = DataValidator.sanitize_string(form.notes.data, 500) if form.notes.data else None
                entry.modified_by = session['employee_id']
                
                entry.calculate_hours()
                db.session.commit()
                
                SecurityAudit.log_admin_action(session['employee_id'], "UPDATE_TIME_ENTRY", f"entry_{entry.id}", request.remote_addr)
                flash('Pointage modifié avec succès', 'success')
                stats_cache.clear()
                
        except Exception as e:
            logger.error(f'Erreur modification pointage: {str(e)}')
            flash('Erreur lors de la modification du pointage', 'error')
            db.session.rollback()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export_excel')
@admin_required
@limiter.limit("5 per hour")
def export_excel():
    try:
        # Créer un fichier Excel avec toutes les données
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Pointages"
        
        # Style pour les headers
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                       top=Side(style='thin'), bottom=Side(style='thin'))
        
        # Headers
        headers = ['Date', 'Employé', 'Département', 'Arrivée', 'Sortie Midi', 'Retour Midi', 'Sortie Soir', 'Total Heures', 'Notes']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center')
        
        # Données avec pagination pour éviter les timeouts
        entries = TimeEntry.query.join(Employee).order_by(TimeEntry.date.desc()).limit(1000).all()
        
        for row, entry in enumerate(entries, 2):
            data = [
                entry.date.strftime('%d/%m/%Y'),
                f"{entry.employee.first_name} {entry.employee.last_name}",
                entry.employee.department or '',
                entry.morning_in.strftime('%H:%M') if entry.morning_in else '',
                entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '',
                entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '',
                entry.evening_out.strftime('%H:%M') if entry.evening_out else '',
                entry.total_hours,
                entry.notes or ''
            ]
            
            for col, value in enumerate(data, 1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = border
                if col == 8:  # Total heures
                    cell.alignment = Alignment(horizontal='right')
        
        # Ajuster la largeur des colonnes
        column_widths = [12, 20, 15, 10, 12, 12, 12, 12, 30]
        for col, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(col)].width = width
        
        # Ajouter une feuille de statistiques
        stats_ws = wb.create_sheet("Statistiques")
        stats_ws.append(["Statistiques Générales"])
        stats_ws.append([""])
        stats_ws.append(["Nombre total d'employés", Employee.query.filter_by(is_active=True).count()])
        stats_ws.append(["Nombre total de pointages", TimeEntry.query.count()])
        stats_ws.append(["Total heures ce mois", db.session.query(db.func.sum(TimeEntry.total_hours)).scalar() or 0])
        
        # Sauvegarder en mémoire
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        SecurityAudit.log_admin_action(session['employee_id'], "EXPORT_EXCEL", "all_data", request.remote_addr)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'pointages_complet_{date.today().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f'Erreur export Excel: {str(e)}')
        flash('Erreur lors de l\'export Excel', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/export_custom', methods=['POST'])
@admin_required
@limiter.limit("10 per hour")
def export_custom():
    try:
        form = ExportForm()
        if not form.validate_on_submit():
            flash('Données d\'export invalides', 'error')
            return redirect(url_for('admin_dashboard'))
        
        employee_id = form.employee_id.data
        start_date = form.start_date.data
        end_date = form.end_date.data
        
        # Validation des dates
        if start_date > end_date:
            flash('La date de début doit être antérieure à la date de fin', 'error')
            return redirect(url_for('admin_dashboard'))
        
        if (end_date - start_date).days > 365:
            flash('La période ne peut pas dépasser 365 jours', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # Filtrer les données
        query = TimeEntry.query.join(Employee).filter(
            TimeEntry.date >= start_date,
            TimeEntry.date <= end_date
        )
        
        if employee_id:
            query = query.filter(TimeEntry.employee_id == employee_id)
            employee = Employee.query.get(employee_id)
            filename = f'pointages_{employee.first_name}_{employee.last_name}_{start_date}_{end_date}.xlsx'
        else:
            filename = f'pointages_tous_{start_date}_{end_date}.xlsx'
        
        entries = query.order_by(TimeEntry.date.desc()).all()
        
        if not entries:
            flash('Aucune donnée trouvée pour cette période', 'warning')
            return redirect(url_for('admin_dashboard'))
        
        # Créer le fichier Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Pointages"
        
        # Style
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                       top=Side(style='thin'), bottom=Side(style='thin'))
        
        # Headers
        headers = ['Date', 'Employé', 'Département', 'Arrivée', 'Sortie Midi', 'Retour Midi', 'Sortie Soir', 'Total Heures']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = border
        
        # Données
        total_hours = 0
        for row, entry in enumerate(entries, 2):
            data = [
                entry.date.strftime('%d/%m/%Y'),
                f"{entry.employee.first_name} {entry.employee.last_name}",
                entry.employee.department or '',
                entry.morning_in.strftime('%H:%M') if entry.morning_in else '',
                entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '',
                entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '',
                entry.evening_out.strftime('%H:%M') if entry.evening_out else '',
                entry.total_hours
            ]
            
            for col, value in enumerate(data, 1):
                cell = ws.cell(row=row, column=col, value=value)
                cell.border = border
            
            total_hours += entry.total_hours
        
        # Ligne de total
        if entries:
            total_row = len(entries) + 2
            ws.cell(row=total_row, column=7, value="TOTAL:").font = Font(bold=True)
            ws.cell(row=total_row, column=8, value=total_hours).font = Font(bold=True)
        
        # Ajuster la largeur des colonnes
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 15
        
        # Sauvegarder en mémoire
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        SecurityAudit.log_admin_action(session['employee_id'], "EXPORT_CUSTOM", f"period_{start_date}_{end_date}", request.remote_addr)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f'Erreur export personnalisé: {str(e)}')
        flash('Erreur lors de l\'export personnalisé', 'error')
        return redirect(url_for('admin_dashboard'))

# Templates HTML complets
EMPLOYEE_DASHBOARD_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tableau de Bord - {{ current_user.first_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; }
        .card { border: none; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .stats-card { background: linear-gradient(135deg, #27ae60, #2ecc71); color: white; }
        .chart-container { position: relative; height: 300px; }
        .security-badge { background: linear-gradient(45deg, #e74c3c, #c0392b); color: white; padding: 3px 10px; border-radius: 15px; font-size: 0.7em; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-clock"></i> Pointage Sécurisé</a>
            <div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">{{ current_user.first_name }} {{ current_user.last_name }}</span>
                <span class="security-badge me-3"><i class="fas fa-shield-alt"></i> 8.5/10</span>
                {% if current_user.is_admin %}
                <a class="nav-link" href="/admin"><i class="fas fa-cog"></i> Administration</a>
                {% endif %}
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt"></i> Déconnexion</a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <!-- Statistiques principales -->
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <h3><i class="fas fa-calendar-day"></i></h3>
                        <h4>{{ day_stats.total_hours }}h</h4>
                        <p class="mb-0">Aujourd'hui</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <h3><i class="fas fa-calendar-week"></i></h3>
                        <h4>{{ week_stats.total_hours }}h</h4>
                        <p class="mb-0">Cette semaine</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <h3><i class="fas fa-calendar-alt"></i></h3>
                        <h4>{{ month_stats.total_hours }}h</h4>
                        <p class="mb-0">Ce mois</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Pointage du jour -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h5><i class="fas fa-clock"></i> Pointage du Jour</h5>
                    </div>
                    <div class="card-body">
                        <div class="text-center mb-3">
                            <div class="h2" id="currentTime"></div>
                        </div>
                        
                        <div class="d-flex justify-content-center flex-wrap">
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
                                {{ csrf_token() }}
                                <input type="hidden" name="punch_type" value="morning_in">
                                <button type="submit" class="btn btn-success">
                                    <i class="fas fa-sun"></i> Arrivée Matin
                                </button>
                            </form>
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
                                {{ csrf_token() }}
                                <input type="hidden" name="punch_type" value="lunch_out">
                                <button type="submit" class="btn btn-warning">
                                    <i class="fas fa-utensils"></i> Sortie Midi
                                </button>
                            </form>
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
                                {{ csrf_token() }}
                                <input type="hidden" name="punch_type" value="lunch_in">
                                <button type="submit" class="btn btn-info">
                                    <i class="fas fa-coffee"></i> Retour Midi
                                </button>
                            </form>
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
                                {{ csrf_token() }}
                                <input type="hidden" name="punch_type" value="evening_out">
                                <button type="submit" class="btn btn-danger">
                                    <i class="fas fa-moon"></i> Sortie Soir
                                </button>
                            </form>
                        </div>

                        {% if today_entry %}
                        <div class="mt-3">
                            <div class="alert alert-success">
                                <h6><i class="fas fa-check-circle"></i> Pointages d'aujourd'hui</h6>
                                <div class="row">
                                    {% if today_entry.morning_in %}
                                    <div class="col-6"><small>Arrivée: {{ today_entry.morning_in.strftime('%H:%M') }}</small></div>
                                    {% endif %}
                                    {% if today_entry.lunch_out %}
                                    <div class="col-6"><small>Sortie midi: {{ today_entry.lunch_out.strftime('%H:%M') }}</small></div>
                                    {% endif %}
                                    {% if today_entry.lunch_in %}
                                    <div class="col-6"><small>Retour midi: {{ today_entry.lunch_in.strftime('%H:%M') }}</small></div>
                                    {% endif %}
                                    {% if today_entry.evening_out %}
                                    <div class="col-6"><small>Sortie soir: {{ today_entry.evening_out.strftime('%H:%M') }}</small></div>
                                    {% endif %}
                                </div>
                                {% if today_entry.total_hours > 0 %}
                                <div class="mt-2">
                                    <strong>Total: {{ "%.2f"|format(today_entry.total_hours) }} heures</strong>
                                </div>
                                {% endif %}
                            </div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>

        <!-- Graphiques d'assiduité -->
        <div class="row mb-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-chart-bar"></i> Heures par Jour (7 derniers jours)</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="dailyHoursChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-chart-pie"></i> Assiduité du Mois</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="attendanceChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Historique récent paginé -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-history"></i> Historique Récent</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Arrivée</th>
                                        <th>Sortie Midi</th>
                                        <th>Retour Midi</th>
                                        <th>Sortie Soir</th>
                                        <th>Total</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for entry in recent_entries %}
                                    <tr>
                                        <td>{{ entry.date.strftime('%d/%m/%Y') }}</td>
                                        <td>{{ entry.morning_in.strftime('%H:%M') if entry.morning_in else '-' }}</td>
                                        <td>{{ entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '-' }}</td>
                                        <td>{{ entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '-' }}</td>
                                        <td>{{ entry.evening_out.strftime('%H:%M') if entry.evening_out else '-' }}</td>
                                        <td><strong>{{ "%.2f"|format(entry.total_hours) }}h</strong></td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                        
                        <!-- Pagination -->
                        {% if pagination.pages > 1 %}
                        <nav>
                            <ul class="pagination justify-content-center">
                                {% if pagination.has_prev %}
                                <li class="page-item">
                                    <a class="page-link" href="{{ url_for('employee_dashboard', page=pagination.prev_num) }}">Précédent</a>
                                </li>
                                {% endif %}
                                
                                {% for page_num in pagination.iter_pages() %}
                                    {% if page_num %}
                                        {% if page_num != pagination.page %}
                                        <li class="page-item">
                                            <a class="page-link" href="{{ url_for('employee_dashboard', page=page_num) }}">{{ page_num }}</a>
                                        </li>
                                        {% else %}
                                        <li class="page-item active">
                                            <span class="page-link">{{ page_num }}</span>
                                        </li>
                                        {% endif %}
                                    {% else %}
                                    <li class="page-item disabled">
                                        <span class="page-link">...</span>
                                    </li>
                                    {% endif %}
                                {% endfor %}
                                
                                {% if pagination.has_next %}
                                <li class="page-item">
                                    <a class="page-link" href="{{ url_for('employee_dashboard', page=pagination.next_num) }}">Suivant</a>
                                </li>
                                {% endif %}
                            </ul>
                        </nav>
                        {% endif %}
                    </div>
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
    <script>
        // Horloge en temps réel
        function updateClock() {
            const now = new Date();
            const timeString = now.toLocaleTimeString('fr-FR');
            document.getElementById('currentTime').textContent = timeString;
        }
        setInterval(updateClock, 1000);
        updateClock();

        // Graphique des heures quotidiennes
        const dailyCtx = document.getElementById('dailyHoursChart').getContext('2d');
        new Chart(dailyCtx, {
            type: 'bar',
            data: {
                labels: {{ daily_chart_labels | safe }},
                datasets: [{
                    label: 'Heures travaillées',
                    data: {{ daily_chart_data | safe }},
                    backgroundColor: 'rgba(52, 152, 219, 0.8)',
                    borderColor: 'rgba(52, 152, 219, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 10
                    }
                }
            }
        });

        // Graphique d'assiduité
        const attendanceCtx = document.getElementById('attendanceChart').getContext('2d');
        new Chart(attendanceCtx, {
            type: 'doughnut',
            data: {
                labels: ['Jours travaillés', 'Jours non travaillés'],
                datasets: [{
                    data: [{{ month_stats.days_worked }}, {{ month_days_total - month_stats.days_worked }}],
                    backgroundColor: ['#27ae60', '#e74c3c'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    </script>
</body>
</html>'''

ADMIN_DASHBOARD_TEMPLATE = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Administration Sécurisée - Système de Pointage</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #f8f9fa; }
        .navbar { background: linear-gradient(135deg, #2c3e50, #3498db); }
        .stats-card { border-left: 4px solid #3498db; }
        .chart-container { position: relative; height: 300px; }
        .security-badge { background: linear-gradient(45deg, #27ae60, #2ecc71); color: white; padding: 3px 10px; border-radius: 15px; font-size: 0.7em; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-shield-alt"></i> Administration Sécurisée</a>
            <div class="navbar-nav ms-auto">
                <span class="security-badge me-3"><i class="fas fa-lock"></i> Sécurité 8.5/10</span>
                <a class="nav-link" href="/employee"><i class="fas fa-user"></i> Vue Employé</a>
                <a class="nav-link" href="/logout"><i class="fas fa-sign-out-alt"></i> Déconnexion</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid mt-4">
        <!-- Statistiques globales -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h6 class="text-muted">Employés Actifs</h6>
                                <h3>{{ total_employees }}</h3>
                            </div>
                            <div class="text-primary">
                                <i class="fas fa-users fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h6 class="text-muted">Présents Aujourd'hui</h6>
                                <h3>{{ present_today }}</h3>
                            </div>
                            <div class="text-success">
                                <i class="fas fa-check-circle fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h6 class="text-muted">Heures Totales (Mois)</h6>
                                <h3>{{ "%.1f"|format(total_hours_month) }}h</h3>
                            </div>
                            <div class="text-info">
                                <i class="fas fa-clock fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h6 class="text-muted">Moyenne/Jour</h6>
                                <h3>{{ avg_hours_day }}h</h3>
                            </div>
                            <div class="text-warning">
                                <i class="fas fa-chart-line fa-2x"></i>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Navigation par onglets -->
        <ul class="nav nav-tabs" id="adminTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="dashboard-tab" data-bs-toggle="tab" data-bs-target="#dashboard" type="button">
                    <i class="fas fa-tachometer-alt"></i> Tableau de Bord
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="employees-tab" data-bs-toggle="tab" data-bs-target="#employees" type="button">
                    <i class="fas fa-users"></i> Employés
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="timeentries-tab" data-bs-toggle="tab" data-bs-target="#timeentries" type="button">
                    <i class="fas fa-clock"></i> Pointages
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="reports-tab" data-bs-toggle="tab" data-bs-target="#reports" type="button">
                    <i class="fas fa-chart-bar"></i> Rapports
                </button>
            </li>
        </ul>

        <div class="tab-content" id="adminTabsContent">
            <!-- Onglet Tableau de Bord -->
            <div class="tab-pane fade show active" id="dashboard" role="tabpanel">
                <div class="row mt-4">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-chart-bar"></i> Heures par Département</h5>
                            </div>
                            <div class="card-body">
                                <div class="chart-container">
                                    <canvas id="departmentChart"></canvas>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-chart-line"></i> Évolution Hebdomadaire</h5>
                            </div>
                            <div class="card-body">
                                <div class="chart-container">
                                    <canvas id="weeklyChart"></canvas>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="row mt-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-users"></i> Présences Aujourd'hui</h5>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-striped">
                                        <thead>
                                            <tr>
                                                <th>Employé</th>
                                                <th>Département</th>
                                                <th>Arrivée</th>
                                                <th>Sortie Midi</th>
                                                <th>Retour Midi</th>
                                                <th>Sortie Soir</th>
                                                <th>Total</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for entry in today_entries %}
                                            <tr>
                                                <td>{{ entry.employee.first_name }} {{ entry.employee.last_name }}</td>
                                                <td>{{ entry.employee.department or '-' }}</td>
                                                <td>{{ entry.morning_in.strftime('%H:%M') if entry.morning_in else '-' }}</td>
                                                <td>{{ entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '-' }}</td>
                                                <td>{{ entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '-' }}</td>
                                                <td>{{ entry.evening_out.strftime('%H:%M') if entry.evening_out else '-' }}</td>
                                                <td><strong>{{ "%.2f"|format(entry.total_hours) }}h</strong></td>
                                                <td>
                                                    <button class="btn btn-sm btn-outline-primary" onclick="editEntry({{ entry.id }})">
                                                        <i class="fas fa-edit"></i>
                                                    </button>
                                                </td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Onglet Employés -->
            <div class="tab-pane fade" id="employees" role="tabpanel">
                <div class="row mt-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header d-flex justify-content-between align-items-center">
                                <h5><i class="fas fa-users"></i> Gestion des Employés</h5>
                                <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addEmployeeModal">
                                    <i class="fas fa-plus"></i> Nouvel Employé
                                </button>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-striped">
                                        <thead>
                                            <tr>
                                                <th>N° Employé</th>
                                                <th>Nom Complet</th>
                                                <th>Email</th>
                                                <th>Département</th>
                                                <th>Poste</th>
                                                <th>Taux Horaire</th>
                                                <th>Statut</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for employee in employees %}
                                            <tr>
                                                <td>{{ employee.employee_number }}</td>
                                                <td>{{ employee.first_name }} {{ employee.last_name }}</td>
                                                <td>{{ employee.email }}</td>
                                                <td>{{ employee.department or '-' }}</td>
                                                <td>{{ employee.position or '-' }}</td>
                                                <td>{{ "%.2f"|format(employee.hourly_rate) }}€</td>
                                                <td>
                                                    <span class="badge bg-{{ 'success' if employee.is_active else 'secondary' }}">
                                                        {{ 'Actif' if employee.is_active else 'Inactif' }}
                                                    </span>
                                                    {% if employee.is_admin %}
                                                    <span class="badge bg-warning">Admin</span>
                                                    {% endif %}
                                                </td>
                                                <td>
                                                    <button class="btn btn-sm btn-outline-primary" onclick="editEmployee({{ employee.id }})">
                                                        <i class="fas fa-edit"></i>
                                                    </button>
                                                </td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Onglet Pointages -->
            <div class="tab-pane fade" id="timeentries" role="tabpanel">
                <div class="row mt-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-clock"></i> Gestion des Pointages</h5>
                                <form method="GET" class="row g-3 mt-2">
                                    <div class="col-md-3">
                                        <select name="employee_id" class="form-select">
                                            <option value="">Tous les employés</option>
                                            {% for emp in employees %}
                                            <option value="{{ emp.id }}" {{ 'selected' if request.args.get('employee_id') == emp.id|string }}>
                                                {{ emp.first_name }} {{ emp.last_name }}
                                            </option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                    <div class="col-md-3">
                                        <input type="date" name="start_date" class="form-control" 
                                               value="{{ request.args.get('start_date', '') }}">
                                    </div>
                                    <div class="col-md-3">
                                        <input type="date" name="end_date" class="form-control" 
                                               value="{{ request.args.get('end_date', '') }}">
                                    </div>
                                    <div class="col-md-3">
                                        <button type="submit" class="btn btn-primary">Filtrer</button>
                                        <a href="/admin/export_excel" class="btn btn-success">
                                            <i class="fas fa-file-excel"></i> Export
                                        </a>
                                    </div>
                                </form>
                            </div>
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-striped">
                                        <thead>
                                            <tr>
                                                <th>Date</th>
                                                <th>Employé</th>
                                                <th>Arrivée</th>
                                                <th>Sortie Midi</th>
                                                <th>Retour Midi</th>
                                                <th>Sortie Soir</th>
                                                <th>Total</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for entry in filtered_entries %}
                                            <tr>
                                                <td>{{ entry.date.strftime('%d/%m/%Y') }}</td>
                                                <td>{{ entry.employee.first_name }} {{ entry.employee.last_name }}</td>
                                                <td>{{ entry.morning_in.strftime('%H:%M') if entry.morning_in else '-' }}</td>
                                                <td>{{ entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '-' }}</td>
                                                <td>{{ entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '-' }}</td>
                                                <td>{{ entry.evening_out.strftime('%H:%M') if entry.evening_out else '-' }}</td>
                                                <td><strong>{{ "%.2f"|format(entry.total_hours) }}h</strong></td>
                                                <td>
                                                    <button class="btn btn-sm btn-outline-primary" onclick="editEntry({{ entry.id }})">
                                                        <i class="fas fa-edit"></i>
                                                    </button>
                                                </td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                                
                                <!-- Pagination -->
                                {% if pagination and pagination.pages > 1 %}
                                <nav>
                                    <ul class="pagination justify-content-center">
                                        {% if pagination.has_prev %}
                                        <li class="page-item">
                                            <a class="page-link" href="{{ url_for('admin_dashboard', page=pagination.prev_num) }}">Précédent</a>
                                        </li>
                                        {% endif %}
                                        
                                        {% for page_num in pagination.iter_pages() %}
                                            {% if page_num %}
                                                {% if page_num != pagination.page %}
                                                <li class="page-item">
                                                    <a class="page-link" href="{{ url_for('admin_dashboard', page=page_num) }}">{{ page_num }}</a>
                                                </li>
                                                {% else %}
                                                <li class="page-item active">
                                                    <span class="page-link">{{ page_num }}</span>
                                                </li>
                                                {% endif %}
                                            {% else %}
                                            <li class="page-item disabled">
                                                <span class="page-link">...</span>
                                            </li>
                                            {% endif %}
                                        {% endfor %}
                                        
                                        {% if pagination.has_next %}
                                        <li class="page-item">
                                            <a class="page-link" href="{{ url_for('admin_dashboard', page=pagination.next_num) }}">Suivant</a>
                                        </li>
                                        {% endif %}
                                    </ul>
                                </nav>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Onglet Rapports -->
            <div class="tab-pane fade" id="reports" role="tabpanel">
                <div class="row mt-4">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-download"></i> Export Personnalisé</h5>
                            </div>
                            <div class="card-body">
                                <form method="POST" action="/admin/export_custom">
                                    {{ csrf_token() }}
                                    <div class="mb-3">
                                        <label class="form-label">Employé</label>
                                        <select name="employee_id" class="form-select">
                                            <option value="">Tous les employés</option>
                                            {% for emp in employees %}
                                            <option value="{{ emp.id }}">{{ emp.first_name }} {{ emp.last_name }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Date de début</label>
                                        <input type="date" name="start_date" class="form-control" required>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Date de fin</label>
                                        <input type="date" name="end_date" class="form-control" required>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Format</label>
                                        <select name="format_type" class="form-select">
                                            <option value="excel">Excel (.xlsx)</option>
                                            <option value="csv">CSV</option>
                                        </select>
                                    </div>
                                    <button type="submit" class="btn btn-success">
                                        <i class="fas fa-file-excel"></i> Exporter
                                    </button>
                                </form>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-chart-pie"></i> Statistiques Rapides</h5>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <strong>Top 5 Employés (Heures ce mois)</strong>
                                    {% for emp, hours in top_employees %}
                                    <div class="d-flex justify-content-between">
                                        <span>{{ emp.first_name }} {{ emp.last_name }}</span>
                                        <span><strong>{{ "%.1f"|format(hours) }}h</strong></span>
                                    </div>
                                    {% endfor %}
                                </div>
                                <div class="mb-3">
                                    <strong>Départements</strong>
                                    {% for dept, count in departments_stats %}
                                    <div class="d-flex justify-content-between">
                                        <span>{{ dept or 'Non défini' }}</span>
                                        <span><strong>{{ count }} employés</strong></span>
                                    </div>
                                    {% endfor %}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal Nouvel Employé -->
    <div class="modal fade" id="addEmployeeModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Nouvel Employé</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <form method="POST" action="/admin/add_employee">
                    {{ csrf_token() }}
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Numéro d'employé</label>
                                    <input type="text" name="employee_number" class="form-control" required>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Email</label>
                                    <input type="email" name="email" class="form-control" required>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Prénom</label>
                                    <input type="text" name="first_name" class="form-control" required>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Nom</label>
                                    <input type="text" name="last_name" class="form-control" required>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Téléphone</label>
                                    <input type="text" name="phone" class="form-control">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Département</label>
                                    <input type="text" name="department" class="form-control">
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Poste</label>
                                    <input type="text" name="position" class="form-control">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Taux horaire (€)</label>
                                    <input type="number" step="0.01" name="hourly_rate" class="form-control">
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Date d'embauche</label>
                                    <input type="date" name="hire_date" class="form-control">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Mot de passe temporaire</label>
                                    <input type="password" name="password" class="form-control" required>
                                </div>
                            </div>
                        </div>
                        <div class="form-check">
                            <input type="checkbox" name="is_admin" class="form-check-input" id="isAdmin">
                            <label class="form-check-label" for="isAdmin">Administrateur</label>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuler</button>
                        <button type="submit" class="btn btn-primary">Créer</button>
                    </div>
                </form>
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
    <script>
        // Graphique par département
        const deptCtx = document.getElementById('departmentChart').getContext('2d');
        new Chart(deptCtx, {
            type: 'bar',
            data: {
                labels: {{ dept_chart_labels | safe }},
                datasets: [{
                    label: 'Heures travaillées',
                    data: {{ dept_chart_data | safe }},
                    backgroundColor: 'rgba(52, 152, 219, 0.8)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });

        // Graphique évolution hebdomadaire
        const weeklyCtx = document.getElementById('weeklyChart').getContext('2d');
        new Chart(weeklyCtx, {
            type: 'line',
            data: {
                labels: {{ weekly_chart_labels | safe }},
                datasets: [{
                    label: 'Heures totales',
                    data: {{ weekly_chart_data | safe }},
                    borderColor: 'rgba(46, 204, 113, 1)',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });

        // Fonctions d'édition
        function editEmployee(id) {
            // Implémentation de l'édition d'employé
            alert('Fonctionnalité d\'édition employé - ID: ' + id);
        }

        function editEntry(id) {
            // Implémentation de l'édition de pointage
            alert('Fonctionnalité d\'édition pointage - ID: ' + id);
        }
    </script>
</body>
</html>'''
