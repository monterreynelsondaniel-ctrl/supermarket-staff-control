from db import get_connection

def calcular_horas_semanales(empleado_id, fecha_inicio, fecha_fin):
    """
    Suma las Horas Totales (HT) de un empleado en un rango de fechas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT SUM(t.ht) 
        FROM programacion p
        JOIN turnos t ON p.turno_id = t.turno_id
        WHERE p.empleado_id = ? AND p.fecha BETWEEN ? AND ?
    """
    
    cursor.execute(query, (empleado_id, fecha_inicio, fecha_fin))
    resultado = cursor.fetchone()[0]
    conn.close()
    
    return resultado if resultado else 0

def validar_limite_44h(horas_totales):
    """Verifica si se pasa del límite legal."""
    LIMITE = 44
    if horas_totales > LIMITE:
        return f"Alerta:{horas_totales} horas."
