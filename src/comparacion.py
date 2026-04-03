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
    print(f"🔍 Iniciando comparación desde {fecha_inicio} hasta {fecha_fin}...")
    
    # 1. Cargar Programación (Expectativa)
    df_expectativa = cargar_datos_db(fecha_inicio, fecha_fin)
    df_expectativa['fecha'] = pd.to_datetime(df_expectativa['fecha']).dt.date

    # 2. Cargar Asistencia (Realidad - Procesada por procesador.py)
    if not os.path.exists(ARCHIVO_ASISTENCIA):
        print("❌ Error: No se encuentra 'huellero_limpio.xlsx'. Ejecuta procesador.py primero.")
        return
    
    df_realidad = pd.read_excel(ARCHIVO_ASISTENCIA)
    df_realidad['fecha'] = pd.to_datetime(df_realidad['fecha']).dt.date
    # Renombrar columna de nombre para evitar conflictos si el ID es el que manda
    df_realidad = df_realidad.rename(columns={'nombre': 'nombre_huellero'})

    # 3. Cruzar ambos mundos (Merge)
    # Nota: Usamos Left Join para detectar si alguien tenía turno y NO marcó
    df_final = pd.merge(
        df_expectativa, 
        df_realidad, 
        left_on=['empleado_id', 'fecha'], 
        right_on=['nombre_huellero', 'fecha'], # Asumiendo que procesador.py usa el ID/Nombre en esa col
        how='left'
    )

    # 4. Aplicar Lógica de Negocio
    resultados = []
    
    # Agrupamos por empleado para el cálculo de las 44h
    for empleado, grupo in df_final.groupby('nombre'):
        horas_ordinarias_semana = 0
        
        for row in grupo.itertuples():
            # Datos base
            horas_reales = getattr(row, 'horas_trabajadas', 0)
            if pd.isna(horas_reales): horas_reales = 0
            
            ht_maestro = row.ht_maestro
            es_descanso = row.es_descanso
            
            # --- REGLA DE LAS 9 HORAS ---
            # El límite es 9 o lo que diga el turno si es más largo (ej. 11h)
            limite_diario = max(9.0, ht_maestro)
            
            ord_dia = min(horas_reales, limite_diario)
            extra_dia = max(0, horas_reales - limite_diario)
            
            horas_ordinarias_semana += ord_dia
            
            # --- ALERTAS ---
            observacion = "OK"
            if es_descanso == 1 and horas_reales > 0:
                observacion = "TRABAJÓ EN DESCANSO"
            elif es_descanso == 0 and horas_reales == 0:
                observacion = "FALTA / NO MARCÓ"
            
            resultados.append({
                'Empleado': empleado,
                'Fecha': row.fecha,
                'Turno': row.turno_id,
                'HT_Prog': ht_maestro,
                'Horas_Reales': horas_reales,
                'Ord_Dia': ord_dia,
                'Extra_Dia': extra_dia,
                'Obs': observacion
            })
            
        # 5. Aplicar Alerta de 44 horas al final de la semana para este empleado
        if horas_ordinarias_semana > UMBRAL_SEMANAL:
            for res in resultados:
                if res['Empleado'] == empleado:
                    res['Alerta_44h'] = f"SÍ ({horas_ordinarias_semana}h)"
        else:
            for res in resultados:
                if res['Empleado'] == empleado:
                    res['Alerta_44h'] = "No"

    # 6. Exportar Reporte de Discrepancias
    df_reporte = pd.DataFrame(resultados)
    output_path = os.path.join(BASE_DIR, "..", "data", "reporte_discrepancias.xlsx")
    df_reporte.to_excel(output_path, index=False)
    
    print(f"✅ Reporte generado en: {output_path}")
    return df_reporte

if __name__ == "__main__":
    # Ejemplo de uso con fechas (esto vendrá de tu Streamlit)
    ejecutar_comparacion('2026-03-30', '2026-04-05')