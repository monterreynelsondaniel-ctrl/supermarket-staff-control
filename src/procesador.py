import pandas as pd
from datetime import datetime, timedelta

def calcular_diferencia_horas(entrada, salida):
    """Calcula la diferencia entre dos objetos datetime en horas decimales."""
    if salida < entrada:
        salida += timedelta(days=1)
    return (salida - entrada).total_seconds() / 3600

def procesar_marcas_huellero(df_datos):
    """
    Toma el DataFrame crudo del CSV y devuelve un DataFrame limpio con 
    horas calculadas por empleado y día.
    """
    # 1. Limpieza inicial
    df_datos['datetime'] = pd.to_datetime(df_datos['Time'], errors='coerce')
    df_datos = df_datos.dropna(subset=['datetime'])
    
    # Limpiar el Person ID (quitar comillas y espacios)
    df_datos['Person ID'] = df_datos['Person ID'].astype(str).str.replace("'", "").str.strip()
    
    # Ordenar cronológicamente
    df_datos = df_datos.sort_values(['Person ID', 'datetime'])
    
    resultados = []
    MAX_JORNADA_HORAS = 16

    # 2. Agrupar por empleado para procesar sus marcas
    for pid, grupo in df_datos.groupby('Person ID'):
        nombre_empleado = grupo['Name'].iloc[0]
        turnos_empleado = []
        jornada_actual = None
        break_inicio = None
        
        for row in grupo.itertuples():
            # row._5 corresponde a la columna 'Attendance Status' según tu script original
            evento = str(row._5).strip() 
            tiempo = row.datetime
            
            # --- Lógica de Descansos (Breaks) ---
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
                    # Si ya había una entrada sin salida, verificamos si cerramos la anterior
                    horas = calcular_diferencia_horas(jornada_actual['entrada'], tiempo)
                    if horas >= 1: # Si pasó más de una hora, asumimos que la anterior fue salida
                        horas_break = sum([calcular_diferencia_horas(b[0], b[1]) for b in jornada_actual['breaks']])
                        
                        turnos_empleado.append({
                            'person_id': pid,
                            'nombre': nombre_empleado,
                            'fecha': jornada_actual['entrada'].date(),
                            'entrada': jornada_actual['entrada'].time(),
                            'salida': tiempo.time(),
                            'horas_break': round(horas_break, 2),
                            'horas_trabajadas': round(horas - horas_break, 2),
                            'estado': 'CHECKIN_COMO_SALIDA'
                        })
                        jornada_actual = {'entrada': tiempo, 'breaks': []}
                continue
                
            # --- Lógica de Salida (Check-out) ---
            if evento == 'Check-out':
                if jornada_actual is None:
                    turnos_empleado.append({
                        'person_id': pid, 'nombre': nombre_empleado, 'fecha': tiempo.date(),
                        'entrada': None, 'salida': tiempo.time(), 'horas_break': 0,
                        'horas_trabajadas': 0, 'estado': 'SOLO_SALIDA'
                    })
                    continue
                
                # Cerrar jornada normal
                horas_totales = calcular_diferencia_horas(jornada_actual['entrada'], tiempo)
                horas_break = sum([calcular_diferencia_horas(b[0], b[1]) for b in jornada_actual['breaks']])
                horas_trabajadas = round(horas_totales - horas_break, 2)
                
                estado = 'OK' if 0 <= horas_trabajadas <= MAX_JORNADA_HORAS else 'ERROR_JORNADA_EXTREMA'
                
                turnos_empleado.append({
                    'person_id': pid,
                    'nombre': nombre_empleado,
                    'fecha': jornada_actual['entrada'].date(),
                    'entrada': jornada_actual['entrada'].time(),
                    'salida': tiempo.time(),
                    'horas_break': round(horas_break, 2),
                    'horas_trabajadas': horas_trabajadas,
                    'estado': estado
                })
                jornada_actual = None
        
        # Guardar si quedó una jornada abierta al final del archivo
        if jornada_actual:
            turnos_empleado.append({
                'person_id': pid, 'nombre': nombre_empleado, 'fecha': jornada_actual['entrada'].date(),
                'entrada': jornada_actual['entrada'].time(), 'salida': None,
                'horas_break': 0, 'horas_trabajadas': 0, 'estado': 'SIN_SALIDA'
            })
            
        if turnos_empleado:
            resultados.append(pd.DataFrame(turnos_empleado))

    if not resultados:
        return pd.DataFrame()
        
    return pd.concat(resultados, ignore_index=True)