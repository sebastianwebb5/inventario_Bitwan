from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3, json, io, base64
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

app = Flask(__name__)
app.secret_key = "bitwan_secret_2024"
DB = "bitwan.db"

# ══════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL, password TEXT NOT NULL, rol TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS materiales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL, cantidad INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS actividades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL, descripcion TEXT NOT NULL,
        usuario_asignado_id INTEGER NOT NULL,
        creado_por_id INTEGER, creado_por_rol TEXT,
        estado TEXT DEFAULT 'pendiente',
        fecha_creacion TEXT NOT NULL,
        firma_imagen TEXT, fecha_firmado TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS actividad_materiales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actividad_id INTEGER NOT NULL,
        material_id INTEGER NOT NULL,
        cantidad INTEGER NOT NULL)""")
    c.execute("SELECT COUNT(*) FROM usuarios WHERE rol='admin'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios (usuario,password,rol) VALUES ('sebastian','1234','admin')")
    conn.commit(); conn.close()
    print("✅ DB lista")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_acta_completa(conn, acta_id, user_id=None):
    """Devuelve acta + lista de materiales. Si user_id, filtra por dueño."""
    q = """SELECT a.*, u.usuario as nombre_usuario
           FROM actividades a JOIN usuarios u ON a.usuario_asignado_id=u.id
           WHERE a.id=?"""
    params = [acta_id]
    if user_id:
        q += " AND a.usuario_asignado_id=?"; params.append(user_id)
    acta = conn.execute(q, params).fetchone()
    if not acta: return None
    acta = dict(acta)
    mats = conn.execute("""SELECT m.nombre, am.cantidad
        FROM actividad_materiales am JOIN materiales m ON am.material_id=m.id
        WHERE am.actividad_id=?""", (acta_id,)).fetchall()
    acta['materiales'] = [dict(m) for m in mats]
    return acta

# ══════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════
@app.route('/')
def inicio(): return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    conn = get_db()
    r = conn.execute("SELECT * FROM usuarios WHERE usuario=? AND password=?",
                     (request.form['usuario'], request.form['password'])).fetchone()
    conn.close()
    if r:
        session.update({'usuario': r['usuario'], 'rol': r['rol'], 'user_id': r['id']})
        return redirect(url_for('admin' if r['rol']=='admin' else 'usuario_panel'))
    return render_template('login.html', error="Usuario o contraseña incorrectos ❌")

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('inicio'))

# ══════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════
@app.route('/admin')
def admin():
    if session.get('rol') != 'admin': return redirect(url_for('inicio'))
    conn = get_db()
    materiales = [dict(m) for m in conn.execute("SELECT * FROM materiales ORDER BY nombre").fetchall()]
    conn.close()
    return render_template('admin.html', usuario=session['usuario'], materiales=materiales)

# API usuarios
@app.route('/api/usuarios')
def api_usuarios():
    if session.get('rol') != 'admin': return jsonify([])
    conn = get_db()
    us = [dict(u) for u in conn.execute("SELECT id,usuario,rol FROM usuarios WHERE rol!='admin'").fetchall()]
    conn.close(); return jsonify(us)

@app.route('/api/usuario/<int:uid>/actividades')
def api_usuario_actividades(uid):
    if session.get('rol') != 'admin': return jsonify([])
    conn = get_db()
    acts = conn.execute("SELECT id,nombre,estado,fecha_creacion FROM actividades WHERE usuario_asignado_id=? ORDER BY fecha_creacion DESC", (uid,)).fetchall()
    result = []
    for a in acts:
        a = dict(a)
        a['materiales'] = [dict(m) for m in conn.execute("""SELECT m.nombre,am.cantidad FROM actividad_materiales am JOIN materiales m ON am.material_id=m.id WHERE am.actividad_id=?""", (a['id'],)).fetchall()]
        result.append(a)
    conn.close(); return jsonify(result)

@app.route('/eliminar_usuario/<int:uid>', methods=['POST'])
def eliminar_usuario(uid):
    if session.get('rol') != 'admin': return jsonify({'ok': False})
    conn = get_db()
    u = conn.execute("SELECT rol FROM usuarios WHERE id=?", (uid,)).fetchone()
    if u and u['rol'] != 'admin':
        conn.execute("DELETE FROM usuarios WHERE id=?", (uid,)); conn.commit()
    conn.close(); return jsonify({'ok': True})

@app.route('/crear_usuario', methods=['GET','POST'])
def crear_usuario():
    if session.get('rol') != 'admin': return redirect(url_for('inicio'))
    if request.method == 'POST':
        conn = get_db()
        conn.execute("INSERT INTO usuarios (usuario,password,rol) VALUES (?,?,?)",
                     (request.form['usuario'], request.form['password'], request.form['rol']))
        conn.commit(); conn.close()
        return render_template('crear_usuario.html', mensaje="✅ Usuario creado correctamente")
    return render_template('crear_usuario.html')

# ══════════════════════════════════════════════
# BODEGA (solo admin gestiona, todos ven)
# ══════════════════════════════════════════════
@app.route('/bodega', methods=['GET','POST'])
def bodega():
    if session.get('rol') != 'admin': return redirect(url_for('inicio'))
    conn = get_db()
    if request.method == 'POST':
        ac = request.form.get('accion')
        if ac == 'agregar':
            n, q = request.form['nombre'].strip(), int(request.form['cantidad'])
            if n and q > 0: conn.execute("INSERT INTO materiales (nombre,cantidad) VALUES (?,?)", (n,q))
        elif ac == 'eliminar':
            conn.execute("DELETE FROM materiales WHERE id=?", (request.form['id'],))
        elif ac == 'editar':
            conn.execute("UPDATE materiales SET cantidad=? WHERE id=?", (int(request.form['cantidad']), request.form['id']))
        conn.commit()
    mats = conn.execute("SELECT * FROM materiales ORDER BY nombre").fetchall()
    conn.close()
    return render_template('bodega.html', materiales=mats, usuario=session['usuario'])

# ══════════════════════════════════════════════
# ACTIVIDADES — admin y usuario pueden crear
# ══════════════════════════════════════════════
def _crear_actividad(nombre, descripcion, usuario_asignado_id, mat_ids, cantidades, creado_por_id, creado_por_rol):
    conn = get_db()
    error = None
    pares = []
    for mid, cant in zip(mat_ids, cantidades):
        if not mid or not cant: continue
        mid, cant = int(mid), int(cant)
        if cant <= 0: continue
        mat = conn.execute("SELECT nombre,cantidad FROM materiales WHERE id=?", (mid,)).fetchone()
        if mat['cantidad'] < cant:
            error = f"❌ Stock insuficiente para '{mat['nombre']}'. Disponible: {mat['cantidad']}"
            conn.close(); return error
        pares.append((mid, cant))

    acta_id = conn.execute("""INSERT INTO actividades (nombre,descripcion,usuario_asignado_id,creado_por_id,creado_por_rol,fecha_creacion)
        VALUES (?,?,?,?,?,?)""",
        (nombre, descripcion, usuario_asignado_id, creado_por_id, creado_por_rol,
         datetime.now().strftime("%Y-%m-%d %H:%M"))).lastrowid

    for mid, cant in pares:
        conn.execute("INSERT INTO actividad_materiales (actividad_id,material_id,cantidad) VALUES (?,?,?)", (acta_id, mid, cant))
        conn.execute("UPDATE materiales SET cantidad=cantidad-? WHERE id=?", (cant, mid))
    conn.commit(); conn.close()
    return None

@app.route('/actividades', methods=['GET','POST'])
def actividades():
    if session.get('rol') != 'admin': return redirect(url_for('inicio'))
    conn = get_db()
    error = None
    if request.method == 'POST':
        error = _crear_actividad(
            request.form['nombre'].strip(),
            request.form['descripcion'].strip(),
            int(request.form['usuario_id']),
            request.form.getlist('material_id[]'),
            request.form.getlist('cantidad_material[]'),
            session['user_id'], 'admin')
        if not error:
            conn.close(); return redirect(url_for('actas_admin'))
    mats = [dict(m) for m in conn.execute("SELECT * FROM materiales WHERE cantidad>0 ORDER BY nombre").fetchall()]
    users = conn.execute("SELECT id,usuario FROM usuarios WHERE rol!='admin' ORDER BY usuario").fetchall()
    conn.close()
    return render_template('actividades.html', materiales=mats, usuarios=users, usuario=session['usuario'], error=error)

@app.route('/actividades_usuario', methods=['GET','POST'])
def actividades_usuario():
    if not session.get('usuario'): return redirect(url_for('inicio'))
    conn = get_db()
    error = None
    if request.method == 'POST':
        error = _crear_actividad(
            request.form['nombre'].strip(),
            request.form['descripcion'].strip(),
            session['user_id'],           # se asigna a sí mismo → va al admin
            request.form.getlist('material_id[]'),
            request.form.getlist('cantidad_material[]'),
            session['user_id'], 'usuario')
        if not error:
            conn.close(); return redirect(url_for('mis_actas'))
    mats = [dict(m) for m in conn.execute("SELECT * FROM materiales WHERE cantidad>0 ORDER BY nombre").fetchall()]
    conn.close()
    return render_template('actividades_usuario.html', materiales=mats, usuario=session['usuario'])

# ══════════════════════════════════════════════
# ACTAS ADMIN
# ══════════════════════════════════════════════
@app.route('/actas')
def actas_admin():
    if session.get('rol') != 'admin': return redirect(url_for('inicio'))
    conn = get_db()
    acts = conn.execute("""SELECT a.*,u.usuario as nombre_usuario
        FROM actividades a JOIN usuarios u ON a.usuario_asignado_id=u.id
        ORDER BY a.fecha_creacion DESC""").fetchall()
    result = []
    for a in acts:
        a = dict(a)
        a['materiales'] = [dict(m) for m in conn.execute("""SELECT m.nombre,am.cantidad FROM actividad_materiales am JOIN materiales m ON am.material_id=m.id WHERE am.actividad_id=?""", (a['id'],)).fetchall()]
        result.append(a)
    conn.close()
    return render_template('actas_admin.html', actas=result, usuario=session['usuario'])

# ══════════════════════════════════════════════
# PANEL USUARIO
# ══════════════════════════════════════════════
@app.route('/panel')
def usuario_panel():
    if not session.get('usuario'): return redirect(url_for('inicio'))
    conn = get_db()
    # Solo materiales asignados al usuario (los que aparecen en sus actividades)
    mats_asignados = conn.execute("""
        SELECT DISTINCT m.id, m.nombre, am.cantidad as cantidad_asignada
        FROM actividad_materiales am
        JOIN materiales m ON am.material_id=m.id
        JOIN actividades a ON am.actividad_id=a.id
        WHERE a.usuario_asignado_id=?
        ORDER BY m.nombre""", (session['user_id'],)).fetchall()
    # Notificaciones: actas pendientes asignadas al usuario (creadas por admin)
    notifs = conn.execute("""SELECT id,nombre,descripcion,fecha_creacion
        FROM actividades WHERE usuario_asignado_id=? AND estado='pendiente' AND (creado_por_rol='admin' OR creado_por_rol IS NULL)
        ORDER BY fecha_creacion DESC""", (session['user_id'],)).fetchall()
    notificaciones = []
    for n in notifs:
        n = dict(n)
        n['materiales'] = [dict(m) for m in conn.execute("""SELECT m.nombre,am.cantidad FROM actividad_materiales am JOIN materiales m ON am.material_id=m.id WHERE am.actividad_id=?""", (n['id'],)).fetchall()]
        notificaciones.append(n)
    conn.close()
    return render_template('panel_usuario.html', materiales=mats_asignados, usuario=session['usuario'], notificaciones=notificaciones)

# ══════════════════════════════════════════════
# VER / FIRMAR ACTA
# ══════════════════════════════════════════════
@app.route('/acta/<int:acta_id>')
def ver_acta(acta_id):
    if not session.get('usuario'): return redirect(url_for('inicio'))
    conn = get_db()
    acta = get_acta_completa(conn, acta_id, session['user_id'])
    conn.close()
    if not acta: return redirect(url_for('usuario_panel'))
    return render_template('firmar_acta.html', acta=acta, usuario=session['usuario'])

@app.route('/firmar_acta/<int:acta_id>', methods=['POST'])
def firmar_acta(acta_id):
    if not session.get('usuario'): return redirect(url_for('inicio'))
    firma = request.form.get('firma')
    conn = get_db()
    a = conn.execute("SELECT * FROM actividades WHERE id=? AND usuario_asignado_id=?", (acta_id, session['user_id'])).fetchone()
    if a and a['estado'] == 'pendiente':
        conn.execute("UPDATE actividades SET firma_imagen=?,estado='firmado',fecha_firmado=? WHERE id=?",
                     (firma, datetime.now().strftime("%Y-%m-%d %H:%M"), acta_id))
        conn.commit()
    conn.close()
    return redirect(url_for('mis_actas'))

# ══════════════════════════════════════════════
# MIS ACTAS USUARIO
# ══════════════════════════════════════════════
@app.route('/mis_actas')
def mis_actas():
    if not session.get('usuario'): return redirect(url_for('inicio'))
    conn = get_db()
    acts = conn.execute("SELECT id,nombre,descripcion,estado,fecha_creacion,fecha_firmado,creado_por_rol FROM actividades WHERE usuario_asignado_id=? ORDER BY fecha_creacion DESC", (session['user_id'],)).fetchall()
    result = []
    for a in acts:
        a = dict(a)
        a['materiales'] = [dict(m) for m in conn.execute("""SELECT m.nombre,am.cantidad FROM actividad_materiales am JOIN materiales m ON am.material_id=m.id WHERE am.actividad_id=?""", (a['id'],)).fetchall()]
        result.append(a)
    conn.close()
    return render_template('mis_actas.html', actas=result, usuario=session['usuario'])

# ══════════════════════════════════════════════
# DESCARGAR PDF (solo admin, actas firmadas)
# ══════════════════════════════════════════════
@app.route('/descargar_pdf/<int:acta_id>')
def descargar_pdf(acta_id):
    if session.get('rol') != 'admin': return redirect(url_for('inicio'))
    conn = get_db()
    acta = get_acta_completa(conn, acta_id)
    conn.close()
    if not acta or acta['estado'] != 'firmado':
        return "Acta no disponible", 404

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    azul   = colors.HexColor('#3a56d4')
    gris   = colors.HexColor('#f4f6fb')
    borde  = colors.HexColor('#e1e8ef')

    title_style = ParagraphStyle('title', parent=styles['Heading1'],
                                 textColor=colors.white, fontSize=18,
                                 spaceAfter=0, alignment=TA_CENTER, fontName='Helvetica-Bold')
    label_style = ParagraphStyle('label', parent=styles['Normal'],
                                 textColor=colors.HexColor('#6b7280'), fontSize=8,
                                 fontName='Helvetica-Bold', spaceAfter=2)
    value_style = ParagraphStyle('value', parent=styles['Normal'],
                                 fontSize=11, fontName='Helvetica', spaceAfter=8)
    section_style = ParagraphStyle('section', parent=styles['Normal'],
                                   textColor=azul, fontSize=12, fontName='Helvetica-Bold',
                                   spaceAfter=6, spaceBefore=12)

    story = []

    # ── Encabezado azul
    header_data = [[Paragraph('ACTA DE ACTIVIDAD — BITWAN', title_style)]]
    header_table = Table(header_data, colWidths=[17*cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), azul),
        ('ROUNDEDCORNERS', [10]),
        ('TOPPADDING',    (0,0), (-1,-1), 18),
        ('BOTTOMPADDING', (0,0), (-1,-1), 18),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.5*cm))

    # ── Datos generales
    story.append(Paragraph('DATOS DE LA ACTIVIDAD', section_style))
    info_data = [
        [Paragraph('ACTIVIDAD', label_style), Paragraph(acta['nombre'], value_style)],
        [Paragraph('ASIGNADA A', label_style), Paragraph(acta['nombre_usuario'], value_style)],
        [Paragraph('FECHA CREACIÓN', label_style), Paragraph(acta['fecha_creacion'], value_style)],
        [Paragraph('FECHA FIRMA', label_style), Paragraph(acta.get('fecha_firmado','—'), value_style)],
    ]
    info_table = Table(info_data, colWidths=[4*cm, 13*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (0,-1), gris),
        ('GRID',          (0,0), (-1,-1), 0.5, borde),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.3*cm))

    # ── Descripción
    story.append(Paragraph('DESCRIPCIÓN', section_style))
    desc_data = [[Paragraph(acta['descripcion'], value_style)]]
    desc_table = Table(desc_data, colWidths=[17*cm])
    desc_table.setStyle(TableStyle([
        ('GRID',          (0,0), (-1,-1), 0.5, borde),
        ('BACKGROUND',    (0,0), (-1,-1), gris),
        ('TOPPADDING',    (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
    ]))
    story.append(desc_table)
    story.append(Spacer(1, 0.3*cm))

    # ── Materiales
    if acta['materiales']:
        story.append(Paragraph('MATERIALES UTILIZADOS', section_style))
        mat_rows = [[Paragraph('Material', ParagraphStyle('th', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.white)),
                     Paragraph('Cantidad', ParagraphStyle('th', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.white, alignment=TA_CENTER))]]
        for m in acta['materiales']:
            mat_rows.append([Paragraph(m['nombre'], value_style),
                             Paragraph(str(m['cantidad']), ParagraphStyle('c', parent=styles['Normal'], fontSize=11, alignment=TA_CENTER))])
        mat_table = Table(mat_rows, colWidths=[13*cm, 4*cm])
        mat_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), azul),
            ('BACKGROUND',    (0,1), (-1,-1), gris),
            ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, gris]),
            ('GRID',          (0,0), (-1,-1), 0.5, borde),
            ('TOPPADDING',    (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING',   (0,0), (-1,-1), 10),
            ('ALIGN',         (1,0), (1,-1), 'CENTER'),
        ]))
        story.append(mat_table)
        story.append(Spacer(1, 0.3*cm))

    # ── Firma del usuario
    story.append(Paragraph('FIRMA DEL TRABAJADOR', section_style))
    firma_row_content = []
    if acta.get('firma_imagen') and acta['firma_imagen'].startswith('data:image'):
        img_data = base64.b64decode(acta['firma_imagen'].split(',')[1])
        img_buf  = io.BytesIO(img_data)
        rl_img   = RLImage(img_buf, width=7*cm, height=2.5*cm)
        firma_row_content.append(rl_img)
    else:
        firma_row_content.append(Paragraph('Sin firma', value_style))

    firma_data = [[firma_row_content[0],
                   Paragraph(f"<b>{acta['nombre_usuario']}</b><br/>Firmado digitalmente<br/>{acta.get('fecha_firmado','')}", value_style)]]
    firma_table = Table(firma_data, colWidths=[9*cm, 8*cm])
    firma_table.setStyle(TableStyle([
        ('GRID',          (0,0), (-1,-1), 0.5, borde),
        ('BACKGROUND',    (0,0), (-1,-1), gris),
        ('TOPPADDING',    (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(firma_table)
    story.append(Spacer(1, 0.5*cm))

    # ── Espacio firma coordinador (para imprimir y firmar a mano)
    story.append(Paragraph('FIRMA DEL JEFE / COORDINADOR', section_style))
    coord_data = [[
        Paragraph('Nombre: ___________________________________', value_style),
        Paragraph('Firma: ___________________________________',  value_style),
    ],[
        Paragraph('Cargo: ___________________________________',  value_style),
        Paragraph('Fecha: ___________________________________',  value_style),
    ]]
    coord_table = Table(coord_data, colWidths=[8.5*cm, 8.5*cm])
    coord_table.setStyle(TableStyle([
        ('GRID',          (0,0), (-1,-1), 0.5, borde),
        ('BACKGROUND',    (0,0), (-1,-1), colors.white),
        ('TOPPADDING',    (0,0), (-1,-1), 18),
        ('BOTTOMPADDING', (0,0), (-1,-1), 18),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
    ]))
    story.append(coord_table)

    # ── Pie
    story.append(Spacer(1, 0.4*cm))
    pie = ParagraphStyle('pie', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#9ca3af'), alignment=TA_CENTER)
    story.append(Paragraph(f'Documento generado el {datetime.now().strftime("%Y-%m-%d %H:%M")} — Sistema Bitwan', pie))

    doc.build(story)
    buf.seek(0)
    nombre_archivo = f"Acta_{acta['nombre'].replace(' ','_')}_{acta_id}.pdf"
    return send_file(buf, as_attachment=True, download_name=nombre_archivo, mimetype='application/pdf')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
