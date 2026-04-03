import streamlit as st
import pandas as pd
from db import get_connection, obtener_todos_turnos
from datetime import datetime, timedelta
from procesador import procesar_marcas_huellero
import io
# Corregido: Importamos la función específica que creamos
from comparacion import ejecutar_comparacion 

st.set_page_config(page_title="Sistema Control de Horas", layout="wide")

# --- FUNCIONES DE APOYO ---
def obtener_datos_completos(depto, inicio, fin):
    conn = get_connection()
    df_emp = pd.read_sql(f"SELECT id, nombre FROM employees WHERE departamento = '{depto}' ORDER BY nombre", conn)
    rango_fechas = pd.date_range(start=inicio, end=fin).strftime('%Y-%m-%d').tolist()
    turnos_info = obtener_todos_turnos()
    turnos_db = {t[0]: t[3] for t in turnos_info} 
    
    matriz = df_emp.copy()
    for fecha in rango_fechas:
        matriz[fecha] = "-"

    query_prog = f"""
        SELECT e.id as emp_id, p.fecha, p.turno_id 
        FROM programacion p
        JOIN employees e ON p.empleado_id = e.id
        WHERE e.departamento = '{depto}' AND p.fecha BETWEEN '{inicio}' AND '{fin}'
    """
    prog_existente = pd.read_sql(query_prog, conn)
    for _, row in prog_existente.iterrows():
        if row['fecha'] in matriz.columns:
            matriz.loc[matriz['id'] == row['emp_id'], row['fecha']] = row['turno_id']
    
    def calcular_fila(fila):
        total_ht = 0
        for f in rango_fechas:
            valor_celda = str(fila[f]).strip().upper()
            total_ht += turnos_db.get(valor_celda, 0)
        return round(total_ht, 2)

    matriz["Total Horas"] = matriz.apply(calcular_fila, axis=1)
    conn.close()
    return matriz, rango_fechas

# --- 1. MENÚ LATERAL ---
with st.sidebar:
    st.title("🚀 Menú Principal")
    paginas = ["📅 Programación de Turnos", "📥 Cargar Huellero (CSV)", "📊 Reporte Horas Extras", "📝 Planillas"]
    seleccion = st.radio("Ir a:", paginas)

# --- 2. LÓGICA DE NAVEGACIÓN ---

if seleccion == "📅 Programación de Turnos":
    st.title("🛒 Programación de Turnos")
    col1, col2, col3 = st.columns(3)
    with col1:
        depto = st.selectbox("Departamento", ["Caja", "Pickers", "CCTV", "Bodega", "Call Center", "Lideres", "Tesorería"])
    with col2:
        fecha_inicio = st.date_input("Fecha Inicial", datetime.now())
    with col3:
        fecha_fin = fecha_inicio + timedelta(days=6)
        st.write(f"**Fin de semana:** {fecha_fin}")

    df_inicial, fechas = obtener_datos_completos(depto, fecha_inicio, fecha_fin)
    st.subheader(f"Cuadrícula: {depto}")

    edicion = st.data_editor(
        df_inicial,
        column_config={
            "id": None,
            "nombre": st.column_config.Column("Empleado", width="medium", disabled=True),
            "Total Horas": st.column_config.NumberColumn("Total Horas", format="%.2f hrs", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_turnos"
    )

    excesos = edicion[edicion["Total Horas"] > 44]
    if not excesos.empty:
        st.warning(f"⚠️ {len(excesos)} personas superan las 44h semanales (Ley Colombiana).")

    if st.button("💾 Guardar Cambios"):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            turnos_validos = [t[0] for t in obtener_todos_turnos()]
            for _, fila in edicion.iterrows():
                emp_id = fila['id']
                for f in fechas:
                    turno_id = str(fila[f]).strip().upper()
                    if turno_id in turnos_validos:
                        cursor.execute("INSERT OR REPLACE INTO programacion (empleado_id, fecha, turno_id) VALUES (?, ?, ?)", (int(emp_id), f, turno_id))
                    elif turno_id in ["-", "", "NONE"]:
                        cursor.execute("DELETE FROM programacion WHERE empleado_id = ? AND fecha = ?", (int(emp_id), f))
            conn.commit()
            st.success("✅ Guardado con éxito.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error al guardar: {e}")
        finally:
            conn.close()

elif seleccion == "📥 Cargar Huellero (CSV)":
    st.header("Procesador de Asistencia Real y Comparativa")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        f_inicio_comp = st.date_input("Fecha Inicio Comparación", datetime.now() - timedelta(days=7))
    with col_f2:
        f_fin_comp = st.date_input("Fecha Fin Comparación", datetime.now())

    archivo = st.file_uploader("Sube el reporte del huellero", type=["csv"])
    
    if archivo:
        # Guardamos temporalmente para el procesador
        with open("temp_huellero.csv", "wb") as f:
            f.write(archivo.getbuffer())
            
        if st.button("🚀 Ejecutar Cruce de Información"):
            st.info("Paso 1: Limpiando marcas del huellero...")
            # Aquí llamamos a tu función de procesador.py
            # Nota: Asegúrate que procesar_marcas_huellero reciba el path o el DF
            
            st.info("Paso 2: Cruzando Realidad vs Programación...")
            try:
                # Llamamos a la función del motor que creamos
                df_comparativo = ejecutar_comparacion(str(f_inicio_comp), str(f_fin_comp))
                
                if df_comparativo is not None:
                    st.success("✅ Comparación finalizada.")
                    m1, m2 = st.columns(2)
                    alertas_count = len(df_comparativo[df_comparativo['Alerta_44h'].str.contains("SÍ", na=False)])
                    faltas_count = len(df_comparativo[df_comparativo['Obs'] == "FALTA / NO MARCÓ"])
                    
                    m1.metric("Alertas > 44h", alertas_count)
                    m2.metric("Faltas/Inconsistencias", faltas_count)

                    def highlight_discrepancy(row):
                        style = [''] * len(row)
                        if "SÍ" in str(row['Alerta_44h']):
                            style = ['background-color: #fff3e0'] * len(row)
                        if row['Obs'] == "FALTA / NO MARCÓ":
                            style = ['color: #d32f2f; font-weight: bold'] * len(row)
                        return style

                    st.dataframe(df_comparativo.style.apply(highlight_discrepancy, axis=1), use_container_width=True)
                    
                    csv_final = df_comparativo.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Descargar Reporte Final", csv_final, "reporte_final.csv", "text/csv")
            except Exception as e:
                st.error(f"Hubo un error en el cruce de datos: {e}")

elif seleccion == "📊 Reporte Horas Extras":
    st.title("📊 Reporte de Horas Extras")
    st.info("Sección en desarrollo: Aquí se mostrarán los acumulados para nómina.")

elif seleccion == "📝 Planillas":
    st.title("📝 Planillas de Firmas")
    st.info("Sección en desarrollo: Generación de PDF para firmas físicas.")