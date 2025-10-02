#!/usr/bin/env python3
"""
Application de Pointage - Version Finale avec HTML Intégré
Application Flask sécurisée pour la gestion du temps de travail
Générée par Claude 4.X avec toutes les améliorations de sécurité
"""

import os
import logging
from datetime import datetime, date, time, timedelta
from functools import wraps
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify, session, render_template_string
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
app = Flask(__name__)

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

# Templates HTML intégrés
INDEX_HTML = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Système de Pointage - Accueil</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.5/dist/purify.min.js"></script>
    <style>
        :root {
            --primary-color: #2c3e50;
            --secondary-color: #3498db;
            --success-color: #27ae60;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
        }
        body {
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .main-container {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border: none;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .card-header {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            border: none;
            padding: 2rem;
            text-align: center;
        }
        .security-badge {
            display: inline-block;
            background: var(--success-color);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 25px;
            font-size: 0.9rem;
            font-weight: 600;
            margin-top: 1rem;
        }
        .clock {
            font-size: 3rem;
            font-weight: 700;
            color: var(--primary-color);
            text-align: center;
            margin: 2rem 0;
            font-family: 'Courier New', monospace;
        }
        .btn {
            border-radius: 10px;
            padding: 0.75rem 2rem;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        .punch-btn {
            margin: 0.5rem;
            min-width: 150px;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="container">
            <div class="row justify-content-center">
                <div class="col-12 col-md-8 col-lg-6">
                    <div class="card">
                        <div class="card-header">
                            <h1><i class="fas fa-clock"></i> Système de Pointage</h1>
                            <p class="subtitle">Gestion moderne du temps de travail</p>
                            <div class="security-badge">
                                <i class="fas fa-shield-alt"></i> Sécurisé Claude 4.X
                            </div>
                        </div>
                        
                        <div class="card-body p-4">
                            <!-- Formulaire de connexion -->
                            <div id="loginForm">
                                <form onsubmit="handleLogin(event)">
                                    <div class="mb-3">
                                        <label for="employee_number" class="form-label">
                                            <i class="fas fa-user"></i> Numéro d'employé
                                        </label>
                                        <input type="text" class="form-control" id="employee_number" 
                                               name="employee_number" required autocomplete="username"
                                               placeholder="Ex: ADMIN001, EMP001...">
                                    </div>
                                    <div class="mb-3">
                                        <label for="password" class="form-label">
                                            <i class="fas fa-lock"></i> Mot de passe
                                        </label>
                                        <input type="password" class="form-control" id="password" 
                                               name="password" required autocomplete="current-password">
                                    </div>
                                    <div class="d-grid">
                                        <button type="submit" class="btn btn-primary">
                                            <i class="fas fa-sign-in-alt"></i> Se connecter
                                        </button>
                                    </div>
                                </form>
                                
                                <div class="mt-4 text-center">
                                    <small class="text-muted">
                                        <strong>Comptes de test:</strong><br>
                                        Admin: ADMIN001 / admin123<br>
                                        Employé: EMP001 / password123
                                    </small>
                                </div>
                            </div>
                            
                            <!-- Système de pointage -->
                            <div id="punchSystem" style="display: none;">
                                <div class="text-center mb-4">
                                    <div class="clock" id="currentTime"></div>
                                    <h4 id="welcomeMessage"></h4>
                                </div>
                                
                                <div class="d-flex justify-content-center flex-wrap">
                                    <button class="btn btn-success punch-btn" onclick="punch('morning_in')">
                                        <i class="fas fa-sun"></i> Arrivée Matin
                                    </button>
                                    <button class="btn btn-warning punch-btn" onclick="punch('lunch_out')">
                                        <i class="fas fa-utensils"></i> Sortie Midi
                                    </button>
                                    <button class="btn btn-info punch-btn" onclick="punch('lunch_in')">
                                        <i class="fas fa-coffee"></i> Retour Midi
                                    </button>
                                    <button class="btn btn-danger punch-btn" onclick="punch('evening_out')">
                                        <i class="fas fa-moon"></i> Sortie Soir
                                    </button>
                                </div>
                                
                                <div class="mt-4 text-center">
                                    <button class="btn btn-outline-secondary" onclick="logout()">
                                        <i class="fas fa-sign-out-alt"></i> Déconnexion
                                    </button>
                                    <button id="adminBtn" class="btn btn-outline-primary ms-2" onclick="goToAdmin()" style="display: none;">
                                        <i class="fas fa-cog"></i> Administration
                                    </button>
                                </div>
                            </div>
                            
                            <!-- Messages d'alerte -->
                            <div id="alertContainer"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentUser = null;

        function sanitizeInput(input) {
            return DOMPurify.sanitize(input.toString().trim());
        }

        function showAlert(message, type = 'info') {
            const alertContainer = document.getElementById('alertContainer');
            const alertId = 'alert-' + Date.now();
            
            const alertHtml = `
                <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show mt-3" role="alert">
                    <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-triangle' : 'info-circle'}"></i>
                    ${sanitizeInput(message)}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
            
            alertContainer.innerHTML = alertHtml;
            
            setTimeout(() => {
                const alert = document.getElementById(alertId);
                if (alert) {
                    alert.remove();
                }
            }, 5000);
        }

        function updateClock() {
            const now = new Date();
            const timeString = now.toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
            const clockElement = document.getElementById('currentTime');
            if (clockElement) {
                clockElement.textContent = timeString;
            }
        }

        setInterval(updateClock, 1000);
        updateClock();

        async function handleLogin(event) {
            event.preventDefault();
            
            const form = event.target;
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connexion...';
            
            const data = {
                employee_number: sanitizeInput(form.employee_number.value),
                password: form.password.value
            };

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (response.ok) {
                    currentUser = result.employee;
                    showAlert('Connexion réussie !', 'success');
                    
                    document.getElementById('loginForm').style.display = 'none';
                    document.getElementById('punchSystem').style.display = 'block';
                    
                    document.getElementById('welcomeMessage').textContent = 
                        `Bienvenue, ${currentUser.first_name} ${currentUser.last_name}`;
                    
                    if (result.is_admin) {
                        document.getElementById('adminBtn').style.display = 'inline-block';
                    }
                } else {
                    showAlert(result.error || 'Erreur de connexion', 'danger');
                }
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur de connexion au serveur', 'danger');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        }

        async function punch(type) {
            const typeLabels = {
                'morning_in': 'Arrivée matin',
                'lunch_out': 'Sortie midi',
                'lunch_in': 'Retour midi',
                'evening_out': 'Sortie soir'
            };

            try {
                const now = new Date();
                const response = await fetch('/api/timeentries', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        [type]: now.toISOString()
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    showAlert(`${typeLabels[type]} enregistrée à ${now.toLocaleTimeString('fr-FR')}`, 'success');
                } else {
                    showAlert(result.error || 'Erreur lors du pointage', 'danger');
                }
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur de connexion au serveur', 'danger');
            }
        }

        async function logout() {
            try {
                const response = await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });

                if (response.ok) {
                    currentUser = null;
                    document.getElementById('loginForm').style.display = 'block';
                    document.getElementById('punchSystem').style.display = 'none';
                    document.getElementById('adminBtn').style.display = 'none';
                    
                    document.querySelector('#loginForm form').reset();
                    
                    showAlert('Déconnexion réussie', 'success');
                } else {
                    showAlert('Erreur lors de la déconnexion', 'danger');
                }
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur de connexion au serveur', 'danger');
            }
        }

        function goToAdmin() {
            window.location.href = '/admin';
        }

        async function checkAuth() {
            try {
                const response = await fetch('/api/auth/check');
                const data = await response.json();

                if (data.authenticated) {
                    currentUser = data.employee;
                    document.getElementById('loginForm').style.display = 'none';
                    document.getElementById('punchSystem').style.display = 'block';
                    
                    document.getElementById('welcomeMessage').textContent = 
                        `Bienvenue, ${currentUser.first_name} ${currentUser.last_name}`;
                    
                    if (data.is_admin) {
                        document.getElementById('adminBtn').style.display = 'inline-block';
                    }
                } else {
                    document.getElementById('loginForm').style.display = 'block';
                    document.getElementById('punchSystem').style.display = 'none';
                }
            } catch (error) {
                console.error('Erreur lors de la vérification de l\'authentification:', error);
                document.getElementById('loginForm').style.display = 'block';
                document.getElementById('punchSystem').style.display = 'none';
            }
        }

        document.addEventListener('DOMContentLoaded', function() {
            checkAuth();
            
            window.addEventListener('error', function(e) {
                console.error('Erreur JavaScript:', e.error);
            });
            
            if (window.location.hash.includes('<script')) {
                window.location.hash = '';
            }
        });
    </script>
</body>
</html>'''

ADMIN_HTML = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Administration - Système de Pointage</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.5/dist/purify.min.js"></script>
    <style>
        :root {
            --primary-color: #2c3e50;
            --secondary-color: #3498db;
            --success-color: #27ae60;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
            --light-bg: #ecf0f1;
        }
        body {
            background-color: var(--light-bg);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
        }
        .stats-card {
            background: white;
            border-radius: 15px;
            padding: 1.5rem;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            border: none;
            transition: transform 0.3s ease;
        }
        .stats-card:hover {
            transform: translateY(-5px);
        }
        .stats-icon {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            color: white;
        }
        .stats-icon.primary { background: var(--primary-color); }
        .stats-icon.success { background: var(--success-color); }
        .stats-icon.warning { background: var(--warning-color); }
        .stats-icon.danger { background: var(--danger-color); }
        .table-container {
            background: white;
            border-radius: 15px;
            padding: 1.5rem;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            margin-top: 2rem;
        }
        .btn {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="#">
                <i class="fas fa-clock"></i> Administration Pointage
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/" onclick="logout()">
                    <i class="fas fa-sign-out-alt"></i> Déconnexion
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <!-- Dashboard -->
        <div class="row mb-4">
            <div class="col-md-3 mb-3">
                <div class="stats-card">
                    <div class="d-flex align-items-center">
                        <div class="stats-icon primary">
                            <i class="fas fa-users"></i>
                        </div>
                        <div class="ms-3">
                            <h3 id="totalEmployees" class="mb-0">-</h3>
                            <small class="text-muted">Employés Actifs</small>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="stats-card">
                    <div class="d-flex align-items-center">
                        <div class="stats-icon success">
                            <i class="fas fa-clock"></i>
                        </div>
                        <div class="ms-3">
                            <h3 id="todayEntries" class="mb-0">-</h3>
                            <small class="text-muted">Pointages Aujourd'hui</small>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="stats-card">
                    <div class="d-flex align-items-center">
                        <div class="stats-icon warning">
                            <i class="fas fa-hourglass-half"></i>
                        </div>
                        <div class="ms-3">
                            <h3 id="weekHours" class="mb-0">-</h3>
                            <small class="text-muted">Heures Cette Semaine</small>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3 mb-3">
                <div class="stats-card">
                    <div class="d-flex align-items-center">
                        <div class="stats-icon danger">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <div class="ms-3">
                            <h3 id="pendingEntries" class="mb-0">-</h3>
                            <small class="text-muted">Pointages Incomplets</small>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Gestion des pointages -->
        <div class="table-container">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2><i class="fas fa-clock"></i> Gestion des Pointages</h2>
                <div>
                    <button class="btn btn-success" onclick="showCreateModal()">
                        <i class="fas fa-plus"></i> Nouveau Pointage
                    </button>
                    <button class="btn btn-info" onclick="exportData()">
                        <i class="fas fa-download"></i> Exporter
                    </button>
                </div>
            </div>

            <!-- Filtres -->
            <div class="row mb-3">
                <div class="col-md-3">
                    <label class="form-label">Employé</label>
                    <select id="filterEmployee" class="form-select">
                        <option value="">Tous les employés</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label class="form-label">Date de début</label>
                    <input type="date" id="filterStartDate" class="form-control">
                </div>
                <div class="col-md-3">
                    <label class="form-label">Date de fin</label>
                    <input type="date" id="filterEndDate" class="form-control">
                </div>
                <div class="col-md-3">
                    <label class="form-label">&nbsp;</label>
                    <div class="d-grid">
                        <button class="btn btn-primary" onclick="loadTimeentries()">
                            <i class="fas fa-search"></i> Filtrer
                        </button>
                    </div>
                </div>
            </div>

            <!-- Table -->
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead class="table-dark">
                        <tr>
                            <th>ID</th>
                            <th>Employé</th>
                            <th>Date</th>
                            <th>Arrivée Matin</th>
                            <th>Sortie Midi</th>
                            <th>Retour Midi</th>
                            <th>Sortie Soir</th>
                            <th>Total Heures</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="timeentriesTableBody">
                        <tr>
                            <td colspan="9" class="text-center">Chargement...</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Pagination -->
            <div class="d-flex justify-content-between align-items-center mt-3">
                <div>
                    <span id="paginationInfo" class="text-muted">Chargement...</span>
                </div>
                <nav>
                    <ul class="pagination" id="pagination"></ul>
                </nav>
            </div>
        </div>
    </div>

    <!-- Modal pour créer/modifier un pointage -->
    <div class="modal fade" id="timeentryModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header bg-primary text-white">
                    <h5 class="modal-title" id="modalTitle">
                        <i class="fas fa-clock"></i> Nouveau Pointage
                    </h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="timeentryForm">
                        <input type="hidden" id="timeentryId">
                        
                        <div class="mb-3">
                            <label for="modalEmployee" class="form-label">Employé *</label>
                            <select id="modalEmployee" class="form-select" required>
                                <option value="">Sélectionner un employé</option>
                            </select>
                        </div>
                        
                        <div class="mb-3">
                            <label for="modalDate" class="form-label">Date *</label>
                            <input type="date" id="modalDate" class="form-control" required>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label for="modalMorningIn" class="form-label">Arrivée Matin</label>
                                <input type="time" id="modalMorningIn" class="form-control">
                            </div>
                            <div class="col-md-6 mb-3">
                                <label for="modalLunchOut" class="form-label">Sortie Midi</label>
                                <input type="time" id="modalLunchOut" class="form-control">
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <label for="modalLunchIn" class="form-label">Retour Midi</label>
                                <input type="time" id="modalLunchIn" class="form-control">
                            </div>
                            <div class="col-md-6 mb-3">
                                <label for="modalEveningOut" class="form-label">Sortie Soir</label>
                                <input type="time" id="modalEveningOut" class="form-control">
                            </div>
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuler</button>
                    <button type="button" class="btn btn-primary" onclick="saveTimeentry()">
                        <i class="fas fa-save"></i> Enregistrer
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let timeentriesData = [];
        let employeesData = [];
        let currentPage = 1;
        let totalPages = 1;

        function sanitize(input) {
            return DOMPurify.sanitize(input.toString());
        }

        function showAlert(message, type = 'info') {
            const alertHtml = `
                <div class="alert alert-${type} alert-dismissible fade show position-fixed" 
                     style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;" role="alert">
                    <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-triangle' : 'info-circle'}"></i>
                    ${sanitize(message)}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', alertHtml);
            
            setTimeout(() => {
                const alerts = document.querySelectorAll('.alert');
                if (alerts.length > 0) {
                    alerts[alerts.length - 1].remove();
                }
            }, 5000);
        }

        async function loadDashboard() {
            try {
                const [employeesRes, timeentriesRes] = await Promise.all([
                    fetch('/api/employees'),
                    fetch('/api/admin/timeentries?limit=100')
                ]);
                
                if (!employeesRes.ok || !timeentriesRes.ok) {
                    throw new Error('Erreur lors du chargement des données');
                }
                
                const employeesData = await employeesRes.json();
                const timeentriesData = await timeentriesRes.json();
                
                document.getElementById('totalEmployees').textContent = employeesData.employees.length;
                
                const today = new Date().toISOString().split('T')[0];
                const todayEntries = timeentriesData.timeentries.filter(entry => entry.date === today);
                document.getElementById('todayEntries').textContent = todayEntries.length;
                
                const weekStart = new Date();
                weekStart.setDate(weekStart.getDate() - weekStart.getDay());
                const weekStartStr = weekStart.toISOString().split('T')[0];
                
                const weekEntries = timeentriesData.timeentries.filter(entry => entry.date >= weekStartStr);
                const weekHours = weekEntries.reduce((sum, entry) => sum + (entry.total_hours || 0), 0);
                document.getElementById('weekHours').textContent = Math.round(weekHours);
                
                const incompleteEntries = timeentriesData.timeentries.filter(entry => 
                    !entry.morning_in || !entry.evening_out
                );
                document.getElementById('pendingEntries').textContent = incompleteEntries.length;
                
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur lors du chargement du dashboard', 'danger');
            }
        }

        async function loadEmployees() {
            try {
                const response = await fetch('/api/employees');
                if (response.ok) {
                    const data = await response.json();
                    employeesData = data.employees;
                    populateEmployeeSelects();
                }
            } catch (error) {
                console.error('Erreur:', error);
            }
        }

        function populateEmployeeSelects() {
            const selects = ['filterEmployee', 'modalEmployee'];
            
            selects.forEach(selectId => {
                const select = document.getElementById(selectId);
                const currentValue = select.value;
                
                const firstOption = select.querySelector('option');
                select.innerHTML = '';
                select.appendChild(firstOption);
                
                employeesData.forEach(emp => {
                    const option = document.createElement('option');
                    option.value = emp.id;
                    option.textContent = `${emp.first_name} ${emp.last_name} (${emp.employee_number})`;
                    select.appendChild(option);
                });
                
                select.value = currentValue;
            });
        }

        async function loadTimeentries() {
            try {
                const params = new URLSearchParams({
                    limit: 20,
                    offset: (currentPage - 1) * 20
                });
                
                const employeeFilter = document.getElementById('filterEmployee').value;
                const startDateFilter = document.getElementById('filterStartDate').value;
                const endDateFilter = document.getElementById('filterEndDate').value;
                
                if (employeeFilter) params.append('employee_id', employeeFilter);
                if (startDateFilter) params.append('start_date', startDateFilter);
                if (endDateFilter) params.append('end_date', endDateFilter);
                
                const response = await fetch(`/api/admin/timeentries?${params}`);
                if (!response.ok) throw new Error('Erreur serveur');
                
                const data = await response.json();
                timeentriesData = data.timeentries;
                
                updateTimeentriesTable();
                
                totalPages = Math.ceil(data.total_count / 20);
                updatePagination(data.total_count);
                
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur lors du chargement des pointages', 'danger');
            }
        }

        function updateTimeentriesTable() {
            const tbody = document.getElementById('timeentriesTableBody');
            tbody.innerHTML = '';
            
            if (timeentriesData.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="text-center">Aucun pointage trouvé</td></tr>';
                return;
            }
            
            timeentriesData.forEach(entry => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${sanitize(entry.id)}</td>
                    <td>${sanitize(entry.employee_name)}</td>
                    <td>${sanitize(entry.date)}</td>
                    <td>${sanitize(entry.morning_in || '-')}</td>
                    <td>${sanitize(entry.lunch_out || '-')}</td>
                    <td>${sanitize(entry.lunch_in || '-')}</td>
                    <td>${sanitize(entry.evening_out || '-')}</td>
                    <td><strong>${sanitize(entry.total_hours || 0)}h</strong></td>
                    <td>
                        <button class="btn btn-sm btn-warning me-1" onclick="editTimeentry(${entry.id})">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteTimeentry(${entry.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }

        function updatePagination(totalCount) {
            const paginationInfo = document.getElementById('paginationInfo');
            const start = (currentPage - 1) * 20 + 1;
            const end = Math.min(currentPage * 20, totalCount);
            paginationInfo.textContent = `Affichage de ${start} à ${end} sur ${totalCount} entrées`;
            
            const pagination = document.getElementById('pagination');
            pagination.innerHTML = '';
            
            if (totalPages <= 1) return;
            
            const prevLi = document.createElement('li');
            prevLi.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
            prevLi.innerHTML = `<a class="page-link" href="#" onclick="changePage(${currentPage - 1})">Précédent</a>`;
            pagination.appendChild(prevLi);
            
            const startPage = Math.max(1, currentPage - 2);
            const endPage = Math.min(totalPages, currentPage + 2);
            
            for (let i = startPage; i <= endPage; i++) {
                const li = document.createElement('li');
                li.className = `page-item ${i === currentPage ? 'active' : ''}`;
                li.innerHTML = `<a class="page-link" href="#" onclick="changePage(${i})">${i}</a>`;
                pagination.appendChild(li);
            }
            
            const nextLi = document.createElement('li');
            nextLi.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
            nextLi.innerHTML = `<a class="page-link" href="#" onclick="changePage(${currentPage + 1})">Suivant</a>`;
            pagination.appendChild(nextLi);
        }

        function changePage(page) {
            if (page >= 1 && page <= totalPages && page !== currentPage) {
                currentPage = page;
                loadTimeentries();
            }
        }

        function showCreateModal() {
            document.getElementById('modalTitle').innerHTML = '<i class="fas fa-plus"></i> Nouveau Pointage';
            document.getElementById('timeentryForm').reset();
            document.getElementById('timeentryId').value = '';
            document.getElementById('modalDate').value = new Date().toISOString().split('T')[0];
            
            const modal = new bootstrap.Modal(document.getElementById('timeentryModal'));
            modal.show();
        }

        async function editTimeentry(id) {
            try {
                const entry = timeentriesData.find(e => e.id === id);
                if (!entry) return;
                
                document.getElementById('modalTitle').innerHTML = '<i class="fas fa-edit"></i> Modifier Pointage';
                document.getElementById('timeentryId').value = entry.id;
                document.getElementById('modalEmployee').value = entry.employee_id;
                document.getElementById('modalDate').value = entry.date;
                document.getElementById('modalMorningIn').value = entry.morning_in || '';
                document.getElementById('modalLunchOut').value = entry.lunch_out || '';
                document.getElementById('modalLunchIn').value = entry.lunch_in || '';
                document.getElementById('modalEveningOut').value = entry.evening_out || '';
                
                const modal = new bootstrap.Modal(document.getElementById('timeentryModal'));
                modal.show();
                
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur lors du chargement du pointage', 'danger');
            }
        }

        async function saveTimeentry() {
            try {
                const form = document.getElementById('timeentryForm');
                if (!form.checkValidity()) {
                    form.reportValidity();
                    return;
                }
                
                const id = document.getElementById('timeentryId').value;
                const data = {
                    employee_id: parseInt(document.getElementById('modalEmployee').value),
                    date: document.getElementById('modalDate').value,
                    morning_in: document.getElementById('modalMorningIn').value || null,
                    lunch_out: document.getElementById('modalLunchOut').value || null,
                    lunch_in: document.getElementById('modalLunchIn').value || null,
                    evening_out: document.getElementById('modalEveningOut').value || null
                };
                
                const url = id ? `/api/admin/timeentries/${id}` : '/api/admin/timeentries';
                const method = id ? 'PUT' : 'POST';
                
                const response = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Erreur serveur');
                }
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('timeentryModal'));
                modal.hide();
                
                showAlert(id ? 'Pointage modifié avec succès' : 'Pointage créé avec succès', 'success');
                loadTimeentries();
                
            } catch (error) {
                console.error('Erreur:', error);
                showAlert(error.message, 'danger');
            }
        }

        async function deleteTimeentry(id) {
            if (!confirm('Êtes-vous sûr de vouloir supprimer ce pointage ?')) {
                return;
            }
            
            try {
                const response = await fetch(`/api/admin/timeentries/${id}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Erreur serveur');
                }
                
                showAlert('Pointage supprimé avec succès', 'success');
                loadTimeentries();
                
            } catch (error) {
                console.error('Erreur:', error);
                showAlert(error.message, 'danger');
            }
        }

        async function exportData() {
            try {
                const params = new URLSearchParams();
                const employeeFilter = document.getElementById('filterEmployee').value;
                const startDateFilter = document.getElementById('filterStartDate').value;
                const endDateFilter = document.getElementById('filterEndDate').value;
                
                if (employeeFilter) params.append('employee_id', employeeFilter);
                if (startDateFilter) params.append('start_date', startDateFilter);
                if (endDateFilter) params.append('end_date', endDateFilter);
                
                params.append('limit', '10000');
                
                const response = await fetch(`/api/admin/timeentries?${params}`);
                if (!response.ok) throw new Error('Erreur serveur');
                
                const data = await response.json();
                
                const headers = ['ID', 'Employé', 'Date', 'Arrivée Matin', 'Sortie Midi', 'Retour Midi', 'Sortie Soir', 'Total Heures'];
                const csvContent = [
                    headers.join(','),
                    ...data.timeentries.map(entry => [
                        entry.id,
                        `"${entry.employee_name}"`,
                        entry.date,
                        entry.morning_in || '',
                        entry.lunch_out || '',
                        entry.lunch_in || '',
                        entry.evening_out || '',
                        entry.total_hours || 0
                    ].join(','))
                ].join('\\n');
                
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = `pointages_${new Date().toISOString().split('T')[0]}.csv`;
                link.click();
                
                showAlert('Export réalisé avec succès', 'success');
                
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur lors de l\\'export', 'danger');
            }
        }

        async function logout() {
            try {
                const response = await fetch('/api/auth/logout', {
                    method: 'POST'
                });
                
                if (response.ok) {
                    window.location.href = '/';
                } else {
                    showAlert('Erreur lors de la déconnexion', 'danger');
                }
            } catch (error) {
                console.error('Erreur:', error);
                showAlert('Erreur de connexion au serveur', 'danger');
            }
        }

        async function checkAuth() {
            try {
                const response = await fetch('/api/auth/check');
                const data = await response.json();
                
                if (!data.authenticated || !data.is_admin) {
                    window.location.href = '/';
                    return;
                }
                
            } catch (error) {
                console.error('Erreur:', error);
                window.location.href = '/';
            }
        }

        document.addEventListener('DOMContentLoaded', async function() {
            await checkAuth();
            await loadEmployees();
            await loadDashboard();
            await loadTimeentries();
            
            window.addEventListener('error', function(e) {
                console.error('Erreur JavaScript:', e.error);
            });
        });
    </script>
</body>
</html>'''

# Routes principales
@app.route('/')
def index():
    """Page d'accueil"""
    return render_template_string(INDEX_HTML)

@app.route('/admin')
def admin():
    """Interface d'administration"""
    return render_template_string(ADMIN_HTML)

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
            return jsonify({'success': False, 'error': 'employee_id et date requis'}), 400
        
        # Vérifier que l'employé existe
        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'error': 'Employé non trouvé'}), 404
        
        # Parser la date
        try:
            entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        # Vérifier si une entrée existe déjà
        existing_entry = TimeEntry.query.filter_by(employee_id=employee_id, date=entry_date).first()
        if existing_entry:
            return jsonify({'success': False, 'error': 'Un pointage existe déjà pour cette date'}), 400
        
        # Créer la nouvelle entrée
        time_entry = TimeEntry(employee_id=employee_id, date=entry_date)
        
        # Mettre à jour les heures de pointage
        for field in ['morning_in', 'lunch_out', 'lunch_in', 'evening_out']:
            if field in data:
                time_str = data[field]
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
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la création du pointage: {str(e)}")
        return jsonify({'success': False, 'error': 'Erreur interne du serveur'}), 500

@app.route('/api/admin/timeentries/<int:timeentry_id>', methods=['PUT'])
@admin_required
def admin_update_timeentry(timeentry_id):
    """Mettre à jour un pointage (admin seulement)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON requises'}), 400
        
        time_entry = TimeEntry.query.get(timeentry_id)
        if not time_entry:
            return jsonify({'success': False, 'error': 'Pointage non trouvé'}), 404
        
        # Mettre à jour les champs si fournis
        if 'employee_id' in data:
            employee = Employee.query.get(data['employee_id'])
            if not employee:
                return jsonify({'success': False, 'error': 'Employé non trouvé'}), 404
            time_entry.employee_id = data['employee_id']
        
        if 'date' in data:
            try:
                time_entry.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Format de date invalide'}), 400
        
        # Mettre à jour les heures de pointage
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
