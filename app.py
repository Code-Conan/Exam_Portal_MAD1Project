# app.py - starting point of the application
# run with: python app.py

from flask import Flask
from werkzeug.security import generate_password_hash

from application.database import db

app = None


def create_app():
    app = Flask(__name__)
    app.debug = True
    app.config['SECRET_KEY'] = 'emp-mad1-secret'   # needed for session and flash messages
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exam_portal.db'
    db.init_app(app)
    app.app_context().push()   # so db and current_app work outside a request
    return app


app = create_app()

# routes are in these files, they use current_app so they need app to exist first
from application.controllers import *
from application.resources import *
from application.models import User


def create_admin():
    # admin cannot register, so we add one here if it is not there
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(name='Admin', email='admin@emp.com',
                     password=generate_password_hash('admin123'),
                     role='admin', is_approved=True)
        db.session.add(admin)
        db.session.commit()
        print('Admin created -> admin@emp.com / admin123')


# tables are created from the models (no manual DB creation)
db.create_all()
create_admin()


if __name__ == '__main__':
    app.run()
