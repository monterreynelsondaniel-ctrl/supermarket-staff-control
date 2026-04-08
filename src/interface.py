import streamlit as st
import pandas as pd
from db import get_connection, obtener_todos_turnos
from datetime import datetime, timedelta
from procesador import procesar_marcas_huellero
import io
# Corregido: Importamos la función específica que creamos
from comparacion import ejecutar_comparacion
import logic

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

    # Separador visual sutil
    st.write("") 
    st.write("") 
    st.divider()

    # CSS para el Pulso Moderno
    st.markdown("""
        <style>
        @keyframes pulse-green {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(46, 204, 113, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(46, 204, 113, 0); }
        }
        .container {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px;
            background: rgba(128, 128, 128, 0.05);
            border-radius: 8px;
            border: 1px solid rgba(128, 128, 128, 0.1);
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            background: #2ecc71;
            border-radius: 50%;
            animation: pulse-green 2s infinite;
        }
        .status-text {
            font-family: 'Source Code Pro', monospace;
            font-size: 0.75rem;
            color: #888;
            letter-spacing: 1px;
        }
        </style>
        
        <div class="container">
            <div class="pulse-dot"></div>
            <div class="status-text">ESTADO // ACTIVO</div>
        </div>
    """, unsafe_allow_html=True)

# --- 2. LÓGICA DE NAVEGACIÓN ---

if seleccion == "📅 Programación de Turnos":
    st.title(" Programación de Turnos")
    col1, col2, col3 = st.columns(3)
    with col1:
        depto = st.selectbox("Departamento", ["Caja", "Pickers", "CCTV", "Bodega", "Call Center", "Lideres", "Tesorería"])
    with col2:
        fecha_inicio = st.date_input("Fecha Inicial", datetime.now())
    with col3:
        fecha_fin = fecha_inicio + timedelta(days=6)
        st.write(f"**Fin de semana:** {fecha_fin}")

    df_inicial, fechas = obtener_datos_completos(depto, fecha_inicio, fecha_fin)
    st.subheader(f"Departamento: {depto}")

    edicion = st.data_editor(
        df_inicial,
        column_config={
            "id": None,
            "nombre": st.column_config.Column("Empleado", width="medium", disabled=True),
            "Total Horas": st.column_config.NumberColumn("Total Horas", format="%.2f hrs", disabled=True),
        },
        hide_index=True,
        use_container_width="stretch",
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
    st.header("📊 Procesador de Asistencia y Comparativa")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        f_inicio_comp = st.date_input("Fecha Inicio Comparación", datetime.now() - timedelta(days=7))
    with col_f2:
        f_fin_comp = st.date_input("Fecha Fin Comparación", datetime.now())

    archivo = st.file_uploader("Sube el reporte del huellero (CSV)", type=["csv"])
    
    if archivo:
        # LEER DIRECTAMENTE DESDE LA MEMORIA (RAM)
        df_crudo = pd.read_csv(archivo)
        st.write("📋 Vista previa del archivo cargado:", df_crudo.head(3))
            
        if st.button("🚀 Ejecutar Cruce de Información"):
            try:
                with st.status("Procesando datos...", expanded=True) as status:
                    # PASO 1: Limpieza con tu procesador.py
                    st.write("🧼 Limpiando marcas del huellero...")
                    df_asistencia_limpia = procesar_marcas_huellero(df_crudo)
                    
                    # PASO 2: Cruce con SQLite y Reglas de Negocio
                    st.write("🔍 Cruzando Realidad vs Programación...")
                    # Modificamos la llamada para pasarle el DF limpio
                    df_comparativo = ejecutar_comparacion(
                        str(f_inicio_comp), 
                        str(f_fin_comp), 
                        df_huellero=df_asistencia_limpia
                    )
                    status.update(label="✅ Proceso completado", state="complete", expanded=False)

                if df_comparativo is not None:
                    # --- MÉTRICAS DE IMPACTO (Para impresionar al jefe) ---
                    m1, m2, m3 = st.columns(3)
                    alertas_44 = len(df_comparativo[df_comparativo['Alerta_44h'].str.contains("SÍ", na=False)])
                    faltas = len(df_comparativo[df_comparativo['Obs'] == "FALTA / NO MARCÓ"])
                    
                    # Calculamos tardanzas con tu logic.py
                    df_tardanzas = logic.analizar_puntualidad(df_comparativo)
                    tardanzas_count = len(df_tardanzas)

                    m1.metric("Excesos Jornada (>44h)", alertas_44, delta="Revisar", delta_color="inverse")
                    m2.metric("Faltas Detectadas", faltas, delta="Inconsistencias", delta_color="off")
                    m3.metric("Llegadas Tarde", tardanzas_count, delta="Puntualidad", delta_color="inverse")

                    # --- SECCIÓN DE TARDANZAS ---
                    if not df_tardanzas.empty:
                        with st.expander("⚠️ Ver Detalle de Llegadas Tarde (Tolerancia 10 min)", expanded=False):
                            st.dataframe(
                                df_tardanzas[['nombre', 'fecha', 'entrada_prog', 'entrada_real', 'retraso_minutos']],
                                use_container_width=True, hide_index=True
                            )
                            # Guardar reporte físico para auditoría
                            os.makedirs("exports", exist_ok=True)
                            df_tardanzas.to_excel("exports/reporte_tardanzas.xlsx", index=False)

                    # --- TABLA PRINCIPAL DE DISCREPANCIAS ---
                    st.subheader("📝 Detalle de Comparación Semanal")
                    
                    def highlight_discrepancy(row):
                        style = [''] * len(row)
                        if "SÍ" in str(row['Alerta_44h']):
                            style = ['background-color: #fff3e0'] * len(row) # Naranja suave
                        if row['Obs'] == "FALTA / NO MARCÓ":
                            style = ['color: #d32f2f; font-weight: bold'] * len(row) # Rojo fuerte
                        return style

                    st.dataframe(
                        df_comparativo.style.apply(highlight_discrepancy, axis=1), 
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Botón de Descarga
                    csv_final = df_comparativo.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Descargar Reporte Completo (CSV)",
                        data=csv_final,
                        file_name=f"reporte_{f_inicio_comp}_{f_fin_comp}.csv",
                        mime="text/csv"
                    )

            except Exception as e:
                st.error(f"❌ Error en el sistema: {e}")
                st.exception(e) # Esto te ayuda a debuguear mientras programas

elif seleccion == "📊 Reporte Horas Extras":
    st.title("📊 Reporte de Horas Extras")
    st.info("Sección en desarrollo: Aquí se mostrarán los acumulados para nómina.")

elif seleccion == "📝 Planillas":
    st.title("📝 Planillas de Firmas")
    st.info("Sección en desarrollo: Generación de PDF para firmas físicas.")