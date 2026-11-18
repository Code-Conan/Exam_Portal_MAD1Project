# Examination Management Portal (MAD 1 Project)

## How to run
```
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

The SQLite database (instance/exam_portal.db) is created automatically on first run.

Default admin login: **admin@emp.com / admin123**

## Folder structure
```
app.py                    -> create_app(), creates tables + admin
application/
    database.py           -> db = SQLAlchemy()
    models.py             -> all tables
    controllers.py        -> all pages (auth, admin, examiner, student, summary charts)
    resources.py          -> JSON API
templates/                -> jinja2 html (admin/, examiner/, student/)
static/                   -> css + generated chart images (static/charts)
```

## Basic flow
1. Admin creates a course, then an exam with its dates and rubrics.
2. Examiner registers, admin approves and assigns them to the exam.
3. Admin sets exam status to *Slot Creation* -> examiner adds slots.
4. Admin sets status to *Booking Open* -> students book slots.
5. Examiner evaluates booked students using rubrics.
6. Admin sets status to *Completed* -> students can see results.

## API (admin login needed, returns JSON)
| Method | URL | What it does |
|---|---|---|
| GET | /api/exams | all exams |
| GET | /api/exams/&lt;id&gt; | one exam |
| POST | /api/exams | create exam |
| PUT | /api/exams/&lt;id&gt; | update exam |
| DELETE | /api/exams/&lt;id&gt; | delete exam (only if no bookings) |
| GET | /api/examiners, /api/examiners/&lt;id&gt; | examiners |
| GET | /api/students, /api/students/&lt;id&gt; | students (one student includes bookings) |
| GET | /api/bookings?exam_id=&status= | bookings with optional filters |
| GET | /api/bookings/&lt;id&gt; | one booking |

Example body for POST / PUT /api/exams:
```json
{"course_id": 1, "name": "Viva 1", "exam_type": "Viva", "duration": 20, "max_marks": 20,
 "slot_start": "2026-11-18", "slot_end": "2026-11-21",
 "booking_start": "2026-11-18", "booking_end": "2026-11-25"}
```
