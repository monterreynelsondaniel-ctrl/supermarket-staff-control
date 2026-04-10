import pandas as pd
import sqlite3
import os
import re
from datetime import datetime

# --- CONFIGURACIÓN ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "sistema_de_control_horas.db"))

def cargar_datos_db(fecha_inicio, fecha_fin):
    """Extrae la programación con TODAS las columnas de la tabla turnos."""
    conn = sqlite3.connect(DATABASE_PATH)
    # IMPORTANTE: Aquí traemos columnas HED, RN, T_PARTIDO, etc.
    query = f"""
    SELECT 
        p.empleado_id, e.nombre, p.fecha, p.turno_id,
        t.descripcion, t.ht, t.rn, t.hed, t.hefd, t.rfn, 
        t.t_partido, t.descanso as es_descanso
    FROM programacion p
    JOIN employees e ON p.empleado_id = e.id
    JOIN turnos t ON p.turno_id = t.turno_id
    WHERE p.fecha BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    """
    df_prog = pd.read_sql_query(query, conn)
    conn.close()
    return df_prog

def ejecutar_comparacion(fecha_inicio, fecha_fin, df_huellero=None):
    df_expectativa = cargar_datos_db(fecha_inicio, fecha_fin)
    df_expectativa['fecha'] = pd.to_datetime(df_expectativa['fecha']).dt.date

    if df_huellero is None:
        path_huellero = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "huellero_limpio.xlsx"))
        if not os.path.exists(path_huellero): return None
        df_realidad = pd.read_excel(path_huellero)
    else:
        df_realidad = df_huellero.copy()

    df_realidad['fecha'] = pd.to_datetime(df_realidad['fecha']).dt.date
    
    # IMPORTANTE: Aseguramos que los IDs sean strings para evitar errores de tipo
    df_expectativa['empleado_id'] = df_expectativa['empleado_id'].astype(str)
    df_realidad['id_empleado'] = df_realidad['id_empleado'].astype(str)

    df_final = pd.merge(df_expectativa, df_realidad, 
                        left_on=['empleado_id', 'fecha'], 
                        right_on=['id_empleado', 'fecha'], 
                        how='left')

    resultados = []
    for row in df_final.itertuples():
        # getattr con default 0.0 por si la columna no existe o es NaN
        h_reales = getattr(row, 'horas_trabajadas', 0.0)
        if pd.isna(h_reales): h_reales = 0.0
        
        ht_turno = float(row.ht)
        
        # Ajuste base
        ajuste = round(h_reales - ht_turno, 2)
        
        # Lógica de estados especiales
        obs = "OK"
        # Incluimos C_V (Vacaciones en algunos de tus turnos) y Q (Calamidad)
        if str(row.turno_id).strip().upper() in ['V', 'Q', 'C_V', 'VACACIONES']:
            ajuste = 0.0
            h_reales = ht_turno # Para que SHT Completas cuadre
            obs = "AUTORIZADO"
        elif row.es_descanso == 1:
            if h_reales > 0:
                obs = "TRABAJÓ EN DESCANSO"
                ajuste = h_reales # Todo es ganancia en descanso
            else:
                ajuste = 0.0
                obs = "DESCANSO"
        elif h_reales == 0:
            obs = "FALTA / NO MARCÓ"

        resultados.append({
            'nombre': row.nombre,
            'fecha': row.fecha,
            'turno_id': row.turno_id,
            'HT': ht_turno,
            'HORAS_REALES': h_reales,
            'AJUSTE': ajuste,
            'HED': row.hed,
            'RN': row.rn,
            'HEFD': row.hefd,
            'T_PARTIDO': row.t_partido,
            'DESCANSOS': row.es_descanso,
            'Obs': obs,
            'SHT_COMPLETAS': round(ht_turno + ajuste, 2)
        })

    return pd.DataFrame(resultados)