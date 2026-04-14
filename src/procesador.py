import pandas as pd
from datetime import datetime, timedelta

def calcular_diferencia_horas(entrada, salida):
    if not entrada or not salida:
        return 0
    # esta parte es para manejar casos donde la salida es al día siguiente (dias de inventario)
    if salida < entrada:
        salida += timedelta(days=1)
    return (salida - entrada).total_seconds() / 3600

def lipiar_dataframe(df_datos):
    """NORMALIZACION DE DATOS Y LIMPIEZA
    RETORNA DATAFRAME LIMPIO Y NORMALIZADO
    Y LISTA DE ERRORES DETECTADOS
    """
    errores = [] #esta lista de errores, la vamos a mostrar pero vamos a ignorar esos registros al momento de hacer calculos
    df = df_datos.copy()
    df['Person ID'] = df['Person ID'].astype(str).str.replace("'", "").str.strip()

    # filtrar persons ID INVALIDOS (VACIOS, ,NAN, NONE)
    mascara_invalidos = df['Person ID'].isin(['', 'nan', 'None', 'NaN', 'none'])
    if mascara_invalidos.any():
        errores.append(f" Se ignoraron {mascara_invalidos.sum()} registros con Person ID inválidos.")
        df = df[~mascara_invalidos]#tomamos los True e ignaramos los False

    # Convertir fechas
    df['datetime'] = pd.to_datetime(df['Time'], errors='coerce')#si falla la conversion devuelve NaT
    mascara_fechas_invalidas = df['datetime'].isna()
    if mascara_fechas_invalidas.any():
        errores.append(f" Se ignoraron {mascara_fechas_invalidas.sum()} registros con fechas inválidas.")
        df = df[~mascara_fechas_invalidas]#tomamos los True e ignaramos los False

    df = df.sort_values(by=['Person ID', 'datetime'])
    return df, errores

def procesar_empleado(pid, grupo, max_jornada_horas=14):

    turnos = []
    eventos_ignorados = []
    nombre_empleado = grupo['Name'].iloc[0]

    jornada_actual = None
    break_inicio = None

    eventos_conocidos = {'Check-in', 'Cheak-out', 'Break-in', 'Break-Out'}

    #buscamos cada fila por empleado, en la columnna  Attendance Status si no hay nada dejamos un espacio en blanco, 
    #pero si hay algo lo convertimos a string y lo limpiamos de espacios
    for row in grupo.intertuples():
        evento = str(getattr(row, 'Attendance Status', '')).strip()
        tiempo = row.datetime
        
        if evento not in eventos_conocidos:
            eventos_ignorados.append({'fecha': tiempo.date(), 'hora': tiempo.time(), 'evento': evento or 'VACÍO'})
            continue

        # BREAK-OUT
        if evento == 'Break-Out':
            if jornada_actual:
                break_inicio = tiempo
            else:
                eventos_ignorados.append({'fecha': tiempo.date(), 'hora': tiempo.time(), 'evento': 'Break-Out sin jornada'})
            continue

        # BREAK-IN
        if evento == 'Break-in':
            if jornada_actual and break_inicio:
                jornada_actual['breaks'].append((break_inicio, tiempo))
                break_inicio = None
            else:
                eventos_ignorados.append({'fecha': tiempo.date(), 'hora': tiempo.time(), 'evento': 'Break-in sin jornada o sin break-out'})
            continue

        # --- Check-in ---
        if evento == 'Check-in':
            if jornada_actual is None:
              jornada_actual = {'entrada': tiempo, 'breaks': [], 'conflictos': []}
            else:
                # REGLA DE NEGOCIO: El empleado ya tenía una entrada abierta. 
                horas_desde_entrada = calcular_diferencia_horas(jornada_actual['entrada'], tiempo)
                
                # Si es el mismo día, lo guardamos como un "evento extraño" dentro de la misma jornada
                if jornada_actual['entrada'].date() == tiempo.date():
                    jornada_actual['conflictos'].append(f"Check-in duplicado a las {tiempo.time()}")
                  # No hacemos nada más, el bucle sigue buscando un Check-out o Break.
                else:
                    # Si es otro día, aquí sí hubo un olvido total de salida del día anterior.
                    # Hacemos el cierre de la jornada vieja como 'INCOMPLETA'
                    turnos.append({
                        'id_empleado': pid,
                        'nombre': nombre_empleado,
                        'fecha': jornada_actual['entrada'].date(),
                        'entrada': jornada_actual['entrada'].time(),
                        'salida': None,
                        'horas_trabajadas': 0,
                        'Obs': 'OLVIDÓ_SALIDA_DIA_ANTERIOR',
                        'eventos_ignorados': jornada_actual['conflictos']
                    })
                    # Abrimos la nueva del día de hoy
                    jornada_actual = {'entrada': tiempo, 'breaks': [], 'conflictos': []}
            continue

        #check-out

        if evento == 'Check-out':
            if jornada_actual is None:
                turnos.append({'id_empleado': pid,
                'nombre': nombre_empleado,
                'fecha': tiempo.date(),
                'entrada': None,
                'salida': tiempo.time(),
                'horas_trabajadas': 0,
                'Obs': 'SOLO SALIDA',
                'eventos_guardados': []})
                continue

        #cerrar jornada con check-out

        horas_totales = calcular_diferencia_horas(jornada_actual['entrada'], tiempo)
        horas_break = sum([calcular_diferencia_horas(b[0], b[1]) for b in jornada_actual['breaks']])
        horas_trabajadas = max(0, round(horas_totales - horas_break, 2))

        obs = 'OK' if horas_trabajadas <= max_jornada_horas else 'JORNADA_EXCESIVA'
        turnos.append({
            'id_empleado': pid,
            'nombre': nombre_empleado,
            'fecha': jornada_actual['entrada'].date(),
            'entrada': jornada_actual['entrada'].time(),
            'salida': tiempo.time(),
            'horas_trabajadas': horas_trabajadas,
            'Obs': obs,
            'eventos_ignorados': []
        })
        jornada_actual = None

        # JORNADA SIN CIERRE
    if jornada_actual:
        turnos.append({
            'id_empleado': pid,
            'nombre': nombre_empleado,
            'fecha': jornada_actual['entrada'].date(),
            'entrada': jornada_actual['entrada'].time(),            
            'salida': None,
            'horas_trabajadas': 0,
            'Obs': 'JORNADA_SIN_CIERRE',
            'eventos_ignorados': jornada_actual['conflictos']
        })

    return turnos, eventos_ignorados

def procesar_marcas_huellero(df_datos):
    df_limpio, errores = limpiar_dataframe(df_datos)
    if df_limpio.empty:
        return pd.DataFrame(columns=['id_empleado', 'nombre', 'fecha', 'entrada', 'salida', 'horas_trabajadas', 'Obs', 'eventos_ignorados'])

    resultados_globales = []
    eventos_ignorados_globales = []
    for pid, grupo in df_limpio.groupby('Person ID'):
        turnos, eventos_ignorados = procesar_empleado(pid, grupo)
        resultados_globales.extend(turnos)
        eventos_ignorados_globales.extend(eventos_ignorados)

    if not resultados_globales:
        return pd.DataFrame(columns=['id_empleado', 'nombre', 'fecha', 'entrada', 'salida', 'horas_trabajadas', 'Obs', 'eventos_ignorados'])
    df_resultados = pd.DataFrame(resultados_globales)
    
    if eventos_ignorados_globales:
        df_ignorados = pd.DataFrame(eventos_ignorados_globales)
        print("Eventos ignorados durante el procesamiento:")
        print(df_ignorados)

    if errores_globales:
        print("Errores detectados durante la limpieza:")
        for error in errores_globales:
            print({error})

    return df_resultados


   


    
