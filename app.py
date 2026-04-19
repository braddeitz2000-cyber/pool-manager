import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pool_manager.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
claude = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

# ── Models ──────────────────────────────────────────────────────────────────

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    pool_size = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    jobs = db.relationship('Job', backref='customer', lazy=True, cascade='all, delete-orphan')
    chemical_logs = db.relationship('ChemicalLog', backref='customer', lazy=True, cascade='all, delete-orphan')


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    job_type = db.Column(db.String(100), nullable=False)
    scheduled_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled
    price = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChemicalLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    log_date = db.Column(db.Date, default=datetime.utcnow)
    ph = db.Column(db.Float)
    chlorine = db.Column(db.Float)
    alkalinity = db.Column(db.Float)
    cyanuric_acid = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ── Routes: Dashboard ────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    total_customers = Customer.query.count()
    scheduled_jobs = Job.query.filter_by(status='scheduled').count()
    completed_jobs = Job.query.filter_by(status='completed').count()
    upcoming_jobs = (Job.query
                     .filter_by(status='scheduled')
                     .join(Customer)
                     .order_by(Job.scheduled_date)
                     .limit(5)
                     .all())
    revenue = db.session.query(db.func.sum(Job.price)).filter_by(status='completed').scalar() or 0
    return render_template('dashboard.html',
                           total_customers=total_customers,
                           scheduled_jobs=scheduled_jobs,
                           completed_jobs=completed_jobs,
                           upcoming_jobs=upcoming_jobs,
                           revenue=revenue)


# ── Routes: Customers ────────────────────────────────────────────────────────

@app.route('/customers')
def customers():
    all_customers = Customer.query.order_by(Customer.name).all()
    return render_template('customers.html', customers=all_customers)


@app.route('/customers/new', methods=['GET', 'POST'])
def new_customer():
    if request.method == 'POST':
        c = Customer(
            name=request.form['name'],
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            pool_size=request.form.get('pool_size'),
            notes=request.form.get('notes'),
        )
        db.session.add(c)
        db.session.commit()
        flash('Customer added!', 'success')
        return redirect(url_for('customers'))
    return render_template('customer_form.html', customer=None)


@app.route('/customers/<int:id>', methods=['GET', 'POST'])
def edit_customer(id):
    c = Customer.query.get_or_404(id)
    if request.method == 'POST':
        c.name = request.form['name']
        c.phone = request.form.get('phone')
        c.email = request.form.get('email')
        c.address = request.form.get('address')
        c.pool_size = request.form.get('pool_size')
        c.notes = request.form.get('notes')
        db.session.commit()
        flash('Customer updated!', 'success')
        return redirect(url_for('customers'))
    return render_template('customer_form.html', customer=c)


@app.route('/customers/<int:id>/delete', methods=['POST'])
def delete_customer(id):
    c = Customer.query.get_or_404(id)
    db.session.delete(c)
    db.session.commit()
    flash('Customer deleted.', 'info')
    return redirect(url_for('customers'))


# ── Routes: Jobs ─────────────────────────────────────────────────────────────

@app.route('/jobs')
def jobs():
    all_jobs = (Job.query.join(Customer).order_by(Job.scheduled_date.desc()).all())
    return render_template('jobs.html', jobs=all_jobs)


@app.route('/jobs/new', methods=['GET', 'POST'])
def new_job():
    customers_list = Customer.query.order_by(Customer.name).all()
    if request.method == 'POST':
        date_str = request.form.get('scheduled_date')
        j = Job(
            customer_id=int(request.form['customer_id']),
            job_type=request.form['job_type'],
            scheduled_date=datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None,
            status=request.form.get('status', 'scheduled'),
            price=float(request.form.get('price') or 0),
            notes=request.form.get('notes'),
        )
        db.session.add(j)
        db.session.commit()
        flash('Job scheduled!', 'success')
        return redirect(url_for('jobs'))
    return render_template('job_form.html', job=None, customers=customers_list)


@app.route('/jobs/<int:id>', methods=['GET', 'POST'])
def edit_job(id):
    j = Job.query.get_or_404(id)
    customers_list = Customer.query.order_by(Customer.name).all()
    if request.method == 'POST':
        date_str = request.form.get('scheduled_date')
        j.customer_id = int(request.form['customer_id'])
        j.job_type = request.form['job_type']
        j.scheduled_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        j.status = request.form.get('status', 'scheduled')
        j.price = float(request.form.get('price') or 0)
        j.notes = request.form.get('notes')
        db.session.commit()
        flash('Job updated!', 'success')
        return redirect(url_for('jobs'))
    return render_template('job_form.html', job=j, customers=customers_list)


@app.route('/jobs/<int:id>/delete', methods=['POST'])
def delete_job(id):
    j = Job.query.get_or_404(id)
    db.session.delete(j)
    db.session.commit()
    flash('Job deleted.', 'info')
    return redirect(url_for('jobs'))


# ── Routes: Chemical Logs ────────────────────────────────────────────────────

@app.route('/chemical-logs')
def chemical_logs():
    logs = (ChemicalLog.query.join(Customer).order_by(ChemicalLog.log_date.desc()).all())
    return render_template('chemical_logs.html', logs=logs)


@app.route('/chemical-logs/new', methods=['GET', 'POST'])
def new_chemical_log():
    customers_list = Customer.query.order_by(Customer.name).all()
    if request.method == 'POST':
        date_str = request.form.get('log_date')
        log = ChemicalLog(
            customer_id=int(request.form['customer_id']),
            log_date=datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date(),
            ph=float(request.form.get('ph') or 0),
            chlorine=float(request.form.get('chlorine') or 0),
            alkalinity=float(request.form.get('alkalinity') or 0),
            cyanuric_acid=float(request.form.get('cyanuric_acid') or 0),
            notes=request.form.get('notes'),
        )
        db.session.add(log)
        db.session.commit()
        flash('Chemical log saved!', 'success')
        return redirect(url_for('chemical_logs'))
    return render_template('chemical_log_form.html', log=None, customers=customers_list)


# ── Routes: AI Assistant ─────────────────────────────────────────────────────

@app.route('/assistant')
def assistant():
    return render_template('assistant.html')


@app.route('/assistant/chat', methods=['POST'])
def assistant_chat():
    user_message = request.json.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    # Build context from the database
    total_customers = Customer.query.count()
    scheduled_jobs = Job.query.filter_by(status='scheduled').count()
    completed_jobs = Job.query.filter_by(status='completed').count()
    revenue = db.session.query(db.func.sum(Job.price)).filter_by(status='completed').scalar() or 0
    upcoming = (Job.query.filter_by(status='scheduled')
                .join(Customer)
                .order_by(Job.scheduled_date)
                .limit(5)
                .all())
    upcoming_text = '\n'.join(
        f"  - {j.scheduled_date}: {j.customer.name} ({j.job_type}, ${j.price:.2f})"
        for j in upcoming
    ) or '  None scheduled'

    system_prompt = f"""You are a helpful AI assistant for a pool service company. 
You help the owner manage customers, schedule jobs, track chemical levels, and run the business efficiently.

Current business snapshot:
- Total customers: {total_customers}
- Scheduled jobs: {scheduled_jobs}
- Completed jobs: {completed_jobs}
- Total revenue from completed jobs: ${revenue:.2f}

Upcoming scheduled jobs:
{upcoming_text}

Be concise, practical, and friendly. Give actionable advice about pool chemistry, scheduling, customer management, pricing, and running a pool service business."""

    try:
        response = claude.messages.create(
            model='claude-opus-4-5',
            max_tokens=1024,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_message}]
        )
        return jsonify({'reply': response.content[0].text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Init ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
