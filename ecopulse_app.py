from flask import Flask, render_template_string, request, send_file, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import matplotlib
import secrets
import string
import os

# Configure matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import io
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ecopulse.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# ===================== DATABASE MODELS =====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='customer')
    employee_id = db.Column(db.String(20), unique=True, nullable=True)
    department = db.Column(db.String(50), nullable=True)
    threshold = db.Column(db.Float, default=600)
    currency = db.Column(db.String(10), default='Ksh')
    unit_cost = db.Column(db.Float, default=0.12)
    alert_email = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships - specify foreign keys explicitly
    readings = db.relationship('Reading',
                               foreign_keys='Reading.user_id',
                               back_populates='user',
                               lazy=True,
                               cascade='all, delete-orphan')

    reviewed_readings = db.relationship('Reading',
                                        foreign_keys='Reading.reviewed_by',
                                        back_populates='reviewer',
                                        lazy=True)

    approved_readings = db.relationship('Reading',
                                        foreign_keys='Reading.approved_by',
                                        back_populates='approver',
                                        lazy=True)

    settings = db.relationship('UserSettings',
                               foreign_keys='UserSettings.user_id',
                               back_populates='user',
                               uselist=False,
                               cascade='all, delete-orphan')

    logs = db.relationship('SystemLog',
                           foreign_keys='SystemLog.user_id',
                           back_populates='user',
                           lazy=True)

    sent_reports = db.relationship('Report',
                                   foreign_keys='Report.sent_by',
                                   back_populates='sender',
                                   lazy=True)

    received_reports = db.relationship('Report',
                                       foreign_keys='Report.sent_to',
                                       back_populates='recipient',
                                       lazy=True)

    financial_records = db.relationship('FinancialRecord',
                                        foreign_keys='FinancialRecord.user_id',
                                        back_populates='user',
                                        lazy=True)

    consumption_reviews = db.relationship('ConsumptionReview',
                                          foreign_keys='ConsumptionReview.examiner_id',
                                          back_populates='examiner',
                                          lazy=True)

    approved_reviews = db.relationship('ConsumptionReview',
                                       foreign_keys='ConsumptionReview.approved_by',
                                       back_populates='approver',
                                       lazy=True)

    customer_submissions = db.relationship('CustomerSubmission',
                                           foreign_keys='CustomerSubmission.customer_id',
                                           back_populates='customer',
                                           lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_employee_id(self):
        prefix = 'ADM' if self.role == 'admin' else 'EXM'
        random_digits = ''.join(secrets.choice(string.digits) for _ in range(6))
        return f"{prefix}{random_digits}"


class Reading(db.Model):
    __tablename__ = 'readings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.String(100), nullable=False)
    kwh = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=True, default=0.0)
    is_reviewed = db.Column(db.Boolean, default=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    is_approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships - specify foreign keys explicitly
    user = db.relationship('User', foreign_keys=[user_id], back_populates='readings')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], back_populates='reviewed_readings')
    approver = db.relationship('User', foreign_keys=[approved_by], back_populates='approved_readings')

    def calculate_cost(self, unit_cost):
        self.cost = self.kwh * unit_cost
        return self.cost


class UserSettings(db.Model):
    __tablename__ = 'user_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    alert_threshold = db.Column(db.Float, default=600)
    alert_frequency = db.Column(db.String(20), default='immediate')
    co2_per_kwh = db.Column(db.Float, default=0.385)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], back_populates='settings')


class SystemLog(db.Model):
    __tablename__ = 'system_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50), nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], back_populates='logs')


class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    report_type = db.Column(db.String(50), nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sent_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pdf_path = db.Column(db.String(500), nullable=True)
    chart_data = db.Column(db.Text, nullable=True)

    # Relationships
    sender = db.relationship('User', foreign_keys=[sent_by], back_populates='sent_reports')
    recipient = db.relationship('User', foreign_keys=[sent_to], back_populates='received_reports')


class FinancialRecord(db.Model):
    __tablename__ = 'financial_records'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period = db.Column(db.String(50), nullable=False)
    total_consumption = db.Column(db.Float, default=0)
    total_cost = db.Column(db.Float, default=0)
    total_paid = db.Column(db.Float, default=0)
    balance = db.Column(db.Float, default=0)
    due_date = db.Column(db.DateTime, nullable=True)
    payment_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], back_populates='financial_records')


class ConsumptionReview(db.Model):
    __tablename__ = 'consumption_reviews'

    id = db.Column(db.Integer, primary_key=True)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period = db.Column(db.String(50), nullable=False)
    total_consumption = db.Column(db.Float, default=0)
    total_customers = db.Column(db.Integer, default=0)
    average_consumption = db.Column(db.Float, default=0)
    peak_consumption = db.Column(db.Float, default=0)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending_review')
    reviewed_at = db.Column(db.DateTime, nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    examiner = db.relationship('User', foreign_keys=[examiner_id], back_populates='consumption_reviews')
    approver = db.relationship('User', foreign_keys=[approved_by], back_populates='approved_reviews')


class CustomerSubmission(db.Model):
    __tablename__ = 'customer_submissions'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period = db.Column(db.String(50), nullable=False)
    total_consumption = db.Column(db.Float, default=0)
    total_cost = db.Column(db.Float, default=0)
    average_daily = db.Column(db.Float, default=0)
    readings_count = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, approved, rejected
    admin_notes = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    customer = db.relationship('User', foreign_keys=[customer_id], back_populates='customer_submissions')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ===================== ROLE-BASED ACCESS CONTROL =====================

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role not in roles:
                return render_template_string(error_page,
                                              error="Access Denied: You don't have permission to access this page.")
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(f):
    return role_required('admin')(f)


def examiner_required(f):
    return role_required('examiner')(f)


# ===================== UTILITY FUNCTIONS =====================

def log_system_action(user_id, action):
    try:
        log = SystemLog(user_id=user_id, action=action, ip_address=request.remote_addr)
        db.session.add(log)
        db.session.commit()
    except:
        db.session.rollback()


def get_user_readings(user_id, days=None, start_date=None, end_date=None):
    query = Reading.query.filter_by(user_id=user_id).order_by(Reading.created_at.desc())
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Reading.created_at >= start, Reading.created_at <= end)
        except:
            pass
    elif days:
        start = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Reading.created_at >= start)
    return query.all()


def calculate_co2_emissions(kwh, co2_per_kwh=0.385):
    return kwh * co2_per_kwh


def generate_consumption_chart(user_id):
    """Generate consumption chart for customer view"""
    try:
        readings = Reading.query.filter_by(user_id=user_id).order_by(Reading.created_at).all()
        user = User.query.get(user_id)
        if not readings or not user:
            return None

        # Prepare data
        dates = [r.date for r in readings[-12:]]
        values = [r.kwh for r in readings[-12:]]

        if not dates:
            return None

        fig = plt.figure(figsize=(14, 10))

        # Main consumption chart
        ax1 = plt.subplot(2, 2, 1)
        colors = ['#00b894' if v <= user.threshold else '#ff6b6b' for v in values]
        bars = ax1.bar(range(len(dates)), values, color=colors, edgecolor='black', linewidth=1.5)
        ax1.set_xlabel("Period", fontsize=12)
        ax1.set_ylabel("Consumption (kWh)", fontsize=12)
        ax1.set_title(f"Energy Consumption - {user.username}", fontsize=14, fontweight='bold')
        ax1.set_xticks(range(len(dates)))
        ax1.set_xticklabels(dates, rotation=45, ha='right')
        ax1.axhline(y=user.threshold, color="#ff6b6b", linestyle="--", linewidth=2,
                    label=f"Threshold: {user.threshold} kWh")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        for bar, v in zip(bars, values):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2., height + 5, f'{v:.0f}',
                     ha='center', va='bottom', fontsize=9)

        # Trend line
        ax2 = plt.subplot(2, 2, 2)
        ax2.plot(range(len(dates)), values, marker='o', linewidth=2, color='#667eea', markersize=8)
        ax2.fill_between(range(len(dates)), values, alpha=0.3, color='#667eea')
        ax2.set_xlabel("Period", fontsize=12)
        ax2.set_ylabel("Consumption (kWh)", fontsize=12)
        ax2.set_title("Consumption Trend", fontsize=14, fontweight='bold')
        ax2.set_xticks(range(len(dates)))
        ax2.set_xticklabels(dates, rotation=45, ha='right')
        ax2.grid(True, alpha=0.3)

        # Cost analysis
        ax3 = plt.subplot(2, 2, 3)
        costs = [v * user.unit_cost for v in values]
        ax3.plot(range(len(dates)), costs, marker='s', linewidth=2, color='#00b894', markersize=8)
        ax3.fill_between(range(len(dates)), costs, alpha=0.3, color='#00b894')
        ax3.set_xlabel("Period", fontsize=12)
        ax3.set_ylabel(f"Cost ({user.currency})", fontsize=12)
        ax3.set_title("Cost Analysis", fontsize=14, fontweight='bold')
        ax3.set_xticks(range(len(dates)))
        ax3.set_xticklabels(dates, rotation=45, ha='right')
        ax3.grid(True, alpha=0.3)

        # CO2 emissions
        ax4 = plt.subplot(2, 2, 4)
        co2 = [v * 0.385 for v in values]
        ax4.bar(range(len(dates)), co2, color='#95a5a6', edgecolor='black', alpha=0.7)
        ax4.set_xlabel("Period", fontsize=12)
        ax4.set_ylabel("CO2 (kg)", fontsize=12)
        ax4.set_title("Carbon Footprint", fontsize=14, fontweight='bold')
        ax4.set_xticks(range(len(dates)))
        ax4.set_xticklabels(dates, rotation=45, ha='right')
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()

        img_bytes = io.BytesIO()
        plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
        img_bytes.seek(0)
        plt.close()

        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()
        return img_base64

    except Exception as e:
        print(f"Chart error: {e}")
        plt.close('all')
        return None


def generate_examiner_consumption_report():
    """Generate consumption report for examiner showing all customers' consumption"""
    try:
        users = User.query.filter_by(role='customer').all()
        readings = Reading.query.all()

        if not readings:
            return {
                'chart': None,
                'summary': {
                    'total_customers': len(users),
                    'total_readings': 0,
                    'total_consumption': 0,
                    'average_consumption': 0,
                    'peak_consumption': 0,
                    'total_revenue': 0,
                    'total_co2': 0
                }
            }

        fig = plt.figure(figsize=(18, 12))

        # 1. Consumption by customer (bar chart)
        ax1 = plt.subplot(3, 3, 1)
        customer_consumption = {}
        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                customer_consumption[user.username] = sum(r.kwh for r in user_readings)

        if customer_consumption:
            customers = list(customer_consumption.keys())
            consumption = list(customer_consumption.values())
            colors = plt.cm.viridis(np.linspace(0, 1, len(customers)))
            ax1.bar(range(len(customers)), consumption, color=colors)
            ax1.set_xlabel("Customers", fontsize=10)
            ax1.set_ylabel("Consumption (kWh)", fontsize=10)
            ax1.set_title("Customer Consumption Distribution", fontsize=12, fontweight='bold')
            ax1.set_xticks(range(len(customers)))
            ax1.set_xticklabels(customers, rotation=45, ha='right')
            ax1.grid(True, alpha=0.3)
        else:
            ax1.text(0.5, 0.5, 'No consumption data', ha='center', va='center', transform=ax1.transAxes)

        # 2. Monthly consumption trend
        ax2 = plt.subplot(3, 3, 2)
        monthly_data = {}
        for reading in readings:
            month_key = reading.created_at.strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = 0
            monthly_data[month_key] += reading.kwh

        months = sorted(monthly_data.keys())
        monthly_totals = [monthly_data[m] for m in months]

        if months:
            ax2.plot(range(len(months)), monthly_totals, marker='o', linewidth=2, color='#ff6b6b')
            ax2.fill_between(range(len(months)), monthly_totals, alpha=0.3, color='#ff6b6b')
            ax2.set_xlabel("Month", fontsize=10)
            ax2.set_ylabel("Total Consumption (kWh)", fontsize=10)
            ax2.set_title("Monthly Consumption Trend", fontsize=12, fontweight='bold')
            ax2.set_xticks(range(len(months)))
            ax2.set_xticklabels(months, rotation=45, ha='right')
            ax2.grid(True, alpha=0.3)
        else:
            ax2.text(0.5, 0.5, 'No monthly data', ha='center', va='center', transform=ax2.transAxes)

        # 3. Peak consumption hours
        ax3 = plt.subplot(3, 3, 3)
        hour_data = [0] * 24
        for reading in readings:
            hour = reading.timestamp.hour
            hour_data[hour] += reading.kwh

        hours = list(range(24))
        ax3.bar(hours, hour_data, color='#9b59b6', edgecolor='black', alpha=0.7)
        ax3.set_xlabel("Hour of Day", fontsize=10)
        ax3.set_ylabel("Consumption (kWh)", fontsize=10)
        ax3.set_title("Peak Consumption Hours", fontsize=12, fontweight='bold')
        ax3.set_xticks(range(0, 24, 3))
        ax3.grid(True, alpha=0.3)

        # 4. Customer efficiency rating
        ax4 = plt.subplot(3, 3, 4)
        efficient = 0
        average = 0
        inefficient = 0

        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                avg_consumption = sum(r.kwh for r in user_readings) / len(user_readings)
                if avg_consumption < user.threshold * 0.7:
                    efficient += 1
                elif avg_consumption < user.threshold:
                    average += 1
                else:
                    inefficient += 1

        efficiency_data = [efficient, average, inefficient]
        efficiency_labels = ['Efficient', 'Average', 'Inefficient']
        colors_efficiency = ['#00b894', '#f39c12', '#ff6b6b']
        ax4.pie(efficiency_data, labels=efficiency_labels, autopct='%1.1f%%', colors=colors_efficiency, startangle=90)
        ax4.set_title("Customer Efficiency Distribution", fontsize=12, fontweight='bold')

        # 5. Cost analysis by customer
        ax5 = plt.subplot(3, 3, 5)
        customer_costs = {}
        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                customer_costs[user.username] = sum(r.kwh * user.unit_cost for r in user_readings)

        if customer_costs:
            top_customers = dict(sorted(customer_costs.items(), key=lambda x: x[1], reverse=True)[:5])
            ax5.barh(list(top_customers.keys()), list(top_customers.values()), color='#00b894')
            ax5.set_xlabel("Cost", fontsize=10)
            ax5.set_title("Top 5 Customers by Cost", fontsize=12, fontweight='bold')
            ax5.grid(True, alpha=0.3)
        else:
            ax5.text(0.5, 0.5, 'No cost data', ha='center', va='center', transform=ax5.transAxes)

        # 6. CO2 emissions by customer
        ax6 = plt.subplot(3, 3, 6)
        customer_co2 = {}
        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                customer_co2[user.username] = sum(r.kwh * 0.385 for r in user_readings)

        if customer_co2:
            top_co2 = dict(sorted(customer_co2.items(), key=lambda x: x[1], reverse=True)[:5])
            ax6.bar(range(len(top_co2)), list(top_co2.values()), color='#95a5a6')
            ax6.set_xlabel("Customers", fontsize=10)
            ax6.set_ylabel("CO2 (kg)", fontsize=10)
            ax6.set_title("Top 5 Customers by CO2", fontsize=12, fontweight='bold')
            ax6.set_xticks(range(len(top_co2)))
            ax6.set_xticklabels(list(top_co2.keys()), rotation=45, ha='right')
            ax6.grid(True, alpha=0.3)
        else:
            ax6.text(0.5, 0.5, 'No CO2 data', ha='center', va='center', transform=ax6.transAxes)

        # 7. Readings per customer
        ax7 = plt.subplot(3, 3, 7)
        readings_count = {}
        for user in users:
            count = Reading.query.filter_by(user_id=user.id).count()
            if count > 0:
                readings_count[user.username] = count

        if readings_count:
            ax7.bar(range(len(readings_count)), list(readings_count.values()), color='#3498db')
            ax7.set_xlabel("Customers", fontsize=10)
            ax7.set_ylabel("Number of Readings", fontsize=10)
            ax7.set_title("Readings per Customer", fontsize=12, fontweight='bold')
            ax7.set_xticks(range(len(readings_count)))
            ax7.set_xticklabels(list(readings_count.keys()), rotation=45, ha='right')
            ax7.grid(True, alpha=0.3)
        else:
            ax7.text(0.5, 0.5, 'No readings data', ha='center', va='center', transform=ax7.transAxes)

        # 8. Consumption vs Threshold
        ax8 = plt.subplot(3, 3, 8)
        above_threshold = 0
        below_threshold = 0

        for reading in readings:
            user = User.query.get(reading.user_id)
            if user:
                if reading.kwh > user.threshold:
                    above_threshold += 1
                else:
                    below_threshold += 1

        ax8.pie([above_threshold, below_threshold], labels=['Above Threshold', 'Below Threshold'],
                autopct='%1.1f%%', colors=['#ff6b6b', '#00b894'], startangle=90)
        ax8.set_title("Readings vs Threshold", fontsize=12, fontweight='bold')

        # 9. Summary statistics
        ax9 = plt.subplot(3, 3, 9)
        total_consumption = sum(r.kwh for r in readings)
        total_customers = len([u for u in users if u.readings])
        avg_consumption = total_consumption / total_customers if total_customers > 0 else 0
        peak_consumption = max(monthly_totals) if monthly_totals else 0

        summary_data = ['Total\nConsumption', 'Avg per\nCustomer', 'Peak\nMonthly']
        summary_values = [total_consumption, avg_consumption, peak_consumption]
        ax9.bar(summary_data, summary_values, color=['#3498db', '#00b894', '#ff6b6b'])
        ax9.set_ylabel("kWh", fontsize=10)
        ax9.set_title("Key Metrics", fontsize=12, fontweight='bold')

        for i, v in enumerate(summary_values):
            ax9.text(i, v + 5, f'{v:.0f}', ha='center', va='bottom', fontsize=9)

        plt.tight_layout()

        img_bytes = io.BytesIO()
        plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
        img_bytes.seek(0)
        plt.close()

        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()

        # Calculate summary statistics
        total_consumption = sum(r.kwh for r in readings)
        total_customers = len([u for u in users if u.readings])
        avg_consumption = total_consumption / total_customers if total_customers > 0 else 0
        peak_consumption = max(monthly_totals) if monthly_totals else 0
        total_revenue = sum(r.kwh * User.query.get(r.user_id).unit_cost for r in readings)
        total_co2 = sum(r.kwh * 0.385 for r in readings)

        summary = {
            'total_customers': total_customers,
            'total_readings': len(readings),
            'total_consumption': total_consumption,
            'average_consumption': avg_consumption,
            'peak_consumption': peak_consumption,
            'total_revenue': total_revenue,
            'total_co2': total_co2,
            'efficient_customers': efficient,
            'inefficient_customers': inefficient,
            'above_threshold_count': above_threshold,
            'below_threshold_count': below_threshold
        }

        return {
            'chart': img_base64,
            'summary': summary
        }

    except Exception as e:
        print(f"Examiner report error: {e}")
        plt.close('all')
        return {
            'chart': None,
            'summary': {
                'total_customers': 0,
                'total_readings': 0,
                'total_consumption': 0,
                'average_consumption': 0,
                'peak_consumption': 0,
                'total_revenue': 0,
                'total_co2': 0,
                'efficient_customers': 0,
                'inefficient_customers': 0,
                'above_threshold_count': 0,
                'below_threshold_count': 0
            }
        }


def generate_examiner_report():
    """Generate comprehensive system report for examiner"""
    try:
        users = User.query.all()
        readings = Reading.query.all()

        if not readings:
            return {
                'chart': None,
                'summary': {
                    'total_users': len(users),
                    'total_readings': 0,
                    'total_consumption': 0,
                    'total_revenue': 0,
                    'total_co2': 0,
                    'avg_consumption_per_user': 0,
                    'peak_month': 'N/A',
                    'efficient_users': 0,
                    'inefficient_users': 0
                }
            }

        fig = plt.figure(figsize=(16, 12))

        # 1. Total consumption by user
        ax1 = plt.subplot(3, 3, 1)
        user_consumption = {}
        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                user_consumption[user.username] = sum(r.kwh for r in user_readings)

        if user_consumption:
            usernames = list(user_consumption.keys())
            totals = list(user_consumption.values())
            colors = plt.cm.Set3(np.linspace(0, 1, len(usernames)))
            ax1.pie(totals, labels=usernames, autopct='%1.1f%%', colors=colors, startangle=90)
            ax1.set_title("Consumption Distribution by User", fontsize=12, fontweight='bold')
        else:
            ax1.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax1.transAxes)

        # 2. Monthly trends
        ax2 = plt.subplot(3, 3, 2)
        monthly_data = {}
        for reading in readings:
            month_key = reading.created_at.strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = 0
            monthly_data[month_key] += reading.kwh

        months = sorted(monthly_data.keys())
        monthly_totals = [monthly_data[m] for m in months]

        if months:
            ax2.plot(range(len(months)), monthly_totals, marker='o', linewidth=2, color='#ff6b6b')
            ax2.fill_between(range(len(months)), monthly_totals, alpha=0.3, color='#ff6b6b')
            ax2.set_xlabel("Month", fontsize=10)
            ax2.set_ylabel("Total Consumption (kWh)", fontsize=10)
            ax2.set_title("System-wide Monthly Trends", fontsize=12, fontweight='bold')
            ax2.set_xticks(range(len(months)))
            ax2.set_xticklabels(months, rotation=45, ha='right')
            ax2.grid(True, alpha=0.3)
        else:
            ax2.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax2.transAxes)

        # 3. Revenue analysis
        ax3 = plt.subplot(3, 3, 3)
        revenue_data = {}
        for reading in readings:
            user = User.query.get(reading.user_id)
            if user:
                month_key = reading.created_at.strftime('%Y-%m')
                cost = reading.kwh * user.unit_cost
                if month_key not in revenue_data:
                    revenue_data[month_key] = 0
                revenue_data[month_key] += cost

        if revenue_data:
            rev_months = sorted(revenue_data.keys())
            revenues = [revenue_data[m] for m in rev_months]
            ax3.bar(range(len(rev_months)), revenues, color='#00b894', edgecolor='black')
            ax3.set_xlabel("Month", fontsize=10)
            ax3.set_ylabel("Revenue", fontsize=10)
            ax3.set_title("Monthly Revenue", fontsize=12, fontweight='bold')
            ax3.set_xticks(range(len(rev_months)))
            ax3.set_xticklabels(rev_months, rotation=45, ha='right')
            ax3.grid(True, alpha=0.3)
        else:
            ax3.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax3.transAxes)

        # 4. User statistics
        ax4 = plt.subplot(3, 3, 4)
        roles = ['admin', 'examiner', 'customer']
        role_counts = [User.query.filter_by(role=r).count() for r in roles]
        ax4.bar(roles, role_counts, color=['#ff6b6b', '#f39c12', '#00b894'])
        ax4.set_xlabel("User Role", fontsize=10)
        ax4.set_ylabel("Count", fontsize=10)
        ax4.set_title("User Distribution", fontsize=12, fontweight='bold')
        ax4.grid(True, alpha=0.3)

        # 5. Peak usage times
        ax5 = plt.subplot(3, 3, 5)
        hour_data = [0] * 24
        for reading in readings:
            hour = reading.timestamp.hour
            hour_data[hour] += reading.kwh

        hours = list(range(24))
        ax5.bar(hours, hour_data, color='#9b59b6', edgecolor='black', alpha=0.7)
        ax5.set_xlabel("Hour of Day", fontsize=10)
        ax5.set_ylabel("Consumption (kWh)", fontsize=10)
        ax5.set_title("Peak Usage Hours", fontsize=12, fontweight='bold')
        ax5.set_xticks(range(0, 24, 3))
        ax5.grid(True, alpha=0.3)

        # 6. CO2 emissions
        ax6 = plt.subplot(3, 3, 6)
        co2_data = {}
        for reading in readings:
            month_key = reading.created_at.strftime('%Y-%m')
            if month_key not in co2_data:
                co2_data[month_key] = 0
            co2_data[month_key] += reading.kwh * 0.385

        if co2_data:
            co2_months = sorted(co2_data.keys())
            co2_values = [co2_data[m] for m in co2_months]
            ax6.fill_between(range(len(co2_months)), co2_values, alpha=0.5, color='#95a5a6')
            ax6.plot(range(len(co2_months)), co2_values, linewidth=2, color='#2c3e50')
            ax6.set_xlabel("Month", fontsize=10)
            ax6.set_ylabel("CO2 (kg)", fontsize=10)
            ax6.set_title("Carbon Footprint Trend", fontsize=12, fontweight='bold')
            ax6.set_xticks(range(len(co2_months)))
            ax6.set_xticklabels(co2_months, rotation=45, ha='right')
            ax6.grid(True, alpha=0.3)
        else:
            ax6.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax6.transAxes)

        # 7. Financial summary
        ax7 = plt.subplot(3, 3, 7)
        payment_status = ['paid', 'pending', 'overdue']
        status_counts = []
        for status in payment_status:
            count = FinancialRecord.query.filter_by(payment_status=status).count()
            status_counts.append(count)

        if sum(status_counts) > 0:
            ax7.pie(status_counts, labels=payment_status, autopct='%1.1f%%',
                    colors=['#00b894', '#f39c12', '#ff6b6b'], startangle=90)
            ax7.set_title("Payment Status Distribution", fontsize=12, fontweight='bold')
        else:
            ax7.text(0.5, 0.5, 'No payment data', ha='center', va='center', transform=ax7.transAxes)

        # 8. Efficiency ratings
        ax8 = plt.subplot(3, 3, 8)
        efficient_users = 0
        average_users = 0
        inefficient_users = 0

        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                avg_consumption = sum(r.kwh for r in user_readings) / len(user_readings)
                if avg_consumption < user.threshold * 0.7:
                    efficient_users += 1
                elif avg_consumption < user.threshold:
                    average_users += 1
                else:
                    inefficient_users += 1

        efficiency_data = [efficient_users, average_users, inefficient_users]
        efficiency_labels = ['Efficient', 'Average', 'Inefficient']
        colors_efficiency = ['#00b894', '#f39c12', '#ff6b6b']
        ax8.bar(efficiency_labels, efficiency_data, color=colors_efficiency)
        ax8.set_xlabel("Efficiency Level", fontsize=10)
        ax8.set_ylabel("Number of Users", fontsize=10)
        ax8.set_title("User Efficiency Distribution", fontsize=12, fontweight='bold')
        ax8.grid(True, alpha=0.3)

        # 9. System health
        ax9 = plt.subplot(3, 3, 9)
        total_readings = len(readings)
        active_users = len([u for u in users if u.readings])
        system_metrics = [active_users, total_readings, len(users)]
        metric_labels = ['Active Users', 'Total Readings', 'Total Users']
        ax9.barh(metric_labels, system_metrics, color='#3498db')
        ax9.set_xlabel("Count", fontsize=10)
        ax9.set_title("System Health Metrics", fontsize=12, fontweight='bold')

        plt.tight_layout()

        img_bytes = io.BytesIO()
        plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
        img_bytes.seek(0)
        plt.close()

        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()

        summary = {
            'total_users': len(users),
            'total_readings': total_readings,
            'total_consumption': sum(r.kwh for r in readings),
            'total_revenue': sum(r.kwh * User.query.get(r.user_id).unit_cost for r in readings),
            'total_co2': sum(r.kwh * 0.385 for r in readings),
            'avg_consumption_per_user': sum(r.kwh for r in readings) / len(users) if users else 0,
            'peak_month': max(monthly_data.items(), key=lambda x: x[1])[0] if monthly_data else 'N/A',
            'efficient_users': efficient_users,
            'inefficient_users': inefficient_users
        }

        return {
            'chart': img_base64,
            'summary': summary
        }

    except Exception as e:
        print(f"Report generation error: {e}")
        plt.close('all')
        return {
            'chart': None,
            'summary': {
                'total_users': User.query.count(),
                'total_readings': 0,
                'total_consumption': 0,
                'total_revenue': 0,
                'total_co2': 0,
                'avg_consumption_per_user': 0,
                'peak_month': 'N/A',
                'efficient_users': 0,
                'inefficient_users': 0
            }
        }


def generate_financial_report():
    """Generate financial report for admin"""
    try:
        users = User.query.all()
        readings = Reading.query.all()
        financial_records = FinancialRecord.query.all()

        total_revenue = sum(r.kwh * User.query.get(r.user_id).unit_cost for r in readings) if readings else 0
        total_outstanding = sum(r.balance for r in financial_records if r.balance > 0) if financial_records else 0
        total_collected = total_revenue - total_outstanding

        if not readings or not users:
            return {
                'chart': None,
                'total_revenue': 0,
                'total_outstanding': 0,
                'total_collected': 0,
                'payment_rate': 0
            }

        fig = plt.figure(figsize=(15, 10))

        # 1. Revenue by user
        ax1 = plt.subplot(2, 3, 1)
        user_revenue = {}
        for user in users:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                user_revenue[user.username] = sum(r.kwh * user.unit_cost for r in user_readings)

        if user_revenue:
            top_users = dict(sorted(user_revenue.items(), key=lambda x: x[1], reverse=True)[:5])
            ax1.bar(range(len(top_users)), list(top_users.values()), color='#00b894')
            ax1.set_xlabel("Top 5 Users", fontsize=10)
            ax1.set_ylabel("Revenue", fontsize=10)
            ax1.set_title("Top Revenue Generating Users", fontsize=12, fontweight='bold')
            ax1.set_xticks(range(len(top_users)))
            ax1.set_xticklabels(list(top_users.keys()), rotation=45, ha='right')
            ax1.grid(True, alpha=0.3)
        else:
            ax1.text(0.5, 0.5, 'No revenue data', ha='center', va='center', transform=ax1.transAxes)

        # 2. Monthly revenue trend
        ax2 = plt.subplot(2, 3, 2)
        monthly_revenue = {}
        for reading in readings:
            user = User.query.get(reading.user_id)
            if user:
                month_key = reading.created_at.strftime('%Y-%m')
                cost = reading.kwh * user.unit_cost
                if month_key not in monthly_revenue:
                    monthly_revenue[month_key] = 0
                monthly_revenue[month_key] += cost

        if monthly_revenue:
            months = sorted(monthly_revenue.keys())
            revenues = [monthly_revenue[m] for m in months]
            ax2.plot(range(len(months)), revenues, marker='o', linewidth=2, color='#ff6b6b')
            ax2.fill_between(range(len(months)), revenues, alpha=0.3, color='#ff6b6b')
            ax2.set_xlabel("Month", fontsize=10)
            ax2.set_ylabel("Revenue", fontsize=10)
            ax2.set_title("Monthly Revenue Trend", fontsize=12, fontweight='bold')
            ax2.set_xticks(range(len(months)))
            ax2.set_xticklabels(months, rotation=45, ha='right')
            ax2.grid(True, alpha=0.3)
        else:
            ax2.text(0.5, 0.5, 'No monthly data', ha='center', va='center', transform=ax2.transAxes)

        # 3. Payment status
        ax3 = plt.subplot(2, 3, 3)
        status_counts = {
            'paid': FinancialRecord.query.filter_by(payment_status='paid').count(),
            'pending': FinancialRecord.query.filter_by(payment_status='pending').count(),
            'overdue': FinancialRecord.query.filter_by(payment_status='overdue').count()
        }

        if sum(status_counts.values()) > 0:
            ax3.pie(status_counts.values(), labels=status_counts.keys(), autopct='%1.1f%%',
                    colors=['#00b894', '#f39c12', '#ff6b6b'], startangle=90)
            ax3.set_title("Payment Status Distribution", fontsize=12, fontweight='bold')
        else:
            ax3.text(0.5, 0.5, 'No payment data', ha='center', va='center', transform=ax3.transAxes)

        # 4. Outstanding balances
        ax4 = plt.subplot(2, 3, 4)
        users_with_balance = []
        balances = []
        for record in financial_records:
            if record.balance > 0:
                user = User.query.get(record.user_id)
                if user:
                    users_with_balance.append(user.username)
                    balances.append(record.balance)

        if users_with_balance:
            ax4.barh(users_with_balance[:5], balances[:5], color='#e74c3c')
            ax4.set_xlabel("Balance", fontsize=10)
            ax4.set_title("Top Outstanding Balances", fontsize=12, fontweight='bold')
            ax4.grid(True, alpha=0.3)
        else:
            ax4.text(0.5, 0.5, 'No outstanding balances', ha='center', va='center', transform=ax4.transAxes)

        # 5. Revenue vs Consumption
        ax5 = plt.subplot(2, 3, 5)
        has_data = False
        for user in users[:5]:
            user_readings = Reading.query.filter_by(user_id=user.id).all()
            if user_readings:
                months_data = {}
                for reading in user_readings:
                    month_key = reading.created_at.strftime('%Y-%m')
                    if month_key not in months_data:
                        months_data[month_key] = {'kwh': 0, 'cost': 0}
                    months_data[month_key]['kwh'] += reading.kwh
                    months_data[month_key]['cost'] += reading.kwh * user.unit_cost

                months = sorted(months_data.keys())[-6:]
                if months:
                    costs = [months_data[m]['cost'] for m in months]
                    ax5.plot(range(len(months)), costs, marker='o', label=user.username)
                    has_data = True

        if has_data:
            ax5.set_xlabel("Months", fontsize=10)
            ax5.set_ylabel("Revenue", fontsize=10)
            ax5.set_title("User Revenue Comparison", fontsize=12, fontweight='bold')
            ax5.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            ax5.grid(True, alpha=0.3)
        else:
            ax5.text(0.5, 0.5, 'No comparison data', ha='center', va='center', transform=ax5.transAxes)

        # 6. Financial summary
        ax6 = plt.subplot(2, 3, 6)
        summary_data = ['Collected', 'Outstanding', 'Total Revenue']
        summary_values = [total_collected, total_outstanding, total_revenue]
        colors_summary = ['#00b894', '#ff6b6b', '#3498db']

        if total_revenue > 0:
            ax6.bar(summary_data, summary_values, color=colors_summary)
            ax6.set_xlabel("Category", fontsize=10)
            ax6.set_ylabel("Amount", fontsize=10)
            ax6.set_title("Financial Summary", fontsize=12, fontweight='bold')
            ax6.grid(True, alpha=0.3)

            for i, v in enumerate(summary_values):
                ax6.text(i, v + 5, f'{v:.0f}', ha='center', va='bottom', fontsize=9)
        else:
            ax6.text(0.5, 0.5, 'No financial data', ha='center', va='center', transform=ax6.transAxes)

        plt.tight_layout()

        img_bytes = io.BytesIO()
        plt.savefig(img_bytes, format='png', dpi=100, bbox_inches='tight')
        img_bytes.seek(0)
        plt.close()

        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()

        return {
            'chart': img_base64,
            'total_revenue': total_revenue,
            'total_outstanding': total_outstanding,
            'total_collected': total_collected,
            'payment_rate': (total_collected / total_revenue * 100) if total_revenue > 0 else 0
        }

    except Exception as e:
        print(f"Financial report error: {e}")
        plt.close('all')
        return {
            'chart': None,
            'total_revenue': 0,
            'total_outstanding': 0,
            'total_collected': 0,
            'payment_rate': 0
        }


def send_report_to_customers(admin_id):
    """Send consumption summary to all customers"""
    customers = User.query.filter_by(role='customer').all()
    count = 0

    for customer in customers:
        customer_readings = Reading.query.filter_by(user_id=customer.id).all()
        if customer_readings:
            total_consumption = sum(r.kwh for r in customer_readings)
            total_cost = sum(r.kwh * customer.unit_cost for r in customer_readings)

            # Calculate if readings are approved
            approved_readings = [r for r in customer_readings if r.is_approved]
            pending_readings = [r for r in customer_readings if not r.is_approved]

            report_content = f"""
            <h2>Energy Consumption Summary - {datetime.utcnow().strftime('%B %Y')}</h2>
            <p>Dear {customer.username},</p>
            <p>Here's your energy consumption summary:</p>
            <ul>
                <li><strong>Total Consumption:</strong> {total_consumption:.2f} kWh</li>
                <li><strong>Total Cost:</strong> {customer.currency} {total_cost:.2f}</li>
                <li><strong>Average Monthly:</strong> {total_consumption / len(customer_readings):.2f} kWh</li>
                <li><strong>Approved Readings:</strong> {len(approved_readings)}</li>
                <li><strong>Pending Review:</strong> {len(pending_readings)}</li>
            </ul>

            <h3>Detailed Breakdown:</h3>
            <table border="1" cellpadding="5" style="border-collapse: collapse;">
                <tr>
                    <th>Period</th>
                    <th>Consumption (kWh)</th>
                    <th>Cost</th>
                    <th>Status</th>
                </tr>
            """

            for reading in customer_readings[-6:]:  # Last 6 readings
                status = " Approved" if reading.is_approved else "⏳ Pending Review"
                report_content += f"""
                <tr>
                    <td>{reading.date}</td>
                    <td>{reading.kwh:.2f}</td>
                    <td>{customer.currency} {(reading.kwh * customer.unit_cost):.2f}</td>
                    <td>{status}</td>
                </tr>
                """

            report_content += """
            </table>

            <p><strong>Next Steps:</strong></p>
            <ul>
                <li>Please review your consumption data</li>
                <li>Ensure timely payment to avoid service interruption</li>
                <li>Contact support for any discrepancies</li>
            </ul>

            <p>Thank you for being an EcoPulse customer!</p>
            """

            report = Report(
                title=f"Consumption Summary - {datetime.utcnow().strftime('%B %Y')}",
                content=report_content,
                report_type='consumption_summary',
                sent_by=admin_id,
                sent_to=customer.id
            )
            db.session.add(report)
            count += 1

    db.session.commit()
    return count


def update_database_schema():
    """Check and update database schema if needed"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)

        # Check if readings table exists and has required columns
        if 'readings' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('readings')]

            # Add missing columns if they don't exist
            required_columns = {
                'cost': 'FLOAT DEFAULT 0',
                'is_reviewed': 'BOOLEAN DEFAULT 0',
                'reviewed_by': 'INTEGER',
                'reviewed_at': 'DATETIME',
                'review_notes': 'TEXT',
                'is_approved': 'BOOLEAN DEFAULT 0',
                'approved_by': 'INTEGER',
                'approved_at': 'DATETIME'
            }

            for col_name, col_type in required_columns.items():
                if col_name not in columns:
                    print(f" Adding missing '{col_name}' column to readings table...")
                    with db.engine.connect() as conn:
                        conn.execute(db.text(f"ALTER TABLE readings ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    print(f" '{col_name}' column added successfully!")

        # Check if consumption_reviews table exists
        if 'consumption_reviews' not in inspector.get_table_names():
            print(" Creating consumption_reviews table...")
            # Table will be created by SQLAlchemy when we run db.create_all()

        # Check if customer_submissions table exists
        if 'customer_submissions' not in inspector.get_table_names():
            print(" Creating customer_submissions table...")
            # Table will be created by SQLAlchemy when we run db.create_all()

    except Exception as e:
        print(f"Note: Schema check - {e}")


# ===================== NEW CUSTOMER SUBMISSION ROUTES =====================

@app.route('/submit_to_admin', methods=['POST'])
@login_required
def submit_to_admin():
    """Allow customer to submit their consumption summary to admin for verification"""
    if current_user.role != 'customer':
        return jsonify({'success': False, 'message': 'Only customers can submit'})

    # Get customer's readings
    readings = Reading.query.filter_by(user_id=current_user.id).all()

    if not readings:
        return jsonify({'success': False, 'message': 'No readings to submit'})

    # Calculate statistics
    total_consumption = sum(r.kwh for r in readings)
    total_cost = sum(r.kwh * current_user.unit_cost for r in readings)
    avg_daily = total_consumption / len(readings) if readings else 0

    # Check if there's already a pending submission
    existing = CustomerSubmission.query.filter_by(
        customer_id=current_user.id,
        status='pending'
    ).first()

    if existing:
        return jsonify({'success': False, 'message': 'You already have a pending submission'})

    # Create submission
    submission = CustomerSubmission(
        customer_id=current_user.id,
        period=datetime.utcnow().strftime('%Y-%m'),
        total_consumption=total_consumption,
        total_cost=total_cost,
        average_daily=avg_daily,
        readings_count=len(readings),
        notes=f"Submitted for verification - {len(readings)} readings",
        status='pending'
    )

    db.session.add(submission)
    db.session.commit()

    # Create a report for admin
    admin = User.query.filter_by(role='admin').first()
    if admin:
        report_content = f"""
        <h2>Customer Consumption Submission - {current_user.username}</h2>
        <p><strong>Customer:</strong> {current_user.username}</p>
        <p><strong>Email:</strong> {current_user.email}</p>
        <p><strong>Period:</strong> {submission.period}</p>
        <p><strong>Total Consumption:</strong> {total_consumption:.2f} kWh</p>
        <p><strong>Total Cost:</strong> {current_user.currency} {total_cost:.2f}</p>
        <p><strong>Average Daily:</strong> {avg_daily:.2f} kWh</p>
        <p><strong>Number of Readings:</strong> {len(readings)}</p>

        <h3>Detailed Readings:</h3>
        <table border="1" cellpadding="5" style="border-collapse: collapse;">
            <tr>
                <th>Period</th>
                <th>Consumption (kWh)</th>
                <th>Cost</th>
                <th>Status</th>
            </tr>
        """

        for reading in readings:
            status = " Approved" if reading.is_approved else "⏳ Pending" if not reading.is_reviewed else "📝 Reviewed"
            report_content += f"""
            <tr>
                <td>{reading.date}</td>
                <td>{reading.kwh:.2f}</td>
                <td>{current_user.currency} {(reading.kwh * current_user.unit_cost):.2f}</td>
                <td>{status}</td>
            </tr>
            """

        report_content += """
        </table>

        <p>Please review this submission and verify the consumption data.</p>
        """

        report = Report(
            title=f"Customer Submission - {current_user.username} - {submission.period}",
            content=report_content,
            report_type='customer_submission',
            sent_by=current_user.id,
            sent_to=admin.id
        )
        db.session.add(report)
        db.session.commit()

    log_system_action(current_user.id, f"Submitted consumption summary to admin")

    return jsonify({
        'success': True,
        'message': 'Submission sent to admin successfully!'
    })


@app.route('/admin_submissions')
@login_required
@admin_required
def admin_submissions():
    """View all customer submissions"""
    submissions = CustomerSubmission.query.order_by(CustomerSubmission.created_at.desc()).all()

    # Create a simple HTML page for submissions
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Customer Submissions - Admin</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
        <style>
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            .container {
                background: white;
                border-radius: 15px;
                padding: 30px;
                margin-top: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            .status-pending { background-color: #f39c12; color: white; padding: 5px 10px; border-radius: 20px; }
            .status-reviewed { background-color: #3498db; color: white; padding: 5px 10px; border-radius: 20px; }
            .status-approved { background-color: #00b894; color: white; padding: 5px 10px; border-radius: 20px; }
            .status-rejected { background-color: #ff6b6b; color: white; padding: 5px 10px; border-radius: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="mb-4"><i class="bi bi-people"></i> Customer Submissions</h1>
            <a href="/admin_financial" class="btn btn-primary mb-3">Back to Dashboard</a>

            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Customer</th>
                            <th>Period</th>
                            <th>Total Consumption</th>
                            <th>Total Cost</th>
                            <th>Readings</th>
                            <th>Status</th>
                            <th>Submitted</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
    """

    for sub in submissions:
        status_class = f"status-{sub.status}"
        html += f"""
        <tr>
            <td>{sub.id}</td>
            <td>{sub.customer.username}</td>
            <td>{sub.period}</td>
            <td>{sub.total_consumption:.2f} kWh</td>
            <td>Ksh {sub.total_cost:.2f}</td>
            <td>{sub.readings_count}</td>
            <td><span class="{status_class}">{sub.status}</span></td>
            <td>{sub.created_at.strftime('%Y-%m-%d %H:%M')}</td>
            <td>
                <button class="btn btn-sm btn-success" onclick="approveSubmission({sub.id})">Approve</button>
                <button class="btn btn-sm btn-warning" onclick="reviewSubmission({sub.id})">Review</button>
                <button class="btn btn-sm btn-danger" onclick="rejectSubmission({sub.id})">Reject</button>
            </td>
        </tr>
        """

    html += """
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            function approveSubmission(id) {
                fetch('/approve_submission/' + id, {method: 'POST'})
                    .then(r => r.json())
                    .then(d => { alert(d.message); location.reload(); });
            }
            function reviewSubmission(id) {
                fetch('/review_submission/' + id, {method: 'POST'})
                    .then(r => r.json())
                    .then(d => { alert(d.message); location.reload(); });
            }
            function rejectSubmission(id) {
                fetch('/reject_submission/' + id, {method: 'POST'})
                    .then(r => r.json())
                    .then(d => { alert(d.message); location.reload(); });
            }
        </script>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """

    return html


@app.route('/approve_submission/<int:submission_id>', methods=['POST'])
@login_required
@admin_required
def approve_submission(submission_id):
    """Approve a customer submission"""
    submission = CustomerSubmission.query.get(submission_id)
    if submission:
        submission.status = 'approved'
        submission.reviewed_by = current_user.id
        submission.reviewed_at = datetime.utcnow()
        submission.admin_notes = "Approved by admin"

        # Mark customer's readings as approved
        readings = Reading.query.filter_by(user_id=submission.customer_id).all()
        for reading in readings:
            reading.is_approved = True
            reading.approved_by = current_user.id
            reading.approved_at = datetime.utcnow()

        db.session.commit()

        # Notify customer
        report = Report(
            title=f"Submission Approved - {submission.period}",
            content=f"Dear {submission.customer.username}, your consumption submission has been approved.",
            report_type='submission_response',
            sent_by=current_user.id,
            sent_to=submission.customer_id
        )
        db.session.add(report)
        db.session.commit()

        log_system_action(current_user.id, f"Approved customer submission ID: {submission_id}")
        return jsonify({'message': 'Submission approved successfully!'})

    return jsonify({'message': 'Submission not found'})


@app.route('/review_submission/<int:submission_id>', methods=['POST'])
@login_required
@admin_required
def review_submission(submission_id):
    """Mark a customer submission as reviewed"""
    submission = CustomerSubmission.query.get(submission_id)
    if submission:
        submission.status = 'reviewed'
        submission.reviewed_by = current_user.id
        submission.reviewed_at = datetime.utcnow()
        db.session.commit()

        log_system_action(current_user.id, f"Reviewed customer submission ID: {submission_id}")
        return jsonify({'message': 'Submission marked as reviewed!'})

    return jsonify({'message': 'Submission not found'})


@app.route('/reject_submission/<int:submission_id>', methods=['POST'])
@login_required
@admin_required
def reject_submission(submission_id):
    """Reject a customer submission"""
    submission = CustomerSubmission.query.get(submission_id)
    if submission:
        submission.status = 'rejected'
        submission.reviewed_by = current_user.id
        submission.reviewed_at = datetime.utcnow()
        submission.admin_notes = "Rejected - Please review your readings"
        db.session.commit()

        # Notify customer
        report = Report(
            title=f"Submission Rejected - {submission.period}",
            content=f"Dear {submission.customer.username}, your consumption submission needs review. Please check your readings.",
            report_type='submission_response',
            sent_by=current_user.id,
            sent_to=submission.customer_id
        )
        db.session.add(report)
        db.session.commit()

        log_system_action(current_user.id, f"Rejected customer submission ID: {submission_id}")
        return jsonify({'message': 'Submission rejected!'})

    return jsonify({'message': 'Submission not found'})


# ===================== TEMPLATES =====================

login_page = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Login - EcoPulse</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css"><style>body{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif}.auth-container{width:100%;max-width:450px;padding:20px}.card{border:none;border-radius:15px;box-shadow:0 10px 40px rgba(0,0,0,0.3)}.card-header{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:white;border-radius:15px 15px 0 0;padding:30px;text-align:center}.card-header h2{margin:0;font-weight:700;font-size:1.8rem}.form-control{border-radius:8px;border:2px solid #e0e0e0;padding:12px 15px}.form-control:focus{border-color:#667eea;box-shadow:0 0 0 0.2rem rgba(102,126,234,0.25)}.btn-primary{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);border:none;padding:12px;font-weight:600;border-radius:8px;color:white}.auth-link{text-align:center;margin-top:20px}.auth-link a{color:#667eea;text-decoration:none;font-weight:600}</style></head><body><div class="auth-container"><div class="card"><div class="card-header"><h2><i class="bi bi-lightning-fill"></i> EcoPulse</h2><p>Energy Management Dashboard</p></div><div class="card-body" style="padding: 40px;">{% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}<form method="POST"><div class="mb-3"><label class="form-label">Username</label><input type="text" name="username" class="form-control" required></div><div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required></div><div class="mb-3"><label class="form-label">Login as</label><select name="role" class="form-select" required><option value="">Select Role</option><option value="customer">Customer</option><option value="admin">Admin</option><option value="examiner">Examiner</option></select></div><button type="submit" class="btn btn-primary w-100 btn-lg"><i class="bi bi-box-arrow-in-right"></i> Login</button></form><div class="auth-link">Don't have an account? <a href="{{ url_for('register') }}">Register here</a></div></div></div></div><script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script></body></html>"""

register_page = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Register - EcoPulse</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css"><style>body{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif}.auth-container{width:100%;max-width:450px;padding:20px}.card{border:none;border-radius:15px;box-shadow:0 10px 40px rgba(0,0,0,0.3)}.card-header{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:white;border-radius:15px 15px 0 0;padding:30px;text-align:center}.card-header h2{margin:0;font-weight:700;font-size:1.8rem}.form-control{border-radius:8px;border:2px solid #e0e0e0;padding:12px 15px}.form-control:focus{border-color:#667eea;box-shadow:0 0 0 0.2rem rgba(102,126,234,0.25)}.btn-primary{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);border:none;padding:12px;font-weight:600;border-radius:8px;color:white}.auth-link{text-align:center;margin-top:20px}.auth-link a{color:#667eea;text-decoration:none;font-weight:600}</style></head><body><div class="auth-container"><div class="card"><div class="card-header"><h2><i class="bi bi-lightning-fill"></i> EcoPulse</h2><p>Create Your Account</p></div><div class="card-body" style="padding: 40px;">{% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}<form method="POST"><div class="mb-3"><label class="form-label">Username</label><input type="text" name="username" class="form-control" required></div><div class="mb-3"><label class="form-label">Email</label><input type="email" name="email" class="form-control" required></div><div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required></div><div class="mb-3"><label class="form-label">Confirm Password</label><input type="password" name="confirm_password" class="form-control" required></div><div class="mb-3"><label class="form-label">Register as</label><select name="role" class="form-select" required><option value="">Select Role</option><option value="customer">Customer</option><option value="admin">Admin</option><option value="examiner">Examiner</option></select></div><div class="mb-3" id="departmentField" style="display:none;"><label class="form-label">Department</label><input type="text" name="department" class="form-control" placeholder="Enter your department"></div><button type="submit" class="btn btn-primary w-100 btn-lg"><i class="bi bi-person-plus"></i> Register</button></form><div class="auth-link">Already have an account? <a href="{{ url_for('login') }}">Login here</a></div></div></div></div><script>document.querySelector('select[name="role"]').addEventListener('change', function() {const deptField = document.getElementById('departmentField');deptField.style.display = (this.value === 'admin' || this.value === 'examiner') ? 'block' : 'none';});</script><script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script></body></html>"""

dashboard_template = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>EcoPulse Dashboard</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css"><style>*{margin:0;padding:0;box-sizing:border-box}body{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);min-height:100vh;font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;padding-top:80px;padding-bottom:30px}.navbar{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);box-shadow:0 5px 20px rgba(0,0,0,0.2)}.navbar-brand{font-weight:700;font-size:1.5rem}.header-section{text-align:center;margin-bottom:40px;color:white}.header-section h1{font-size:3rem;font-weight:700;margin-bottom:10px;text-shadow:2px 2px 4px rgba(0,0,0,0.3)}.role-badge{display:inline-block;padding:5px 15px;border-radius:20px;font-size:0.9rem;font-weight:600;margin-top:10px}.role-customer{background-color:#00b894;color:white}.role-admin{background-color:#ff6b6b;color:white}.role-examiner{background-color:#ff9800;color:white}.card{border:none;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.2);margin-bottom:30px;transition:transform 0.3s ease, box-shadow 0.3s ease}.card:hover{transform:translateY(-5px);box-shadow:0 15px 40px rgba(0,0,0,0.3)}.card-header{border-radius:15px 15px 0 0;padding:20px;font-weight:600;font-size:1.2rem;display:flex;align-items:center;gap:10px;color:white}.card-header.bg-primary{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important}.card-header.bg-info{background:linear-gradient(135deg, #00d4ff 0%, #0099ff 100%) !important}.card-header.bg-warning{background:linear-gradient(135deg, #ffc107 0%, #ff9800 100%) !important}.card-header.bg-success{background:linear-gradient(135deg, #00b894 0%, #00cec9 100%) !important}.card-header.bg-secondary{background:linear-gradient(135deg, #6c757d 0%, #495057 100%) !important}.card-body{padding:30px}.stats-grid{display:grid;grid-template-columns:repeat(auto-fit, minmax(250px, 1fr));gap:20px;margin-bottom:30px}.stat-card{background:white;padding:20px;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1);text-align:center}.stat-value{font-size:2.5rem;font-weight:700;color:#667eea}.stat-label{color:#666;font-size:0.9rem;margin-top:10px}.stat-icon{font-size:2rem;margin-bottom:10px;color:#667eea}.form-control,.form-select{border-radius:8px;border:2px solid #e0e0e0;padding:12px 15px}.form-control:focus,.form-select:focus{border-color:#667eea;box-shadow:0 0 0 0.2rem rgba(102,126,234,0.25)}.btn{border-radius:8px;padding:10px 20px;font-weight:600;transition:all 0.3s ease}.btn-success{background:linear-gradient(135deg, #00b894 0%, #00cec9 100%);border:none;color:white}.btn-success:hover{background:linear-gradient(135deg, #00a884 0%, #00beb9 100%)}.btn-primary{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);border:none;color:white}.btn-warning{background:linear-gradient(135deg, #ffc107 0%, #ff9800 100%);border:none;color:white}.btn-danger{background:linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);border:none;color:white}.btn-sm{padding:5px 10px;font-size:0.875rem}.alert{border-radius:10px;border:none;margin-bottom:20px}.table{color:#333}.table thead{background:#f5f5f5;font-weight:600}.table tbody tr:hover{background-color:#f9f9f9}.no-data{text-align:center;padding:30px;color:#999;font-style:italic}.img-fluid{border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1);max-width:100%;height:auto}.employee-info{background:rgba(255,255,255,0.1);padding:10px;border-radius:10px;margin-top:10px;color:white;font-size:0.9rem}.employee-info i{margin-right:5px}@media (max-width:768px){body{padding-top:100px}.header-section h1{font-size:2rem}.stats-grid{grid-template-columns:1fr}}</style></head><body><nav class="navbar navbar-expand-lg navbar-dark fixed-top"><div class="container"><a class="navbar-brand" href="{{ url_for('dashboard') }}"><i class="bi bi-lightning-fill"></i> EcoPulse</a><button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav"><span class="navbar-toggler-icon"></span></button><div class="collapse navbar-collapse" id="navbarNav"><ul class="navbar-nav ms-auto"><li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}"><i class="bi bi-house"></i> Dashboard</a></li><li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}"><i class="bi bi-gear"></i> Settings</a></li>{% if current_user.role == 'admin' %}<li class="nav-item"><a class="nav-link" href="{{ url_for('admin_financial') }}"><i class="bi bi-cash-stack"></i> Financial</a></li>{% endif %}{% if current_user.role == 'examiner' %}<li class="nav-item"><a class="nav-link" href="{{ url_for('examiner_dashboard') }}"><i class="bi bi-clipboard-data"></i> Examiner</a></li>{% endif %}<li class="nav-item dropdown"><a class="nav-link dropdown-toggle" href="#" id="navbarDropdown" role="button" data-bs-toggle="dropdown"><i class="bi bi-person-circle"></i> {{ current_user.username }}</a><ul class="dropdown-menu dropdown-menu-end"><li><a class="dropdown-item" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right"></i> Logout</a></li></ul></li></ul></div></div></nav><div class="container"><div class="header-section"><h1><i class="bi bi-lightning-fill"></i> EcoPulse</h1><p>Welcome, {{ current_user.username }}!</p>{% if current_user.role == 'admin' %}<span class="role-badge role-admin"><i class="bi bi-shield-fill"></i> Administrator</span>{% elif current_user.role == 'examiner' %}<span class="role-badge role-examiner"><i class="bi bi-eye-fill"></i> Examiner</span>{% else %}<span class="role-badge role-customer"><i class="bi bi-person-fill"></i> Customer</span>{% endif %}{% if current_user.employee_id %}<div class="employee-info"><i class="bi bi-building"></i> Employee ID: {{ current_user.employee_id }} | <i class="bi bi-diagram-3"></i> {{ current_user.department or 'General' }}</div>{% endif %}</div>{% if message %}<div class="alert alert-success"><i class="bi bi-check-circle"></i> {{ message }}</div>{% endif %}{% if analytics %}<div class="stats-grid"><div class="stat-card"><div class="stat-icon"><i class="bi bi-lightning-charge"></i></div><div class="stat-label">Total</div><div class="stat-value">{{ analytics.total_kwh }}</div><small>kWh</small></div><div class="stat-card"><div class="stat-icon"><i class="bi bi-graph-up"></i></div><div class="stat-label">Average</div><div class="stat-value">{{ analytics.avg_kwh }}</div><small>kWh</small></div><div class="stat-card"><div class="stat-icon"><i class="bi bi-cash-coin"></i></div><div class="stat-label">Total Cost</div><div class="stat-value">{{ analytics.currency }} {{ analytics.total_cost }}</div><small>Est.</small></div><div class="stat-card"><div class="stat-icon"><i class="bi bi-cloud"></i></div><div class="stat-label">CO2</div><div class="stat-value">{{ analytics.total_co2 }}</div><small>kg</small></div></div>{% endif %}<div class="card"><div class="card-header bg-primary"><i class="bi bi-plus-circle"></i> Add Reading</div><div class="card-body"><form method="POST" action="{{ url_for('add_reading') }}"><div class="row"><div class="col-md-4 mb-3"><label class="form-label">Month</label><input type="text" name="date" class="form-control" placeholder="e.g. January" required></div><div class="col-md-4 mb-3"><label class="form-label">kWh</label><input type="number" name="kwh" class="form-control" placeholder="e.g. 520" step="0.01" required></div><div class="col-md-4 mb-3"><label class="form-label">Timestamp</label><input type="datetime-local" name="timestamp" class="form-control" required></div></div><button type="submit" class="btn btn-success"><i class="bi bi-check-circle"></i> Submit</button></form></div></div><div class="row mb-4"><div class="col-md-6"><div class="card"><div class="card-header bg-info"><i class="bi bi-funnel"></i> Filter</div><div class="card-body"><form method="GET" action="{{ url_for('dashboard') }}" class="row g-3"><div class="col-md-4"><label class="form-label">Start</label><input type="date" name="start_date" class="form-control"></div><div class="col-md-4"><label class="form-label">End</label><input type="date" name="end_date" class="form-control"></div><div class="col-md-4"><label class="form-label">Days</label><select name="days" class="form-select"><option value="">All</option><option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option></select></div><div class="col-md-12 mt-2"><button type="submit" class="btn btn-primary w-100">Filter</button></div></form></div></div></div><div class="col-md-6"><div class="card"><div class="card-header bg-warning"><i class="bi bi-send"></i> Submit to Admin</div><div class="card-body text-center"><p>Submit your consumption summary to admin for verification and comparison</p><button class="btn btn-warning w-100" onclick="submitToAdmin()"><i class="bi bi-send"></i> Submit My Consumption</button></div></div></div></div><div class="card"><div class="card-header bg-warning"><i class="bi bi-bar-chart"></i> Consumption Analysis</div><div class="card-body">{% if chart %}<img src="data:image/png;base64,{{ chart }}" class="img-fluid" alt="Consumption Chart">{% else %}<p class="no-data">No chart available. Add some readings to see visualization.</p>{% endif %}</div></div><div class="card"><div class="card-header bg-secondary"><i class="bi bi-table"></i> Readings</div><div class="card-body">{% if readings %}<div class="table-responsive"><table class="table table-hover"><thead><tr><th>Period</th><th>kWh</th><th>Cost</th><th>CO2</th><th>Status</th><th>Timestamp</th><th>Actions</th></tr></thead><tbody>{% for reading in readings %}<tr><td><strong>{{ reading.date }}</strong></td><td><span class="badge {% if reading.kwh > current_user.threshold %}bg-danger{% else %}bg-success{% endif %}">{{ reading.kwh }}</span></td><td>{{ "%.2f"|format(reading.kwh * current_user.unit_cost) }}</td><td>{{ "%.2f"|format(reading.kwh * 0.385) }}</td><td>{% if reading.is_approved %}<span class="badge bg-success">Approved</span>{% elif reading.is_reviewed %}<span class="badge bg-info">Reviewed</span>{% else %}<span class="badge bg-warning">Pending</span>{% endif %}</td><td><small>{{ reading.timestamp.strftime('%Y-%m-%d %H:%M') }}</small></td><td><button class="btn btn-warning btn-sm" data-bs-toggle="modal" data-bs-target="#editModal{{ reading.id }}"><i class="bi bi-pencil"></i></button><form method="POST" action="{{ url_for('delete_reading', reading_id=reading.id) }}" style="display: inline;" onsubmit="return confirm('Delete?');"><button type="submit" class="btn btn-danger btn-sm"><i class="bi bi-trash"></i></button></form></td></tr><div class="modal fade" id="editModal{{ reading.id }}" tabindex="-1"><div class="modal-dialog"><div class="modal-content"><div class="modal-header"><h5 class="modal-title">Edit</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><form method="POST" action="{{ url_for('update_reading', reading_id=reading.id) }}"><div class="modal-body"><div class="mb-3"><label class="form-label">Period</label><input type="text" name="date" class="form-control" value="{{ reading.date }}" required></div><div class="mb-3"><label class="form-label">kWh</label><input type="number" name="kwh" class="form-control" value="{{ reading.kwh }}" step="0.01" required></div><div class="mb-3"><label class="form-label">Timestamp</label><input type="datetime-local" name="timestamp" class="form-control" value="{{ reading.timestamp.strftime('%Y-%m-%dT%H:%M') }}" required></div></div><div class="modal-footer"><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button><button type="submit" class="btn btn-success">Update</button></div></form></div></div></div>{% endfor %}</tbody></table></div>{% else %}<p class="no-data">No readings yet. Add your first reading above.</p>{% endif %}</div></div><div class="card"><div class="card-header bg-success"><i class="bi bi-download"></i> Export</div><div class="card-body"><div class="row g-3"><div class="col-md-6"><a href="{{ url_for('export_csv') }}" class="btn btn-success w-100"><i class="bi bi-file-earmark-spreadsheet"></i> CSV</a></div><div class="col-md-6"><a href="{{ url_for('export_pdf') }}" class="btn btn-danger w-100"><i class="bi bi-file-pdf"></i> PDF</a></div></div></div></div>{% if reports %}<div class="card"><div class="card-header bg-info"><i class="bi bi-envelope"></i> Recent Reports</div><div class="card-body"><div class="list-group">{% for report in reports %}<a href="#" class="list-group-item list-group-item-action"><div class="d-flex w-100 justify-content-between"><h6 class="mb-1">{{ report.title }}</h6><small>{{ report.created_at.strftime('%Y-%m-%d') }}</small></div><p class="mb-1">{{ report.content|safe }}</p></a>{% endfor %}</div></div></div>{% endif %}</div><script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script><script>const now=new Date();now.setMinutes(now.getMinutes()-now.getTimezoneOffset());const ts=document.querySelector('input[name="timestamp"]');if(ts)ts.value=now.toISOString().slice(0,16);function submitToAdmin(){fetch('/submit_to_admin',{method:'POST'}).then(r=>r.json()).then(d=>{alert(d.message);if(d.success){location.reload();}});}</script></body></html>"""

settings_template = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Settings - EcoPulse</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css"><style>body{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);min-height:100vh;font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;padding-top:80px;padding-bottom:30px}.navbar{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);box-shadow:0 5px 20px rgba(0,0,0,0.2)}.container{max-width:800px}.card{border:none;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.2);margin-bottom:30px}.card-header{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:white;border-radius:15px 15px 0 0;padding:20px;font-weight:600;font-size:1.2rem}.card-body{padding:30px}.form-control,.form-select{border-radius:8px;border:2px solid #e0e0e0;padding:12px 15px}.form-control:focus,.form-select:focus{border-color:#667eea;box-shadow:0 0 0 0.2rem rgba(102,126,234,0.25)}.btn{border-radius:8px;padding:10px 20px;font-weight:600}.btn-primary{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);border:none;color:white}.btn-secondary{background:linear-gradient(135deg, #a4a4a4 0%, #797979 100%);border:none;color:white}.form-label{font-weight:600;color:#333}.settings-section{margin-bottom:30px;padding-bottom:30px;border-bottom:2px solid #e0e0e0}.settings-section:last-child{border-bottom:none}.settings-title{font-size:1.3rem;font-weight:700;color:#333;margin-bottom:20px;display:flex;align-items:center;gap:10px}</style></head><body><nav class="navbar navbar-expand-lg navbar-dark fixed-top"><div class="container"><a class="navbar-brand" href="{{ url_for('dashboard') }}"><i class="bi bi-lightning-fill"></i> EcoPulse</a><div class="navbar-nav ms-auto"><a class="nav-link" href="{{ url_for('dashboard') }}"><i class="bi bi-arrow-left"></i> Back</a></div></div></nav><div class="container"><div class="card"><div class="card-header"><i class="bi bi-gear"></i> Settings</div><div class="card-body">{% if message %}<div class="alert alert-success"><i class="bi bi-check-circle"></i> {{ message }}</div>{% endif %}<form method="POST"><div class="settings-section"><div class="settings-title"><i class="bi bi-speedometer2"></i> Threshold</div><div class="row"><div class="col-md-6 mb-3"><label class="form-label">Monthly (kWh)</label><input type="number" name="threshold" class="form-control" value="{{ current_user.threshold }}" step="10" required></div></div></div><div class="settings-section"><div class="settings-title"><i class="bi bi-cash-coin"></i> Cost</div><div class="row"><div class="col-md-6 mb-3"><label class="form-label">Currency</label><select name="currency" class="form-select"><option value="USD" {% if current_user.currency == 'USD' %}selected{% endif %}>USD</option><option value="EUR" {% if current_user.currency == 'EUR' %}selected{% endif %}>EUR</option><option value="GBP" {% if current_user.currency == 'GBP' %}selected{% endif %}>GBP</option><option value="INR" {% if current_user.currency == 'INR' %}selected{% endif %}>INR</option><option value="Ksh" {% if current_user.currency == 'Ksh' %}selected{% endif %}>Ksh</option></select></div><div class="col-md-6 mb-3"><label class="form-label">Cost/kWh</label><input type="number" name="unit_cost" class="form-control" value="{{ current_user.unit_cost }}" step="0.01" required></div></div></div><div class="settings-section"><div class="settings-title"><i class="bi bi-bell"></i> Alerts</div><div class="mb-3"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" name="alert_email" id="alertEmail" {% if current_user.alert_email %}checked{% endif %}><label class="form-check-label" for="alertEmail">Email Alerts</label></div></div></div>{% if current_user.role in ['admin', 'examiner'] %}<div class="settings-section"><div class="settings-title"><i class="bi bi-building"></i> Employee Information</div><div class="row"><div class="col-md-6 mb-3"><label class="form-label">Employee ID</label><input type="text" class="form-control" value="{{ current_user.employee_id or 'Not assigned' }}" readonly></div><div class="col-md-6 mb-3"><label class="form-label">Department</label><input type="text" class="form-control" value="{{ current_user.department or 'Not specified' }}" readonly></div></div></div>{% endif %}<div class="d-flex gap-3"><button type="submit" class="btn btn-primary"><i class="bi bi-check-circle"></i> Save</button><a href="{{ url_for('dashboard') }}" class="btn btn-secondary"><i class="bi bi-x-circle"></i> Cancel</a></div></form></div></div></div><script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script></body></html>"""

examiner_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Examiner Dashboard - EcoPulse</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding-top: 80px;
            padding-bottom: 30px;
        }
        .navbar {
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
            box-shadow: 0 5px 20px rgba(0,0,0,0.2);
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        .card-header {
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
            color: white;
            border-radius: 15px 15px 0 0;
            padding: 20px;
            font-weight: 600;
            font-size: 1.2rem;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: #f39c12;
        }
        .btn-warning {
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
            border: none;
            color: white;
        }
        .btn-success {
            background: linear-gradient(135deg, #00b894 0%, #00cec9 100%);
            border: none;
            color: white;
        }
        .btn-info {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            border: none;
            color: white;
        }
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            color: white;
        }
        .report-preview {
            max-width: 100%;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .status-badge {
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .status-pending {
            background-color: #f39c12;
            color: white;
        }
        .status-reviewed {
            background-color: #3498db;
            color: white;
        }
        .status-approved {
            background-color: #00b894;
            color: white;
        }
        .status-rejected {
            background-color: #ff6b6b;
            color: white;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark fixed-top">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('examiner_dashboard') }}">
                <i class="bi bi-clipboard-data"></i> EcoPulse Examiner
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="{{ url_for('dashboard') }}">
                    <i class="bi bi-house"></i> Dashboard
                </a>
                <a class="nav-link" href="{{ url_for('logout') }}">
                    <i class="bi bi-box-arrow-right"></i> Logout
                </a>
            </div>
        </div>
    </nav>

    <div class="container">
        <div class="header-section text-center text-white mb-4">
            <h1><i class="bi bi-graph-up"></i> Examiner Dashboard</h1>
            <p>Review customer consumption and prepare reports for admin approval</p>
        </div>

        {% if message %}
        <div class="alert alert-success">{{ message }}</div>
        {% endif %}

        <!-- Summary Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-people fs-1 text-warning"></i></div>
                <div class="stat-value">{{ consumption_stats.total_customers }}</div>
                <div class="stat-label">Active Customers</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-lightning fs-1 text-warning"></i></div>
                <div class="stat-value">{{ "%.0f"|format(consumption_stats.total_consumption) }}</div>
                <div class="stat-label">Total kWh</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-cash fs-1 text-warning"></i></div>
                <div class="stat-value">Ksh {{ "%.0f"|format(consumption_stats.total_revenue) }}</div>
                <div class="stat-label">Est. Revenue</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-cloud fs-1 text-warning"></i></div>
                <div class="stat-value">{{ "%.0f"|format(consumption_stats.total_co2) }}</div>
                <div class="stat-label">CO2 (kg)</div>
            </div>
        </div>

        <!-- Reading Stats Summary -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card bg-light">
                    <div class="card-body text-center">
                        <h5>Total Readings</h5>
                        <h3>{{ consumption_stats.total_readings }}</h3>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card bg-light">
                    <div class="card-body text-center">
                        <h5>Reviewed</h5>
                        <h3 class="text-info">{{ consumption_stats.reviewed_count }}</h3>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card bg-light">
                    <div class="card-body text-center">
                        <h5>Pending</h5>
                        <h3 class="text-warning">{{ consumption_stats.pending_count }}</h3>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card bg-light">
                    <div class="card-body text-center">
                        <h5>Approved</h5>
                        <h3 class="text-success">{{ consumption_stats.approved_count }}</h3>
                    </div>
                </div>
            </div>
        </div>

        <!-- Main Action Buttons -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-bar-chart"></i> View Report
                    </div>
                    <div class="card-body text-center">
                        <p>Generate detailed consumption analysis</p>
                        <form method="POST" action="{{ url_for('view_consumption_report') }}">
                            <button type="submit" class="btn btn-info w-100">
                                <i class="bi bi-graph-up"></i> View Report
                            </button>
                        </form>
                    </div>
                </div>
            </div>

            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-check-circle"></i> Review
                    </div>
                    <div class="card-body text-center">
                        <p>Review pending readings</p>
                        <a href="#pendingReadings" class="btn btn-warning w-100">
                            <i class="bi bi-eye"></i> Review ({{ pending_count }})
                        </a>
                    </div>
                </div>
            </div>

            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-send"></i> Send to Admin
                    </div>
                    <div class="card-body text-center">
                        <p>Send all readings to admin</p>
                        <button class="btn btn-primary w-100" onclick="sendToAdmin()">
                            <i class="bi bi-send"></i> Send Report
                        </button>
                        <small class="text-muted">{{ consumption_stats.total_readings }} total readings</small>
                    </div>
                </div>
            </div>

            <div class="col-md-3">
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-download"></i> Export
                    </div>
                    <div class="card-body text-center">
                        <p>Export consumption data</p>
                        <a href="{{ url_for('export_csv') }}" class="btn btn-success w-100 mb-2">
                            <i class="bi bi-file-earmark-spreadsheet"></i> CSV
                        </a>
                        <a href="{{ url_for('export_pdf') }}" class="btn btn-danger w-100">
                            <i class="bi bi-file-pdf"></i> PDF
                        </a>
                    </div>
                </div>
            </div>
        </div>

        {% if consumption_report and consumption_report.chart %}
        <!-- Consumption Analysis Chart -->
        <div class="card">
            <div class="card-header">
                <i class="bi bi-bar-chart"></i> Customer Consumption Analysis
            </div>
            <div class="card-body">
                <img src="data:image/png;base64,{{ consumption_report.chart }}" class="img-fluid report-preview" alt="Consumption Report">

                <div class="row mt-4">
                    <div class="col-md-3">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5>Total Customers</h5>
                                <h3>{{ consumption_report.summary.total_customers }}</h3>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5>Total Consumption</h5>
                                <h3>{{ "%.0f"|format(consumption_report.summary.total_consumption) }} kWh</h3>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5>Average per Customer</h5>
                                <h3>{{ "%.0f"|format(consumption_report.summary.average_consumption) }} kWh</h3>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5>Peak Consumption</h5>
                                <h3>{{ "%.0f"|format(consumption_report.summary.peak_consumption) }} kWh</h3>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="row mt-3">
                    <div class="col-md-4">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h6>Efficient Customers</h6>
                                <h4 class="text-success">{{ consumption_report.summary.efficient_customers }}</h4>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h6>Above Threshold</h6>
                                <h4 class="text-danger">{{ consumption_report.summary.above_threshold_count }}</h4>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h6>Below Threshold</h6>
                                <h4 class="text-success">{{ consumption_report.summary.below_threshold_count }}</h4>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        {% endif %}

        <!-- Pending Readings for Review -->
        <div class="card" id="pendingReadings">
            <div class="card-header">
                <i class="bi bi-clock-history"></i> Pending Readings for Review
            </div>
            <div class="card-body">
                {% if pending_readings %}
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Customer</th>
                                <th>Period</th>
                                <th>kWh</th>
                                <th>Cost</th>
                                <th>Submitted</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for reading in pending_readings %}
                            <tr>
                                <td>{{ reading.user.username }}</td>
                                <td>{{ reading.date }}</td>
                                <td><span class="badge {% if reading.kwh > reading.user.threshold %}bg-danger{% else %}bg-success{% endif %}">{{ reading.kwh }}</span></td>
                                <td>Ksh {{ "%.2f"|format(reading.kwh * reading.user.unit_cost) }}</td>
                                <td><small>{{ reading.timestamp.strftime('%Y-%m-%d %H:%M') }}</small></td>
                                <td>
                                    <button class="btn btn-sm btn-info" onclick="reviewReading({{ reading.id }})">
                                        <i class="bi bi-eye"></i> Review
                                    </button>
                                </td>
                            </tr>

                            <!-- Review Modal -->
                            <div class="modal fade" id="reviewModal{{ reading.id }}" tabindex="-1">
                                <div class="modal-dialog">
                                    <div class="modal-content">
                                        <div class="modal-header">
                                            <h5 class="modal-title">Review Reading - {{ reading.user.username }}</h5>
                                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                        </div>
                                        <form method="POST" action="{{ url_for('review_reading', reading_id=reading.id) }}">
                                            <div class="modal-body">
                                                <div class="mb-3">
                                                    <label class="form-label">Period</label>
                                                    <input type="text" class="form-control" value="{{ reading.date }}" readonly>
                                                </div>
                                                <div class="mb-3">
                                                    <label class="form-label">Consumption (kWh)</label>
                                                    <input type="number" class="form-control" value="{{ reading.kwh }}" readonly>
                                                </div>
                                                <div class="mb-3">
                                                    <label class="form-label">Calculated Cost</label>
                                                    <input type="text" class="form-control" value="Ksh {{ "%.2f"|format(reading.kwh * reading.user.unit_cost) }}" readonly>
                                                </div>
                                                <div class="mb-3">
                                                    <label class="form-label">Review Notes</label>
                                                    <textarea name="notes" class="form-control" rows="3" placeholder="Add your review notes..."></textarea>
                                                </div>
                                                <div class="mb-3">
                                                    <label class="form-label">Review Decision</label>
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="radio" name="decision" value="approve" id="approve{{ reading.id }}" checked>
                                                        <label class="form-check-label" for="approve{{ reading.id }}">
                                                            <span class="text-success">✓ Approve - Ready for admin</span>
                                                        </label>
                                                    </div>
                                                    <div class="form-check">
                                                        <input class="form-check-input" type="radio" name="decision" value="reject" id="reject{{ reading.id }}">
                                                        <label class="form-check-label" for="reject{{ reading.id }}">
                                                            <span class="text-danger">✗ Reject - Needs correction</span>
                                                        </label>
                                                    </div>
                                                </div>
                                            </div>
                                            <div class="modal-footer">
                                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                                <button type="submit" class="btn btn-primary">Submit Review</button>
                                            </div>
                                        </form>
                                    </div>
                                </div>
                            </div>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-center text-muted">No pending readings to review.</p>
                {% endif %}
            </div>
        </div>

        <!-- Reviewed Readings -->
        <div class="card">
            <div class="card-header">
                <i class="bi bi-check-circle"></i> Reviewed Readings
            </div>
            <div class="card-body">
                {% if reviewed_readings %}
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Customer</th>
                                <th>Period</th>
                                <th>kWh</th>
                                <th>Review Notes</th>
                                <th>Reviewed At</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for reading in reviewed_readings %}
                            <tr>
                                <td>{{ reading.user.username }}</td>
                                <td>{{ reading.date }}</td>
                                <td>{{ reading.kwh }}</td>
                                <td><small>{{ reading.review_notes or 'No notes' }}</small></td>
                                <td><small>{{ reading.reviewed_at.strftime('%Y-%m-%d %H:%M') if reading.reviewed_at }}</small></td>
                                <td>
                                    {% if reading.is_approved %}
                                        <span class="status-badge status-approved">Approved by Admin</span>
                                    {% else %}
                                        <span class="status-badge status-reviewed">Reviewed</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-center text-muted">No reviewed readings yet.</p>
                {% endif %}
            </div>
        </div>

        <!-- All Readings -->
        <div class="card">
            <div class="card-header">
                <i class="bi bi-table"></i> All Readings
            </div>
            <div class="card-body">
                {% if all_readings %}
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Customer</th>
                                <th>Period</th>
                                <th>kWh</th>
                                <th>Cost</th>
                                <th>Status</th>
                                <th>Reviewed By</th>
                                <th>Notes</th>
                                <th>Timestamp</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for reading in all_readings %}
                            <tr>
                                <td>{{ reading.user.username }}</td>
                                <td>{{ reading.date }}</td>
                                <td><span class="badge {% if reading.kwh > reading.user.threshold %}bg-danger{% else %}bg-success{% endif %}">{{ reading.kwh }}</span></td>
                                <td>Ksh {{ "%.2f"|format(reading.kwh * reading.user.unit_cost) }}</td>
                                <td>
                                    {% if reading.is_approved %}
                                        <span class="badge bg-success">Approved</span>
                                    {% elif reading.is_reviewed %}
                                        <span class="badge bg-info">Reviewed</span>
                                    {% else %}
                                        <span class="badge bg-warning">Pending</span>
                                    {% endif %}
                                </td>
                                <td>
                                    {% if reading.reviewer %}
                                        {{ reading.reviewer.username }}
                                    {% else %}
                                        -
                                    {% endif %}
                                </td>
                                <td><small>{{ reading.review_notes or '-' }}</small></td>
                                <td><small>{{ reading.timestamp.strftime('%Y-%m-%d %H:%M') }}</small></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-center text-muted">No readings available.</p>
                {% endif %}
            </div>
        </div>

        <!-- Report History -->
        <div class="card">
            <div class="card-header">
                <i class="bi bi-clock-history"></i> Report History
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Report Type</th>
                                <th>Total Customers</th>
                                <th>Total Consumption</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for review in review_history %}
                            <tr>
                                <td>{{ review.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                                <td>Consumption Review</td>
                                <td>{{ review.total_customers }}</td>
                                <td>{{ "%.0f"|format(review.total_consumption) }} kWh</td>
                                <td>
                                    {% if review.status == 'approved' %}
                                        <span class="badge bg-success">Approved</span>
                                    {% elif review.status == 'pending_review' %}
                                        <span class="badge bg-warning">Pending Admin</span>
                                    {% else %}
                                        <span class="badge bg-info">Reviewed</span>
                                    {% endif %}
                                </td>
                                <td>
                                    <button class="btn btn-sm btn-info" onclick="viewDetails({{ review.id }})">
                                        <i class="bi bi-eye"></i>
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

    <script>
        function reviewReading(readingId) {
            $('#reviewModal' + readingId).modal('show');
        }

        function sendToAdmin() {
            fetch('/send_review_to_admin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                if (data.success) {
                    location.reload();
                }
            });
        }

        function viewDetails(reviewId) {
            window.open('/view_review/' + reviewId, '_blank');
        }
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

admin_financial_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Financial Management - EcoPulse Admin</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding-top: 80px;
            padding-bottom: 30px;
        }
        .navbar {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
            box-shadow: 0 5px 20px rgba(0,0,0,0.2);
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        .card-header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
            color: white;
            border-radius: 15px 15px 0 0;
            padding: 20px;
            font-weight: 600;
            font-size: 1.2rem;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: #ff6b6b;
        }
        .btn-danger {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
            border: none;
        }
        .btn-success {
            background: linear-gradient(135deg, #00b894 0%, #00cec9 100%);
            border: none;
        }
        .btn-warning {
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
            border: none;
            color: white;
        }
        .btn-info {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            border: none;
            color: white;
        }
        .financial-chart {
            max-width: 100%;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .status-paid {
            background-color: #00b894;
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
        }
        .status-pending {
            background-color: #f39c12;
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
        }
        .status-overdue {
            background-color: #ff6b6b;
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
        }
        .status-badge {
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .status-pending-admin {
            background-color: #f39c12;
            color: white;
        }
        .status-approved {
            background-color: #00b894;
            color: white;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark fixed-top">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('admin_financial') }}">
                <i class="bi bi-cash-stack"></i> EcoPulse Financial Admin
            </a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="{{ url_for('dashboard') }}">
                    <i class="bi bi-house"></i> Dashboard
                </a>
                <a class="nav-link" href="{{ url_for('admin_submissions') }}">
                    <i class="bi bi-people"></i> Submissions
                </a>
                <a class="nav-link" href="{{ url_for('logout') }}">
                    <i class="bi bi-box-arrow-right"></i> Logout
                </a>
            </div>
        </div>
    </nav>

    <div class="container">
        <div class="header-section text-center text-white mb-4">
            <h1><i class="bi bi-calculator"></i> Financial Management</h1>
            <p>Approve examiner reports and send consumption summaries to customers</p>
        </div>

        {% if message %}
        <div class="alert alert-success">{{ message }}</div>
        {% endif %}

        <!-- Financial Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-cash-stack fs-1 text-danger"></i></div>
                <div class="stat-value">Ksh {{ "%.2f"|format(financial.total_revenue) }}</div>
                <div class="stat-label">Total Revenue</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-exclamation-triangle fs-1 text-danger"></i></div>
                <div class="stat-value">Ksh {{ "%.2f"|format(financial.total_outstanding) }}</div>
                <div class="stat-label">Outstanding</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-check-circle fs-1 text-danger"></i></div>
                <div class="stat-value">Ksh {{ "%.2f"|format(financial.total_collected) }}</div>
                <div class="stat-label">Collected</div>
            </div>
            <div class="stat-card">
                <div class="stat-icon"><i class="bi bi-percent fs-1 text-danger"></i></div>
                <div class="stat-value">{{ "%.1f"|format(financial.payment_rate) }}%</div>
                <div class="stat-label">Payment Rate</div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-8">
                <!-- Financial Chart -->
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-graph-up"></i> Financial Overview
                    </div>
                    <div class="card-body">
                        {% if financial.chart %}
                        <img src="data:image/png;base64,{{ financial.chart }}" class="img-fluid financial-chart" alt="Financial Chart">
                        {% else %}
                        <div class="alert alert-info text-center">
                            <i class="bi bi-info-circle"></i> No financial data available yet. Add some readings to see charts.
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>

            <div class="col-md-4">
                <!-- Quick Actions -->
                <div class="card">
                    <div class="card-header">
                        <i class="bi bi-envelope-paper"></i> Send Customer Summaries
                    </div>
                    <div class="card-body">
                        <p>Generate and send monthly consumption summaries to all customers</p>
                        <form method="POST" action="{{ url_for('send_customer_summaries') }}">
                            <button type="submit" class="btn btn-danger w-100 mb-3">
                                <i class="bi bi-send"></i> Send to All Customers
                            </button>
                        </form>
                        <hr>
                        <h6>Recent Reports from Examiner</h6>
                        <div class="list-group" style="max-height: 300px; overflow-y: auto;">
                            {% for report in examiner_reports %}
                            <a href="#" class="list-group-item list-group-item-action">
                                <div class="d-flex w-100 justify-content-between">
                                    <h6 class="mb-1">{{ report.title }}</h6>
                                    <small>{{ report.created_at.strftime('%d/%m/%Y') }}</small>
                                </div>
                                <p class="mb-1">From: Examiner</p>
                            </a>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Pending Examiner Reviews -->
        <div class="card">
            <div class="card-header">
                <i class="bi bi-clipboard-check"></i> Pending Examiner Reviews
            </div>
            <div class="card-body">
                {% if pending_reviews %}
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Period</th>
                                <th>Examiner</th>
                                <th>Total Customers</th>
                                <th>Total Consumption</th>
                                <th>Average Consumption</th>
                                <th>Peak Consumption</th>
                                <th>Notes</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for review in pending_reviews %}
                            <tr>
                                <td>{{ review.period }}</td>
                                <td>{{ review.examiner.username }}</td>
                                <td>{{ review.total_customers }}</td>
                                <td>{{ "%.0f"|format(review.total_consumption) }} kWh</td>
                                <td>{{ "%.0f"|format(review.average_consumption) }} kWh</td>
                                <td>{{ "%.0f"|format(review.peak_consumption) }} kWh</td>
                                <td><small>{{ review.notes or 'No notes' }}</small></td>
                                <td>
                                    <button class="btn btn-sm btn-success" onclick="approveReview({{ review.id }})">
                                        <i class="bi bi-check-circle"></i> Approve
                                    </button>
                                    <button class="btn btn-sm btn-danger" onclick="rejectReview({{ review.id }})">
                                        <i class="bi bi-x-circle"></i> Reject
                                    </button>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <p class="text-center text-muted">No pending reviews from examiner.</p>
                {% endif %}
            </div>
        </div>

        <!-- Customer Financial Status -->
        <div class="card">
            <div class="card-header">
                <i class="bi bi-people"></i> Customer Financial Status
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Customer</th>
                                <th>Period</th>
                                <th>Consumption (kWh)</th>
                                <th>Total Cost</th>
                                <th>Paid</th>
                                <th>Balance</th>
                                <th>Due Date</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for record in financial_records %}
                            <tr>
                                <td>{{ record.user.username }}</td>
                                <td>{{ record.period }}</td>
                                <td>{{ "%.2f"|format(record.total_consumption) }}</td>
                                <td>Ksh {{ "%.2f"|format(record.total_cost) }}</td>
                                <td>Ksh {{ "%.2f"|format(record.total_paid) }}</td>
                                <td>Ksh {{ "%.2f"|format(record.balance) }}</td>
                                <td>{{ record.due_date.strftime('%Y-%m-%d') if record.due_date else 'N/A' }}</td>
                                <td>
                                    <span class="badge {% if record.payment_status == 'paid' %}bg-success{% elif record.payment_status == 'pending' %}bg-warning{% else %}bg-danger{% endif %}">
                                        {{ record.payment_status }}
                                    </span>
                                </td>
                                <td>
                                    <button class="btn btn-sm btn-success" onclick="markAsPaid({{ record.id }})">
                                        <i class="bi bi-check"></i>
                                    </button>
                                    <button class="btn btn-sm btn-danger" onclick="sendReminder({{ record.id }})">
                                        <i class="bi bi-envelope"></i>
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

    <script>
        function markAsPaid(recordId) {
            fetch('/mark_as_paid/' + recordId, {
                method: 'POST'
            }).then(response => response.json())
              .then(data => {
                  alert(data.message);
                  location.reload();
              });
        }

        function sendReminder(recordId) {
            fetch('/send_payment_reminder/' + recordId, {
                method: 'POST'
            }).then(response => response.json())
              .then(data => {
                  alert(data.message);
              });
        }

        function approveReview(reviewId) {
            fetch('/approve_review/' + reviewId, {
                method: 'POST'
            }).then(response => response.json())
              .then(data => {
                  alert(data.message);
                  location.reload();
              });
        }

        function rejectReview(reviewId) {
            fetch('/reject_review/' + reviewId, {
                method: 'POST'
            }).then(response => response.json())
              .then(data => {
                  alert(data.message);
                  location.reload();
              });
        }
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

error_page = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Error - EcoPulse</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css"><style>body{background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif}.error-container{max-width:500px;padding:20px}.card{border:none;border-radius:15px;box-shadow:0 10px 40px rgba(0,0,0,0.3)}.card-header{background:linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);color:white;border-radius:15px 15px 0 0;padding:30px;text-align:center}</style></head><body><div class="error-container"><div class="card"><div class="card-header"><h2><i class="bi bi-exclamation-triangle"></i> Access Denied</h2></div><div class="card-body p-5 text-center"><p class="lead">{{ error }}</p><a href="{{ url_for('dashboard') }}" class="btn btn-primary mt-3">Go to Dashboard</a></div></div></div></body></html>"""


# ===================== ROUTES =====================

@app.route('/')
def index():
    """Home page route"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')
        department = request.form.get('department') if role in ['admin', 'examiner'] else None

        if not username or not email or not password or not role:
            return render_template_string(register_page, error='All fields required')
        if password != confirm_password:
            return render_template_string(register_page, error='Passwords do not match')
        if User.query.filter_by(username=username).first():
            return render_template_string(register_page, error='Username exists')
        if User.query.filter_by(email=email).first():
            return render_template_string(register_page, error='Email registered')

        user = User(username=username, email=email, role=role, department=department)
        user.set_password(password)

        if role in ['admin', 'examiner']:
            user.employee_id = user.generate_employee_id()

        db.session.add(user)
        db.session.flush()

        # Check if settings already exist
        if not UserSettings.query.filter_by(user_id=user.id).first():
            settings = UserSettings(user_id=user.id)
            db.session.add(settings)

        db.session.commit()

        log_system_action(user.id, f"User registered as {role}")

        return redirect(url_for('login'))
    return render_template_string(register_page)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login route"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        selected_role = request.form.get('role')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.role != selected_role:
                return render_template_string(login_page,
                                              error=f'Invalid role selected. You are registered as {user.role}')

            login_user(user)
            log_system_action(user.id, f"User logged in as {user.role}")
            return redirect(url_for('dashboard'))

        return render_template_string(login_page, error='Invalid credentials')
    return render_template_string(login_page)


@app.route('/logout')
@login_required
def logout():
    """User logout route"""
    log_system_action(current_user.id, "User logged out")
    logout_user()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard route - redirects based on role"""
    if current_user.role == 'examiner':
        return redirect(url_for('examiner_dashboard'))
    elif current_user.role == 'admin':
        return redirect(url_for('admin_financial'))

    # Customer dashboard
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    days = request.args.get('days', type=int)

    readings = get_user_readings(current_user.id, days=days, start_date=start_date, end_date=end_date)

    # Generate analytics
    analytics = None
    if readings:
        total_kwh = sum(r.kwh for r in readings)
        avg_kwh = total_kwh / len(readings) if readings else 0
        total_cost = sum(r.kwh * current_user.unit_cost for r in readings)
        total_co2 = total_kwh * 0.385

        analytics = {
            'total_kwh': round(total_kwh, 2),
            'avg_kwh': round(avg_kwh, 2),
            'total_cost': round(total_cost, 2),
            'total_co2': round(total_co2, 2),
            'currency': current_user.currency
        }

    # Generate chart
    chart = generate_consumption_chart(current_user.id)

    # Get reports sent by admin
    reports = Report.query.filter_by(sent_to=current_user.id).order_by(Report.created_at.desc()).limit(5).all()

    # Check if customer has pending submission
    pending_submission = CustomerSubmission.query.filter_by(customer_id=current_user.id, status='pending').first()

    return render_template_string(dashboard_template,
                                  readings=readings,
                                  analytics=analytics,
                                  chart=chart,
                                  reports=reports,
                                  pending_submission=pending_submission,
                                  now=int(datetime.utcnow().timestamp()))


@app.route('/examiner_dashboard')
@login_required
@examiner_required
def examiner_dashboard():
    """Examiner dashboard route"""
    # Get consumption stats
    customers = User.query.filter_by(role='customer').all()
    readings = Reading.query.all()

    # Calculate statistics
    total_customers = len([c for c in customers if c.readings])
    total_consumption = sum(r.kwh for r in readings)
    total_revenue = sum(r.kwh * User.query.get(r.user_id).unit_cost for r in readings)
    total_co2 = sum(r.kwh * 0.385 for r in readings)

    consumption_stats = {
        'total_customers': total_customers,
        'total_consumption': total_consumption,
        'total_revenue': total_revenue,
        'total_co2': total_co2,
        'total_readings': len(readings),
        'reviewed_count': len([r for r in readings if r.is_reviewed]),
        'pending_count': len([r for r in readings if not r.is_reviewed]),
        'approved_count': len([r for r in readings if r.is_approved])
    }

    # Get pending readings
    pending_readings = Reading.query.filter_by(is_reviewed=False).all()
    pending_count = len(pending_readings)

    # Get reviewed but not approved readings
    reviewed_readings = Reading.query.filter_by(is_reviewed=True, is_approved=False).all()

    # Get all readings for the report (for display)
    all_readings = Reading.query.order_by(Reading.created_at.desc()).limit(20).all()

    # Get review history
    review_history = ConsumptionReview.query.filter_by(examiner_id=current_user.id) \
        .order_by(ConsumptionReview.created_at.desc()) \
        .limit(10).all()

    return render_template_string(examiner_template,
                                  consumption_stats=consumption_stats,
                                  pending_readings=pending_readings,
                                  pending_count=pending_count,
                                  reviewed_readings=reviewed_readings,
                                  all_readings=all_readings,
                                  review_history=review_history,
                                  consumption_report=None)


@app.route('/view_consumption_report', methods=['POST'])
@login_required
@examiner_required
def view_consumption_report():
    """Generate and view consumption report"""
    # Generate consumption report
    consumption_report = generate_examiner_consumption_report()

    # Get other data for the template
    customers = User.query.filter_by(role='customer').all()
    readings = Reading.query.all()

    consumption_stats = {
        'total_customers': len([c for c in customers if c.readings]),
        'total_consumption': sum(r.kwh for r in readings),
        'total_revenue': sum(r.kwh * User.query.get(r.user_id).unit_cost for r in readings),
        'total_co2': sum(r.kwh * 0.385 for r in readings),
        'total_readings': len(readings),
        'reviewed_count': len([r for r in readings if r.is_reviewed]),
        'pending_count': len([r for r in readings if not r.is_reviewed]),
        'approved_count': len([r for r in readings if r.is_approved])
    }

    pending_readings = Reading.query.filter_by(is_reviewed=False).all()
    pending_count = len(pending_readings)
    reviewed_readings = Reading.query.filter_by(is_reviewed=True, is_approved=False).all()
    all_readings = Reading.query.order_by(Reading.created_at.desc()).limit(20).all()
    review_history = ConsumptionReview.query.filter_by(examiner_id=current_user.id) \
        .order_by(ConsumptionReview.created_at.desc()) \
        .limit(10).all()

    return render_template_string(examiner_template,
                                  consumption_stats=consumption_stats,
                                  pending_readings=pending_readings,
                                  pending_count=pending_count,
                                  reviewed_readings=reviewed_readings,
                                  all_readings=all_readings,
                                  review_history=review_history,
                                  consumption_report=consumption_report)


@app.route('/review_reading/<int:reading_id>', methods=['POST'])
@login_required
@examiner_required
def review_reading(reading_id):
    """Review a single reading"""
    reading = Reading.query.get(reading_id)
    if reading:
        decision = request.form.get('decision')
        notes = request.form.get('notes')

        reading.is_reviewed = True
        reading.reviewed_by = current_user.id
        reading.reviewed_at = datetime.utcnow()
        reading.review_notes = notes

        if decision == 'approve':
            # Mark as reviewed and ready for admin
            reading.is_approved = False
        else:
            # Reject - needs correction
            reading.is_approved = False

        db.session.commit()

        log_system_action(current_user.id, f"Reviewed reading ID: {reading_id} - {decision}")

    return redirect(url_for('examiner_dashboard'))


@app.route('/send_review_to_admin', methods=['POST'])
@login_required
@examiner_required
def send_review_to_admin():
    """Send consolidated review to admin - includes all readings"""
    # Get all readings (both reviewed and unreviewed)
    all_readings = Reading.query.all()

    if not all_readings:
        return jsonify({'success': False, 'message': 'No readings available to send'})

    # Calculate statistics for all readings
    customers = User.query.filter_by(role='customer').all()
    total_customers = len([c for c in customers if c.readings])
    total_consumption = sum(r.kwh for r in all_readings)
    avg_consumption = total_consumption / total_customers if total_customers > 0 else 0
    peak_consumption = max([r.kwh for r in all_readings]) if all_readings else 0

    # Count readings by status
    reviewed_count = len([r for r in all_readings if r.is_reviewed])
    pending_count = len([r for r in all_readings if not r.is_reviewed])
    approved_count = len([r for r in all_readings if r.is_approved])

    # Create a comprehensive review
    notes = f"""Consumption Review Report - {datetime.utcnow().strftime('%B %Y')}

Summary:
- Total Readings: {len(all_readings)}
- Reviewed Readings: {reviewed_count}
- Pending Review: {pending_count}
- Approved Readings: {approved_count}
- Total Customers: {total_customers}
- Total Consumption: {total_consumption:.2f} kWh
- Average Consumption: {avg_consumption:.2f} kWh
- Peak Consumption: {peak_consumption:.2f} kWh

Please review and approve this consumption report.
"""

    review = ConsumptionReview(
        examiner_id=current_user.id,
        period=datetime.utcnow().strftime('%Y-%m'),
        total_consumption=total_consumption,
        total_customers=total_customers,
        average_consumption=avg_consumption,
        peak_consumption=peak_consumption,
        notes=notes,
        status='pending_review'
    )
    db.session.add(review)
    db.session.commit()

    log_system_action(current_user.id, f"Sent consumption review to admin with {len(all_readings)} readings")

    return jsonify({
        'success': True,
        'message': f'Review sent to admin successfully! ({len(all_readings)} readings, {reviewed_count} reviewed, {pending_count} pending)'
    })


@app.route('/admin_financial')
@login_required
@admin_required
def admin_financial():
    """Admin financial dashboard route"""
    # Generate financial report with safe defaults
    financial = generate_financial_report()

    # If financial is None, create a default structure
    if financial is None:
        financial = {
            'chart': None,
            'total_revenue': 0,
            'total_outstanding': 0,
            'total_collected': 0,
            'payment_rate': 0
        }

    # Get financial records or empty list
    financial_records = FinancialRecord.query.all()
    if not financial_records:
        financial_records = []

    # Get pending reviews from examiner
    pending_reviews = ConsumptionReview.query.filter_by(status='pending_review').all()

    # Get examiner reports
    examiner_reports = Report.query.filter_by(report_type='system_analysis') \
        .order_by(Report.created_at.desc()) \
        .limit(5) \
        .all()
    if not examiner_reports:
        examiner_reports = []

    return render_template_string(admin_financial_template,
                                  financial=financial,
                                  financial_records=financial_records,
                                  examiner_reports=examiner_reports,
                                  pending_reviews=pending_reviews)


@app.route('/approve_review/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def approve_review(review_id):
    """Approve a consumption review"""
    review = ConsumptionReview.query.get(review_id)
    if review:
        review.status = 'approved'
        review.approved_by = current_user.id
        review.approved_at = datetime.utcnow()

        # Mark all readings as approved
        readings = Reading.query.all()
        for reading in readings:
            reading.is_approved = True
            reading.approved_by = current_user.id
            reading.approved_at = datetime.utcnow()

        db.session.commit()

        log_system_action(current_user.id, f"Approved consumption review ID: {review_id}")
        return jsonify({'message': 'Review approved successfully!'})

    return jsonify({'message': 'Review not found'})


@app.route('/reject_review/<int:review_id>', methods=['POST'])
@login_required
@admin_required
def reject_review(review_id):
    """Reject a consumption review"""
    review = ConsumptionReview.query.get(review_id)
    if review:
        review.status = 'rejected'
        db.session.commit()

        log_system_action(current_user.id, f"Rejected consumption review ID: {review_id}")
        return jsonify({'message': 'Review rejected. Please ask examiner to revise.'})

    return jsonify({'message': 'Review not found'})


@app.route('/send_customer_summaries', methods=['POST'])
@login_required
@admin_required
def send_customer_summaries():
    """Send consumption summaries to all customers"""
    customers_sent = send_report_to_customers(current_user.id)

    # Update financial records
    customers = User.query.filter_by(role='customer').all()
    for customer in customers:
        readings = Reading.query.filter_by(user_id=customer.id).all()
        if readings:
            total_kwh = sum(r.kwh for r in readings)
            total_cost = sum(r.kwh * customer.unit_cost for r in readings)

            # Create or update financial record
            period = datetime.utcnow().strftime('%Y-%m')
            record = FinancialRecord.query.filter_by(user_id=customer.id, period=period).first()

            if not record:
                record = FinancialRecord(
                    user_id=customer.id,
                    period=period,
                    total_consumption=total_kwh,
                    total_cost=total_cost,
                    balance=total_cost,
                    due_date=datetime.utcnow() + timedelta(days=30),
                    payment_status='pending'
                )
                db.session.add(record)
            else:
                record.total_consumption = total_kwh
                record.total_cost = total_cost
                record.balance = total_cost - record.total_paid

            db.session.commit()

    return redirect(url_for('admin_financial'))


@app.route('/add_reading', methods=['POST'])
@login_required
def add_reading():
    """Add a new reading"""
    date = request.form.get('date')
    kwh = request.form.get('kwh')
    timestamp_str = request.form.get('timestamp')

    try:
        kwh = float(kwh)
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.utcnow()

        # Calculate cost
        cost = kwh * current_user.unit_cost

        reading = Reading(
            user_id=current_user.id,
            date=date,
            kwh=kwh,
            cost=cost,
            timestamp=timestamp,
            is_reviewed=False,
            is_approved=False
        )
        db.session.add(reading)
        db.session.commit()

        log_system_action(current_user.id, f"Added reading: {kwh} kWh for {date}")

        # Check threshold and send alert
        if kwh > current_user.threshold:
            print(f" Alert: Reading {kwh} kWh exceeds threshold {current_user.threshold}")

    except Exception as e:
        print(f"Error adding reading: {e}")
        db.session.rollback()

    return redirect(url_for('dashboard'))


@app.route('/update_reading/<int:reading_id>', methods=['POST'])
@login_required
def update_reading(reading_id):
    """Update an existing reading"""
    reading = Reading.query.filter_by(id=reading_id, user_id=current_user.id).first()
    if reading:
        reading.date = request.form.get('date')
        reading.kwh = float(request.form.get('kwh'))
        reading.cost = reading.kwh * current_user.unit_cost
        reading.timestamp = datetime.fromisoformat(request.form.get('timestamp'))
        reading.is_reviewed = False  # Reset review status
        reading.is_approved = False
        db.session.commit()
        log_system_action(current_user.id, f"Updated reading ID: {reading_id}")
    return redirect(url_for('dashboard'))


@app.route('/delete_reading/<int:reading_id>', methods=['POST'])
@login_required
def delete_reading(reading_id):
    """Delete a reading"""
    reading = Reading.query.filter_by(id=reading_id, user_id=current_user.id).first()
    if reading:
        db.session.delete(reading)
        db.session.commit()
        log_system_action(current_user.id, f"Deleted reading ID: {reading_id}")
    return redirect(url_for('dashboard'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings route"""
    user_settings = UserSettings.query.filter_by(user_id=current_user.id).first()
    message = None

    if request.method == 'POST':
        current_user.threshold = float(request.form.get('threshold'))
        current_user.currency = request.form.get('currency')
        current_user.unit_cost = float(request.form.get('unit_cost'))
        current_user.alert_email = 'alert_email' in request.form
        db.session.commit()
        message = " Settings Updated!"
        log_system_action(current_user.id, "Updated settings")

    return render_template_string(settings_template, user_settings=user_settings, message=message)


@app.route('/mark_as_paid/<int:record_id>', methods=['POST'])
@login_required
@admin_required
def mark_as_paid(record_id):
    """Mark a financial record as paid"""
    record = FinancialRecord.query.get(record_id)
    if record:
        record.payment_status = 'paid'
        record.total_paid = record.total_cost
        record.balance = 0
        db.session.commit()
        return jsonify({'message': 'Marked as paid successfully'})
    return jsonify({'message': 'Record not found'})


@app.route('/send_payment_reminder/<int:record_id>', methods=['POST'])
@login_required
@admin_required
def send_payment_reminder(record_id):
    """Send payment reminder to customer"""
    record = FinancialRecord.query.get(record_id)
    if record and record.user:
        print(f"📧 Payment reminder sent to {record.user.email} for Ksh {record.balance}")
        return jsonify({'message': 'Reminder sent successfully'})
    return jsonify({'message': 'Error sending reminder'})


@app.route('/view_review/<int:review_id>')
@login_required
def view_review(review_id):
    """View review details"""
    review = ConsumptionReview.query.get(review_id)
    if review:
        return f"<html><body><h1>Review Details</h1><pre>{review}</pre></body></html>"
    return "Review not found", 404


@app.route('/export_csv')
@login_required
def export_csv():
    """Export readings as CSV"""
    readings = Reading.query.filter_by(user_id=current_user.id).all()
    if not readings:
        return "No data", 404

    output = "Month,kWh,Cost,CO2,Status,Timestamp\n"
    for reading in readings:
        co2 = reading.kwh * 0.385
        status = "Approved" if reading.is_approved else "Pending" if not reading.is_reviewed else "Reviewed"
        output += f"{reading.date},{reading.kwh},{reading.cost:.2f},{co2:.2f},{status},{reading.timestamp}\n"

    log_system_action(current_user.id, "Exported data to CSV")

    return send_file(
        io.BytesIO(output.encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"ecopulse_{current_user.username}.csv"
    )


@app.route('/export_pdf')
@login_required
def export_pdf():
    """Export readings as PDF"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        import io as io_lib

        readings = Reading.query.filter_by(user_id=current_user.id).all()
        if not readings:
            return "No data", 404

        buffer = io_lib.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)

        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"EcoPulse Energy Report - {current_user.username}", styles['Title']))
        elements.append(Spacer(1, 20))

        # Summary
        total_kwh = sum(r.kwh for r in readings)
        total_cost = sum(r.kwh * current_user.unit_cost for r in readings)
        approved_count = len([r for r in readings if r.is_approved])
        pending_count = len([r for r in readings if not r.is_reviewed])

        summary_data = [
            ["Metric", "Value"],
            ["Total Consumption", f"{total_kwh:.2f} kWh"],
            ["Total Cost", f"{current_user.currency} {total_cost:.2f}"],
            ["Approved Readings", str(approved_count)],
            ["Pending Review", str(pending_count)],
            ["Number of Readings", str(len(readings))]
        ]

        summary_table = Table(summary_data)
        summary_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey)
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # Readings table
        data = [["Period", "kWh", f"Cost ({current_user.currency})", "CO2", "Status", "Timestamp"]]
        for r in readings:
            co2 = r.kwh * 0.385
            status = "Approved" if r.is_approved else "Pending" if not r.is_reviewed else "Reviewed"
            data.append([
                r.date,
                f"{r.kwh:.2f}",
                f"{r.cost:.2f}",
                f"{co2:.2f}",
                status,
                r.timestamp.strftime("%Y-%m-%d")
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke)
        ]))

        elements.append(table)
        doc.build(elements)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"ecopulse_report_{current_user.username}.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        return f"Error generating PDF: {str(e)}"


def update_database_schema():
    """Check and update database schema if needed"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)

        # Check if readings table exists and has required columns
        if 'readings' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('readings')]

            # Add missing columns if they don't exist
            required_columns = {
                'cost': 'FLOAT DEFAULT 0',
                'is_reviewed': 'BOOLEAN DEFAULT 0',
                'reviewed_by': 'INTEGER',
                'reviewed_at': 'DATETIME',
                'review_notes': 'TEXT',
                'is_approved': 'BOOLEAN DEFAULT 0',
                'approved_by': 'INTEGER',
                'approved_at': 'DATETIME'
            }

            for col_name, col_type in required_columns.items():
                if col_name not in columns:
                    print(f" Adding missing '{col_name}' column to readings table...")
                    with db.engine.connect() as conn:
                        conn.execute(db.text(f"ALTER TABLE readings ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    print(f" '{col_name}' column added successfully!")

        # Check if consumption_reviews table exists
        if 'consumption_reviews' not in inspector.get_table_names():
            print(" Creating consumption_reviews table...")
            # Table will be created by SQLAlchemy when we run db.create_all()

        # Check if customer_submissions table exists
        if 'customer_submissions' not in inspector.get_table_names():
            print(" Creating customer_submissions table...")
            # Table will be created by SQLAlchemy when we run db.create_all()

    except Exception as e:
        print(f"Note: Schema check - {e}")


if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        print(" Database tables created/verified")

        # Update schema if needed
        update_database_schema()

        # Create default admin if not exists
        if not User.query.filter_by(role='admin').first():
            admin = User(
                username='admin',
                email='admin@ecopulse.com',
                role='admin',
                department='Administration'
            )
            admin.set_password('admin123')
            admin.employee_id = admin.generate_employee_id()
            db.session.add(admin)
            db.session.flush()

            # Check if settings already exist
            if not UserSettings.query.filter_by(user_id=admin.id).first():
                settings = UserSettings(user_id=admin.id)
                db.session.add(settings)

            db.session.commit()
            print(" Default admin created (username: admin, password: admin123)")
        else:
            print(" Admin user already exists")

        # Create default examiner if not exists
        if not User.query.filter_by(role='examiner').first():
            examiner = User(
                username='examiner',
                email='examiner@ecopulse.com',
                role='examiner',
                department='Audit'
            )
            examiner.set_password('examiner123')
            examiner.employee_id = examiner.generate_employee_id()
            db.session.add(examiner)
            db.session.flush()

            # Check if settings already exist
            if not UserSettings.query.filter_by(user_id=examiner.id).first():
                settings = UserSettings(user_id=examiner.id)
                db.session.add(settings)

            db.session.commit()
            print(" Default examiner created (username: examiner, password: examiner123)")
        else:
            print(" Examiner user already exists")

        # Create sample customer if not exists
        if not User.query.filter_by(role='customer').first():
            customer = User(
                username='customer',
                email='customer@example.com',
                role='customer'
            )
            customer.set_password('customer123')
            db.session.add(customer)
            db.session.flush()

            # Check if settings already exist
            if not UserSettings.query.filter_by(user_id=customer.id).first():
                settings = UserSettings(user_id=customer.id)
                db.session.add(settings)

            db.session.commit()

            # Add sample readings with cost calculation
            sample_readings = [
                Reading(user_id=customer.id, date='January', kwh=450,
                        cost=450 * 0.12, timestamp=datetime.utcnow() - timedelta(days=150),
                        is_reviewed=True, is_approved=True),
                Reading(user_id=customer.id, date='February', kwh=520,
                        cost=520 * 0.12, timestamp=datetime.utcnow() - timedelta(days=120),
                        is_reviewed=True, is_approved=True),
                Reading(user_id=customer.id, date='March', kwh=480,
                        cost=480 * 0.12, timestamp=datetime.utcnow() - timedelta(days=90),
                        is_reviewed=True, is_approved=False),
                Reading(user_id=customer.id, date='April', kwh=610,
                        cost=610 * 0.12, timestamp=datetime.utcnow() - timedelta(days=60),
                        is_reviewed=False, is_approved=False),
                Reading(user_id=customer.id, date='May', kwh=550,
                        cost=550 * 0.12, timestamp=datetime.utcnow() - timedelta(days=30),
                        is_reviewed=False, is_approved=False),
                Reading(user_id=customer.id, date='June', kwh=580,
                        cost=580 * 0.12, timestamp=datetime.utcnow(),
                        is_reviewed=False, is_approved=False)
            ]

            for reading in sample_readings:
                db.session.add(reading)

            db.session.commit()
            print(" Sample customer created with readings")
        else:
            print(" Customer user already exists")

        # Create sample financial records if none exist
        if not FinancialRecord.query.first():
            customers = User.query.filter_by(role='customer').all()
            for customer in customers:
                readings = Reading.query.filter_by(user_id=customer.id).all()
                if readings:
                    total_kwh = sum(r.kwh for r in readings)
                    total_cost = sum(r.kwh * customer.unit_cost for r in readings)

                    record = FinancialRecord(
                        user_id=customer.id,
                        period=datetime.utcnow().strftime('%Y-%m'),
                        total_consumption=total_kwh,
                        total_cost=total_cost,
                        total_paid=total_cost * 0.9,
                        balance=total_cost * 0.4,
                        due_date=datetime.utcnow() + timedelta(days=15),
                        payment_status='pending'
                    )
                    db.session.add(record)
            db.session.commit()
            print(" Sample financial records created")

    print("\n" + "=" * 70)
    print(" EcoPulse Energy Dashboard with Customer Submissions")
    print("=" * 70)
    print("\n New Features:")
    print("   • Customers can submit their consumption summary to admin")
    print("   • Admin can approve/review/reject customer submissions")
    print("   • Examiner can send reports regardless of review status")
    print("   • Complete workflow from customer to admin")
    print("\n Workflow:")
    print("   1. Customer adds readings")
    print("   2. Customer can submit summary to admin for verification")
    print("   3. Examiner reviews readings and sends reports to admin")
    print("   4. Admin approves/reviews/rejects submissions")
    print("   5. Admin sends approved summaries to customers")
    print("\n Default Logins:")
    print("   Admin:    username: admin,    password: admin123")
    print("   Examiner: username: examiner, password: examiner123")
    print("   Customer: username: customer, password: customer123")
    print("\n Access the application at: http://localhost:5000")
    print("\n" + "=" * 70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)