import os
from collections import defaultdict
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# --- 1. CONFIGURACIÓN DE LA APP ---
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
upload_folder = os.path.join(basedir, 'uploads')
if not os.path.exists(upload_folder):
    os.makedirs(upload_folder)

app.config['SECRET_KEY'] = 'hrn_sigma_risk_matrix_key_2026'
app.config['UPLOAD_FOLDER'] = upload_folder
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- 2. BASE DE DATOS ---
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if "?sslmode=" not in database_url:
        database_url += "?sslmode=require"
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'database.db')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- 3. MODELOS ---
class User(UserMixin, db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    full_name  = db.Column(db.String(100), nullable=False)
    username   = db.Column(db.String(50), unique=True, nullable=False)
    password   = db.Column(db.String(100), nullable=False)
    role       = db.Column(db.String(20), nullable=False)
    area       = db.Column(db.String(50))

class HRNSubmission(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    filename        = db.Column(db.String(100))
    month           = db.Column(db.String(20))
    status          = db.Column(db.String(20), default='Pendiente')
    supervisor_name = db.Column(db.String(100))
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'))

class RiskMatrixData(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    fila_index = db.Column(db.Integer, nullable=False)
    col_index  = db.Column(db.Integer, nullable=False)
    valor      = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- 4. CONTEXT PROCESSOR (notificaciones globales) ---
@app.context_processor
def inject_globals():
    count = 0
    if current_user.is_authenticated:
        count = HRNSubmission.query.filter_by(status='Pendiente').count()
    return dict(pendientes_count=count)

# --- 5. UTILIDADES ---
def get_risk_cell_class(row, col):
    rojo_oscuro = [(8,4),(8,5),(8,6),(7,4),(7,5),(7,6),(6,4),(6,5),(6,6)]
    rojo_claro  = [(8,1),(8,2),(8,3),(7,1),(7,2),(7,3),(6,2),(6,3),(5,2),(5,3),(5,4),(5,5),(5,6),(4,4),(4,5),(4,6),(3,5),(3,6),(2,5),(2,6)]
    amarillo    = [(8,0),(7,0),(6,0),(6,1),(5,0),(5,1),(4,1),(4,2),(4,3),(3,1),(3,2),(3,3),(3,4),(2,1),(2,2),(2,3),(2,4),(1,2),(1,4),(1,5),(1,6),(0,6)]
    if (row, col) in rojo_oscuro: return "celda-roja-oscuro"
    if (row, col) in rojo_claro:  return "celda-roja-claro"
    if (row, col) in amarillo:    return "celda-amarilla"
    return "celda-verde"

def build_supervisor_stats(entregas):
    """Agrupa estadísticas por supervisor."""
    data = {}
    for e in entregas:
        key = e.supervisor_name
        if key not in data:
            area = ''
            if '_' in (e.filename or ''):
                parts = e.filename.split('_')
                area = parts[1] if len(parts) > 1 else ''
            data[key] = {'nombre': key, 'area': area, 'total': 0, 'revisados': 0, 'pendientes': 0}
        data[key]['total'] += 1
        if e.status == 'Revisado':
            data[key]['revisados'] += 1
        else:
            data[key]['pendientes'] += 1
    return list(data.values())

def build_area_chart(all_entregas):
    """Datos para la gráfica de barras por área."""
    areas_data = defaultdict(lambda: {'revisados': 0, 'pendientes': 0})
    for e in all_entregas:
        area = ''
        if '_' in (e.filename or ''):
            parts = e.filename.split('_')
            area = parts[1] if len(parts) > 1 else 'Desconocida'
        if not area:
            area = 'Desconocida'
        if e.status == 'Revisado':
            areas_data[area]['revisados'] += 1
        else:
            areas_data[area]['pendientes'] += 1
    labels    = list(areas_data.keys())
    revisados = [areas_data[a]['revisados'] for a in labels]
    pendientes= [areas_data[a]['pendientes'] for a in labels]
    return {'labels': labels, 'revisados': revisados, 'pendientes': pendientes}

# --- 6. RUTAS ---

@app.route('/guardar_matriz_riesgos', methods=['POST'])
@login_required
def guardar_matriz_riesgos():
    if current_user.role != 'admin':
        return "No permitido", 403
    try:
        for key, value in request.form.items():
            if key.startswith('cell_'):
                parts = key.split('_')
                row, col = int(parts[1]), int(parts[2])
                val  = int(value) if value.strip() else 0
                cell = RiskMatrixData.query.filter_by(fila_index=row, col_index=col).first()
                if cell:
                    cell.valor = val
        db.session.commit()
        flash('Matriz guardada con éxito', 'success')
    except Exception as ex:
        flash('Error al guardar la matriz', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/usuarios')
@login_required
def lista_usuarios():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    return render_template('usuarios.html', usuarios=User.query.all())

@app.route('/usuarios/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_usuario():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        db.session.add(User(
            full_name=request.form.get('full_name', '').strip(),
            username =request.form.get('username',  '').strip(),
            password =request.form.get('password',  '').strip(),
            role     =request.form.get('role'),
            area     =request.form.get('area')
        ))
        db.session.commit()
        flash('Usuario creado correctamente', 'success')
        return redirect(url_for('lista_usuarios'))
    return render_template('usuario_form.html', titulo="Nuevo Usuario", user_edit=None)

@app.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    u = db.session.get(User, id)
    if request.method == 'POST':
        u.full_name = request.form.get('full_name')
        u.username  = request.form.get('username')
        u.password  = request.form.get('password')
        u.role      = request.form.get('role')
        u.area      = request.form.get('area')
        db.session.commit()
        flash('Usuario actualizado', 'success')
        return redirect(url_for('lista_usuarios'))
    return render_template('usuario_form.html', titulo="Editar Usuario", user_edit=u)

@app.route('/usuarios/eliminar/<int:id>')
@login_required
def eliminar_usuario(id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    u = db.session.get(User, id)
    if u and u.username != 'admin':
        db.session.delete(u)
        db.session.commit()
        flash('Usuario eliminado', 'success')
    return redirect(url_for('lista_usuarios'))

@app.route('/')
@login_required
def dashboard():
    if current_user.role == 'supervisor':
        return redirect(url_for('upload_hrn'))

    # --- Filtros ---
    filtro_mes    = request.args.get('mes', '')
    filtro_area   = request.args.get('area', '')
    filtro_estado = request.args.get('estado', '')

    query = HRNSubmission.query
    if filtro_mes:
        query = query.filter(HRNSubmission.month == filtro_mes)
    if filtro_estado:
        query = query.filter(HRNSubmission.status == filtro_estado)
    entregas = query.all()

    # Filtro por área (sobre filename)
    if filtro_area:
        entregas = [e for e in entregas if filtro_area in (e.filename or '')]

    # Áreas disponibles para el select de filtros
    todas = HRNSubmission.query.all()
    areas_set = set()
    for e in todas:
        if '_' in (e.filename or ''):
            parts = e.filename.split('_')
            if len(parts) > 1:
                areas_set.add(parts[1])
    areas_disponibles = sorted(areas_set)

    # Matriz de riesgos
    matrix_cells = RiskMatrixData.query.all()
    data = [[0]*7 for _ in range(9)]
    for cell in matrix_cells:
        data[cell.fila_index][cell.col_index] = cell.valor

    # Stats de supervisores (sobre entregas filtradas)
    supervisor_stats  = build_supervisor_stats(entregas)

    # Chart data (siempre sobre TODOS los registros para no confundir la gráfica)
    area_chart_data = build_area_chart(todas)

    return render_template(
        'dashboard.html',
        entregas          = entregas,
        risk_matrix_data  = data,
        get_risk_cell_class = get_risk_cell_class,
        supervisor_stats  = supervisor_stats,
        area_chart_data   = area_chart_data,
        areas_disponibles = areas_disponibles,
        filtro_mes        = filtro_mes,
        filtro_area       = filtro_area,
        filtro_estado     = filtro_estado,
    )

@app.route('/review/<int:id>')
@login_required
def review_hrn(id):
    ent = db.session.get(HRNSubmission, id)
    if ent and current_user.role in ['admin', 'subcomite']:
        ent.status = 'Revisado'
        db.session.commit()
        flash('Reporte marcado como revisado', 'success')
    return redirect(url_for('dashboard'))

@app.route('/edit_reporte/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_hrn(id):
    ent = db.session.get(HRNSubmission, id)
    if request.method == 'POST':
        ent.month  = request.form.get('month')
        ent.status = request.form.get('status')
        db.session.commit()
        flash('Reporte actualizado', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit.html', entrega=ent)

@app.route('/delete_reporte/<int:id>')
@login_required
def delete_hrn(id):
    ent = db.session.get(HRNSubmission, id)
    if ent and current_user.role == 'admin':
        db.session.delete(ent)
        db.session.commit()
        flash('Reporte eliminado', 'success')
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username', '').strip()).first()
        if user and user.password == request.form.get('password', '').strip():
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Nómina o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_hrn():
    if request.method == 'POST':
        file  = request.files.get('file')
        month = request.form.get('month')
        if file:
            filename = f"HRN_{current_user.area}_{month}.xlsx".replace(" ", "_")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            db.session.add(HRNSubmission(
                filename        = filename,
                month           = month,
                supervisor_name = current_user.full_name,
                user_id         = current_user.id
            ))
            db.session.commit()
            flash('Reporte subido correctamente', 'success')
            return redirect(url_for('dashboard'))
        flash('No se seleccionó ningún archivo', 'danger')
    return render_template('upload.html')

@app.route('/uploads/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/reset-db-total')
def reset_db():
    db.drop_all()
    db.create_all()
    db.session.add(User(full_name='Administrador', username='admin', password='123', role='admin', area='Sistemas'))
    for r in range(9):
        for c in range(7):
            db.session.add(RiskMatrixData(fila_index=r, col_index=c, valor=0))
    db.session.commit()
    return "Base de Datos Reiniciada. Entra con admin / 123"

if __name__ == '__main__':
    app.run(debug=True)