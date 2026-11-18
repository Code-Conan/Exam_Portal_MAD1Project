# Examination Management Portal
# Entry point of the application. Run with: python app.py

from flask import Flask
from werkzeug.security import generate_password_hash

from application.database import db

# App Setup

app = None


def create_app():
    app = Flask(__name__)
    app.debug = True
    app.config['SECRET_KEY'] = 'emp-mad1-secret'   # Required for sessions and flash messages
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exam_portal.db'
    db.init_app(app)
    app.app_context().push()   # Allows db and current_app to work outside a request
    return app


app = create_app()

# Routes and API

# Routes use current_app, so they are imported after the app is created
from application.controllers import *
from application.resources import *
from application.models import User


# Default Admin

def create_admin():
    # Admin registration is not allowed, so a default admin is created when missing
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(name='Admin', email='admin@emp.com',
                     password=generate_password_hash('admin123'),
                     role='admin', is_approved=True)
        db.session.add(admin)
        db.session.commit()
        print('Admin created -> admin@emp.com / admin123')


# Database Setup

# Tables are created from the models, no manual database creation
db.create_all()
create_admin()


# Run Server

if __name__ == '__main__':
    app.run()
