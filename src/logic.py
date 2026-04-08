import pandas as pd
from datetime import datetime, time

def analizar_puntualidad(df_conciliado, tolerancia=10):
    """
    Calcula retrasos comparando entrada_prog vs entrada_real.
    """
    df = df_conciliado.copy()
    
    # 1. Filtramos registros que tengan ambas marcas y que no sean faltas
    df = df.dropna(subset=['entrada_prog', 'entrada_real'])
    df = df[df['Obs'] != "FALTA / NO MARCÓ"]

    def calcular_retraso(row):
        try:
            # entrada_prog viene como string "07:00:00"
            # entrada_real viene del procesador (posiblemente objeto time o datetime)
            
            # Convertimos la fecha y la hora programada en un solo objeto datetime
            h_prog, m_prog, s_prog = map(int, str(row['entrada_prog']).split(':'))
            dt_prog = datetime.combine(row['fecha'], time(h_prog, m_prog, s_prog))
            
            # Convertimos la entrada real (si es solo hora) a datetime usando la misma fecha
            e_real = row['entrada_real']
            if isinstance(e_real, time):
                dt_real = datetime.combine(row['fecha'], e_real)
            elif isinstance(e_real, str):
                # Por si acaso el Excel lo lee como texto
                dt_real = datetime.combine(row['fecha'], datetime.strptime(e_real, "%H:%M:%S").time())
            else:
                dt_real = e_real # Si ya es datetime, lo dejamos quieto

            # Calculamos diferencia en minutos
            diferencia = (dt_real - dt_prog).total_seconds() / 60
            return int(diferencia) if diferencia > 0 else 0
        except:
            return 0

    # 2. Aplicamos el cálculo
    df['retraso_minutos'] = df.apply(calcular_retraso, axis=1)
    
    # 3. Filtramos solo los que superan la tolerancia fija (10 min)
    tardanzas = df[df['retraso_minutos'] > tolerancia].copy()
    
    # Ordenamos por los más impuntuales primero
    columnas_finales = ['nombre', 'fecha', 'turno_id', 'descripcion', 'entrada_prog', 'entrada_real', 'retraso_minutos']
    return tardanzas[columnas_finales].sort_values(by='retraso_minutos', ascending=False)