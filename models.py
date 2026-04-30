from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'admin', 'subcomite', 'supervisor'
    area = db.Column(db.String(50))

class HRNSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100))
    month = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Pendiente') # Pendiente, Revisado
    supervisor_id = db.Column(db.Integer, db.ForeignKey('user.id'))