import sqlite3
import os

# --- CONFIGURACIÓN DE RUTA ABSOLUTA ---
# Esto obtiene la ruta de la carpeta 'src'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Esto sube un nivel a la raíz del proyecto y entra en 'data'
DATABASE_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "sistema_de_control_horas.db"))

print(f"DEBUG: Python está leyendo este archivo: {DATABASE_PATH}")
# --------------------------------------

def get_connection():
    """Establece conexión con la DB y activa llaves foráneas."""
    # Verificamos si el archivo existe antes de conectar
    if not os.path.exists(DATABASE_PATH):
        print(f"⚠️ ALERTA: El archivo no existe en {DATABASE_PATH}. Se creará uno vacío.")
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON;") 
    return conn

def init_db():
    """Crea el esquema de tablas inicial."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Tabla de Empleados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            cedula TEXT UNIQUE NOT NULL
        )
    ''')

    # 2. Tabla de Turnos (Tu fuente de verdad)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS turnos (
            turno_id TEXT PRIMARY KEY,
            descripcion TEXT,
            t_comida REAL,
            ht REAL,
            rn REAL,
            t_partido INTEGER DEFAULT 0,
            descanso INTEGER DEFAULT 0,
            hed REAL DEFAULT 0,
            hefd REAL DEFAULT 0
        )
    ''')

    # 3. Tabla de Programación (La unión de ambos)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS programacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER,
            fecha DATE NOT NULL,
            turno_id TEXT,
            FOREIGN KEY (empleado_id) REFERENCES employees(id),
            FOREIGN KEY (turno_id) REFERENCES turnos(turno_id),
            UNIQUE(empleado_id, fecha)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Base de datos '{os.path.basename(DATABASE_PATH)}' inicializada en /data.")

# --- FUNCIONES DE LECTURA Y ESCRITURA ---

def obtener_todos_empleados():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, cedula FROM employees ORDER BY nombre ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def obtener_todos_turnos():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM turnos")
    rows = cursor.fetchall()
    conn.close()
    return rows

def guardar_programacion(empleado_id, fecha, turno_id):
    """Guarda o actualiza un turno. Si el empleado ya tiene turno ese día, lo sobreescribe."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO programacion (empleado_id, fecha, turno_id)
            VALUES (?, ?, ?)
            ON CONFLICT(empleado_id, fecha) DO UPDATE SET turno_id = excluded.turno_id
        ''', (empleado_id, fecha, turno_id))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error al guardar programación: {e}")
    finally:
        conn.close()

def guardar_asistencia_incremental(df):
    """Guarda o actualiza las marcas del huellero en la DB."""
    conn = get_connection()
    cursor = conn.cursor()
    
    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO asistencia_procesada (id_empleado, fecha, entrada, salida, horas_trabajadas, obs)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id_empleado, fecha) DO UPDATE SET
                entrada=excluded.entrada,
                salida=excluded.salida,
                horas_trabajadas=excluded.horas_trabajadas,
                obs=excluded.obs
        """, (str(row['id_empleado']), row['fecha'], str(row['entrada']), 
              str(row['salida']), row['horas_trabajadas'], row['Obs']))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()