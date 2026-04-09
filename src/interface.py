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
            margin-top: 50px;
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
        f_inicio_comp = st.date_input("Fecha Inicio", datetime.now() - timedelta(days=15))
    with col_f2:
        f_fin_comp = st.date_input("Fecha Fin", datetime.now())

    archivo = st.file_uploader("Sube el reporte del huellero (CSV)", type=["csv"])
    
    if archivo:
        df_crudo = pd.read_csv(archivo)
        
        if st.button("🚀 Ejecutar Cruce de Información"):
            try:
                with st.status("Procesando datos...", expanded=True) as status:
                    st.write("🧼 Limpiando marcas...")
                    df_asistencia_limpia = procesar_marcas_huellero(df_crudo)
                    
                    st.write("🔍 Comparando contra Turnos Asignados...")
                    # Ahora ejecutar_comparacion devuelve el AJUSTE basado en el turno
                    df_comparativo = ejecutar_comparacion(
                        str(f_inicio_comp), 
                        str(f_fin_comp), 
                        df_huellero=df_asistencia_limpia
                    )
                    status.update(label="✅ Comparación Lista", state="complete", expanded=False)

                if df_comparativo is not None:
                    # --- INTERFAZ DE EDICIÓN PARA EL AJUSTE ---
                    st.subheader("🛠️ Revisión de Novedades y Ajustes")
                    st.info("Aquí puedes corregir el AJUSTE manualmente antes de generar el reporte final.")
                    
                    # Mostramos las columnas clave para que tú o Carlos decidan
                    df_editado = st.data_editor(
                        df_comparativo,
                        column_config={
                            "nombre": st.column_config.Column("Empleado", disabled=True),
                            "fecha": st.column_config.Column("Fecha", disabled=True),
                            "turno_id": st.column_config.Column("Turno", disabled=True),
                            "HT": st.column_config.NumberColumn("HT (Turno)", format="%.2f", disabled=True),
                            "HORAS_REALES": st.column_config.NumberColumn("Real (Reloj)", format="%.2f", disabled=True),
                            "AJUSTE": st.column_config.NumberColumn("AJUSTE", format="%.2f", help="Modifica este valor si hubo un error en la marca"),
                            "Obs": st.column_config.SelectboxColumn("Obs", options=["OK", "FALTA", "VACACIONES", "CALAMIDAD", "AJUSTE MANUAL"])
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="editor_ajustes_final"
                    )

                    # --- GENERACIÓN DEL REPORTE QUINCENAL (ESTILO CARLOS) ---
                    if st.button("📦 Generar Reporte Quincenal para Excel"):
                        # Agrupamos por nombre para sumar la quincena
                        reporte_carlos = df_editado.groupby('nombre').agg({
                            'HT': 'sum',
                            'AJUSTE': 'sum',
                            'HED': 'sum',
                            'RN': 'sum',
                            'HEFD': 'sum',
                            'T_PARTIDO': 'sum',
                            'DESCANSOS': 'sum'
                        }).reset_index()

                        # Renombramos a tus cabeceras exactas
                        reporte_carlos.columns = ['EMPLEADOS', 'HT', 'AJUSTE', 'HED', 'RN', 'HEFD', 'T. Partido', 'DESCANSOS']
                        
                        # Cálculo de SHT Completas
                        reporte_carlos['SHT. Completas'] = reporte_carlos['HT'] + reporte_carlos['AJUSTE']
                        
                        # Semáforo de Estado
                        reporte_carlos['ESTADO'] = reporte_carlos['SHT. Completas'].apply(
                            lambda x: "✅ OK" if x <= 44 else f"🔴 Exceso: {round(x-44, 2)}h"
                        )

                        st.success("✅ Reporte consolidado con éxito.")
                        st.dataframe(reporte_carlos, use_container_width=True, hide_index=True)

                        # Exportación a Excel Real (para que Carlos solo copie y pegue)
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                            reporte_carlos.to_excel(writer, index=False, sheet_name='Hoja1')
                        
                        st.download_button(
                            label="📥 Descargar Excel para Sincronizar",
                            data=buffer,
                            file_name=f"Reporte_Quincenal_{f_inicio_comp}.xlsx",
                            mime="application/vnd.ms-excel"
                        )

            except Exception as e:
                st.error(f"❌ Error en el proceso: {e}")
                st.exception(e)

elif seleccion == "📊 Reporte Horas Extras":
    st.title("📊 Reporte de Horas Extras")
    st.info("Sección en desarrollo: Aquí se mostrarán los acumulados para nómina.")

elif seleccion == "📝 Planillas":
    st.title("📝 Planillas de Firmas")
    st.info("Sección en desarrollo: Generación de PDF para firmas físicas.")