# models.py
# All the database tables for the exam portal.
# Tables get created from app.py using db.create_all() so no manual DB setup is needed.

from datetime import datetime
from .database import db   # db object is created in database.py


# one table for all users, the role column decides admin / examiner / student
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # stored as hash
    role = db.Column(db.String(20), nullable=False)       # admin / examiner / student
    phone = db.Column(db.String(20))
    department = db.Column(db.String(100))   # only used for examiners
    roll_no = db.Column(db.String(30))       # only used for students
    # examiners start as False and admin approves them. students are approved by default
    is_approved = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_on = db.Column(db.DateTime, default=datetime.now)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='Active')   # Active / Inactive

    exams = db.relationship('Exam', backref='course', cascade='all, delete-orphan')


# link table - which examiners are assigned to which exam
exam_examiners = db.Table(
    'exam_examiners',
    db.Column('exam_id', db.Integer, db.ForeignKey('exam.id'), primary_key=True),
    db.Column('examiner_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    exam_type = db.Column(db.String(30))     # Viva / Practical / Project Demo / Assessment
    duration = db.Column(db.Integer)         # in minutes
    max_marks = db.Column(db.Integer)
    slot_start = db.Column(db.Date)          # slot creation start
    slot_end = db.Column(db.Date)            # slot creation end
    booking_start = db.Column(db.Date)
    booking_end = db.Column(db.Date)
    # Draft / Slot Creation / Booking Open / Closed / Completed
    status = db.Column(db.String(20), default='Draft')

    examiners = db.relationship('User', secondary=exam_examiners, backref='assigned_exams')
    rubrics = db.relationship('Rubric', backref='exam', cascade='all, delete-orphan')
    slots = db.relationship('Slot', backref='exam', cascade='all, delete-orphan')

    # helper checks used in a few routes
    def slot_creation_allowed(self):
        today = datetime.now().date()
        return self.status == 'Slot Creation' and self.slot_start <= today <= self.slot_end

    def booking_allowed(self):
        today = datetime.now().date()
        return self.status == 'Booking Open' and self.booking_start <= today <= self.booking_end


class Rubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    criterion = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    weightage = db.Column(db.Integer, default=0)   # percent
    description = db.Column(db.Text)


class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Available')  # Available / Full / Cancelled / Completed

    examiner = db.relationship('User')
    bookings = db.relationship('Booking', backref='slot')


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('slot.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    booked_on = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='Booked')   # Booked / Cancelled / Completed

    student = db.relationship('User')
    exam = db.relationship('Exam')
    evaluation = db.relationship('Evaluation', backref='booking', uselist=False)


class Evaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), unique=True, nullable=False)
    total_marks = db.Column(db.Float, default=0)
    remarks = db.Column(db.Text)
    evaluated_on = db.Column(db.DateTime, default=datetime.now)

    scores = db.relationship('RubricScore', backref='evaluation', cascade='all, delete-orphan')


# marks given for each rubric criterion
class RubricScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey('evaluation.id'), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey('rubric.id'), nullable=False)
    marks = db.Column(db.Float, default=0)

    rubric = db.relationship('Rubric')
