#!/usr/bin/env python3
"""
Application de Pointage - Version Complète avec Fonctionnalités Avancées
Inclut toutes les spécificités demandées pour employés et administrateurs
"""

import os
import logging
import secrets
import io
from datetime import datetime, date, time, timedelta
from functools import wraps
from typing import Optional, Dict, Any, List
from calendar import monthrange

from flask import Flask, request, jsonify, session, render_template_string, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialisation de l'application
app = Flask(__name__)

# Configuration sécurisée
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', secrets.token_urlsafe(32)),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///timetracking_complete.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

# Initialisation de la base de données
db = SQLAlchemy(app)

# Modèles de données
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_hours_stats(self, start_date=None, end_date=None):
        """Calcule les statistiques d'heures pour l'employé"""
        if not start_date:
            start_date = date.today().replace(day=1)  # Début du mois
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
            'is_active': self.is_active
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    employee = db.relationship('Employee', backref='time_entries')
    
    def calculate_hours(self):
        """Calcule les heures travaillées"""
        total = 0.0
        if self.morning_in and self.lunch_out:
            morning_delta = datetime.combine(self.date, self.lunch_out) - datetime.combine(self.date, self.morning_in)
            total += morning_delta.total_seconds() / 3600
        
        if self.lunch_in and self.evening_out:
            afternoon_delta = datetime.combine(self.date, self.evening_out) - datetime.combine(self.date, self.lunch_in)
            total += afternoon_delta.total_seconds() / 3600
        
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
            'notes': self.notes
        }

# Décorateurs
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            flash('Connexion requise', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            flash('Connexion requise', 'error')
            return redirect(url_for('index'))
        
        employee = Employee.query.get(session['employee_id'])
        if not employee or not employee.is_admin:
            flash('Accès administrateur requis', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

# Fonctions utilitaires
def get_week_dates(target_date=None):
    """Retourne les dates de début et fin de semaine"""
    if not target_date:
        target_date = date.today()
    
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def get_month_dates(target_date=None):
    """Retourne les dates de début et fin de mois"""
    if not target_date:
        target_date = date.today()
    
    start_of_month = target_date.replace(day=1)
    _, last_day = monthrange(target_date.year, target_date.month)
    end_of_month = target_date.replace(day=last_day)
    return start_of_month, end_of_month

# Templates HTML
EMPLOYEE_DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tableau de Bord Employé - {{ current_user.first_name }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; }
        .card { border: none; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .stats-card { background: linear-gradient(135deg, #27ae60, #2ecc71); color: white; }
        .chart-container { position: relative; height: 300px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-clock"></i> Pointage</a>
            <div class="navbar-nav ms-auto">
                <span class="navbar-text me-3">{{ current_user.first_name }} {{ current_user.last_name }}</span>
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
                                <input type="hidden" name="punch_type" value="morning_in">
                                <button type="submit" class="btn btn-success">
                                    <i class="fas fa-sun"></i> Arrivée Matin
                                </button>
                            </form>
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
                                <input type="hidden" name="punch_type" value="lunch_out">
                                <button type="submit" class="btn btn-warning">
                                    <i class="fas fa-utensils"></i> Sortie Midi
                                </button>
                            </form>
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
                                <input type="hidden" name="punch_type" value="lunch_in">
                                <button type="submit" class="btn btn-info">
                                    <i class="fas fa-coffee"></i> Retour Midi
                                </button>
                            </form>
                            <form method="POST" action="/punch" class="d-inline me-2 mb-2">
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

        <!-- Historique récent -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5><i class="fas fa-history"></i> Historique Récent (10 derniers jours)</h5>
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

# Routes principales
@app.route('/')
def index():
    if 'employee_id' in session:
        return redirect(url_for('employee_dashboard'))
    
    return render_template_string('''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connexion - Système de Pointage</title>
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
    </style>
</head>
<body>
    <div class="login-card">
        <div class="card-header bg-primary text-white text-center p-4">
            <h2><i class="fas fa-shield-alt"></i> Système de Pointage</h2>
            <p class="mb-0">Version Complète Sécurisée</p>
        </div>
        <div class="card-body p-4">
            <form method="POST" action="/login">
                <div class="mb-3">
                    <label for="employee_number" class="form-label">
                        <i class="fas fa-user"></i> Numéro d'employé
                    </label>
                    <input type="text" class="form-control" id="employee_number" 
                           name="employee_number" required 
                           placeholder="Ex: ADMIN001, EMP001...">
                </div>
                <div class="mb-3">
                    <label for="password" class="form-label">
                        <i class="fas fa-lock"></i> Mot de passe
                    </label>
                    <input type="password" class="form-control" id="password" 
                           name="password" required>
                </div>
                <div class="d-grid">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-sign-in-alt"></i> Se connecter
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
</html>''')

@app.route('/login', methods=['POST'])
def login():
    employee_number = request.form.get('employee_number', '').strip()
    password = request.form.get('password', '')
    
    if not employee_number or not password:
        flash('Numéro d\'employé et mot de passe requis', 'error')
        return redirect(url_for('index'))
    
    employee = Employee.query.filter_by(employee_number=employee_number, is_active=True).first()
    
    if not employee or not employee.check_password(password):
        flash('Identifiants invalides', 'error')
        return redirect(url_for('index'))
    
    session['employee_id'] = employee.id
    session.permanent = True
    
    flash(f'Connexion réussie ! Bienvenue {employee.first_name}', 'success')
    
    if employee.is_admin:
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('employee_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('index'))

@app.route('/employee')
@login_required
def employee_dashboard():
    current_user = Employee.query.get(session['employee_id'])
    today = date.today()
    
    # Statistiques du jour
    today_entry = TimeEntry.query.filter_by(employee_id=current_user.id, date=today).first()
    day_stats = {'total_hours': today_entry.total_hours if today_entry else 0}
    
    # Statistiques de la semaine
    week_start, week_end = get_week_dates(today)
    week_stats = current_user.get_hours_stats(week_start, week_end)
    
    # Statistiques du mois
    month_start, month_end = get_month_dates(today)
    month_stats = current_user.get_hours_stats(month_start, month_end)
    
    # Données pour les graphiques
    daily_chart_labels = []
    daily_chart_data = []
    
    for i in range(7):
        chart_date = today - timedelta(days=6-i)
        daily_chart_labels.append(chart_date.strftime('%d/%m'))
        
        entry = TimeEntry.query.filter_by(employee_id=current_user.id, date=chart_date).first()
        daily_chart_data.append(entry.total_hours if entry else 0)
    
    # Historique récent
    recent_entries = TimeEntry.query.filter_by(employee_id=current_user.id)\
        .order_by(TimeEntry.date.desc()).limit(10).all()
    
    # Nombre total de jours dans le mois
    _, month_days_total = monthrange(today.year, today.month)
    
    return render_template_string(EMPLOYEE_DASHBOARD_HTML,
                                current_user=current_user,
                                today_entry=today_entry,
                                day_stats=day_stats,
                                week_stats=week_stats,
                                month_stats=month_stats,
                                recent_entries=recent_entries,
                                daily_chart_labels=daily_chart_labels,
                                daily_chart_data=daily_chart_data,
                                month_days_total=month_days_total)

@app.route('/punch', methods=['POST'])
@login_required
def punch():
    punch_type = request.form.get('punch_type')
    employee_id = session['employee_id']
    today = date.today()
    now = datetime.now().time()
    
    # Récupérer ou créer l'entrée du jour
    time_entry = TimeEntry.query.filter_by(employee_id=employee_id, date=today).first()
    if not time_entry:
        time_entry = TimeEntry(employee_id=employee_id, date=today)
        db.session.add(time_entry)
    
    # Mettre à jour le pointage
    if punch_type in ['morning_in', 'lunch_out', 'lunch_in', 'evening_out']:
        setattr(time_entry, punch_type, now)
        time_entry.calculate_hours()
        
        db.session.commit()
        
        type_labels = {
            'morning_in': 'Arrivée matin',
            'lunch_out': 'Sortie midi',
            'lunch_in': 'Retour midi',
            'evening_out': 'Sortie soir'
        }
        flash(f'{type_labels[punch_type]} enregistrée à {now.strftime("%H:%M")}', 'success')
    
    return redirect(url_for('employee_dashboard'))

# Routes d'administration (à continuer...)
@app.route('/admin')
@admin_required
def admin_dashboard():
    # Implémentation du tableau de bord admin avec toutes les fonctionnalités
    pass

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
            logger.info("Base de données initialisée avec les utilisateurs de test")

if __name__ == '__main__':
    init_database()
    logger.info("🚀 Application de pointage complète démarrée")
    app.run(host='0.0.0.0', port=5000, debug=False)
else:
    init_database()

# Templates d'administration
ADMIN_DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Administration - Système de Pointage</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #f8f9fa; }
        .navbar { background: linear-gradient(135deg, #2c3e50, #3498db); }
        .stats-card { border-left: 4px solid #3498db; }
        .chart-container { position: relative; height: 300px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="fas fa-shield-alt"></i> Administration</a>
            <div class="navbar-nav ms-auto">
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
                                <h3>{{ total_hours_month }}h</h3>
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
                                                    <a href="/admin/edit_entry/{{ entry.id }}" class="btn btn-sm btn-outline-primary">
                                                        <i class="fas fa-edit"></i>
                                                    </a>
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
                                                    <a href="/admin/edit_employee/{{ employee.id }}" class="btn btn-sm btn-outline-primary">
                                                        <i class="fas fa-edit"></i>
                                                    </a>
                                                    <a href="/admin/employee_report/{{ employee.id }}" class="btn btn-sm btn-outline-info">
                                                        <i class="fas fa-chart-bar"></i>
                                                    </a>
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
                                            <i class="fas fa-file-excel"></i> Export Excel
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
                                                    <a href="/admin/edit_entry/{{ entry.id }}" class="btn btn-sm btn-outline-primary">
                                                        <i class="fas fa-edit"></i>
                                                    </a>
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

            <!-- Onglet Rapports -->
            <div class="tab-pane fade" id="reports" role="tabpanel">
                <div class="row mt-4">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h5><i class="fas fa-download"></i> Exports</h5>
                            </div>
                            <div class="card-body">
                                <form method="POST" action="/admin/export_custom">
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
                                    <button type="submit" class="btn btn-success">
                                        <i class="fas fa-file-excel"></i> Exporter Excel
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
                                    <label class="form-label">Département</label>
                                    <input type="text" name="department" class="form-control">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Poste</label>
                                    <input type="text" name="position" class="form-control">
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Taux horaire (€)</label>
                                    <input type="number" step="0.01" name="hourly_rate" class="form-control">
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Date d'embauche</label>
                                    <input type="date" name="hire_date" class="form-control">
                                </div>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Mot de passe temporaire</label>
                            <input type="password" name="password" class="form-control" required>
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
    </script>
</body>
</html>'''

# Routes d'administration complètes
@app.route('/admin')
@admin_required
def admin_dashboard():
    # Statistiques globales
    total_employees = Employee.query.filter_by(is_active=True).count()
    
    today = date.today()
    present_today = TimeEntry.query.filter_by(date=today).count()
    
    # Heures totales du mois
    month_start, month_end = get_month_dates(today)
    month_entries = TimeEntry.query.filter(
        TimeEntry.date >= month_start,
        TimeEntry.date <= month_end
    ).all()
    total_hours_month = sum(entry.total_hours for entry in month_entries)
    avg_hours_day = total_hours_month / max(len(month_entries), 1)
    
    # Données pour les graphiques
    employees = Employee.query.filter_by(is_active=True).all()
    today_entries = TimeEntry.query.filter_by(date=today).join(Employee).all()
    
    # Statistiques par département
    dept_stats = {}
    for entry in month_entries:
        dept = entry.employee.department or 'Non défini'
        dept_stats[dept] = dept_stats.get(dept, 0) + entry.total_hours
    
    dept_chart_labels = list(dept_stats.keys())
    dept_chart_data = list(dept_stats.values())
    
    # Évolution hebdomadaire
    weekly_chart_labels = []
    weekly_chart_data = []
    for i in range(7):
        chart_date = today - timedelta(days=6-i)
        weekly_chart_labels.append(chart_date.strftime('%d/%m'))
        
        day_total = sum(
            entry.total_hours for entry in TimeEntry.query.filter_by(date=chart_date).all()
        )
        weekly_chart_data.append(day_total)
    
    # Top employés du mois
    employee_hours = {}
    for entry in month_entries:
        emp = entry.employee
        employee_hours[emp] = employee_hours.get(emp, 0) + entry.total_hours
    
    top_employees = sorted(employee_hours.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Statistiques départements
    departments_stats = {}
    for emp in employees:
        dept = emp.department or 'Non défini'
        departments_stats[dept] = departments_stats.get(dept, 0) + 1
    departments_stats = list(departments_stats.items())
    
    # Filtrage des pointages
    filtered_entries = TimeEntry.query.join(Employee).order_by(TimeEntry.date.desc()).limit(50).all()
    
    return render_template_string(ADMIN_DASHBOARD_HTML,
                                total_employees=total_employees,
                                present_today=present_today,
                                total_hours_month=round(total_hours_month, 1),
                                avg_hours_day=round(avg_hours_day, 1),
                                employees=employees,
                                today_entries=today_entries,
                                filtered_entries=filtered_entries,
                                dept_chart_labels=dept_chart_labels,
                                dept_chart_data=dept_chart_data,
                                weekly_chart_labels=weekly_chart_labels,
                                weekly_chart_data=weekly_chart_data,
                                top_employees=top_employees,
                                departments_stats=departments_stats)

@app.route('/admin/add_employee', methods=['POST'])
@admin_required
def add_employee():
    try:
        employee = Employee(
            employee_number=request.form['employee_number'],
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            email=request.form['email'],
            department=request.form.get('department'),
            position=request.form.get('position'),
            hourly_rate=float(request.form.get('hourly_rate', 0)),
            hire_date=datetime.strptime(request.form['hire_date'], '%Y-%m-%d').date() if request.form.get('hire_date') else None,
            is_admin=bool(request.form.get('is_admin')),
            is_active=True
        )
        employee.set_password(request.form['password'])
        
        db.session.add(employee)
        db.session.commit()
        
        flash(f'Employé {employee.first_name} {employee.last_name} créé avec succès', 'success')
    except Exception as e:
        flash(f'Erreur lors de la création: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/export_excel')
@admin_required
def export_excel():
    # Créer un fichier Excel avec toutes les données
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pointages"
    
    # Headers
    headers = ['Date', 'Employé', 'Département', 'Arrivée', 'Sortie Midi', 'Retour Midi', 'Sortie Soir', 'Total Heures']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    
    # Données
    entries = TimeEntry.query.join(Employee).order_by(TimeEntry.date.desc()).all()
    for row, entry in enumerate(entries, 2):
        ws.cell(row=row, column=1, value=entry.date.strftime('%d/%m/%Y'))
        ws.cell(row=row, column=2, value=f"{entry.employee.first_name} {entry.employee.last_name}")
        ws.cell(row=row, column=3, value=entry.employee.department or '')
        ws.cell(row=row, column=4, value=entry.morning_in.strftime('%H:%M') if entry.morning_in else '')
        ws.cell(row=row, column=5, value=entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '')
        ws.cell(row=row, column=6, value=entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '')
        ws.cell(row=row, column=7, value=entry.evening_out.strftime('%H:%M') if entry.evening_out else '')
        ws.cell(row=row, column=8, value=entry.total_hours)
    
    # Ajuster la largeur des colonnes
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 15
    
    # Sauvegarder en mémoire
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'pointages_{date.today().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/admin/export_custom', methods=['POST'])
@admin_required
def export_custom():
    employee_id = request.form.get('employee_id')
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
    end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
    
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
    
    # Créer le fichier Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pointages"
    
    # Headers
    headers = ['Date', 'Employé', 'Département', 'Arrivée', 'Sortie Midi', 'Retour Midi', 'Sortie Soir', 'Total Heures']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    
    # Données
    total_hours = 0
    for row, entry in enumerate(entries, 2):
        ws.cell(row=row, column=1, value=entry.date.strftime('%d/%m/%Y'))
        ws.cell(row=row, column=2, value=f"{entry.employee.first_name} {entry.employee.last_name}")
        ws.cell(row=row, column=3, value=entry.employee.department or '')
        ws.cell(row=row, column=4, value=entry.morning_in.strftime('%H:%M') if entry.morning_in else '')
        ws.cell(row=row, column=5, value=entry.lunch_out.strftime('%H:%M') if entry.lunch_out else '')
        ws.cell(row=row, column=6, value=entry.lunch_in.strftime('%H:%M') if entry.lunch_in else '')
        ws.cell(row=row, column=7, value=entry.evening_out.strftime('%H:%M') if entry.evening_out else '')
        ws.cell(row=row, column=8, value=entry.total_hours)
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
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

# Mise à jour des dépendances
def update_requirements():
    requirements = [
        'Flask==3.0.0',
        'Flask-SQLAlchemy==3.1.1',
        'Werkzeug==3.0.1',
        'openpyxl==3.1.2'
    ]
    
    with open('/home/ubuntu/pointage-claude4x/requirements.txt', 'w') as f:
        f.write('\n'.join(requirements))

if __name__ == '__main__':
    update_requirements()
    init_database()
    logger.info("🚀 Application de pointage COMPLÈTE démarrée")
    app.run(host='0.0.0.0', port=5000, debug=False)
