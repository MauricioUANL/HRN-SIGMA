import os
from collections import defaultdict
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import inspect

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
    year            = db.Column(db.Integer, index=True)
    status          = db.Column(db.String(20), default='Pendiente')
    supervisor_name = db.Column(db.String(100))
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'))

class RiskMatrixData(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    fila_index = db.Column(db.Integer, nullable=False)
    col_index  = db.Column(db.Integer, nullable=False)
    valor      = db.Column(db.Integer, default=0)

class AuditLog(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username  = db.Column(db.String(100))
    action    = db.Column(db.String(50), nullable=False, index=True)
    entity    = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details   = db.Column(db.String(500))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- 3.1 MIGRACIONES LIGERAS (idempotentes) ---
def _run_lightweight_migrations():
    """Crea tablas nuevas y agrega columnas faltantes en BDs existentes.
    Es seguro ejecutarse en cada arranque."""
    db.create_all()
    insp = inspect(db.engine)
    if 'hrn_submission' in insp.get_table_names():
        cols = [c['name'] for c in insp.get_columns('hrn_submission')]
        if 'year' not in cols:
            current_year = datetime.utcnow().year
            with db.engine.begin() as conn:
                conn.exec_driver_sql('ALTER TABLE hrn_submission ADD COLUMN year INTEGER')
                conn.exec_driver_sql(
                    f'UPDATE hrn_submission SET year = {current_year} WHERE year IS NULL'
                )

with app.app_context():
    try:
        _run_lightweight_migrations()
    except Exception as ex:
        # No tumbamos el arranque si la BD aún no está lista
        print(f'[migrations] saltado: {ex}')

# --- 3.2 HELPER DE AUDITORÍA ---
def log_action(action, entity=None, entity_id=None, details=None):
    """Registra una acción en AuditLog. Falla en silencio para no romper la request."""
    try:
        u = current_user if (current_user and current_user.is_authenticated) else None
        entry = AuditLog(
            user_id   = u.id if u else None,
            username  = u.username if u else None,
            action    = action,
            entity    = entity,
            entity_id = entity_id,
            details   = (details or '')[:500] or None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()

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

MESES_ORDEN = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
               'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

def build_monthly_trend(entregas):
    """Tendencia mensual: revisados, pendientes y total por mes (orden Enero..Diciembre)."""
    revisados   = [0] * 12
    pendientes  = [0] * 12
    for e in entregas:
        if e.month in MESES_ORDEN:
            idx = MESES_ORDEN.index(e.month)
            if e.status == 'Revisado':
                revisados[idx] += 1
            else:
                pendientes[idx] += 1
    totales = [r + p for r, p in zip(revisados, pendientes)]
    return {
        'labels':     MESES_ORDEN,
        'revisados':  revisados,
        'pendientes': pendientes,
        'totales':    totales,
    }

def build_area_compliance(entregas):
    """% de cumplimiento (revisados/total) por área para la gráfica radar."""
    areas_data = defaultdict(lambda: {'total': 0, 'revisados': 0})
    for e in entregas:
        area = 'Desconocida'
        if '_' in (e.filename or ''):
            parts = e.filename.split('_')
            if len(parts) > 1 and parts[1]:
                area = parts[1]
        areas_data[area]['total'] += 1
        if e.status == 'Revisado':
            areas_data[area]['revisados'] += 1
    labels = sorted(areas_data.keys())
    porcentajes = [
        round(areas_data[a]['revisados'] / areas_data[a]['total'] * 100, 1)
        if areas_data[a]['total'] > 0 else 0
        for a in labels
    ]
    return {'labels': labels, 'porcentajes': porcentajes}

def get_available_years():
    """Años distintos presentes en HRNSubmission, descendentes. Incluye el actual."""
    rows = db.session.query(HRNSubmission.year).filter(HRNSubmission.year.isnot(None)).distinct().all()
    years = {r[0] for r in rows if r[0] is not None}
    years.add(datetime.utcnow().year)
    return sorted(years, reverse=True)

# --- 6. RUTAS ---

@app.route('/guardar_matriz_riesgos', methods=['POST'])
@login_required
def guardar_matriz_riesgos():
    if current_user.role != 'admin':
        return "No permitido", 403
    try:
        cambios = 0
        for key, value in request.form.items():
            if key.startswith('cell_'):
                parts = key.split('_')
                row, col = int(parts[1]), int(parts[2])
                val  = int(value) if value.strip() else 0
                cell = RiskMatrixData.query.filter_by(fila_index=row, col_index=col).first()
                if cell and cell.valor != val:
                    cell.valor = val
                    cambios += 1
        db.session.commit()
        log_action('guardar_matriz', entity='RiskMatrix', details=f'{cambios} celdas actualizadas')
        flash('Matriz guardada con éxito', 'success')
    except Exception:
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
        u = User(
            full_name=request.form.get('full_name', '').strip(),
            username =request.form.get('username',  '').strip(),
            password =request.form.get('password',  '').strip(),
            role     =request.form.get('role'),
            area     =request.form.get('area')
        )
        db.session.add(u)
        db.session.commit()
        log_action('crear_usuario', entity='User', entity_id=u.id,
                   details=f'username={u.username} role={u.role} area={u.area}')
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
        log_action('editar_usuario', entity='User', entity_id=u.id,
                   details=f'username={u.username} role={u.role} area={u.area}')
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
        eliminado_username = u.username
        eliminado_id = u.id
        db.session.delete(u)
        db.session.commit()
        log_action('eliminar_usuario', entity='User', entity_id=eliminado_id,
                   details=f'username={eliminado_username}')
        flash('Usuario eliminado', 'success')
    return redirect(url_for('lista_usuarios'))

@app.route('/')
@login_required
def dashboard():
    if current_user.role == 'supervisor':
        return supervisor_dashboard()

    anios_disponibles = get_available_years()
    anio_actual_str   = str(datetime.utcnow().year)

    # --- Filtros ---
    filtro_mes    = request.args.get('mes', '')
    filtro_area   = request.args.get('area', '')
    filtro_estado = request.args.get('estado', '')
    filtro_anio   = request.args.get('anio', anio_actual_str)

    query = HRNSubmission.query
    if filtro_mes:
        query = query.filter(HRNSubmission.month == filtro_mes)
    if filtro_estado:
        query = query.filter(HRNSubmission.status == filtro_estado)
    if filtro_anio:
        try:
            query = query.filter(HRNSubmission.year == int(filtro_anio))
        except ValueError:
            filtro_anio = ''
    entregas = query.all()

    # Filtro por área (sobre filename)
    if filtro_area:
        entregas = [e for e in entregas if filtro_area in (e.filename or '')]

    # Áreas disponibles para el select de filtros (todos los años)
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

    # Chart data por área (filtradas, para que respete año)
    area_chart_data       = build_area_chart(entregas)
    monthly_trend_data    = build_monthly_trend(entregas)
    area_compliance_data  = build_area_compliance(entregas)

    return render_template(
        'dashboard.html',
        entregas             = entregas,
        risk_matrix_data     = data,
        get_risk_cell_class  = get_risk_cell_class,
        supervisor_stats     = supervisor_stats,
        area_chart_data      = area_chart_data,
        monthly_trend_data   = monthly_trend_data,
        area_compliance_data = area_compliance_data,
        areas_disponibles    = areas_disponibles,
        anios_disponibles    = anios_disponibles,
        filtro_mes           = filtro_mes,
        filtro_area          = filtro_area,
        filtro_estado        = filtro_estado,
        filtro_anio          = filtro_anio,
    )

def supervisor_dashboard():
    """Vista exclusiva del supervisor: sus propias métricas y gráficas."""
    anios_disponibles = get_available_years()
    anio_actual_str   = str(datetime.utcnow().year)
    filtro_anio       = request.args.get('anio', anio_actual_str)

    query = HRNSubmission.query.filter(HRNSubmission.user_id == current_user.id)
    if filtro_anio:
        try:
            query = query.filter(HRNSubmission.year == int(filtro_anio))
        except ValueError:
            filtro_anio = ''
    mis_entregas = query.order_by(HRNSubmission.id.desc()).all()

    total      = len(mis_entregas)
    revisados  = sum(1 for e in mis_entregas if e.status == 'Revisado')
    pendientes = total - revisados
    cumplimiento = round((revisados / total * 100), 0) if total > 0 else 0
    meses_subidos = len({e.month for e in mis_entregas})

    monthly_trend_data = build_monthly_trend(mis_entregas)

    return render_template(
        'dashboard_supervisor.html',
        mis_entregas       = mis_entregas,
        total              = total,
        revisados          = revisados,
        pendientes         = pendientes,
        cumplimiento       = int(cumplimiento),
        meses_subidos      = meses_subidos,
        monthly_trend_data = monthly_trend_data,
        anios_disponibles  = anios_disponibles,
        filtro_anio        = filtro_anio,
    )

@app.route('/auditoria')
@login_required
def auditoria():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))

    filtro_accion  = request.args.get('accion', '')
    filtro_usuario = request.args.get('usuario', '')

    query = AuditLog.query
    if filtro_accion:
        query = query.filter(AuditLog.action == filtro_accion)
    if filtro_usuario:
        query = query.filter(AuditLog.username.ilike(f'%{filtro_usuario}%'))

    logs = query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    acciones = [r[0] for r in db.session.query(AuditLog.action).distinct().all()]

    return render_template(
        'auditoria.html',
        logs = logs,
        acciones = sorted(acciones),
        filtro_accion = filtro_accion,
        filtro_usuario = filtro_usuario,
    )

@app.route('/review/<int:id>')
@login_required
def review_hrn(id):
    ent = db.session.get(HRNSubmission, id)
    if ent and current_user.role in ['admin', 'subcomite']:
        ent.status = 'Revisado'
        db.session.commit()
        log_action('revisar_hrn', entity='HRNSubmission', entity_id=ent.id,
                   details=f'{ent.filename} ({ent.month} {ent.year})')
        flash('Reporte marcado como revisado', 'success')
    return redirect(url_for('dashboard'))

@app.route('/edit_reporte/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_hrn(id):
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))
    ent = db.session.get(HRNSubmission, id)
    if request.method == 'POST':
        ent.month  = request.form.get('month')
        ent.status = request.form.get('status')
        anio_str   = request.form.get('year', '').strip()
        if anio_str:
            try:
                ent.year = int(anio_str)
            except ValueError:
                pass
        db.session.commit()
        log_action('editar_hrn', entity='HRNSubmission', entity_id=ent.id,
                   details=f'mes={ent.month} año={ent.year} status={ent.status}')
        flash('Reporte actualizado', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit.html', entrega=ent, anios_disponibles=get_available_years())

@app.route('/delete_reporte/<int:id>')
@login_required
def delete_hrn(id):
    ent = db.session.get(HRNSubmission, id)
    if ent and current_user.role == 'admin':
        eliminado_filename = ent.filename
        eliminado_id = ent.id
        db.session.delete(ent)
        db.session.commit()
        log_action('eliminar_hrn', entity='HRNSubmission', entity_id=eliminado_id,
                   details=eliminado_filename)
        flash('Reporte eliminado', 'success')
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_input = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username_input).first()
        if user and user.password == request.form.get('password', '').strip():
            login_user(user)
            log_action('login', entity='User', entity_id=user.id, details=f'username={user.username}')
            return redirect(url_for('dashboard'))
        # Log fallido sin user_id (current_user es Anónimo)
        try:
            db.session.add(AuditLog(
                action='login_fallido', entity='User',
                username=username_input or None,
                details='Credenciales inválidas',
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        flash('Nómina o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        log_action('logout', entity='User', entity_id=current_user.id,
                   details=f'username={current_user.username}')
    logout_user()
    return redirect(url_for('login'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_hrn():
    if request.method == 'POST':
        file  = request.files.get('file')
        month = request.form.get('month')
        anio_str = request.form.get('year', '').strip()
        try:
            year = int(anio_str) if anio_str else datetime.utcnow().year
        except ValueError:
            year = datetime.utcnow().year
        if file:
            filename = f"HRN_{current_user.area}_{month}_{year}.xlsx".replace(" ", "_")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            sub = HRNSubmission(
                filename        = filename,
                month           = month,
                year            = year,
                supervisor_name = current_user.full_name,
                user_id         = current_user.id,
            )
            db.session.add(sub)
            db.session.commit()
            log_action('subir_hrn', entity='HRNSubmission', entity_id=sub.id,
                       details=f'{filename}')
            flash('Reporte subido correctamente', 'success')
            return redirect(url_for('dashboard'))
        flash('No se seleccionó ningún archivo', 'danger')
    return render_template('upload.html', anio_actual=datetime.utcnow().year,
                           anios_disponibles=get_available_years())

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