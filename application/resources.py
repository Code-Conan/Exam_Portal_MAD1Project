# JSON API
# API resources for examinations, examiners, students and bookings
# Only a logged in admin can access these routes
# Can be tested in the browser after admin login, or with Postman

from datetime import datetime
from flask import current_app as app, request, jsonify, session

from .database import db
from .models import User, Course, Exam, Booking


# Access Check

def not_admin():
    # Called first by every API route
    return session.get('role') != 'admin'


# Helpers
# Convert database rows into dictionaries for jsonify

def exam_to_dict(e):
    return {
        'id': e.id, 'course_id': e.course_id, 'course_code': e.course.code,
        'name': e.name, 'exam_type': e.exam_type, 'duration': e.duration,
        'max_marks': e.max_marks, 'status': e.status,
        'slot_start': str(e.slot_start), 'slot_end': str(e.slot_end),
        'booking_start': str(e.booking_start), 'booking_end': str(e.booking_end),
        'examiners': [x.id for x in e.examiners],
    }


def user_to_dict(u):
    d = {'id': u.id, 'name': u.name, 'email': u.email, 'phone': u.phone,
         'is_active': u.is_active}
    if u.role == 'examiner':
        d['department'] = u.department
        d['is_approved'] = u.is_approved
    else:
        d['roll_no'] = u.roll_no
    return d


def booking_to_dict(b):
    return {
        'id': b.id, 'student_id': b.student_id, 'student_name': b.student.name,
        'exam_id': b.exam_id, 'exam_name': b.exam.name, 'slot_id': b.slot_id,
        'date': str(b.slot.date), 'start_time': b.slot.start_time,
        'examiner': b.slot.examiner.name, 'status': b.status,
        'booked_on': b.booked_on.strftime('%Y-%m-%d %H:%M'),
        'marks': b.evaluation.total_marks if b.evaluation else None,
    }


# Examinations

@app.get('/api/exams')
def api_get_exams():
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    return jsonify([exam_to_dict(e) for e in Exam.query.all()]), 200


@app.get('/api/exams/<int:exam_id>')
def api_get_exam(exam_id):
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    e = db.session.get(Exam, exam_id)
    if not e:
        return jsonify(error='Exam not found'), 404
    return jsonify(exam_to_dict(e)), 200


def fill_exam(e, data):
    # Copies JSON values into the exam object, used by POST and PUT
    e.course_id = int(data['course_id'])
    e.name = data['name']
    e.exam_type = data.get('exam_type', 'Viva')
    e.duration = int(data['duration'])
    e.max_marks = int(data['max_marks'])
    e.slot_start = datetime.strptime(data['slot_start'], '%Y-%m-%d').date()
    e.slot_end = datetime.strptime(data['slot_end'], '%Y-%m-%d').date()
    e.booking_start = datetime.strptime(data['booking_start'], '%Y-%m-%d').date()
    e.booking_end = datetime.strptime(data['booking_end'], '%Y-%m-%d').date()
    if not db.session.get(Course, e.course_id):
        raise ValueError('Course not found')
    if e.slot_start > e.slot_end or e.booking_start > e.booking_end:
        raise ValueError('Start date must be before end date')
    if e.duration < 1 or e.max_marks < 1:
        raise ValueError('Duration and max marks must be at least 1')
    if e.max_marks < sum(r.max_marks for r in e.rubrics):
        raise ValueError('Max marks cannot be less than total rubric marks')


@app.post('/api/exams')
def api_create_exam():
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    data = request.get_json(silent=True) or {}
    e = Exam()
    try:
        fill_exam(e, data)
    except (KeyError, ValueError) as err:
        return jsonify(error='Invalid data: ' + str(err)), 400
    db.session.add(e)
    db.session.commit()
    return jsonify(message='Exam created', exam=exam_to_dict(e)), 201


@app.put('/api/exams/<int:exam_id>')
def api_update_exam(exam_id):
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    e = db.session.get(Exam, exam_id)
    if not e:
        return jsonify(error='Exam not found'), 404
    data = request.get_json(silent=True) or {}
    try:
        fill_exam(e, data)
    except (KeyError, ValueError) as err:
        db.session.rollback()
        return jsonify(error='Invalid data: ' + str(err)), 400
    db.session.commit()
    return jsonify(message='Exam updated', exam=exam_to_dict(e)), 200


@app.delete('/api/exams/<int:exam_id>')
def api_delete_exam(exam_id):
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    e = db.session.get(Exam, exam_id)
    if not e:
        return jsonify(error='Exam not found'), 404
    # Exams with bookings are kept for history, same rule as the web page
    if Booking.query.filter_by(exam_id=e.id).first():
        return jsonify(error='Exam has bookings, cannot delete'), 400
    db.session.delete(e)
    db.session.commit()
    return jsonify(message='Exam deleted'), 200


# Examiners and Students

@app.get('/api/examiners')
def api_get_examiners():
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    return jsonify([user_to_dict(u) for u in User.query.filter_by(role='examiner').all()]), 200


@app.get('/api/examiners/<int:user_id>')
def api_get_examiner(user_id):
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    u = db.session.get(User, user_id)
    if not u or u.role != 'examiner':
        return jsonify(error='Examiner not found'), 404
    d = user_to_dict(u)
    d['assigned_exams'] = [e.id for e in u.assigned_exams]
    return jsonify(d), 200


@app.get('/api/students')
def api_get_students():
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    return jsonify([user_to_dict(u) for u in User.query.filter_by(role='student').all()]), 200


@app.get('/api/students/<int:user_id>')
def api_get_student(user_id):
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    u = db.session.get(User, user_id)
    if not u or u.role != 'student':
        return jsonify(error='Student not found'), 404
    d = user_to_dict(u)
    d['bookings'] = [booking_to_dict(b) for b in Booking.query.filter_by(student_id=u.id).all()]
    return jsonify(d), 200


# Bookings

@app.get('/api/bookings')
def api_get_bookings():
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    query = Booking.query
    # Optional filters by exam_id and status in the query string
    if request.args.get('exam_id'):
        query = query.filter_by(exam_id=int(request.args['exam_id']))
    if request.args.get('status'):
        query = query.filter_by(status=request.args['status'])
    return jsonify([booking_to_dict(b) for b in query.all()]), 200


@app.get('/api/bookings/<int:booking_id>')
def api_get_booking(booking_id):
    if not_admin():
        return jsonify(error='Unauthorized'), 401
    b = db.session.get(Booking, booking_id)
    if not b:
        return jsonify(error='Booking not found'), 404
    return jsonify(booking_to_dict(b)), 200
