# Controllers
# All web routes of the portal: Auth, Admin, Examiner and Student

import os
from datetime import datetime
from functools import wraps

# Matplotlib for the summary charts. The Agg backend draws without opening a window
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask import current_app as app   # App object created in app.py
from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

from .database import db
from .models import User, Course, Exam, Rubric, Slot, Booking, Evaluation, RubricScore

EXAM_TYPES = ['Viva', 'Practical', 'Project Demo', 'Assessment']
EXAM_STATUSES = ['Draft', 'Slot Creation', 'Booking Open', 'Closed', 'Completed']


# Helpers

def login_required(role):
    # Decorator that opens a page only for a logged in user with the given role
    # Other users are redirected to the login page
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get('role') != role:
                flash('Please login to continue', 'warning')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    uid = session.get('user_id')
    return db.session.get(User, uid) if uid else None


def to_date(value):
    # HTML date inputs send dates in year, month, day format
    return datetime.strptime(value, '%Y-%m-%d').date()


# Home

@app.route('/')
def home():
    # Logged in users are sent to their own dashboard
    role = session.get('role')
    if role:
        return redirect(url_for(role + '_dashboard'))
    return redirect(url_for('login'))


# Login, Register and Logout

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash('Invalid email or password', 'danger')
            return redirect(url_for('login'))

        if not user.is_active:
            flash('Your account has been deactivated. Contact admin.', 'danger')
            return redirect(url_for('login'))

        # Examiners cannot log in until the admin approves them
        if user.role == 'examiner' and not user.is_approved:
            flash('Your account is waiting for admin approval', 'warning')
            return redirect(url_for('login'))

        # User ID is kept in the session, not in the URL
        session['user_id'] = user.id
        session['role'] = user.role
        session['name'] = user.name
        return redirect(url_for(user.role + '_dashboard'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()

        # Only students and examiners can register, the admin already exists
        if role not in ('student', 'examiner'):
            flash('Invalid role', 'danger')
            return redirect(url_for('register'))

        if not name or not email or len(password) < 4:
            flash('Fill all fields. Password should be at least 4 characters', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))

        # Passwords are stored as hashes, never as plain text
        user = User(name=name, email=email, phone=phone, role=role,
                    password=generate_password_hash(password))
        if role == 'student':
            user.roll_no = request.form.get('roll_no', '').strip()
            user.is_approved = True
        else:
            user.department = request.form.get('department', '').strip()
            user.is_approved = False

        db.session.add(user)
        db.session.commit()

        if role == 'examiner':
            flash('Registered! You can login once admin approves your account.', 'info')
        else:
            flash('Registered successfully, please login', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('login'))


# Admin Dashboard

@app.route('/admin/dashboard')
@login_required('admin')
def admin_dashboard():
    counts = {
        'courses': Course.query.count(),
        'exams': Exam.query.count(),
        'examiners': User.query.filter_by(role='examiner').count(),
        'students': User.query.filter_by(role='student').count(),
        'slots': Slot.query.count(),
        'bookings': Booking.query.count(),
    }
    pending = User.query.filter_by(role='examiner', is_approved=False).all()
    return render_template('admin/dashboard.html', counts=counts, pending=pending)


# Admin Courses

@app.route('/admin/courses')
@login_required('admin')
def admin_courses():
    return render_template('admin/courses.html', courses=Course.query.all())


@app.route('/admin/course/new', methods=['GET', 'POST'])
@app.route('/admin/course/<int:course_id>/edit', methods=['GET', 'POST'])
@login_required('admin')
def admin_course_form(course_id=None):
    # Same function handles both add and edit
    course = db.session.get(Course, course_id) if course_id else None

    if request.method == 'POST':
        code = request.form['code'].strip()
        # Course code must be unique
        other = Course.query.filter_by(code=code).first()
        if other and (course is None or other.id != course.id):
            flash('Course code already exists', 'danger')
            return redirect(request.url)

        if course is None:
            course = Course()
            db.session.add(course)
        course.code = code
        course.name = request.form['name'].strip()
        course.description = request.form.get('description', '')
        course.status = request.form.get('status', 'Active')
        db.session.commit()
        flash('Course saved', 'success')
        return redirect(url_for('admin_courses'))

    return render_template('admin/course_form.html', course=course)


@app.route('/admin/course/<int:course_id>/delete', methods=['POST'])
@login_required('admin')
def admin_delete_course(course_id):
    course = db.session.get(Course, course_id)
    # Courses whose exams have bookings are kept to preserve history
    for exam in course.exams:
        if Booking.query.filter_by(exam_id=exam.id).first():
            flash('Cannot delete, this course has exams with bookings. Mark it Inactive instead.', 'danger')
            return redirect(url_for('admin_courses'))
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted', 'info')
    return redirect(url_for('admin_courses'))


# Admin Exams

@app.route('/admin/exams')
@login_required('admin')
def admin_exams():
    return render_template('admin/exams.html', exams=Exam.query.all())


@app.route('/admin/exam/new', methods=['GET', 'POST'])
@app.route('/admin/exam/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required('admin')
def admin_exam_form(exam_id=None):
    exam = db.session.get(Exam, exam_id) if exam_id else None
    courses = Course.query.filter_by(status='Active').all()

    if request.method == 'POST':
        try:
            slot_start = to_date(request.form['slot_start'])
            slot_end = to_date(request.form['slot_end'])
            booking_start = to_date(request.form['booking_start'])
            booking_end = to_date(request.form['booking_end'])
        except (KeyError, ValueError):
            flash('Please enter all dates', 'danger')
            return redirect(request.url)

        # Validates that the exam timeline makes sense
        if slot_start > slot_end or booking_start > booking_end:
            flash('Start date must be before end date', 'danger')
            return redirect(request.url)
        if booking_start < slot_start:
            flash('Booking cannot start before slot creation starts', 'danger')
            return redirect(request.url)

        try:
            duration = int(request.form['duration'])
            max_marks = int(request.form['max_marks'])
        except (KeyError, ValueError):
            flash('Duration and max marks must be numbers', 'danger')
            return redirect(request.url)
        if duration < 1 or max_marks < 1:
            flash('Duration and max marks must be at least 1', 'danger')
            return redirect(request.url)
        # Max marks cannot be lower than the total of existing rubric marks
        if exam and max_marks < sum(r.max_marks for r in exam.rubrics):
            flash('Max marks cannot be less than total rubric marks', 'danger')
            return redirect(request.url)

        if exam is None:
            exam = Exam()
            db.session.add(exam)
        exam.course_id = int(request.form['course_id'])
        exam.name = request.form['name'].strip()
        exam.exam_type = request.form['exam_type']
        exam.duration = duration
        exam.max_marks = max_marks
        exam.slot_start = slot_start
        exam.slot_end = slot_end
        exam.booking_start = booking_start
        exam.booking_end = booking_end
        db.session.commit()
        flash('Exam saved', 'success')
        return redirect(url_for('admin_exam_detail', exam_id=exam.id))

    return render_template('admin/exam_form.html', exam=exam, courses=courses, types=EXAM_TYPES)


@app.route('/admin/exam/<int:exam_id>')
@login_required('admin')
def admin_exam_detail(exam_id):
    exam = db.session.get(Exam, exam_id)
    examiners = User.query.filter_by(role='examiner', is_approved=True, is_active=True).all()
    return render_template('admin/exam_detail.html', exam=exam, examiners=examiners,
                           statuses=EXAM_STATUSES)


@app.route('/admin/exam/<int:exam_id>/delete', methods=['POST'])
@login_required('admin')
def admin_delete_exam(exam_id):
    exam = db.session.get(Exam, exam_id)
    if Booking.query.filter_by(exam_id=exam.id).first():
        flash('This exam has bookings, it cannot be deleted. Close it instead.', 'danger')
        return redirect(url_for('admin_exam_detail', exam_id=exam.id))
    db.session.delete(exam)
    db.session.commit()
    flash('Exam deleted', 'info')
    return redirect(url_for('admin_exams'))


# Admin Exam Status and Examiner Assignment

@app.route('/admin/exam/<int:exam_id>/status', methods=['POST'])
@login_required('admin')
def admin_change_status(exam_id):
    # Admin opens and closes slot creation and booking by changing the status
    exam = db.session.get(Exam, exam_id)
    new_status = request.form['status']
    if new_status in EXAM_STATUSES:
        exam.status = new_status
        # Completing an exam also completes its slots and bookings
        if new_status == 'Completed':
            for slot in exam.slots:
                if slot.status != 'Cancelled':
                    slot.status = 'Completed'
                for b in slot.bookings:
                    if b.status == 'Booked':
                        b.status = 'Completed'
        db.session.commit()
        flash('Exam status changed to ' + new_status, 'success')
    return redirect(url_for('admin_exam_detail', exam_id=exam.id))


@app.route('/admin/exam/<int:exam_id>/assign', methods=['POST'])
@login_required('admin')
def admin_assign_examiner(exam_id):
    exam = db.session.get(Exam, exam_id)
    examiner = db.session.get(User, int(request.form['examiner_id']))
    if examiner and examiner not in exam.examiners:
        exam.examiners.append(examiner)
        db.session.commit()
        flash(examiner.name + ' assigned', 'success')
    return redirect(url_for('admin_exam_detail', exam_id=exam.id))


@app.route('/admin/exam/<int:exam_id>/unassign/<int:examiner_id>', methods=['POST'])
@login_required('admin')
def admin_unassign_examiner(exam_id, examiner_id):
    exam = db.session.get(Exam, exam_id)
    examiner = db.session.get(User, examiner_id)
    # Examiners with slots in this exam must be replaced on those slots first
    if Slot.query.filter_by(exam_id=exam.id, examiner_id=examiner_id).first():
        flash('This examiner has slots in this exam. Change the slot examiner first.', 'danger')
    else:
        exam.examiners.remove(examiner)
        db.session.commit()
        flash('Examiner removed from exam', 'info')
    return redirect(url_for('admin_exam_detail', exam_id=exam.id))


# Admin Rubrics

def read_rubric_numbers():
    # Returns (max_marks, weightage, error) from the rubric form
    try:
        max_marks = int(request.form['max_marks'])
        weightage = int(request.form.get('weightage') or 0)
    except (KeyError, ValueError):
        return None, None, 'Marks and weightage must be numbers'
    if max_marks < 1:
        return None, None, 'Rubric max marks must be at least 1'
    if weightage < 0 or weightage > 100:
        return None, None, 'Weightage must be between 0 and 100'
    return max_marks, weightage, None


@app.route('/admin/exam/<int:exam_id>/rubric/add', methods=['POST'])
@login_required('admin')
def admin_add_rubric(exam_id):
    exam = db.session.get(Exam, exam_id)
    max_marks, weightage, error = read_rubric_numbers()
    if error:
        flash(error, 'danger')
        return redirect(url_for('admin_exam_detail', exam_id=exam.id))
    # Total rubric marks cannot exceed the exam max marks
    used = sum(r.max_marks for r in exam.rubrics)
    if used + max_marks > exam.max_marks:
        flash('Total rubric marks cannot exceed exam max marks (%d)' % exam.max_marks, 'danger')
        return redirect(url_for('admin_exam_detail', exam_id=exam.id))

    r = Rubric(exam_id=exam.id, criterion=request.form['criterion'].strip(),
               max_marks=max_marks, weightage=weightage,
               description=request.form.get('description', ''))
    db.session.add(r)
    db.session.commit()
    flash('Rubric added', 'success')
    return redirect(url_for('admin_exam_detail', exam_id=exam.id))


@app.route('/admin/rubric/<int:rubric_id>/edit', methods=['GET', 'POST'])
@login_required('admin')
def admin_edit_rubric(rubric_id):
    r = db.session.get(Rubric, rubric_id)
    if request.method == 'POST':
        max_marks, weightage, error = read_rubric_numbers()
        if error:
            flash(error, 'danger')
            return redirect(request.url)
        used = sum(x.max_marks for x in r.exam.rubrics if x.id != r.id)
        if used + max_marks > r.exam.max_marks:
            flash('Total rubric marks cannot exceed exam max marks', 'danger')
            return redirect(request.url)
        r.criterion = request.form['criterion'].strip()
        r.max_marks = max_marks
        r.weightage = weightage
        r.description = request.form.get('description', '')
        db.session.commit()
        flash('Rubric updated', 'success')
        return redirect(url_for('admin_exam_detail', exam_id=r.exam_id))
    return render_template('admin/rubric_form.html', r=r)


@app.route('/admin/rubric/<int:rubric_id>/delete', methods=['POST'])
@login_required('admin')
def admin_delete_rubric(rubric_id):
    r = db.session.get(Rubric, rubric_id)
    exam_id = r.exam_id
    if RubricScore.query.filter_by(rubric_id=r.id).first():
        flash('Students are already evaluated on this rubric, cannot delete', 'danger')
    else:
        db.session.delete(r)
        db.session.commit()
        flash('Rubric deleted', 'info')
    return redirect(url_for('admin_exam_detail', exam_id=exam_id))


# Admin Examiners and Students

@app.route('/admin/examiners')
@login_required('admin')
def admin_examiners():
    return render_template('admin/examiners.html',
                           examiners=User.query.filter_by(role='examiner').all())


@app.route('/admin/examiner/add', methods=['GET', 'POST'])
@login_required('admin')
def admin_add_examiner():
    # Examiners added by the admin are approved directly
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(request.url)
        u = User(name=request.form['name'].strip(), email=email,
                 phone=request.form.get('phone', ''), department=request.form.get('department', ''),
                 password=generate_password_hash(request.form['password']),
                 role='examiner', is_approved=True)
        db.session.add(u)
        db.session.commit()
        flash('Examiner added', 'success')
        return redirect(url_for('admin_examiners'))
    return render_template('admin/examiner_form.html')


@app.route('/admin/user/<int:user_id>/approve', methods=['POST'])
@login_required('admin')
def admin_approve(user_id):
    u = db.session.get(User, user_id)
    u.is_approved = True
    db.session.commit()
    flash(u.name + ' approved', 'success')
    return redirect(request.referrer or url_for('admin_examiners'))


@app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
@login_required('admin')
def admin_toggle_active(user_id):
    # Activates or deactivates an examiner or student
    u = db.session.get(User, user_id)
    if u.role != 'admin':
        u.is_active = not u.is_active
        db.session.commit()
        flash(u.name + (' activated' if u.is_active else ' deactivated'), 'info')
    return redirect(request.referrer or url_for('admin_dashboard'))


@app.route('/admin/students')
@login_required('admin')
def admin_students():
    return render_template('admin/students.html',
                           students=User.query.filter_by(role='student').all())


@app.route('/admin/student/<int:student_id>')
@login_required('admin')
def admin_student_detail(student_id):
    # Complete booking history of one student
    s = db.session.get(User, student_id)
    bookings = Booking.query.filter_by(student_id=s.id).order_by(Booking.booked_on.desc()).all()
    return render_template('admin/student_detail.html', s=s, bookings=bookings)


# Admin Slots and Bookings

@app.route('/admin/slots')
@login_required('admin')
def admin_slots():
    return render_template('admin/slots.html', slots=Slot.query.order_by(Slot.date).all())


@app.route('/admin/slot/<int:slot_id>/change-examiner', methods=['GET', 'POST'])
@login_required('admin')
def admin_change_examiner(slot_id):
    slot = db.session.get(Slot, slot_id)
    if request.method == 'POST':
        new_ex = db.session.get(User, int(request.form['examiner_id']))
        slot.examiner_id = new_ex.id
        # New examiner is also assigned to the exam
        if new_ex not in slot.exam.examiners:
            slot.exam.examiners.append(new_ex)
        db.session.commit()
        flash('Examiner changed to ' + new_ex.name, 'success')
        return redirect(url_for('admin_slots'))
    examiners = User.query.filter_by(role='examiner', is_approved=True, is_active=True).all()
    return render_template('admin/change_examiner.html', slot=slot, examiners=examiners)


@app.route('/admin/bookings')
@login_required('admin')
def admin_bookings():
    all_bookings = Booking.query.order_by(Booking.booked_on.desc()).all()
    return render_template('admin/bookings.html', bookings=all_bookings)


@app.route('/admin/booking/<int:booking_id>/reschedule', methods=['GET', 'POST'])
@login_required('admin')
def admin_reschedule(booking_id):
    b = db.session.get(Booking, booking_id)
    # Other slots of the same exam that still have free seats
    options = Slot.query.filter(Slot.exam_id == b.exam_id, Slot.id != b.slot_id,
                                Slot.status == 'Available').all()

    if request.method == 'POST':
        new_slot = db.session.get(Slot, int(request.form['slot_id']))
        if new_slot.available_seats <= 0:
            flash('That slot is full', 'danger')
            return redirect(request.url)

        old_slot = b.slot
        # Frees the seat in the old slot
        old_slot.available_seats += 1
        if old_slot.status == 'Full':
            old_slot.status = 'Available'
        # Takes a seat in the new slot
        new_slot.available_seats -= 1
        if new_slot.available_seats == 0:
            new_slot.status = 'Full'

        b.slot_id = new_slot.id
        db.session.commit()
        flash('Booking rescheduled', 'success')
        return redirect(url_for('admin_bookings'))

    return render_template('admin/reschedule.html', b=b, options=options)


# Admin Search

@app.route('/admin/search')
@login_required('admin')
def admin_search():
    q = request.args.get('q', '').strip()
    results = {'students': [], 'examiners': [], 'exams': [], 'bookings': []}

    if q:
        like = '%' + q + '%'
        id_val = int(q) if q.isdigit() else -1   # A numeric search also matches IDs

        results['students'] = User.query.filter(
            User.role == 'student',
            (User.name.ilike(like)) | (User.email.ilike(like)) |
            (User.roll_no.ilike(like)) | (User.id == id_val)).all()

        results['examiners'] = User.query.filter(
            User.role == 'examiner',
            (User.name.ilike(like)) | (User.email.ilike(like)) | (User.id == id_val)).all()

        results['exams'] = Exam.query.filter(
            (Exam.name.ilike(like)) | (Exam.id == id_val)).all()

        # Bookings matched by booking ID or student name
        results['bookings'] = Booking.query.join(User, Booking.student_id == User.id).filter(
            (Booking.id == id_val) | (User.name.ilike(like))).all()

    return render_template('admin/search.html', q=q, results=results)


# Admin Summary Charts

@app.route('/admin/summary')
@login_required('admin')
def admin_summary():
    # Charts are drawn with matplotlib and saved as PNG files in static/charts
    def empty_chart(title):
        # Shown when there is no data to plot
        plt.text(0.5, 0.5, 'No data yet', ha='center', fontsize=14)
        plt.axis('off')
        plt.title(title)

    folder = os.path.join(app.static_folder, 'charts')
    os.makedirs(folder, exist_ok=True)

    # Chart 1: Booking trend, number of bookings made on each day
    per_day = {}
    for b in Booking.query.order_by(Booking.booked_on).all():
        day = b.booked_on.strftime('%d-%m')
        per_day[day] = per_day.get(day, 0) + 1
    plt.figure(figsize=(6, 4))
    if per_day:
        plt.bar(list(per_day.keys()), list(per_day.values()), color='steelblue')
        plt.gca().yaxis.get_major_locator().set_params(integer=True)   # Whole numbers only on the axis
        plt.title('Booking Trend')
        plt.xlabel('Date')
        plt.ylabel('Bookings')
    else:
        empty_chart('Booking Trend')
    plt.tight_layout()
    plt.savefig(os.path.join(folder, 'trend.png'))
    plt.clf()

    # Chart 2: Examiner workload, students booked in each examiner's slots
    workload = {}
    for ex in User.query.filter_by(role='examiner').all():
        count = Booking.query.join(Slot).filter(Slot.examiner_id == ex.id,
                                                Booking.status != 'Cancelled').count()
        workload[ex.name] = count
    plt.figure(figsize=(6, 4))
    if workload:
        plt.bar(list(workload.keys()), list(workload.values()), color='teal')
        plt.gca().yaxis.get_major_locator().set_params(integer=True)
        plt.title('Examiner Workload')
        plt.ylabel('Students')
        plt.xticks(rotation=20)
    else:
        empty_chart('Examiner Workload')
    plt.tight_layout()
    plt.savefig(os.path.join(folder, 'workload.png'))
    plt.clf()

    # Chart 3: Examination completion, split of booking statuses
    labels = ['Booked', 'Completed', 'Cancelled']
    sizes = [Booking.query.filter_by(status=x).count() for x in labels]
    plt.figure(figsize=(5, 4))
    if sum(sizes) > 0:
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=['orange', 'green', 'grey'])
        plt.title('Examination Completion')
    else:
        empty_chart('Examination Completion')
    plt.savefig(os.path.join(folder, 'completion.png'))
    plt.close('all')

    # Timestamp in the image URL prevents the browser from showing a cached chart
    return render_template('admin/summary.html', t=int(datetime.now().timestamp()))


# Examiner Dashboard

@app.route('/examiner/dashboard')
@login_required('examiner')
def examiner_dashboard():
    me = current_user()
    my_slots = Slot.query.filter_by(examiner_id=me.id).order_by(Slot.date).all()

    # Bookings in this examiner's slots
    booked = Booking.query.join(Slot).filter(Slot.examiner_id == me.id,
                                             Booking.status != 'Cancelled').all()
    pending = [b for b in booked if b.evaluation is None]

    return render_template('examiner/dashboard.html', exams=me.assigned_exams,
                           slots=my_slots, booked_count=len(booked), pending=pending)


# Examiner Slots

@app.route('/examiner/exam/<int:exam_id>')
@login_required('examiner')
def examiner_exam_detail(exam_id):
    me = current_user()
    exam = db.session.get(Exam, exam_id)
    if exam is None or me not in exam.examiners:
        flash('You are not assigned to this exam', 'danger')
        return redirect(url_for('examiner_dashboard'))
    slots = Slot.query.filter_by(exam_id=exam.id, examiner_id=me.id).order_by(Slot.date).all()
    return render_template('examiner/exam_detail.html', exam=exam, slots=slots)


def read_slot_form(exam):
    # Reads and validates the slot form, returns (data, error)
    try:
        date = to_date(request.form['date'])
    except (KeyError, ValueError):
        return None, 'Invalid date'
    start = request.form['start_time']
    end = request.form['end_time']
    try:
        capacity = int(request.form['capacity'] or 0)
    except ValueError:
        return None, 'Capacity must be a number'

    if start >= end:
        return None, 'End time must be after start time'
    if capacity < 1:
        return None, 'Capacity should be at least 1'
    # Exams take place after the booking period ends
    if date <= exam.booking_end:
        return None, 'Slot date must be after booking end date (%s)' % exam.booking_end
    return {'date': date, 'start': start, 'end': end, 'capacity': capacity}, None


@app.route('/examiner/exam/<int:exam_id>/slot/new', methods=['GET', 'POST'])
@login_required('examiner')
def examiner_create_slot(exam_id):
    me = current_user()
    exam = db.session.get(Exam, exam_id)
    if me not in exam.examiners:
        flash('You are not assigned to this exam', 'danger')
        return redirect(url_for('examiner_dashboard'))

    # Slots can be created only during the slot creation period
    if not exam.slot_creation_allowed():
        flash('Slot creation is not open for this exam right now', 'warning')
        return redirect(url_for('examiner_exam_detail', exam_id=exam.id))

    if request.method == 'POST':
        data, error = read_slot_form(exam)
        if error:
            flash(error, 'danger')
            return redirect(request.url)
        slot = Slot(exam_id=exam.id, examiner_id=me.id, date=data['date'],
                    start_time=data['start'], end_time=data['end'],
                    capacity=data['capacity'], available_seats=data['capacity'])
        db.session.add(slot)
        db.session.commit()
        flash('Slot created', 'success')
        return redirect(url_for('examiner_exam_detail', exam_id=exam.id))

    return render_template('examiner/slot_form.html', exam=exam, slot=None)


def can_modify(slot):
    # Slots can change only before booking starts and only when nobody has booked them
    if slot.exam.status not in ('Draft', 'Slot Creation'):
        return False
    return len([b for b in slot.bookings if b.status != 'Cancelled']) == 0


@app.route('/examiner/slot/<int:slot_id>/edit', methods=['GET', 'POST'])
@login_required('examiner')
def examiner_edit_slot(slot_id):
    slot = db.session.get(Slot, slot_id)
    if slot is None or slot.examiner_id != session['user_id']:
        return redirect(url_for('examiner_dashboard'))
    if not can_modify(slot):
        flash('Booking has started, this slot cannot be edited now', 'warning')
        return redirect(url_for('examiner_exam_detail', exam_id=slot.exam_id))

    if request.method == 'POST':
        data, error = read_slot_form(slot.exam)
        if error:
            flash(error, 'danger')
            return redirect(request.url)
        slot.date = data['date']
        slot.start_time = data['start']
        slot.end_time = data['end']
        slot.capacity = data['capacity']
        slot.available_seats = data['capacity']   # No bookings yet, so all seats are free
        db.session.commit()
        flash('Slot updated', 'success')
        return redirect(url_for('examiner_exam_detail', exam_id=slot.exam_id))

    return render_template('examiner/slot_form.html', exam=slot.exam, slot=slot)


@app.route('/examiner/slot/<int:slot_id>/delete', methods=['POST'])
@login_required('examiner')
def examiner_delete_slot(slot_id):
    slot = db.session.get(Slot, slot_id)
    exam_id = slot.exam_id
    if slot.examiner_id == session['user_id'] and can_modify(slot):
        db.session.delete(slot)
        db.session.commit()
        flash('Slot removed', 'info')
    else:
        flash('This slot cannot be removed now', 'warning')
    return redirect(url_for('examiner_exam_detail', exam_id=exam_id))


# Examiner Booked Students and Evaluation

@app.route('/examiner/slot/<int:slot_id>/students')
@login_required('examiner')
def examiner_slot_students(slot_id):
    slot = db.session.get(Slot, slot_id)
    if slot is None or slot.examiner_id != session['user_id']:
        flash('Not your slot', 'danger')
        return redirect(url_for('examiner_dashboard'))
    bookings = [b for b in slot.bookings if b.status != 'Cancelled']
    return render_template('examiner/slot_students.html', slot=slot, bookings=bookings)


@app.route('/examiner/evaluate/<int:booking_id>', methods=['GET', 'POST'])
@login_required('examiner')
def examiner_evaluate(booking_id):
    b = db.session.get(Booking, booking_id)
    # Examiners can evaluate only students booked in their own slots
    if b is None or b.slot.examiner_id != session['user_id'] or b.status == 'Cancelled':
        flash('You cannot evaluate this student', 'danger')
        return redirect(url_for('examiner_dashboard'))

    rubrics = b.exam.rubrics
    if not rubrics:
        flash('Admin has not added rubrics for this exam yet', 'warning')
        return redirect(url_for('examiner_slot_students', slot_id=b.slot_id))

    ev = b.evaluation
    # Previous marks, used to prefill the form when editing an evaluation
    old = {s.rubric_id: s.marks for s in ev.scores} if ev else {}

    if request.method == 'POST':
        if ev is None:
            ev = Evaluation(booking_id=b.id)
            db.session.add(ev)
        else:
            ev.scores.clear()   # Removes old marks before saving the new ones

        total = 0
        for r in rubrics:
            # Every criterion needs marks, a blank or missing value is an error
            try:
                m = float(request.form['r_%d' % r.id])
            except (KeyError, ValueError):
                db.session.rollback()
                flash('Please enter valid marks for ' + r.criterion, 'danger')
                return redirect(request.url)
            if m < 0 or m > r.max_marks:
                db.session.rollback()
                flash('Marks for %s must be between 0 and %d' % (r.criterion, r.max_marks), 'danger')
                return redirect(request.url)
            ev.scores.append(RubricScore(rubric_id=r.id, marks=m))
            total += m

        ev.total_marks = total
        ev.remarks = request.form.get('remarks', '')
        ev.evaluated_on = datetime.now()
        b.status = 'Completed'
        db.session.commit()
        flash('Marks submitted for ' + b.student.name, 'success')
        return redirect(url_for('examiner_slot_students', slot_id=b.slot_id))

    return render_template('examiner/evaluate.html', b=b, rubrics=rubrics, ev=ev, old=old)


# Student Dashboard

@app.route('/student/dashboard')
@login_required('student')
def student_dashboard():
    me = current_user()
    today = datetime.now().date()

    # Exams currently open for booking
    open_exams = [e for e in Exam.query.filter_by(status='Booking Open').all() if e.booking_allowed()]
    open_slots = []
    for e in open_exams:
        open_slots += [s for s in e.slots if s.status == 'Available']

    my_bookings = Booking.query.filter_by(student_id=me.id).all()
    active = [b for b in my_bookings if b.status == 'Booked']
    upcoming = [b for b in active if b.slot.date >= today]
    # Results are shown only after the admin marks the exam Completed
    results = [b for b in my_bookings if b.evaluation and b.exam.status == 'Completed']

    return render_template('student/dashboard.html', open_exams=open_exams, open_slots=open_slots,
                           active=active, upcoming=upcoming, results=results)


# Student Exams, Search and Booking

@app.route('/student/exams')
@login_required('student')
def student_exams():
    # Search and filter values come from the URL query string
    q = request.args.get('q', '').strip()
    exam_type = request.args.get('type', '')
    course_id = request.args.get('course', '')

    query = Exam.query.filter(Exam.status != 'Draft')
    if q:
        query = query.join(Course).filter(Exam.name.ilike('%' + q + '%') |
                                          Course.name.ilike('%' + q + '%') |
                                          Course.code.ilike('%' + q + '%'))
    if exam_type:
        query = query.filter(Exam.exam_type == exam_type)
    if course_id.isdigit():
        query = query.filter(Exam.course_id == int(course_id))

    return render_template('student/exams.html', exams=query.all(), courses=Course.query.all(),
                           q=q, exam_type=exam_type, course_id=course_id)


@app.route('/student/exam/<int:exam_id>')
@login_required('student')
def student_exam_detail(exam_id):
    exam = db.session.get(Exam, exam_id)
    # Checks whether the student already has a booking for this exam
    existing = Booking.query.filter_by(student_id=session['user_id'], exam_id=exam.id,
                                       status='Booked').first()
    slots = [s for s in exam.slots if s.status in ('Available', 'Full')]
    return render_template('student/exam_detail.html', exam=exam, slots=slots, existing=existing)


@app.route('/student/book/<int:slot_id>', methods=['POST'])
@login_required('student')
def student_book(slot_id):
    slot = db.session.get(Slot, slot_id)
    exam = slot.exam

    if not exam.booking_allowed():
        flash('Booking is not open for this exam', 'warning')
        return redirect(url_for('student_exam_detail', exam_id=exam.id))

    # Only one booking per exam is allowed
    already = Booking.query.filter(Booking.student_id == session['user_id'],
                                   Booking.exam_id == exam.id,
                                   Booking.status != 'Cancelled').first()
    if already:
        flash('You already have a booking for this exam', 'danger')
        return redirect(url_for('student_exam_detail', exam_id=exam.id))

    # Capacity check prevents overbooking
    if slot.status != 'Available' or slot.available_seats <= 0:
        flash('Sorry, this slot is full', 'danger')
        return redirect(url_for('student_exam_detail', exam_id=exam.id))

    booking = Booking(student_id=session['user_id'], slot_id=slot.id, exam_id=exam.id)
    slot.available_seats -= 1
    if slot.available_seats == 0:
        slot.status = 'Full'   # Slot closes automatically when full

    db.session.add(booking)
    db.session.commit()
    flash('Slot booked!', 'success')
    return redirect(url_for('student_bookings'))


@app.route('/student/cancel/<int:booking_id>', methods=['POST'])
@login_required('student')
def student_cancel(booking_id):
    b = db.session.get(Booking, booking_id)
    if b is None or b.student_id != session['user_id'] or b.status != 'Booked':
        flash('Invalid booking', 'danger')
        return redirect(url_for('student_bookings'))

    # Cancellation is allowed only until the booking deadline
    if datetime.now().date() > b.exam.booking_end:
        flash('Booking deadline has passed, cannot cancel now', 'warning')
        return redirect(url_for('student_bookings'))

    b.status = 'Cancelled'
    b.slot.available_seats += 1
    if b.slot.status == 'Full':
        b.slot.status = 'Available'
    db.session.commit()
    flash('Booking cancelled', 'info')
    return redirect(url_for('student_bookings'))


# Student History, Schedule and Results

@app.route('/student/bookings')
@login_required('student')
def student_bookings():
    # Full history including cancelled bookings
    all_b = Booking.query.filter_by(student_id=session['user_id']) \
        .order_by(Booking.booked_on.desc()).all()
    today = datetime.now().date()
    return render_template('student/bookings.html', bookings=all_b, today=today)


@app.route('/student/schedule')
@login_required('student')
def student_schedule():
    upcoming = Booking.query.join(Slot).filter(Booking.student_id == session['user_id'],
                                               Booking.status == 'Booked') \
        .order_by(Slot.date, Slot.start_time).all()
    return render_template('student/schedule.html', bookings=upcoming)


@app.route('/student/result/<int:booking_id>')
@login_required('student')
def student_result(booking_id):
    b = db.session.get(Booking, booking_id)
    if b is None or b.student_id != session['user_id'] or not b.evaluation \
            or b.exam.status != 'Completed':
        flash('Result not published yet', 'warning')
        return redirect(url_for('student_bookings'))
    return render_template('student/result.html', b=b)


# Student Profile

@app.route('/student/profile', methods=['GET', 'POST'])
@login_required('student')
def student_profile():
    me = current_user()
    if request.method == 'POST':
        me.name = request.form['name'].strip()
        me.phone = request.form.get('phone', '').strip()
        me.roll_no = request.form.get('roll_no', '').strip()
        db.session.commit()
        session['name'] = me.name
        flash('Profile updated', 'success')
        return redirect(url_for('student_profile'))
    return render_template('student/profile.html', me=me)
