import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

# =========================
# 🔧 CREAR BASE DE DATOS
# =========================
def init_db():
    conexion = sqlite3.connect("bitwan.db")
    cursor = conexion.cursor()

    # TABLA USUARIOS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL,
        password TEXT NOT NULL,
        rol TEXT NOT NULL
    )
    """)

    # TABLA MATERIALES
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS materiales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        cantidad INTEGER NOT NULL
    )
    """)

    conexion.commit()
    conexion.close()
    print("✅ Base de datos lista")

# =========================
# 🏠 RUTA BODEGA
# =========================
@app.route("/bodega")
def bodega():
    conexion = sqlite3.connect("bitwan.db")
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM materiales")
    materiales = cursor.fetchall()

    conexion.close()

    return render_template("bodega.html", materiales=materiales)

# =========================
# 🚀 INICIAR APP
# =========================
if __name__ == "__main__":
    init_db()  # 👈 CLAVE: crea tablas antes de arrancar Flask
    app.run(debug=True)