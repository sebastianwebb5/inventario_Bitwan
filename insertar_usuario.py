import sqlite3

conexion = sqlite3.connect('bitwan.db')

cursor = conexion.cursor()

usuarios = [

    ('sebastian', '1234', 'admin'),

    ('juan', '1111', 'usuario'),

    ('carlos', '2222', 'usuario'),
    
    ('kely', '5555', 'usuario')

]

cursor.executemany('''
INSERT INTO usuarios (usuario, password, rol)
VALUES (?, ?, ?)
''', usuarios)

conexion.commit()

print("Usuarios creados correctamente 🔥")

conexion.close()
