import pandas as pd
from datetime import datetime, timedelta

def calcular_diferencia_horas(entrada, salida):
    """Calcula la diferencia entre dos objetos datetime en horas decimales."""
    if salida < entrada:
        salida += timedelta(days=1)
    return (salida - entrada).total_seconds() / 3600

import pandas as pd
from datetime import datetime

def calcular_diferencia_horas(inicio, fin):
    """Auxiliar para restar datetimes y obtener float de horas."""
    if not inicio or not fin: return 0
    diferencia = fin - inicio
    return diferencia.total_seconds() / 3600

def procesar_marcas_huellero(df_datos):
    """
    Toma el DataFrame crudo del CSV y devuelve un DataFrame limpio.
    """
    # 1. Limpieza inicial
    # Asegúrate que la columna del CSV se llame 'Time' y 'Attendance Status'
    df_datos['datetime'] = pd.to_datetime(df_datos['Time'], errors='coerce')
    df_datos = df_datos.dropna(subset=['datetime'])
    
    # Limpiar ID: quitar comillas de los strings si vienen como "'123'"
    df_datos['Person ID'] = df_datos['Person ID'].astype(str).str.replace("'", "").str.strip()
    
    # Ordenar por persona y tiempo para que el loop tenga sentido
    df_datos = df_datos.sort_values(['Person ID', 'datetime'])
    
    resultados_globales = []
    MAX_JORNADA_HORAS = 16

    # 2. Procesar por empleado
    for pid, grupo in df_datos.groupby('Person ID'):
        nombre_empleado = grupo['Name'].iloc[0]
        turnos_empleado = []
        jornada_actual = None
        break_inicio = None
        
        for row in grupo.itertuples():
            # Nota: Si el CSV cambia de orden, usa row.Attendance_Status o el nombre exacto
            evento = str(getattr(row, 'Attendance Status', '')).strip() 
            tiempo = row.datetime
            
            # --- Lógica de Descansos ---
            if evento == 'Break-Out' and jornada_actual:
                break_inicio = tiempo
                continue
            
            if evento == 'Break-In' and jornada_actual and break_inicio:
                jornada_actual['breaks'].append((break_inicio, tiempo))
                break_inicio = None
                continue
                
            # --- Lógica de Entrada (Check-in) ---
            if evento == 'Check-in':
                if jornada_actual is None:
                    jornada_actual = {'entrada': tiempo, 'breaks': []}
                else:
                    # Caso: Marcó entrada dos veces. Cerramos la anterior automáticamente.
                    horas = calcular_diferencia_horas(jornada_actual['entrada'], tiempo)
                    if horas >= 1: 
                        turnos_empleado.append({
                            'id_empleado': pid,
                            'nombre': nombre_empleado,
                            'fecha': jornada_actual['entrada'].date(),
                            'entrada': jornada_actual['entrada'].time(),
                            'salida': tiempo.time(),
                            'horas_trabajadas': round(horas, 2),
                            'Obs': 'CHECKIN_AUTO_CIERRE'
                        })
                    jornada_actual = {'entrada': tiempo, 'breaks': []}
                continue
                
            # --- Lógica de Salida (Check-out) ---
            if evento == 'Check-out':
                if jornada_actual is None:
                    # Caso: Salida sin entrada previa
                    turnos_empleado.append({
                        'id_empleado' : pid, 
                        'nombre': nombre_empleado, 'fecha': tiempo.date(),
                        'entrada': None, 'salida': tiempo.time(),
                        'horas_trabajadas': 0, 'Obs': 'SOLO_SALIDA'
                    })
                    continue
                
                horas_totales = calcular_diferencia_horas(jornada_actual['entrada'], tiempo)
                horas_break = sum([calcular_diferencia_horas(b[0], b[1]) for b in jornada_actual['breaks']])
                horas_trabajadas = round(horas_totales - horas_break, 2)
                
                turnos_empleado.append({
                    'id_empleado': pid,
                    'nombre': nombre_empleado,
                    'fecha': jornada_actual['entrada'].date(),
                    'entrada': jornada_actual['entrada'].time(),
                    'salida': tiempo.time(),
                    'horas_trabajadas': horas_trabajadas,
                    'Obs': 'OK' if horas_trabajadas <= MAX_JORNADA_HORAS else 'JORNADA_EXTREMA'
                })
                jornada_actual = None
        
        # Guardar jornada huérfana (Entrada sin salida al final del día)
        if jornada_actual:
            turnos_empleado.append({
                'id_empleado': pid,
                'nombre': nombre_empleado, 'fecha': jornada_actual['entrada'].date(),
                'entrada': jornada_actual['entrada'].time(), 'salida': None,
                'horas_trabajadas': 0, 'Obs': 'SIN_SALIDA'
            })
            
        if turnos_empleado:
            resultados_globales.extend(turnos_empleado)

    # 3. Retorno de DataFrame Consolidado
    if not resultados_globales:
        return pd.DataFrame(columns=['nombre', 'fecha', 'entrada', 'salida', 'horas_trabajadas', 'Obs'])
        
    return pd.DataFrame(resultados_globales)