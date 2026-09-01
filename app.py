from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from types import SimpleNamespace
from sqlalchemy import inspect, text
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# Use Render's Postgres if DATABASE_URL is set, otherwise fall back to local SQLite for dev.
database_url = os.environ.get('DATABASE_URL', 'sqlite:///school.db')
# Render provides URLs starting with "postgres://" — convert to the pg8000 driver format
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+pg8000://', 1)
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+pg8000://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['ASSIGNMENT_UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')
os.makedirs(app.config['ASSIGNMENT_UPLOAD_FOLDER'], exist_ok=True)

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    flash('The uploaded file is too large. The maximum file size is 10 MB.', 'error')
    return redirect(request.referrer or url_for('student_assignments'))

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Make datetime available in templates
@app.context_processor
def inject_datetime():
    return dict(datetime=datetime)

@app.after_request
def add_security_headers(response):
    if response.content_type and 'text/html' in response.content_type:
        csp = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "font-src 'self' data:; "
            "form-action 'self'; "
            "upgrade-insecure-requests"
        )
        response.headers['Content-Security-Policy'] = csp

    if response.content_type.startswith('text/html'):
        html = response.get_data(as_text=True)
        script_tag = '<script src="/static/mobile-sidebar.js"></script>'
        if script_tag not in html and '</body>' in html:
            response.set_data(html.replace('</body>', f'{script_tag}</body>'))
    return response

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'teacher', 'student'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=True)

    __mapper_args__ = {
        'polymorphic_identity': 'user',
        'polymorphic_on': role
    }

class Admin(User):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))

    __mapper_args__ = {
        'polymorphic_identity': 'admin',
    }

class Teacher(User):
    __tablename__ = 'teacher'
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    department = db.Column(db.String(50))
    qualification = db.Column(db.String(100))
    teacher_id = db.Column(db.String(20), unique=True, nullable=False)

    __mapper_args__ = {
        'polymorphic_identity': 'teacher',
    }

class Student(User):
    __tablename__ = 'student'
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    parent_name = db.Column(db.String(100))
    parent_phone = db.Column(db.String(20))
    admission_date = db.Column(db.Date, default=datetime.utcnow)
    
    # Relationships
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'))
    student_class = db.relationship('Class', backref='students')

    @property
    def class_assigned(self):
        return self.student_class

    __mapper_args__ = {
        'polymorphic_identity': 'student',
    }

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # e.g., "JSS 1", "SS 2"
    level = db.Column(db.String(20))  # e.g., "Junior Secondary", "Senior Secondary"
    capacity = db.Column(db.Integer, default=40)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    class_assigned = db.relationship('Class', backref='subjects')

    __table_args__ = (
        db.UniqueConstraint('class_id', 'name', name='uq_subject_name_per_class'),
        db.UniqueConstraint('class_id', 'code', name='uq_subject_code_per_class'),
    )

class TeacherSubjectRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    notes = db.Column(db.Text)
    
    teacher = db.relationship('Teacher', backref='subject_requests')
    subject = db.relationship('Subject', backref='teacher_requests')
    class_assigned = db.relationship('Class', backref='teacher_requests')
    reviewer = db.relationship('Admin', backref='reviewed_requests')

class StudentSubjectChoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    selected_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship('Student', backref='selected_subjects')
    subject = db.relationship('Subject', backref='selected_students')
    class_assigned = db.relationship('Class', backref='selected_subjects')

    __table_args__ = (
        db.UniqueConstraint('student_id', 'subject_id', name='uq_student_subject_choice'),
    )

class AcademicSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)  # e.g., "2026/2027"
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Term(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)  # e.g., "First Term", "Second Term"
    session_id = db.Column(db.Integer, db.ForeignKey('academic_session.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    session = db.relationship('AcademicSession', backref='terms')

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_session.id'), nullable=False)
    
    ca_score = db.Column(db.Float, default=0)
    exam_score = db.Column(db.Float, default=0)
    total_score = db.Column(db.Float, default=0)
    grade = db.Column(db.String(5))
    remark = db.Column(db.String(100))
    
    status = db.Column(db.String(20), default='draft')  # 'draft', 'submitted', 'approved', 'rejected'
    submitted_at = db.Column(db.DateTime)
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    student = db.relationship('Student', backref='results')
    subject = db.relationship('Subject', backref='results')
    class_result = db.relationship('Class', backref='results')
    teacher = db.relationship('Teacher', backref='submitted_results')
    term = db.relationship('Term', backref='results')
    session = db.relationship('AcademicSession', backref='results')
    approver = db.relationship('Admin', backref='approved_results')

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'present', 'absent', 'late'
    recorded_by = db.Column(db.Integer, db.ForeignKey('teacher.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref='attendance')
    class_attendance = db.relationship('Class', backref='attendance_records')
    teacher = db.relationship('Teacher', backref='recorded_attendance')

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=False)  # 'Monday', 'Tuesday', etc.
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    class_timetable = db.relationship('Class', backref='timetable_entries')
    subject = db.relationship('Subject', backref='timetable_entries')
    teacher = db.relationship('Teacher', backref='timetable_entries')

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))  # 'student', 'teacher', 'result', etc.
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='activity_logs')

class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))  # 'general', 'academic', 'sports', 'events'
    image_url = db.Column(db.String(500))
    is_published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    
    author = db.relationship('Admin', backref='news_articles')

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.Time)
    location = db.Column(db.String(200))
    category = db.Column(db.String(50))  # 'academic', 'sports', 'cultural', 'meeting'
    image_url = db.Column(db.String(500))
    is_published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    
    author = db.relationship('Admin', backref='events')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50))  # 'news', 'event', 'result', 'general'
    related_id = db.Column(db.Integer)  # ID of related news/event/etc.
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    max_score = db.Column(db.Integer, nullable=False, default=100)
    question_type = db.Column(db.String(20), nullable=False, default='theory')
    questions = db.Column(db.Text, nullable=False, default='[]')
    google_form_url = db.Column(db.String(500))

    class_assigned = db.relationship('Class', backref='assignments')
    subject = db.relationship('Subject', backref='assignments')
    teacher = db.relationship('Teacher', backref='assignments')
    submissions = db.relationship('Submission', backref='assignment', cascade='all, delete-orphan')

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    text_answer = db.Column(db.Text)
    file_path = db.Column(db.String(500))
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    score = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    graded_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default='submitted')
    answers = db.Column(db.Text, nullable=False, default='{}')

    student = db.relationship('Student', backref='assignment_submissions')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/contact', methods=['POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        message = request.form.get('message')
        
        contact_message = ContactMessage(
            name=name,
            email=email,
            phone=phone,
            message=message
        )
        
        db.session.add(contact_message)
        db.session.commit()
        
        flash('Your message has been sent successfully. We will get back to you soon.', 'success')
        return redirect(url_for('index') + '#contact')
    
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact administrator.', 'error')
                return redirect(url_for('login'))
            
            login_user(user)
            
            # Log the login
            log_activity(user.id, 'login', 'User', user.id, f'User {username} logged in')
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_activity(current_user.id, 'logout', 'User', current_user.id, f'User {current_user.username} logged out')
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return redirect(url_for('change_password'))
        
        current_user.password_hash = generate_password_hash(new_password)
        current_user.must_change_password = False
        db.session.commit()
        
        log_activity(current_user.id, 'password_change', 'User', current_user.id, 'User changed password')
        flash('Password changed successfully', 'success')
        
        # Redirect based on role
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student_dashboard'))
    
    return render_template('change_password.html')

# Admin Routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get summary statistics
    total_students = Student.query.filter_by(is_active=True).count()
    total_teachers = Teacher.query.filter_by(is_active=True).count()
    total_classes = Class.query.filter_by(is_active=True).count()
    total_subjects = Subject.query.filter_by(is_active=True).count()
    pending_requests = TeacherSubjectRequest.query.filter_by(status='pending').count()
    pending_results = Result.query.filter_by(status='submitted').count()
    
    current_session = AcademicSession.query.filter_by(is_active=True).first()
    current_term = Term.query.filter_by(is_active=True).first() if current_session else None
    
    # Efficiently count unread notifications
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    unread_count += ContactMessage.query.filter_by(is_read=False).count()
    unread_count += pending_requests + pending_results
    
    return render_template('admin/dashboard.html', 
                         total_students=total_students,
                         total_teachers=total_teachers,
                         total_classes=total_classes,
                         total_subjects=total_subjects,
                         pending_requests=pending_requests,
                         pending_results=pending_results,
                         current_session=current_session,
                         current_term=current_term,
                         unread_count=unread_count)

@app.route('/admin/teacher-requests')
@login_required
def admin_teacher_requests():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    requests = TeacherSubjectRequest.query.order_by(TeacherSubjectRequest.requested_at.desc()).all()
    return render_template('admin/teacher_requests.html', requests=requests)

@app.route('/admin/approve-request/<int:request_id>', methods=['POST'])
@login_required
def approve_request(request_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teaching_request = TeacherSubjectRequest.query.get_or_404(request_id)
    teaching_request.status = 'approved'
    teaching_request.reviewed_at = datetime.utcnow()
    teaching_request.reviewed_by = current_user.id
    
    log_activity(current_user.id, 'request_approve', 'TeacherSubjectRequest', request_id,
               f'Admin approved teaching request for teacher {teaching_request.teacher_id}')
    
    db.session.commit()
    flash('Teaching request has been approved', 'success')
    return redirect(url_for('admin_teacher_requests'))

@app.route('/admin/reject-request/<int:request_id>', methods=['POST'])
@login_required
def reject_request(request_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teaching_request = TeacherSubjectRequest.query.get_or_404(request_id)
    teaching_request.status = 'rejected'
    teaching_request.reviewed_at = datetime.utcnow()
    teaching_request.reviewed_by = current_user.id
    teaching_request.notes = request.form.get('notes', '')
    
    log_activity(current_user.id, 'request_reject', 'TeacherSubjectRequest', request_id,
               f'Admin rejected teaching request for teacher {teaching_request.teacher_id}. Reason: {teaching_request.notes}')
    
    db.session.commit()
    flash('Teaching request has been rejected', 'success')
    return redirect(url_for('admin_teacher_requests'))

# Student Management
@app.route('/admin/students')
@login_required
def admin_students():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    students = Student.query.all()
    classes = Class.query.filter_by(is_active=True).all()
    return render_template('admin/students.html', students=students, classes=classes)

@app.route('/admin/students/print/<int:class_id>')
@login_required
def print_class_students(class_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    class_obj = Class.query.get_or_404(class_id)
    students = Student.query.filter_by(class_id=class_id, is_active=True).order_by(Student.full_name).all()
    
    return render_template('admin/print_students.html', students=students, class_obj=class_obj)

@app.route('/teacher/students/print/<int:class_id>')
@login_required
def teacher_print_class_students(class_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Verify teacher is assigned to this class
    assignment = TeacherSubjectRequest.query.filter_by(
        teacher_id=current_user.id,
        class_id=class_id,
        status='approved'
    ).first()
    
    if not assignment:
        flash('Access denied. You are not assigned to this class.', 'error')
        return redirect(url_for('teacher_classes'))
    
    class_obj = Class.query.get_or_404(class_id)
    students = Student.query.filter_by(class_id=class_id, is_active=True).order_by(Student.full_name).all()
    
    return render_template('admin/print_students.html', students=students, class_obj=class_obj)

@app.route('/admin/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Get manual LIN (Learners Identification Number)
        lin = request.form.get('student_id')
        if not lin:
            flash('Learners Identification Number (LIN) is required', 'error')
            return redirect(url_for('add_student'))
        
        # Check if LIN already exists
        if Student.query.filter_by(student_id=lin).first():
            flash('Learners Identification Number (LIN) already exists', 'error')
            return redirect(url_for('add_student'))
        
        # Generate username
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('add_student'))
        
        # Create student
        student = Student(
            username=username,
            password_hash=generate_password_hash(request.form.get('password', 'temp123')),
            role='student',
            full_name=request.form.get('full_name'),
            student_id=lin,
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            date_of_birth=datetime.strptime(request.form.get('date_of_birth'), '%Y-%m-%d').date() if request.form.get('date_of_birth') else None,
            gender=request.form.get('gender'),
            address=request.form.get('address'),
            parent_name=request.form.get('parent_name'),
            parent_phone=request.form.get('parent_phone'),
            class_id=request.form.get('class_id') if request.form.get('class_id') else None,
            must_change_password=True
        )
        
        db.session.add(student)
        log_activity(current_user.id, 'student_create', 'Student', student.id, f'Admin created student {student.full_name}', commit=False)
        db.session.commit()
        
        flash(f'Student created successfully. Username: {username}, LIN: {lin}', 'success')
        return redirect(url_for('admin_students'))
    
    classes = Class.query.filter_by(is_active=True).all()
    return render_template('admin/add_student.html', classes=classes)

@app.route('/admin/students/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    log_activity(current_user.id, 'student_delete', 'Student', student_id, f'Admin deleted student {student.full_name}')
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted successfully', 'success')
    return redirect(url_for('admin_students'))

@app.route('/admin/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            flash('Username is required', 'error')
            return redirect(url_for('edit_student', student_id=student_id))

        existing_user = User.query.filter(User.username == username, User.id != student.id).first()
        if existing_user:
            flash('Username already exists', 'error')
            return redirect(url_for('edit_student', student_id=student_id))

        new_lin = request.form.get('student_id')
        if new_lin and new_lin != student.student_id:
            if Student.query.filter_by(student_id=new_lin).first():
                flash('Learners Identification Number (LIN) already exists', 'error')
                return redirect(url_for('edit_student', student_id=student_id))
            student.student_id = new_lin
        
        student.username = username
        student.full_name = request.form.get('full_name')
        student.email = request.form.get('email')
        student.phone = request.form.get('phone')
        student.date_of_birth = datetime.strptime(request.form.get('date_of_birth'), '%Y-%m-%d').date() if request.form.get('date_of_birth') else None
        student.gender = request.form.get('gender')
        student.address = request.form.get('address')
        student.parent_name = request.form.get('parent_name')
        student.parent_phone = request.form.get('parent_phone')
        student.class_id = request.form.get('class_id') if request.form.get('class_id') else None
        
        if request.form.get('password'):
            student.password_hash = generate_password_hash(request.form.get('password'))
        
        log_activity(current_user.id, 'student_update', 'Student', student_id, f'Admin updated student {student.full_name}')
        db.session.commit()
        flash('Student updated successfully', 'success')
        return redirect(url_for('admin_students'))
    
    classes = Class.query.filter_by(is_active=True).all()
    return render_template('admin/edit_student.html', student=student, classes=classes)

# Teacher Management
@app.route('/admin/teachers')
@login_required
def admin_teachers():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teachers = Teacher.query.all()
    return render_template('admin/teachers.html', teachers=teachers)

@app.route('/admin/teachers/add', methods=['GET', 'POST'])
@login_required
def add_teacher():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Generate unique teacher ID
        teacher_id = f"TCH{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Generate username
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('add_teacher'))
        
        # Create teacher
        teacher = Teacher(
            username=username,
            password_hash=generate_password_hash(request.form.get('password', 'temp123')),
            role='teacher',
            full_name=request.form.get('full_name'),
            teacher_id=teacher_id,
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            department=request.form.get('department'),
            qualification=request.form.get('qualification'),
            must_change_password=True
        )
        
        db.session.add(teacher)
        log_activity(current_user.id, 'teacher_create', 'Teacher', teacher.id, f'Admin created teacher {teacher.full_name}', commit=False)
        db.session.commit()
        
        flash(f'Teacher created successfully. Username: {username}, Teacher ID: {teacher_id}', 'success')
        return redirect(url_for('admin_teachers'))
    
    return render_template('admin/add_teacher.html')

@app.route('/admin/teachers/<int:teacher_id>/delete', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get_or_404(teacher_id)
    log_activity(current_user.id, 'teacher_delete', 'Teacher', teacher_id, f'Admin deleted teacher {teacher.full_name}')
    db.session.delete(teacher)
    db.session.commit()
    flash('Teacher deleted successfully', 'success')
    return redirect(url_for('admin_teachers'))

@app.route('/admin/teachers/<int:teacher_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_teacher(teacher_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get_or_404(teacher_id)
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            flash('Username is required', 'error')
            return redirect(url_for('edit_teacher', teacher_id=teacher_id))

        existing_user = User.query.filter(User.username == username, User.id != teacher.id).first()
        if existing_user:
            flash('Username already exists', 'error')
            return redirect(url_for('edit_teacher', teacher_id=teacher_id))

        teacher.username = username
        teacher.full_name = request.form.get('full_name')
        teacher.email = request.form.get('email')
        teacher.phone = request.form.get('phone')
        teacher.department = request.form.get('department')
        teacher.qualification = request.form.get('qualification')
        
        if request.form.get('password'):
            teacher.password_hash = generate_password_hash(request.form.get('password'))
        
        log_activity(current_user.id, 'teacher_update', 'Teacher', teacher_id, f'Admin updated teacher {teacher.full_name}')
        db.session.commit()
        flash('Teacher updated successfully', 'success')
        return redirect(url_for('admin_teachers'))
    
    return render_template('admin/edit_teacher.html', teacher=teacher)

# Class Management
@app.route('/admin/classes')
@login_required
def admin_classes():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    classes = Class.query.all()
    return render_template('admin/classes.html', classes=classes)

@app.route('/admin/classes/add', methods=['GET', 'POST'])
@login_required
def add_class():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        if Class.query.filter_by(name=name).first():
            flash('Class name already exists', 'error')
            return redirect(url_for('add_class'))
        
        new_class = Class(
            name=name,
            level=request.form.get('level'),
            capacity=request.form.get('capacity', 40)
        )
        
        db.session.add(new_class)
        log_activity(current_user.id, 'class_create', 'Class', new_class.id, f'Admin created class {new_class.name}', commit=False)
        db.session.commit()
        
        flash('Class created successfully', 'success')
        return redirect(url_for('admin_classes'))
    
    return render_template('admin/add_class.html')

@app.route('/admin/classes/<int:class_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_class(class_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    school_class = Class.query.get_or_404(class_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Class name is required', 'error')
            return redirect(url_for('edit_class', class_id=class_id))

        existing_class = Class.query.filter(Class.id != class_id, Class.name == name).first()
        if existing_class:
            flash('Class name already exists', 'error')
            return redirect(url_for('edit_class', class_id=class_id))

        school_class.name = name
        school_class.level = request.form.get('level')
        school_class.capacity = request.form.get('capacity', school_class.capacity)
        school_class.is_active = 'is_active' in request.form

        log_activity(current_user.id, 'class_update', 'Class', class_id,
                     f'Admin updated class {school_class.name}')
        db.session.commit()

        flash('Class updated successfully', 'success')
        return redirect(url_for('admin_classes'))

    return render_template('admin/edit_class.html', school_class=school_class)

@app.route('/admin/classes/<int:class_id>/delete', methods=['POST'])
@login_required
def delete_class(class_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    school_class = Class.query.get_or_404(class_id)
    log_activity(current_user.id, 'class_delete', 'Class', class_id,
                 f'Admin deleted class {school_class.name}')
    db.session.delete(school_class)
    db.session.commit()

    flash('Class deleted successfully', 'success')
    return redirect(url_for('admin_classes'))

# Subject Management
@app.route('/admin/subjects')
@login_required
def admin_subjects():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    subjects = Subject.query.all()
    return render_template('admin/subjects.html', subjects=subjects)

@app.route('/admin/subjects/add', methods=['GET', 'POST'])
@login_required
def add_subject():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    classes = Class.query.order_by(Class.name).all()

    if request.method == 'GET' and not classes:
        flash('No classes exist yet. Please create a class before adding a subject.', 'error')
        return redirect(url_for('add_class'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        class_id = request.form.get('class_id')

        # Basic validation
        if not name or not code:
            flash('Please provide both subject name and code.', 'error')
            return redirect(url_for('add_subject'))

        try:
            class_id = int(class_id)
        except (TypeError, ValueError):
            flash('Please select a valid class for this subject.', 'error')
            return redirect(url_for('add_subject'))

        if not class_id:
            flash('Please select a class for this subject.', 'error')
            return redirect(url_for('add_subject'))
        
        if Subject.query.filter_by(class_id=class_id, name=name).first():
            flash('This subject name already exists for the selected class.', 'error')
            return redirect(url_for('add_subject'))
        
        if Subject.query.filter_by(class_id=class_id, code=code).first():
            flash('This subject code already exists for the selected class.', 'error')
            return redirect(url_for('add_subject'))
        
        new_subject = Subject(
            class_id=class_id,
            name=name,
            code=code,
            description=request.form.get('description')
        )
        
        try:
            db.session.add(new_subject)
            db.session.flush()

            class_name = Class.query.get(class_id).name if Class.query.get(class_id) else 'Unknown class'
            log_activity(current_user.id, 'subject_create', 'Subject', new_subject.id,
                         f'Admin created subject {new_subject.name} for class {class_name}', commit=False)
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            # Log internally if logger exists; for now flash a user-friendly message
            flash('Unable to create subject due to a database constraint. Please check your inputs.', 'error')
            return redirect(url_for('add_subject'))
        except Exception:
            db.session.rollback()
            flash('An unexpected error occurred while creating the subject.', 'error')
            return redirect(url_for('add_subject'))

        flash('Subject created successfully', 'success')
        return redirect(url_for('admin_subjects'))
    
    return render_template('admin/add_subject.html', classes=classes)


# Edit Subject
@app.route('/admin/subjects/<int:subject_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_subject(subject_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    subject = Subject.query.get_or_404(subject_id)
    classes = Class.query.order_by(Class.name).all()

    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        class_id = request.form.get('class_id')

        if not name or not code:
            flash('Please provide both subject name and code.', 'error')
            return redirect(url_for('edit_subject', subject_id=subject_id))

        try:
            class_id = int(class_id)
        except (TypeError, ValueError):
            flash('Please select a valid class for this subject.', 'error')
            return redirect(url_for('edit_subject', subject_id=subject_id))

        # Check uniqueness constraints excluding current subject
        existing_name = Subject.query.filter(Subject.class_id == class_id, Subject.name == name, Subject.id != subject_id).first()
        if existing_name:
            flash('This subject name already exists for the selected class.', 'error')
            return redirect(url_for('edit_subject', subject_id=subject_id))

        existing_code = Subject.query.filter(Subject.class_id == class_id, Subject.code == code, Subject.id != subject_id).first()
        if existing_code:
            flash('This subject code already exists for the selected class.', 'error')
            return redirect(url_for('edit_subject', subject_id=subject_id))

        subject.name = name
        subject.code = code
        subject.class_id = class_id
        subject.description = request.form.get('description')
        subject.is_active = 'is_active' in request.form

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Unable to update subject due to a database constraint.', 'error')
            return redirect(url_for('edit_subject', subject_id=subject_id))
        except Exception:
            db.session.rollback()
            flash('An unexpected error occurred while updating the subject.', 'error')
            return redirect(url_for('edit_subject', subject_id=subject_id))

        flash('Subject updated successfully', 'success')
        return redirect(url_for('admin_subjects'))

    return render_template('admin/edit_subject.html', subject=subject, classes=classes)


@app.route('/admin/subjects/<int:subject_id>/delete', methods=['POST'])
@login_required
def delete_subject(subject_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    subject = Subject.query.get_or_404(subject_id)
    try:
        db.session.delete(subject)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Unable to delete subject.', 'error')
        return redirect(url_for('admin_subjects'))

    flash('Subject deleted successfully', 'success')
    return redirect(url_for('admin_subjects'))

# Student Routes
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    student = Student.query.get(current_user.id)
    if not student:
        flash('Student record not found', 'error')
        return redirect(url_for('index'))
    
    # Get student's academic information
    subjects_count = db.session.query(Result.subject_id).filter_by(student_id=student.id).distinct().count()
    recent_results = Result.query.filter_by(student_id=student.id).order_by(Result.created_at.desc()).limit(5).all()
    
    current_session = AcademicSession.query.filter_by(is_active=True).first()
    current_term = Term.query.filter_by(is_active=True).first() if current_session else None
    
    # Efficiently count unread notifications
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    return render_template('student/dashboard.html',
                         student=student,
                         subjects_count=subjects_count,
                         recent_results=recent_results,
                         current_session=current_session,
                         current_term=current_term,
                         unread_count=unread_count)

# Teacher Routes
@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    if not teacher:
        flash('Teacher record not found', 'error')
        return redirect(url_for('index'))
    
    # Get teacher's information
    approved_assignments = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id, 
        status='approved'
    ).all()
    
    pending_requests = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id,
        status='pending'
    ).count()
    
    rejected_requests = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id,
        status='rejected'
    ).count()
    
    current_session = AcademicSession.query.filter_by(is_active=True).first()
    current_term = Term.query.filter_by(is_active=True).first() if current_session else None
    
    # Efficiently count unread notifications
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    return render_template('teacher/dashboard.html',
                         teacher=teacher,
                         approved_assignments=approved_assignments,
                         pending_requests=pending_requests,
                         rejected_requests=rejected_requests,
                         current_session=current_session,
                         current_term=current_term,
                         unread_count=unread_count)

@app.route('/teacher/requests')
@login_required
def teacher_requests():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    requests = TeacherSubjectRequest.query.filter_by(teacher_id=teacher.id).order_by(TeacherSubjectRequest.requested_at.desc()).all()
    
    return render_template('teacher/requests.html', teacher=teacher, requests=requests)

@app.route('/teacher/submit-request', methods=['GET', 'POST'])
@login_required
def submit_teaching_request():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    teacher = Teacher.query.get(current_user.id)
    if not teacher:
        flash('Teacher profile not found. Please contact the administrator.', 'error')
        return redirect(url_for('index'))

    subjects = Subject.query.filter_by(is_active=True).all()
    classes = Class.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        try:
            class_id = int(request.form.get('class_id'))
        except (TypeError, ValueError):
            flash('Please select a valid class before submitting your request.', 'error')
            return redirect(url_for('teacher_requests'))

        school_class = Class.query.get(class_id)
        if not school_class:
            flash('The selected class could not be found.', 'error')
            return redirect(url_for('teacher_requests'))

        submitted_subject_ids = request.form.getlist('subject_ids')
        if not submitted_subject_ids:
            submitted_subject_ids = [request.form.get('subject_id')] if request.form.get('subject_id') else []

        valid_subject_ids = []
        for raw_subject_id in submitted_subject_ids:
            try:
                subject_id = int(raw_subject_id)
            except (TypeError, ValueError):
                continue
            subject = Subject.query.get(subject_id)
            if subject and subject.is_active:
                valid_subject_ids.append(subject_id)

        if not valid_subject_ids:
            flash('Please select at least one valid subject before submitting your request.', 'error')
            return redirect(url_for('teacher_requests'))

        created_count = 0
        for subject_id in valid_subject_ids:
            subject = Subject.query.get(subject_id)
            if not subject:
                continue

            existing_request = TeacherSubjectRequest.query.filter_by(
                teacher_id=teacher.id,
                subject_id=subject_id,
                class_id=class_id
            ).first()

            if existing_request:
                if existing_request.status == 'rejected':
                    existing_request.status = 'pending'
                    existing_request.requested_at = datetime.utcnow()
                    log_activity(teacher.id, 'request_resubmit', 'TeacherSubjectRequest', existing_request.id,
                                 f'Teacher resubmitted request for subject {subject_id} and class {class_id}')
                continue

            new_request = TeacherSubjectRequest(
                teacher_id=teacher.id,
                subject_id=subject_id,
                class_id=class_id,
                status='pending'
            )
            db.session.add(new_request)
            created_count += 1
            log_activity(teacher.id, 'request_create', 'TeacherSubjectRequest', new_request.id,
                         f'Teacher submitted request for subject {subject_id} and class {class_id}')

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Unable to submit request. Please contact the administrator.', 'error')
            return redirect(url_for('teacher_requests'))

        if created_count > 0:
            flash(f'Your teaching request for {created_count} subject(s) has been submitted for approval', 'success')
        else:
            flash('All selected subject requests were already submitted.', 'warning')
        return redirect(url_for('teacher_requests'))

    return render_template('teacher/submit_request.html', teacher=teacher, subjects=subjects, classes=classes)

ALLOWED_ASSIGNMENT_FILES = {
    'pdf': {'application/pdf'},
    'doc': {'application/msword', 'application/octet-stream'},
    'docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/zip', 'application/octet-stream'},
    'jpg': {'image/jpeg'},
    'jpeg': {'image/jpeg'},
    'png': {'image/png'}
}

def get_assignment_file(upload):
    if not upload or not upload.filename:
        return None, None
    filename = secure_filename(upload.filename)
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if extension not in ALLOWED_ASSIGNMENT_FILES or upload.mimetype not in ALLOWED_ASSIGNMENT_FILES[extension]:
        return None, 'Only PDF, DOC, DOCX, JPG, and PNG files are allowed.'
    upload.stream.seek(0)
    header = upload.stream.read(12)
    upload.stream.seek(0)
    valid_header = (
        (extension == 'pdf' and header.startswith(b'%PDF')) or
        (extension in {'jpg', 'jpeg'} and header.startswith(b'\xff\xd8\xff')) or
        (extension == 'png' and header.startswith(b'\x89PNG\r\n\x1a\n')) or
        (extension in {'doc', 'docx'} and (header.startswith(b'PK') or header.startswith(b'\xd0\xcf\x11\xe0')))
    )
    if not valid_header:
        return None, 'The uploaded file content does not match its file type.'
    return upload, None

def teacher_has_assignment_access(teacher_id, class_id, subject_id):
    return TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher_id, class_id=class_id, subject_id=subject_id, status='approved'
    ).first() is not None

def parse_assignment_questions(form):
    question_type = form.get('question_type', 'theory')
    if question_type not in {'theory', 'multiple_choice'}:
        return None, 'Choose either theory or multiple-choice questions.'
    try:
        questions = json.loads(form.get('questions_json', '[]'))
    except json.JSONDecodeError:
        return None, 'Please enter valid assignment questions.'
    if not isinstance(questions, list) or not questions:
        return None, 'Add at least one question.'
    cleaned = []
    for question in questions:
        text = str(question.get('text', '')).strip()
        options = [str(option).strip() for option in question.get('options', []) if str(option).strip()]
        answer = str(question.get('answer', '')).strip()
        if not text:
            return None, 'Every question needs text.'
        if question_type == 'multiple_choice' and (len(options) < 2 or answer not in options):
            return None, 'Each multiple-choice question needs options and a valid correct answer.'
        cleaned.append({'text': text, 'options': options if question_type == 'multiple_choice' else [], 'answer': answer if question_type == 'multiple_choice' else ''})
    return {'type': question_type, 'questions': cleaned}, None

@app.route('/teacher/assignments')
@login_required
def teacher_assignments():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    assignments = Assignment.query.filter_by(teacher_id=current_user.id).order_by(Assignment.due_date.asc()).all()
    return render_template('teacher/assignments.html', assignments=assignments)

@app.route('/teacher/assignments/add', methods=['GET', 'POST'])
@login_required
def add_assignment():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    approved_assignments = TeacherSubjectRequest.query.filter_by(teacher_id=current_user.id, status='approved').all()
    if request.method == 'POST':
        try:
            due_date = datetime.strptime(request.form.get('due_date', ''), '%Y-%m-%dT%H:%M')
            max_score = int(request.form.get('max_score', '100'))
            class_id = int(request.form.get('class_id'))
            subject_id = int(request.form.get('subject_id'))
        except (TypeError, ValueError):
            flash('Please provide valid class, subject, due date, and score values.', 'error')
            return redirect(url_for('add_assignment'))
        if max_score < 1 or not teacher_has_assignment_access(current_user.id, class_id, subject_id):
            flash('You can only assign approved subjects to approved classes, with a valid maximum score.', 'error')
            return redirect(url_for('add_assignment'))
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        if not title or not description:
            flash('Title and description are required.', 'error')
            return redirect(url_for('add_assignment'))
        question_data, question_error = parse_assignment_questions(request.form)
        if question_error:
            flash(question_error, 'error')
            return redirect(url_for('add_assignment'))
        google_form_url = request.form.get('google_form_url', '').strip()
        assignment = Assignment(title=title, description=description, class_id=class_id, subject_id=subject_id,
                                teacher_id=current_user.id, due_date=due_date, max_score=max_score,
                                question_type=question_data['type'], questions=json.dumps(question_data['questions']),
                                google_form_url=google_form_url or None)
        db.session.add(assignment)
        db.session.commit()
        flash('Assignment created successfully.', 'success')
        return redirect(url_for('teacher_assignments'))
    return render_template('teacher/add_assignment.html', approved_assignments=approved_assignments)

@app.route('/teacher/assignments/<int:assignment_id>')
@login_required
def teacher_assignment_submissions(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    assignment = Assignment.query.filter_by(id=assignment_id, teacher_id=current_user.id).first_or_404()
    submissions = Submission.query.filter_by(assignment_id=assignment.id).order_by(Submission.submitted_at.desc()).all()
    return render_template('teacher/assignment_submissions.html', assignment=assignment, submissions=submissions)

@app.route('/teacher/submissions/<int:submission_id>/grade', methods=['POST'])
@login_required
def grade_submission(submission_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    submission = Submission.query.get_or_404(submission_id)
    if submission.assignment.teacher_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('teacher_assignments'))
    try:
        score = int(request.form.get('score', ''))
    except ValueError:
        flash('Score must be a whole number.', 'error')
        return redirect(url_for('teacher_assignment_submissions', assignment_id=submission.assignment_id))
    if score < 0 or score > submission.assignment.max_score:
        flash(f'Score must be between 0 and {submission.assignment.max_score}.', 'error')
        return redirect(url_for('teacher_assignment_submissions', assignment_id=submission.assignment_id))
    submission.score = score
    submission.feedback = request.form.get('feedback', '').strip()
    submission.graded_at = datetime.utcnow()
    submission.status = 'graded'
    db.session.commit()
    flash('Submission graded successfully.', 'success')
    return redirect(url_for('teacher_assignment_submissions', assignment_id=submission.assignment_id))

@app.route('/teacher/assignments/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_assignment(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    assignment = Assignment.query.filter_by(id=assignment_id, teacher_id=current_user.id).first_or_404()
    if assignment.submissions:
        flash('Assignments with submissions cannot be edited.', 'error')
        return redirect(url_for('teacher_assignment_submissions', assignment_id=assignment.id))
    if request.method == 'POST':
        try:
            assignment.due_date = datetime.strptime(request.form.get('due_date', ''), '%Y-%m-%dT%H:%M')
            assignment.max_score = int(request.form.get('max_score', '100'))
        except (TypeError, ValueError):
            flash('Please provide a valid due date and maximum score.', 'error')
            return redirect(url_for('edit_assignment', assignment_id=assignment.id))
        assignment.title = request.form.get('title', '').strip()
        assignment.description = request.form.get('description', '').strip()
        if not assignment.title or not assignment.description or assignment.max_score < 1:
            flash('Title, instructions, and a valid maximum score are required.', 'error')
            return redirect(url_for('edit_assignment', assignment_id=assignment.id))
        db.session.commit()
        flash('Assignment updated successfully.', 'success')
        return redirect(url_for('teacher_assignments'))
    return render_template('teacher/edit_assignment.html', assignment=assignment)

@app.route('/teacher/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    assignment = Assignment.query.filter_by(id=assignment_id, teacher_id=current_user.id).first_or_404()
    if assignment.submissions:
        flash('Assignments with submissions cannot be deleted.', 'error')
        return redirect(url_for('teacher_assignment_submissions', assignment_id=assignment.id))
    db.session.delete(assignment)
    db.session.commit()
    flash('Assignment deleted successfully.', 'success')
    return redirect(url_for('teacher_assignments'))

@app.route('/student/assignments')
@login_required
def student_assignments():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    student = Student.query.get_or_404(current_user.id)
    assignments = Assignment.query.filter_by(class_id=student.class_id).order_by(Assignment.due_date.asc()).all()
    return render_template('student/assignments.html', assignments=assignments, student=student, now=datetime.utcnow())

@app.route('/student/assignments/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def student_assignment_detail(assignment_id):
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    student = Student.query.get_or_404(current_user.id)
    assignment = Assignment.query.filter_by(id=assignment_id, class_id=student.class_id).first_or_404()
    submission = Submission.query.filter_by(assignment_id=assignment.id, student_id=student.id).first()
    questions = json.loads(assignment.questions or '[]')
    if request.method == 'POST':
        if submission and submission.status == 'graded':
            flash('This submission has already been graded and cannot be resubmitted.', 'error')
            return redirect(url_for('student_assignment_detail', assignment_id=assignment.id))
        text_answer = request.form.get('text_answer', '').strip()
        answers = {str(index): request.form.get(f'answer_{index}', '') for index in range(len(questions))}
        upload, file_error = get_assignment_file(request.files.get('file'))
        if file_error:
            flash(file_error, 'error')
            return redirect(url_for('student_assignment_detail', assignment_id=assignment.id))
        if assignment.question_type == 'multiple_choice' and not any(answers.values()) and not upload:
            flash('Answer at least one question or attach a file.', 'error')
            return redirect(url_for('student_assignment_detail', assignment_id=assignment.id))
        if assignment.question_type == 'theory' and not text_answer and not upload:
            flash('Submit a text answer, a file, or both.', 'error')
            return redirect(url_for('student_assignment_detail', assignment_id=assignment.id))
        if not submission:
            submission = Submission(assignment_id=assignment.id, student_id=student.id)
            db.session.add(submission)
        if upload:
            stored_name = f'{student.id}_{assignment.id}_{datetime.utcnow().timestamp()}_{secure_filename(upload.filename)}'
            upload.save(os.path.join(app.config['ASSIGNMENT_UPLOAD_FOLDER'], stored_name))
            submission.file_path = stored_name
        submission.text_answer = text_answer or None
        submission.answers = json.dumps(answers)
        submission.submitted_at = datetime.utcnow()
        submission.status = 'late' if submission.submitted_at > assignment.due_date else 'submitted'
        if assignment.question_type == 'multiple_choice':
            correct = sum(answers.get(str(index)) == question.get('answer') for index, question in enumerate(questions))
            submission.score = round((correct / len(questions)) * assignment.max_score)
            submission.status = 'graded'
            submission.graded_at = datetime.utcnow()
            submission.feedback = f'Automatically graded: {correct} of {len(questions)} correct.'
        db.session.commit()
        flash('Assignment submitted successfully.', 'success')
        return redirect(url_for('student_assignment_detail', assignment_id=assignment.id))
    return render_template('student/assignment_detail.html', assignment=assignment, submission=submission, questions=questions, now=datetime.utcnow())

@app.route('/assignment-files/<path:filename>')
@login_required
def assignment_file(filename):
    submission = Submission.query.filter_by(file_path=filename).first_or_404()
    if current_user.role == 'teacher' and submission.assignment.teacher_id != current_user.id:
        return redirect(url_for('index'))
    if current_user.role == 'student' and submission.student_id != current_user.id:
        return redirect(url_for('index'))
    return send_from_directory(app.config['ASSIGNMENT_UPLOAD_FOLDER'], filename, as_attachment=True)

# Results Management - Teachers can enter results for their assigned classes
@app.route('/teacher/results')
@login_required
def teacher_results():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    approved_assignments = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id, 
        status='approved'
    ).all()
    
    return render_template('teacher/results.html', teacher=teacher, approved_assignments=approved_assignments)

@app.route('/teacher/enter-results/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def enter_results(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    assignment = TeacherSubjectRequest.query.get_or_404(assignment_id)
    
    # Verify this assignment belongs to the teacher
    if assignment.teacher_id != teacher.id:
        flash('Access denied', 'error')
        return redirect(url_for('teacher_results'))
    
    if request.method == 'POST':
        current_session = AcademicSession.query.filter_by(is_active=True).first()
        current_term = Term.query.filter_by(is_active=True).first()
        
        if not current_session or not current_term:
            flash('No active academic session or term configured', 'error')
            return redirect(url_for('teacher_results'))
        
        # Get students in the class
        students = Student.query.filter_by(class_id=assignment.class_id).all()
        
        for student in students:
            ca_score = request.form.get(f'ca_{student.id}', 0)
            exam_score = request.form.get(f'exam_{student.id}', 0)
            
            try:
                ca_score = float(ca_score)
                exam_score = float(exam_score)
                total_score = ca_score + exam_score
                grade = calculate_grade(total_score)
                remark = calculate_remark(grade)
                
                # Check if result already exists
                existing_result = Result.query.filter_by(
                    student_id=student.id,
                    subject_id=assignment.subject_id,
                    class_id=assignment.class_id,
                    term_id=current_term.id,
                    session_id=current_session.id
                ).first()
                
                if existing_result:
                    # Update existing result
                    existing_result.ca_score = ca_score
                    existing_result.exam_score = exam_score
                    existing_result.total_score = total_score
                    existing_result.grade = grade
                    existing_result.remark = remark
                    existing_result.status = 'draft'
                    existing_result.updated_at = datetime.utcnow()
                else:
                    # Create new result
                    new_result = Result(
                        student_id=student.id,
                        subject_id=assignment.subject_id,
                        class_id=assignment.class_id,
                        teacher_id=teacher.id,
                        term_id=current_term.id,
                        session_id=current_session.id,
                        ca_score=ca_score,
                        exam_score=exam_score,
                        total_score=total_score,
                        grade=grade,
                        remark=remark,
                        status='draft'
                    )
                    db.session.add(new_result)
                
            except ValueError:
                flash(f'Invalid score for student {student.full_name}', 'error')
                return redirect(url_for('enter_results', assignment_id=assignment_id))
        
        log_activity(teacher.id, 'results_draft', 'Result', assignment_id, 
                   f'Teacher saved draft results for {assignment.subject.name} in {assignment.class_assigned.name}')
        db.session.commit()
        flash('Results saved as draft', 'success')
        return redirect(url_for('teacher_results'))
    
    students = Student.query.filter_by(class_id=assignment.class_id).all()
    return render_template('teacher/enter_results.html', teacher=teacher, assignment=assignment, students=students)

@app.route('/teacher/submit-results/<int:assignment_id>', methods=['POST'])
@login_required
def submit_results(assignment_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    assignment = TeacherSubjectRequest.query.get_or_404(assignment_id)
    
    if assignment.teacher_id != teacher.id:
        flash('Access denied', 'error')
        return redirect(url_for('teacher_results'))
    
    current_session = AcademicSession.query.filter_by(is_active=True).first()
    current_term = Term.query.filter_by(is_active=True).first()
    
    # Submit all draft results for this assignment
    results = Result.query.filter_by(
        subject_id=assignment.subject_id,
        class_id=assignment.class_id,
        term_id=current_term.id if current_term else None,
        session_id=current_session.id if current_session else None,
        status='draft'
    ).all()
    
    for result in results:
        result.status = 'submitted'
        result.submitted_at = datetime.utcnow()
    
    log_activity(teacher.id, 'results_submit', 'Result', assignment_id,
               f'Teacher submitted results for {assignment.subject.name} in {assignment.class_assigned.name}')
    db.session.commit()
    flash('Results submitted for approval', 'success')
    return redirect(url_for('teacher_results'))

# Results Management - Admin can approve/reject results
@app.route('/admin/results')
@login_required
def admin_results():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    pending_results = Result.query.filter_by(status='submitted').all()
    return render_template('admin/results.html', pending_results=pending_results)

@app.route('/admin/approve-result/<int:result_id>', methods=['POST'])
@login_required
def approve_result(result_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    result = Result.query.get_or_404(result_id)
    result.status = 'approved'
    result.approved_at = datetime.utcnow()
    result.approved_by = current_user.id
    
    log_activity(current_user.id, 'result_approve', 'Result', result_id,
               f'Admin approved result for student {result.student_id}')
    db.session.commit()
    flash('Result approved successfully', 'success')
    return redirect(url_for('admin_results'))

@app.route('/admin/reject-result/<int:result_id>', methods=['POST'])
@login_required
def reject_result(result_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    result = Result.query.get_or_404(result_id)
    result.status = 'rejected'
    
    log_activity(current_user.id, 'result_reject', 'Result', result_id,
               f'Admin rejected result for student {result.student_id}')
    db.session.commit()
    flash('Result rejected', 'success')
    return redirect(url_for('admin_results'))

# Student Results View
@app.route('/student/my-results')
@login_required
def student_results():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    student = Student.query.get(current_user.id)
    if not student:
        flash('Student profile not found. Please contact the administrator.', 'error')
        return redirect(url_for('index'))

    approved_results = Result.query.filter_by(
        student_id=student.id,
        status='approved'
    ).order_by(Result.created_at.desc()).all()

    return render_template('student/results.html', student=student, results=approved_results)

# Teacher Profile
@app.route('/teacher/profile')
@login_required
def teacher_profile():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    return render_template('teacher/profile.html', teacher=teacher)

# Teacher Subjects
@app.route('/teacher/subjects')
@login_required
def teacher_subjects():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    approved_assignments = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id, 
        status='approved'
    ).all()
    
    return render_template('teacher/subjects.html', teacher=teacher, approved_assignments=approved_assignments)

# Teacher Classes
@app.route('/teacher/classes')
@login_required
def teacher_classes():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    teacher = Teacher.query.get(current_user.id)
    approved_requests = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id,
        status='approved'
    ).all()
    class_ids = sorted({request.class_id for request in approved_requests})
    teacher_classes = Class.query.filter(Class.id.in_(class_ids)).order_by(Class.name.asc()).all() if class_ids else []
    teacher_class_counts = {
        school_class.id: Student.query.filter_by(class_id=school_class.id).count()
        for school_class in teacher_classes
    }

    return render_template(
        'teacher/classes.html',
        teacher=teacher,
        teacher_classes=teacher_classes,
        teacher_class_counts=teacher_class_counts,
    )

# Teacher Attendance
@app.route('/teacher/attendance')
@login_required
def teacher_attendance():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    teacher = Teacher.query.get(current_user.id)
    approved_requests = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id,
        status='approved'
    ).all()
    class_ids = sorted({request.class_id for request in approved_requests})
    teacher_classes = Class.query.filter(Class.id.in_(class_ids)).order_by(Class.name.asc()).all() if class_ids else []
    teacher_class_counts = {
        school_class.id: Student.query.filter_by(class_id=school_class.id).count()
        for school_class in teacher_classes
    }

    attendance_history = []
    if teacher_classes:
        attendance_history = Attendance.query.filter(
            Attendance.class_id.in_([school_class.id for school_class in teacher_classes]),
            Attendance.recorded_by == teacher.id,
        ).order_by(Attendance.date.desc(), Attendance.created_at.desc()).all()

    return render_template(
        'teacher/attendance.html',
        teacher=teacher,
        teacher_classes=teacher_classes,
        teacher_class_counts=teacher_class_counts,
        attendance_history=attendance_history,
    )

@app.route('/teacher/attendance/<int:class_id>', methods=['GET', 'POST'])
@login_required
def teacher_record_attendance(class_id):
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    teacher = Teacher.query.get(current_user.id)
    if not teacher:
        flash('Teacher profile not found. Please contact the administrator.', 'error')
        return redirect(url_for('index'))

    approved_request = TeacherSubjectRequest.query.filter_by(
        teacher_id=teacher.id,
        class_id=class_id,
        status='approved'
    ).first()
    if not approved_request:
        flash('You can only record attendance for your approved classes.', 'error')
        return redirect(url_for('teacher_attendance'))

    school_class = Class.query.get_or_404(class_id)
    students = Student.query.filter_by(class_id=class_id).order_by(Student.full_name.asc()).all()

    if request.method == 'POST':
        date_value = request.form.get('date') or datetime.utcnow().strftime('%Y-%m-%d')
        try:
            attendance_date = datetime.strptime(date_value, '%Y-%m-%d').date()
        except ValueError:
            flash('Please enter a valid attendance date.', 'error')
            return redirect(url_for('teacher_record_attendance', class_id=class_id))

        for student in students:
            status = request.form.get(f'status_{student.id}', 'present')
            notes = request.form.get(f'notes_{student.id}', '')

            existing_record = Attendance.query.filter_by(
                student_id=student.id,
                class_id=class_id,
                date=attendance_date,
            ).first()

            if existing_record:
                existing_record.status = status
                existing_record.notes = notes
                existing_record.recorded_by = teacher.id
            else:
                db.session.add(Attendance(
                    student_id=student.id,
                    class_id=class_id,
                    date=attendance_date,
                    status=status,
                    notes=notes,
                    recorded_by=teacher.id,
                ))

        db.session.commit()
        flash(f'Attendance recorded successfully for {school_class.name}.', 'success')
        return redirect(url_for('teacher_attendance'))

    return render_template('teacher/record_attendance.html', teacher=teacher, school_class=school_class, students=students)

# Teacher Timetable
@app.route('/teacher/timetable')
@login_required
def teacher_timetable():
    if current_user.role != 'teacher':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    teacher = Teacher.query.get(current_user.id)
    timetable_entries = Timetable.query.filter_by(teacher_id=teacher.id, is_active=True).all()
    
    return render_template('teacher/timetable.html', teacher=teacher, timetable_entries=timetable_entries)

# Student Profile
@app.route('/student/profile')
@login_required
def student_profile():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    student = Student.query.get(current_user.id)
    return render_template('student/profile.html', student=student)

# Student Subjects
@app.route('/student/subjects')
@login_required
def student_subjects():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    student = Student.query.get(current_user.id)
    selected_subjects = {choice.subject_id for choice in StudentSubjectChoice.query.filter_by(student_id=student.id).all()} if student else set()
    available_subjects = Subject.query.filter_by(class_id=student.class_id, is_active=True).order_by(Subject.name.asc()).all() if student and student.class_id else []
    return render_template('student/subjects.html', student=student, available_subjects=available_subjects, selected_subjects=selected_subjects)

@app.route('/student/subjects/select', methods=['POST'])
@login_required
def student_select_subject():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    student = Student.query.get(current_user.id)
    if not student or not student.class_id:
        flash('You must be assigned to a class before selecting a subject.', 'error')
        return redirect(url_for('student_subjects'))

    raw_subject_ids = request.form.getlist('subject_ids')
    if not raw_subject_ids:
        raw_subject_ids = [request.form.get('subject_id')] if request.form.get('subject_id') else []

    valid_subject_ids = []
    for raw_subject_id in raw_subject_ids:
        try:
            subject_id = int(raw_subject_id)
        except (TypeError, ValueError):
            continue
        subject = Subject.query.filter_by(id=subject_id, class_id=student.class_id, is_active=True).first()
        if subject:
            valid_subject_ids.append(subject.id)

    if not valid_subject_ids:
        flash('You can only choose subjects from your own class.', 'error')
        return redirect(url_for('student_subjects'))

    existing_choices = StudentSubjectChoice.query.filter_by(student_id=student.id).all()
    existing_ids = {choice.subject_id for choice in existing_choices}

    selected_ids = set(valid_subject_ids)
    invalid_cross_class = selected_ids - {subject.id for subject in Subject.query.filter_by(class_id=student.class_id, is_active=True).all()}
    if invalid_cross_class:
        flash('You can only choose subjects from your own class.', 'error')
        return redirect(url_for('student_subjects'))

    for choice in existing_choices:
        if choice.subject_id not in selected_ids:
            db.session.delete(choice)

    for subject_id in sorted(selected_ids):
        if subject_id not in existing_ids:
            db.session.add(StudentSubjectChoice(student_id=student.id, subject_id=subject_id, class_id=student.class_id))

    db.session.commit()
    flash('Your subject selections have been saved.', 'success')
    return redirect(url_for('student_subjects'))

# Student Attendance
@app.route('/student/attendance')
@login_required
def student_attendance():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    student = Student.query.get(current_user.id)
    attendance_records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).limit(50).all()
    
    return render_template('student/attendance.html', student=student, attendance_records=attendance_records)

# Student Timetable
@app.route('/student/timetable')
@login_required
def student_timetable():
    if current_user.role != 'student':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    student = Student.query.get(current_user.id)
    timetable_entries = Timetable.query.filter_by(class_id=student.class_id, is_active=True).all()
    
    return render_template('student/timetable.html', student=student, timetable_entries=timetable_entries)

# Attendance Management - Admin
@app.route('/admin/attendance')
@login_required
def admin_attendance():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    attendance_records = Attendance.query.order_by(Attendance.date.desc()).limit(100).all()
    classes = Class.query.filter_by(is_active=True).all()
    return render_template('admin/attendance.html', attendance_records=attendance_records, classes=classes)

@app.route('/admin/attendance/add', methods=['GET', 'POST'])
@login_required
def add_attendance():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        class_id = request.form.get('class_id')
        date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        
        students = Student.query.filter_by(class_id=class_id).all()
        
        for student in students:
            status = request.form.get(f'status_{student.id}', 'present')
            notes = request.form.get(f'notes_{student.id}', '')
            
            attendance = Attendance(
                student_id=student.id,
                class_id=class_id,
                date=date,
                status=status,
                notes=notes,
                recorded_by=None
            )
            db.session.add(attendance)
        
        log_activity(current_user.id, 'attendance_create', 'Attendance', class_id, f'Admin recorded attendance for class {class_id} on {date}', commit=False)
        db.session.commit()
        flash('Attendance recorded successfully', 'success')
        return redirect(url_for('admin_attendance'))
    
    classes = Class.query.filter_by(is_active=True).all()
    return render_template('admin/add_attendance.html', classes=classes)

# Timetable Management - Admin
@app.route('/admin/timetable')
@login_required
def admin_timetable():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    timetable_entries = Timetable.query.filter_by(is_active=True).all()
    classes = Class.query.filter_by(is_active=True).all()
    subjects = Subject.query.filter_by(is_active=True).all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    
    return render_template('admin/timetable.html', timetable_entries=timetable_entries, classes=classes, subjects=subjects, teachers=teachers)

@app.route('/admin/timetable/add', methods=['GET', 'POST'])
@login_required
def add_timetable():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        new_entry = Timetable(
            class_id=request.form.get('class_id'),
            subject_id=request.form.get('subject_id'),
            teacher_id=request.form.get('teacher_id'),
            day_of_week=request.form.get('day_of_week'),
            start_time=datetime.strptime(request.form.get('start_time'), '%H:%M').time(),
            end_time=datetime.strptime(request.form.get('end_time'), '%H:%M').time(),
            room=request.form.get('room')
        )
        
        db.session.add(new_entry)
        log_activity(current_user.id, 'timetable_create', 'Timetable', new_entry.id, f'Admin added timetable entry', commit=False)
        db.session.commit()
        flash('Timetable entry added successfully', 'success')
        return redirect(url_for('admin_timetable'))
    
    classes = Class.query.filter_by(is_active=True).all()
    subjects = Subject.query.filter_by(is_active=True).all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    
    return render_template('admin/add_timetable.html', classes=classes, subjects=subjects, teachers=teachers)

# Academic Sessions Management - Admin
@app.route('/admin/academic-sessions')
@login_required
def admin_academic_sessions():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    sessions = AcademicSession.query.order_by(AcademicSession.start_date.desc()).all()
    return render_template('admin/academic_sessions.html', sessions=sessions)

@app.route('/admin/academic-sessions/add', methods=['GET', 'POST'])
@login_required
def add_academic_session():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        if AcademicSession.query.filter_by(name=name).first():
            flash('Academic session name already exists', 'error')
            return redirect(url_for('add_academic_session'))
        
        new_session = AcademicSession(
            name=name,
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date(),
            is_active=request.form.get('is_active') == 'on'
        )
        
        db.session.add(new_session)
        log_activity(current_user.id, 'session_create', 'AcademicSession', new_session.id, f'Admin created academic session {name}', commit=False)
        db.session.commit()
        flash('Academic session created successfully', 'success')
        return redirect(url_for('admin_academic_sessions'))
    
    return render_template('admin/add_academic_session.html')

@app.route('/admin/academic-sessions/<int:session_id>/activate', methods=['POST'])
@login_required
def activate_session(session_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    session = AcademicSession.query.get_or_404(session_id)
    
    # Deactivate all sessions
    AcademicSession.query.update({'is_active': False})
    
    # Activate selected session
    session.is_active = True
    
    log_activity(current_user.id, 'session_activate', 'AcademicSession', session_id, f'Admin activated session {session.name}', commit=False)
    db.session.commit()
    flash(f'Academic session {session.name} activated successfully', 'success')
    return redirect(url_for('admin_academic_sessions'))

# Terms Management - Admin
@app.route('/admin/terms')
@login_required
def admin_terms():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    terms = Term.query.order_by(Term.start_date.desc()).all()
    sessions = AcademicSession.query.all()
    return render_template('admin/terms.html', terms=terms, sessions=sessions)

@app.route('/admin/terms/add', methods=['GET', 'POST'])
@login_required
def add_term():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        new_term = Term(
            name=request.form.get('name'),
            session_id=request.form.get('session_id'),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date(),
            is_active=request.form.get('is_active') == 'on'
        )
        
        db.session.add(new_term)
        log_activity(current_user.id, 'term_create', 'Term', new_term.id, f'Admin created term {new_term.name}', commit=False)
        db.session.commit()
        flash('Term created successfully', 'success')
        return redirect(url_for('admin_terms'))
    
    sessions = AcademicSession.query.all()
    return render_template('admin/add_term.html', sessions=sessions)

@app.route('/admin/terms/<int:term_id>/activate', methods=['POST'])
@login_required
def activate_term(term_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    term = Term.query.get_or_404(term_id)
    
    # Deactivate all terms in the same session
    Term.query.filter_by(session_id=term.session_id).update({'is_active': False})
    
    # Activate selected term
    term.is_active = True
    
    log_activity(current_user.id, 'term_activate', 'Term', term_id, f'Admin activated term {term.name}', commit=False)
    db.session.commit()
    flash(f'Term {term.name} activated successfully', 'success')
    return redirect(url_for('admin_terms'))

# Administrators Management - Admin
@app.route('/admin/administrators')
@login_required
def admin_administrators():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    administrators = Admin.query.all()
    return render_template('admin/administrators.html', administrators=administrators)

@app.route('/admin/administrators/add', methods=['GET', 'POST'])
@login_required
def add_administrator():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('add_administrator'))
        
        admin = Admin(
            username=username,
            password_hash=generate_password_hash(request.form.get('password', 'admin123')),
            role='admin',
            full_name=request.form.get('full_name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            must_change_password=True
        )
        
        db.session.add(admin)
        log_activity(current_user.id, 'admin_create', 'Admin', admin.id, f'Admin created administrator {admin.full_name}', commit=False)
        db.session.commit()
        flash('Administrator created successfully', 'success')
        return redirect(url_for('admin_administrators'))
    
    return render_template('admin/add_administrator.html')

@app.route('/admin/administrators/<int:admin_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_administrator(admin_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    administrator = Admin.query.get_or_404(admin_id)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        existing_user = User.query.filter(User.username == username, User.id != administrator.id).first()
        if existing_user:
            flash('Username already exists', 'error')
            return redirect(url_for('edit_administrator', admin_id=admin_id))

        administrator.username = username
        administrator.full_name = request.form.get('full_name', '').strip()
        administrator.email = request.form.get('email', '').strip()
        administrator.phone = request.form.get('phone', '').strip()
        new_password = request.form.get('password', '')
        if new_password:
            administrator.password_hash = generate_password_hash(new_password)
            administrator.must_change_password = True

        log_activity(current_user.id, 'admin_update', 'Admin', admin_id, f'Admin updated administrator {administrator.full_name}')
        db.session.commit()
        flash('Administrator updated successfully', 'success')
        return redirect(url_for('admin_administrators'))

    return render_template('admin/edit_administrator.html', administrator=administrator)

@app.route('/admin/administrators/<int:admin_id>/delete', methods=['POST'])
@login_required
def delete_administrator(admin_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    if admin_id == current_user.id:
        flash('You cannot delete the administrator account you are currently using', 'error')
        return redirect(url_for('admin_administrators'))

    administrator = Admin.query.get_or_404(admin_id)
    log_activity(current_user.id, 'admin_delete', 'Admin', admin_id, f'Admin deleted administrator {administrator.full_name}')
    db.session.delete(administrator)
    db.session.commit()
    flash('Administrator deleted successfully', 'success')
    return redirect(url_for('admin_administrators'))

# Activity Logs - Admin
@app.route('/admin/activity-logs')
@login_required
def admin_activity_logs():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return render_template('admin/activity_logs.html', logs=logs)

# Settings - Admin
@app.route('/admin/settings')
@login_required
def admin_settings():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin/settings.html')

@app.route('/admin/settings/update', methods=['POST'])
@login_required
def update_settings():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Update settings here
    log_activity(current_user.id, 'settings_update', 'Settings', None, 'Admin updated system settings')
    flash('Settings updated successfully', 'success')
    return redirect(url_for('admin_settings'))

# News Management - Admin
@app.route('/admin/news')
@login_required
def admin_news():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    news_articles = News.query.order_by(News.created_at.desc()).all()
    return render_template('admin/news.html', news_articles=news_articles)

@app.route('/admin/news/add', methods=['GET', 'POST'])
@login_required
def add_news():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        news = News(
            title=request.form.get('title'),
            content=request.form.get('content'),
            category=request.form.get('category'),
            image_url=request.form.get('image_url'),
            is_published=request.form.get('is_published') == 'on',
            created_by=current_user.id
        )
        
        db.session.add(news)
        log_activity(current_user.id, 'news_create', 'News', news.id, f'Admin created news: {news.title}')
        
        # If published, send notifications to all users
        if news.is_published:
            news.published_at = datetime.utcnow()
            send_notification_to_all(
                title=f'New News: {news.title}',
                message=f'A new news article has been published: {news.title[:100]}...',
                notification_type='news',
                related_id=news.id
            )
        
        db.session.commit()
        flash('News article created successfully', 'success')
        return redirect(url_for('admin_news'))
    
    return render_template('admin/add_news.html')

@app.route('/admin/news/<int:news_id>/publish', methods=['POST'])
@login_required
def publish_news(news_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    news = News.query.get_or_404(news_id)
    news.is_published = True
    news.published_at = datetime.utcnow()
    
    # Send notifications to all users
    send_notification_to_all(
        title=f'New News: {news.title}',
        message=f'A new news article has been published: {news.title[:100]}...',
        notification_type='news',
        related_id=news.id
    )
    
    log_activity(current_user.id, 'news_publish', 'News', news_id, f'Admin published news: {news.title}', commit=False)
    db.session.commit()
    flash('News article published successfully', 'success')
    return redirect(url_for('admin_news'))

# Events Management - Admin
@app.route('/admin/events')
@login_required
def admin_events():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    events = Event.query.order_by(Event.event_date.desc()).all()
    return render_template('admin/events.html', events=events)

@app.route('/admin/events/add', methods=['GET', 'POST'])
@login_required
def add_event():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        event = Event(
            title=request.form.get('title'),
            description=request.form.get('description'),
            event_date=datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date(),
            event_time=datetime.strptime(request.form.get('event_time'), '%H:%M').time() if request.form.get('event_time') else None,
            location=request.form.get('location'),
            category=request.form.get('category'),
            image_url=request.form.get('image_url'),
            is_published=request.form.get('is_published') == 'on',
            created_by=current_user.id
        )
        
        db.session.add(event)
        log_activity(current_user.id, 'event_create', 'Event', event.id, f'Admin created event: {event.title}')
        
        # If published, send notifications to all users
        if event.is_published:
            event.published_at = datetime.utcnow()
            send_notification_to_all(
                title=f'Upcoming Event: {event.title}',
                message=f'New event announced: {event.title} on {event.event_date.strftime("%B %d, %Y")}',
                notification_type='event',
                related_id=event.id
            )
        
        db.session.commit()
        flash('Event created successfully', 'success')
        return redirect(url_for('admin_events'))
    
    return render_template('admin/add_event.html')

# Contact Messages Management - Admin
@app.route('/admin/messages')
@login_required
def admin_messages():
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template('admin/messages.html', messages=messages)

@app.route('/admin/messages/<int:message_id>/mark-read', methods=['POST'])
@login_required
def mark_message_read(message_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    message = ContactMessage.query.get_or_404(message_id)
    message.is_read = True
    db.session.commit()
    flash('Message marked as read', 'success')
    return redirect(url_for('admin_messages'))

@app.route('/admin/messages/<int:message_id>/delete', methods=['POST'])
@login_required
def delete_message(message_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    message = ContactMessage.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully', 'success')
    return redirect(url_for('admin_messages'))


@app.route('/admin/messages/<int:message_id>')
@login_required
def view_message(message_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    message = ContactMessage.query.get_or_404(message_id)
    # mark as read when viewed
    if not message.is_read:
        message.is_read = True
        db.session.commit()

    return render_template('admin/message_detail.html', message=message)

@app.route('/admin/events/<int:event_id>/publish', methods=['POST'])
@login_required
def publish_event(event_id):
    if current_user.role != 'admin':
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    event = Event.query.get_or_404(event_id)
    event.is_published = True
    event.published_at = datetime.utcnow()
    
    # Send notifications to all users
    send_notification_to_all(
        title=f'Upcoming Event: {event.title}',
        message=f'New event announced: {event.title} on {event.event_date.strftime("%B %d, %Y")}',
        notification_type='event',
        related_id=event.id
    )
    
    log_activity(current_user.id, 'event_publish', 'Event', event_id, f'Admin published event: {event.title}', commit=False)
    db.session.commit()
    flash('Event published successfully', 'success')
    return redirect(url_for('admin_events'))

# Notifications - User
@app.route('/notifications')
@login_required
def user_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    admin_alerts = []
    if current_user.role == 'admin':
        unread_messages = ContactMessage.query.filter_by(is_read=False).count()
        pending_requests = TeacherSubjectRequest.query.filter_by(status='pending').count()
        pending_results = Result.query.filter_by(status='submitted').count()

        if unread_messages:
            admin_alerts.append(SimpleNamespace(
                title='New Contact Messages',
                message=f'{unread_messages} contact message(s) need your attention.',
                notification_type='message',
                created_at=datetime.utcnow(),
                url=url_for('admin_messages')
            ))
        if pending_requests:
            admin_alerts.append(SimpleNamespace(
                title='Teacher Requests Awaiting Approval',
                message=f'{pending_requests} teacher request(s) are waiting for approval.',
                notification_type='request',
                created_at=datetime.utcnow(),
                url=url_for('admin_teacher_requests')
            ))
        if pending_results:
            admin_alerts.append(SimpleNamespace(
                title='Results Awaiting Approval',
                message=f'{pending_results} result submission(s) are waiting for approval.',
                notification_type='result',
                created_at=datetime.utcnow(),
                url=url_for('admin_results')
            ))

    return render_template('notifications.html', notifications=notifications, admin_alerts=admin_alerts)

@app.route('/notifications/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('user_notifications'))
    
    notification.is_read = True
    db.session.commit()
    
    # Redirect to related content if applicable
    if notification.notification_type == 'news' and notification.related_id:
        return redirect(url_for('view_news', news_id=notification.related_id))
    elif notification.notification_type == 'event' and notification.related_id:
        return redirect(url_for('view_event', event_id=notification.related_id))
    
    return redirect(url_for('user_notifications'))

@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('All notifications marked as read', 'success')
    return redirect(url_for('user_notifications'))

# Public News/Events Pages
@app.route('/news')
def view_all_news():
    news_articles = News.query.filter_by(is_published=True).order_by(News.published_at.desc()).all()
    return render_template('public/news.html', news_articles=news_articles)

@app.route('/news/<int:news_id>')
def view_news(news_id):
    news = News.query.get_or_404(news_id)
    if not news.is_published:
        flash('This news article is not published', 'error')
        return redirect(url_for('view_all_news'))
    return render_template('public/news_detail.html', news=news)

@app.route('/events')
def view_all_events():
    events = Event.query.filter_by(is_published=True).order_by(Event.event_date.asc()).all()
    return render_template('public/events.html', events=events)

@app.route('/events/<int:event_id>')
def view_event(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_published:
        flash('This event is not published', 'error')
        return redirect(url_for('view_all_events'))
    return render_template('public/event_detail.html', event=event)

# Helper Functions
def log_activity(user_id, action, entity_type, entity_id, details, commit=True):
    log = ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details
    )
    db.session.add(log)
    if commit:
        db.session.commit()
    else:
        db.session.flush()

def create_notification(user_ids, title, message, notification_type, related_id=None):
    """Create notifications for multiple users"""
    for user_id in user_ids:
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_id=related_id
        )
        db.session.add(notification)
    db.session.commit()

def send_notification_to_all(title, message, notification_type, related_id=None):
    """Send notification to all active users"""
    active_users = User.query.filter_by(is_active=True).all()
    user_ids = [user.id for user in active_users]
    create_notification(user_ids, title, message, notification_type, related_id)

def send_notification_to_role(role, title, message, notification_type, related_id=None):
    """Send notification to users with specific role"""
    users = User.query.filter_by(role=role, is_active=True).all()
    user_ids = [user.id for user in users]
    create_notification(user_ids, title, message, notification_type, related_id)

def calculate_grade(total_score):
    if total_score >= 70:
        return 'A'
    elif total_score >= 60:
        return 'B'
    elif total_score >= 50:
        return 'C'
    elif total_score >= 40:
        return 'D'
    elif total_score >= 30:
        return 'E'
    else:
        return 'F'

def calculate_remark(grade):
    remarks = {
        'A': 'Excellent',
        'B': 'Very Good',
        'C': 'Good',
        'D': 'Credit',
        'E': 'Pass',
        'F': 'Fail'
    }
    return remarks.get(grade, '')

# Initialize Database
def init_db():
    with app.app_context():
        db.create_all()

        table_names = inspect(db.engine).get_table_names()
        if 'student_subject_choice' in table_names:
            if db.engine.dialect.name == 'sqlite':
                index_rows = db.session.execute(text("PRAGMA index_list('student_subject_choice')")).fetchall()
                needs_migration = False
                for index_row in index_rows:
                    index_name = index_row[1]
                    is_unique = bool(index_row[2])
                    if not is_unique:
                        continue
                    index_info_rows = db.session.execute(text(f"PRAGMA index_info('{index_name}')")).fetchall()
                    columns = [info_row[2] for info_row in index_info_rows]
                    if columns == ['student_id']:
                        needs_migration = True
                        break

                if needs_migration:
                    db.session.execute(text('ALTER TABLE student_subject_choice RENAME TO student_subject_choice_old'))
                    db.session.execute(text('''
                        CREATE TABLE student_subject_choice (
                            id INTEGER NOT NULL PRIMARY KEY,
                            student_id INTEGER NOT NULL,
                            subject_id INTEGER NOT NULL,
                            class_id INTEGER NOT NULL,
                            selected_at DATETIME,
                            updated_at DATETIME,
                            FOREIGN KEY (student_id) REFERENCES student (id),
                            FOREIGN KEY (subject_id) REFERENCES subject (id),
                            FOREIGN KEY (class_id) REFERENCES class (id),
                            UNIQUE (student_id, subject_id)
                        )
                    '''))
                    db.session.execute(text('''
                        INSERT INTO student_subject_choice (id, student_id, subject_id, class_id, selected_at, updated_at)
                        SELECT id, student_id, subject_id, class_id, selected_at, updated_at
                        FROM student_subject_choice_old
                    '''))
                    db.session.execute(text('DROP TABLE student_subject_choice_old'))
                    db.session.commit()

        subject_columns = {column['name'] for column in inspect(db.engine).get_columns('subject')}
        if 'class_id' not in subject_columns:
            db.session.execute(text('ALTER TABLE subject ADD COLUMN class_id INTEGER'))
            db.session.commit()

            first_class = Class.query.order_by(Class.id.asc()).first()
            if first_class:
                db.session.execute(
                    text('UPDATE subject SET class_id = :class_id WHERE class_id IS NULL'),
                    {'class_id': first_class.id}
                )

        try:
            db.session.execute(text('ALTER TABLE subject ALTER COLUMN class_id SET NOT NULL'))
        except Exception:
            pass

        assignment_columns = {column['name'] for column in inspect(db.engine).get_columns('assignment')}
        submission_columns = {column['name'] for column in inspect(db.engine).get_columns('submission')}
        upgrades = {
            'assignment': {
                'question_type': "VARCHAR(20) NOT NULL DEFAULT 'theory'",
                'questions': "TEXT NOT NULL DEFAULT '[]'",
                'google_form_url': 'VARCHAR(500)'
            },
            'submission': {'answers': "TEXT NOT NULL DEFAULT '{}'"}
        }
        for table, columns in upgrades.items():
            existing = assignment_columns if table == 'assignment' else submission_columns
            for column, definition in columns.items():
                if column not in existing:
                    db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {definition}'))
        db.session.commit()
        
        # Create default admin accounts if they don't exist
        if Admin.query.count() == 0:
            admins = [
                {
                    'username': 'admin1',
                    'password': 'admin123',
                    'full_name': 'System Administrator',
                    'email': 'admin1@lapaixschools.edu',
                    'phone': '+1234567890'
                },
                {
                    'username': 'admin2', 
                    'password': 'admin123',
                    'full_name': 'Academic Director',
                    'email': 'admin2@lapaixschools.edu',
                    'phone': '+1234567891'
                },
                {
                    'username': 'admin3',
                    'password': 'admin123',
                    'full_name': 'School Principal',
                    'email': 'admin3@lapaixschools.edu',
                    'phone': '+1234567892'
                }
            ]
            
            for admin_data in admins:
                admin = Admin(
                    username=admin_data['username'],
                    password_hash=generate_password_hash(admin_data['password']),
                    role='admin',
                    full_name=admin_data['full_name'],
                    email=admin_data['email'],
                    phone=admin_data['phone'],
                    must_change_password=True
                )
                db.session.add(admin)
            
            # Create default academic session
            current_session = AcademicSession(
                name='2026/2027',
                start_date=datetime(2026, 9, 1).date(),
                end_date=datetime(2027, 7, 31).date(),
                is_active=True
            )
            db.session.add(current_session)
            db.session.commit()  # Commit session first to get the ID
            
            # Create default terms
            terms = [
                {'name': 'First Term', 'start': datetime(2026, 9, 1).date(), 'end': datetime(2026, 12, 15).date()},
                {'name': 'Second Term', 'start': datetime(2027, 1, 8).date(), 'end': datetime(2027, 3, 28).date()},
                {'name': 'Third Term', 'start': datetime(2027, 4, 17).date(), 'end': datetime(2027, 7, 28).date()}
            ]
            
            for i, term_data in enumerate(terms):
                term = Term(
                    name=term_data['name'],
                    session_id=current_session.id,
                    start_date=term_data['start'],
                    end_date=term_data['end'],
                    is_active=(i == 0)  # First term is active by default
                )
                db.session.add(term)
            
            db.session.commit()
            print("Database initialized with default admin accounts and academic data")

# Run once when the module is imported (needed for gunicorn/production, not just `python app.py`)
init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)