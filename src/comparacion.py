import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- CONFIGURACIÓN DE RUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "sistema_de_control_horas.db"))
ARCHIVO_ASISTENCIA = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "huellero_limpio.xlsx"))
UMBRAL_SEMANAL = 44.0

def cargar_datos_db(fecha_inicio, fecha_fin):
    """Extrae la programación y maestros de turnos de la DB."""
    conn = sqlite3.connect(DATABASE_PATH)
    
    # Query para traer programación con los datos del turno asociados
    query = f"""
    SELECT 
        p.empleado_id, 
        e.nombre, 
        p.fecha, 
        p.turno_id,
        t.ht as ht_maestro,
        t.descripcion, 
        t.t_comida as comida_maestro,
        t.descanso as es_descanso
    FROM programacion p
    JOIN employees e ON p.empleado_id = e.id
    JOIN turnos t ON p.turno_id = t.turno_id
    WHERE p.fecha BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    """
    df_prog = pd.read_sql_query(query, conn)
    conn.close()
    return df_prog

def ejecutar_comparacion(fecha_inicio, fecha_fin):
    print(f"🔍 Iniciando comparación...")
    
    df_expectativa = cargar_datos_db(fecha_inicio, fecha_fin)
    df_expectativa['fecha'] = pd.to_datetime(df_expectativa['fecha']).dt.date

    if not os.path.exists(ARCHIVO_ASISTENCIA):
        print("❌ Error: Falta huellero_limpio.xlsx")
        return None
    
    df_realidad = pd.read_excel(ARCHIVO_ASISTENCIA)
    df_realidad['fecha'] = pd.to_datetime(df_realidad['fecha']).dt.date
    df_realidad = df_realidad.rename(columns={'nombre': 'nombre_huellero'})

    df_final = pd.merge(df_expectativa, df_realidad, 
                        left_on=['empleado_id', 'fecha'], 
                        right_on=['nombre_huellero', 'fecha'], 
                        how='left')

    resultados = []
    import re

    for empleado, grupo in df_final.groupby('nombre'):
        horas_ordinarias_semana = 0
        temp_resultados_empleado = [] # Guardamos temporalmente para aplicar las 44h luego
        
        for row in grupo.itertuples():
            # 1. Extraer Hora Programada
            hora_entrada_prog = None
            try:
                match = re.search(r'(\d{1,2})[\.:](\d{2})', str(row.descripcion))
                if match:
                    h, m = match.groups()
                    hora_entrada_prog = f"{int(h):02d}:{m}:00"
            except:
                hora_entrada_prog = None

            # 2. Datos de horas
            horas_reales = getattr(row, 'horas_trabajadas', 0)
            if pd.isna(horas_reales): horas_reales = 0
            
            ht_maestro = row.ht_maestro
            es_descanso = row.es_descanso
            
            # Lógica 44h (Regla de las 9h)
            limite_diario = max(9.0, ht_maestro)
            ord_dia = min(horas_reales, limite_diario)
            extra_dia = max(0, horas_reales - limite_diario)
            horas_ordinarias_semana += ord_dia
            
            # Observaciones
            observacion = "OK"
            if es_descanso == 1 and horas_reales > 0:
                observacion = "TRABAJÓ EN DESCANSO"
            elif es_descanso == 0 and horas_reales == 0:
                observacion = "FALTA / NO MARCÓ"
            
            temp_resultados_empleado.append({
                'nombre': empleado,
                'fecha': row.fecha,
                'turno_id': row.turno_id,
                'descripcion': row.descripcion,
                'entrada_prog': hora_entrada_prog,
                'entrada_real': getattr(row, 'entrada', None),
                'HT_Prog': ht_maestro,
                'Horas_Reales': horas_reales,
                'Ord_Dia': ord_dia,
                'Extra_Dia': extra_dia,
                'Obs': observacion,
                'Alerta_44h': "No" # Default
            })

        # 3. Aplicar alerta de 44h a los registros de este empleado
        alerta = f"SÍ ({round(horas_ordinarias_semana, 2)}h)" if horas_ordinarias_semana > UMBRAL_SEMANAL else "No"
        for res in temp_resultados_empleado:
            res['Alerta_44h'] = alerta
            resultados.append(res)

    df_reporte = pd.DataFrame(resultados)
    output_path = os.path.join(BASE_DIR, "..", "data", "reporte_discrepancias.xlsx")
    df_reporte.to_excel(output_path, index=False)
    
    return df_reporte