import os
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'webm', 'm4v'}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
VIDEO_EXTENSIONS = {'mp4', 'mov', 'webm', 'm4v'}

PROFESSIONS = {
    'medical': 'Medical Staff',
    'electrician': 'Electrician',
    'plumber': 'Plumber',
    'hvac': 'HVAC',
    'aircraft': 'Aircraft Mechanic',
    'ironworker': 'Ironworker',
    'automotive': 'Automotive Mechanic',
    'construction': 'Construction',
    'pool': 'Pool / Water Systems',
    'general': 'General Workforce',
}

SPECIALTIES = {
    'medical': ['ER', 'ICU', 'Pediatrics', 'Surgery', 'EMS', 'Diagnostics'],
    'electrician': ['Residential', 'Commercial', 'Industrial', 'Panels', 'Motors', 'Solar'],
    'plumber': ['Residential', 'Commercial', 'Water Heaters', 'Drainage', 'Pumps', 'Gas Lines'],
    'hvac': ['Residential', 'Commercial', 'Refrigeration', 'Controls', 'Install', 'Troubleshooting'],
    'aircraft': ['Airframe', 'Powerplant', 'Avionics', 'Hydraulics', 'Inspection', 'Line Maintenance'],
    'ironworker': ['Structural', 'Rebar', 'Rigging', 'Welding', 'Safety', 'Blueprints'],
    'automotive': ['Diagnostics', 'Electrical', 'Engine', 'Transmission', 'Diesel', 'Brakes'],
    'construction': ['Framing', 'Concrete', 'Roofing', 'Blueprints', 'Safety', 'Equipment'],
    'pool': ['Pumps', 'Plumbing', 'Chemistry', 'Electrical', 'Install', 'Emergency'],
    'general': ['Operations', 'Safety', 'Tools', 'Troubleshooting', 'Training'],
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hyperfocused.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024

db = SQLAlchemy(app)

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', os.getenv('APP_USERNAME', 'admin'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', os.getenv('APP_PASSWORD', 'change-me'))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    profession = db.Column(db.String(80), default='general')
    specialties = db.Column(db.Text, default='')
    notify_urgent_only = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship('Post', backref='author', lazy=True)
    replies = db.relationship('Reply', backref='author', lazy=True)
    notifications = db.relationship('Notification', backref='recipient', lazy=True, cascade='all, delete-orphan')

    def specialty_list(self):
        return [s.strip() for s in (self.specialties or '').split(',') if s.strip()]


class Invite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    invited_name = db.Column(db.String(120))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime)
    used_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    @property
    def is_used(self):
        return self.used_at is not None


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    profession = db.Column(db.String(80), default='general')
    specialty = db.Column(db.String(80), default='General')
    category = db.Column(db.String(80), default='General Help')
    is_urgent = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(30), default='open')
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    replies = db.relationship('Reply', backref='post', lazy=True, cascade='all, delete-orphan')
    attachments = db.relationship('Attachment', backref='post', lazy=True, cascade='all, delete-orphan')


class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attachments = db.relationship('Attachment', backref='reply', lazy=True, cascade='all, delete-orphan')


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    media_type = db.Column(db.String(20), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    reply_id = db.Column(db.Integer, db.ForeignKey('reply.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    post = db.relationship('Post')


def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


@app.context_processor
def inject_globals():
    user = current_user()
    unread_count = 0
    if user:
        unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return {
        'current_user': user,
        'unread_count': unread_count,
        'professions': PROFESSIONS,
        'specialties': SPECIALTIES,
    }


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = current_user()
        if not user or not user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('board'))
        return view(*args, **kwargs)
    return wrapped_view


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def media_type_for(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    if ext in VIDEO_EXTENSIONS:
        return 'video'
    return None


def save_attachments(files, post=None, reply=None):
    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            flash(f'Skipped unsupported file: {file.filename}', 'danger')
            continue
        original = secure_filename(file.filename)
        ext = original.rsplit('.', 1)[1].lower()
        stored = f'{datetime.utcnow().strftime("%Y%m%d%H%M%S")}_{secrets.token_hex(8)}.{ext}'
        file.save(UPLOAD_FOLDER / stored)
        db.session.add(Attachment(filename=stored, original_filename=original, media_type=media_type_for(original), post=post, reply=reply))


def notify_user(user_id, post, message):
    if user_id == post.author_id:
        return
    db.session.add(Notification(user_id=user_id, post_id=post.id, message=message))


def notify_matching_experts(post):
    posters_specialty = (post.specialty or '').lower()
    users = User.query.filter(User.id != post.author_id).all()
    for user in users:
        if user.notify_urgent_only and not post.is_urgent:
            continue
        profession_match = user.profession == post.profession
        specialty_match = not posters_specialty or posters_specialty == 'general' or posters_specialty in [s.lower() for s in user.specialty_list()]
        if profession_match and specialty_match:
            urgency = 'URGENT: ' if post.is_urgent else ''
            notify_user(user.id, post, f'{urgency}New {PROFESSIONS.get(post.profession, post.profession)} question: {post.title}')


def notify_thread_participants(post, replier):
    participant_ids = {post.author_id}
    participant_ids.update(r.author_id for r in post.replies)
    for user_id in participant_ids:
        if user_id != replier.id:
            notify_user(user_id, post, f'{replier.display_name} replied to: {post.title}')


def ensure_admin_user():
    admin = User.query.filter_by(username=ADMIN_USERNAME).first()
    if admin:
        if not admin.profession:
            admin.profession = 'general'
        return
    db.session.add(User(username=ADMIN_USERNAME, display_name='Admin', password_hash=generate_password_hash(ADMIN_PASSWORD), is_admin=True, profession='general', specialties='Operations,Safety,Troubleshooting'))
    db.session.commit()


def ensure_schema_updates():
    # Simple dev-friendly SQLite schema patches so older local databases keep running.
    engine = db.engine
    with engine.connect() as conn:
        user_cols = [row[1] for row in conn.exec_driver_sql('PRAGMA table_info(user)').fetchall()]
        if 'profession' not in user_cols:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN profession VARCHAR(80) DEFAULT 'general'")
        if 'specialties' not in user_cols:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN specialties TEXT DEFAULT ''")
        if 'notify_urgent_only' not in user_cols:
            conn.exec_driver_sql('ALTER TABLE user ADD COLUMN notify_urgent_only BOOLEAN DEFAULT 0')

        post_cols = [row[1] for row in conn.exec_driver_sql('PRAGMA table_info(post)').fetchall()]
        if 'profession' not in post_cols:
            conn.exec_driver_sql("ALTER TABLE post ADD COLUMN profession VARCHAR(80) DEFAULT 'general'")
        if 'specialty' not in post_cols:
            conn.exec_driver_sql("ALTER TABLE post ADD COLUMN specialty VARCHAR(80) DEFAULT 'General'")
        if 'is_urgent' not in post_cols:
            conn.exec_driver_sql('ALTER TABLE post ADD COLUMN is_urgent BOOLEAN DEFAULT 0')
        conn.commit()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('board'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash('Welcome back to Hyperfocused.', 'success')
            return redirect(request.args.get('next') or url_for('board'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/join/<token>', methods=['GET', 'POST'])
def join(token):
    invite = Invite.query.filter_by(token=token).first_or_404()
    if invite.is_used:
        flash('That invite has already been used. Ask the admin for a new invite.', 'danger')
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        display_name = request.form.get('display_name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        profession = request.form.get('profession', 'general')
        selected_specialties = request.form.getlist('specialties')
        if not username or not display_name or not password:
            flash('All fields are required.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('That username is already taken.', 'danger')
        else:
            user = User(username=username, display_name=display_name, password_hash=generate_password_hash(password), profession=profession, specialties=','.join(selected_specialties))
            db.session.add(user)
            db.session.flush()
            invite.used_at = datetime.utcnow()
            invite.used_by_id = user.id
            db.session.commit()
            session['user_id'] = user.id
            flash('Account created. Welcome to Hyperfocused.', 'success')
            return redirect(url_for('board'))
    return render_template('join.html', invite=invite)


@app.route('/')
@login_required
def board():
    user = current_user()
    scope = request.args.get('scope', 'my-field')
    query = Post.query
    if scope == 'my-field' and user.profession:
        query = query.filter(Post.profession == user.profession)
    elif scope in PROFESSIONS:
        query = query.filter(Post.profession == scope)
    posts = query.order_by(Post.is_urgent.desc(), Post.created_at.desc()).all()
    open_posts = Post.query.filter_by(status='open').count()
    solved_posts = Post.query.filter_by(status='solved').count()
    urgent_posts = Post.query.filter_by(is_urgent=True, status='open').count()
    return render_template('board.html', posts=posts, open_posts=open_posts, solved_posts=solved_posts, urgent_posts=urgent_posts, scope=scope)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user()
    if request.method == 'POST':
        user.display_name = request.form.get('display_name', user.display_name).strip() or user.display_name
        user.profession = request.form.get('profession', 'general')
        user.specialties = ','.join(request.form.getlist('specialties'))
        user.notify_urgent_only = bool(request.form.get('notify_urgent_only'))
        db.session.commit()
        flash('Profile updated. You will be notified for matching questions.', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html')


@app.route('/posts/new', methods=['GET', 'POST'])
@login_required
def new_post():
    user = current_user()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        body = request.form.get('body', '').strip()
        profession = request.form.get('profession', user.profession or 'general')
        specialty = request.form.get('specialty', 'General')
        is_urgent = bool(request.form.get('is_urgent'))
        if not title or not body:
            flash('Title and details are required.', 'danger')
        else:
            post = Post(title=title, body=body, profession=profession, specialty=specialty, category=specialty, is_urgent=is_urgent, author=user)
            db.session.add(post)
            db.session.flush()
            save_attachments(request.files.getlist('attachments'), post=post)
            notify_matching_experts(post)
            db.session.commit()
            flash('Help request posted and routed to matching experts.', 'success')
            return redirect(url_for('view_post', post_id=post.id))
    return render_template('post_form.html')


@app.route('/posts/<int:post_id>', methods=['GET', 'POST'])
@login_required
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    user = current_user()
    Notification.query.filter_by(user_id=user.id, post_id=post.id, is_read=False).update({'is_read': True})
    db.session.commit()
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if not body:
            flash('Reply cannot be empty.', 'danger')
        else:
            reply = Reply(body=body, author=user, post=post)
            db.session.add(reply)
            db.session.flush()
            save_attachments(request.files.getlist('attachments'), reply=reply)
            notify_thread_participants(post, user)
            db.session.commit()
            flash('Reply added.', 'success')
            return redirect(url_for('view_post', post_id=post.id))
    return render_template('post_detail.html', post=post)


@app.route('/posts/<int:post_id>/solve', methods=['POST'])
@login_required
def mark_solved(post_id):
    post = Post.query.get_or_404(post_id)
    user = current_user()
    if user.id != post.author_id and not user.is_admin:
        flash('Only the post author or admin can mark this solved.', 'danger')
    else:
        post.status = 'solved'
        db.session.commit()
        flash('Post marked solved.', 'success')
    return redirect(url_for('view_post', post_id=post.id))


@app.route('/notifications')
@login_required
def notifications():
    user = current_user()
    items = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).all()
    return render_template('notifications.html', notifications=items)


@app.route('/notifications/count')
@login_required
def notification_count():
    user = current_user()
    return jsonify({'unread_count': Notification.query.filter_by(user_id=user.id, is_read=False).count()})


@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/admin/invites', methods=['GET', 'POST'])
@login_required
@admin_required
def invites():
    new_invite_url = None
    if request.method == 'POST':
        invited_name = request.form.get('invited_name', '').strip()
        invite = Invite(token=secrets.token_urlsafe(32), invited_name=invited_name, created_by_id=current_user().id)
        db.session.add(invite)
        db.session.commit()
        new_invite_url = url_for('join', token=invite.token, _external=True)
        flash('One-time invite created. Copy it now and send it directly to that worker.', 'success')
    all_invites = Invite.query.order_by(Invite.created_at.desc()).all()
    return render_template('invites.html', invites=all_invites, new_invite_url=new_invite_url)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        ensure_admin_user()
    app.run(debug=True)
