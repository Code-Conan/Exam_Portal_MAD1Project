# database object is kept in its own file so models and controllers can both import it
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
