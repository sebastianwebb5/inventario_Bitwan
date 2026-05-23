import sqlite3

conexion = sqlite3.connect('bitwan.db')
cursor = conexion.cursor()

cursor.execute("SELECT * FROM usuarios")

usuarios = cursor.fetchall()

for usuario in usuarios:
    print(usuario)

conexion.close()
