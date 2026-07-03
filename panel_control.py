import streamlit as st
import pandas as pd
from io import BytesIO
import folium
from streamlit_folium import st_folium
import random
from datetime import datetime
import os

# --- IMPORTACIÓN DE NUESTROS MÓDULOS SEPARADOS ---
from modulos.ingesta_datos import extraer_coordenadas_kmz, cargar_padron_matricial
from modulos.motor_gps import (
    snap_punto_a_ruta, 
    evaluar_operacion, 
    determinar_sector, 
    generar_tramo_realista_por_sector
)

# 1. Configuración de página e Identidad Institucional
st.set_page_config(layout="wide", page_title="S.V.R. — Ministerio de Transportes", page_icon="🇨🇱")

# 2. Inyección de CSS Avanzado del Framework Digital Gob.cl
st.markdown("""
    <style>
        /* Tipografía oficial y fondo de la aplicación */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
        
        html, body, [data-testid="stAppViewContainer"] {
            font-family: 'Roboto', sans-serif;
            background-color: #F8F9FA !important;
        }
        
        /* Ocultar elementos nativos de Streamlit para mayor formalidad */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Estilización de las Tarjetas Métricas (KPI Cards) */
        .kpi-container {
            background-color: #FFFFFF;
            border-left: 5px solid #0033A0;
            border-radius: 4px;
            padding: 15px 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            margin-bottom: 15px;
        }
        .kpi-title {
            color: #666666;
            font-size: 0.85rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        .kpi-value {
            color: #0033A0;
            font-size: 1.8rem;
            font-weight: 700;
            line-height: 1;
        }
        
        /* Estilización de Botones Institucionales (Azul Gobierno) */
        div.stButton > button:first-child {
            background-color: #0033A0 !important;
            color: white !important;
            border-radius: 4px !important;
            border: none !important;
            font-weight: 500 !important;
            padding: 0.6rem 1.2rem !important;
            width: 100%;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        div.stButton > button:first-child:hover {
            background-color: #002266 !important;
            box-shadow: 0 3px 6px rgba(0,0,0,0.15);
        }
        
        /* Estilización de la Barra Lateral */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #E5E5E5 !important;
        }
        
        /* Estilización de pestañas (Tabs) */
        button[data-baseweb="tab"] {
            font-size: 1rem !important;
            font-weight: 500 !important;
            color: #555555 !important;
        }
        button[aria-selected="true"] {
            color: #0033A0 !important;
            border-bottom-color: #0033A0 !important;
        }
    </style>
""", unsafe_allow_html=True)

# Inicialización de Estados Globales
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'role' not in st.session_state: st.session_state.role = None
if 'alertas' not in st.session_state: st.session_state.alertas = []
if 'buses_en_vivo' not in st.session_state: st.session_state.buses_en_vivo = []
if 'historial_ok' not in st.session_state: st.session_state.historial_ok = []
if 'alerta_focus' not in st.session_state: st.session_state.alerta_focus = None

# --- VISTA 1: PANTALLA DE LOGIN GOB.CL ---
def pantalla_login():
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    
    with col_l2:
        # Contenedor del Escudo y Encabezado
        st.markdown("""
            <div style="background-color: #0033A0; padding: 30px; border-bottom: 5px solid #EF3340; text-align: center; color: white; border-radius: 6px 6px 0 0;">
                <span style="font-weight: bold; font-size: 0.85rem; letter-spacing: 2px; opacity: 0.85;">MINISTERIO DE TRANSPORTES Y TELECOMUNICACIONES</span><br>
                <h2 style="margin: 10px 0 0 0; color: white; font-size: 1.7rem; font-weight: 700;">Sistema de Validación en Red (S.V.R)</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.75; font-size: 0.9rem;">Subsecretaría de Transportes — Región de O'Higgins</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Formulario de Acceso Seguro
        with st.container(border=True):
            st.markdown("<p style='text-align: center; font-weight: 500; color: #444; margin-top: 10px;'>Portal Único de Autenticación de Funcionarios</p>", unsafe_allow_html=True)
            with st.form("Formulario_Gob_Login"):
                usuario = st.text_input("📍 Clave Única o Usuario Institucional", placeholder="ejemplo.funcionario")
                contrasena = st.text_input("🔒 Contraseña del Sistema", type="password", placeholder="••••••••")
                st.markdown("<br>", unsafe_allow_html=True)
                
                if st.form_submit_button("Autenticar e Ingresar al Panel"):
                    if usuario == "admin" and contrasena == "rancagua2026":
                        st.session_state.logged_in = True
                        st.session_state.role = "admin"
                        st.rerun()
                    elif usuario == "visor" and contrasena == "consulta2026":
                        st.session_state.logged_in = True
                        st.session_state.role = "visor"
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas o usuario no registrado en el perímetro.")
            st.caption("⚠️ El acceso no autorizado a este sistema estatal está penalizado según la normativa de seguridad vigente.")

# --- VISTA 2: PLATAFORMA PRINCIPAL AUTENTICADA ---
if not st.session_state.logged_in:
    pantalla_login()
else:
    # Banner Superior Oficial Gob.cl
    st.markdown("""
        <div style="background-color: #0033A0; padding: 15px 25px; border-bottom: 4px solid #EF3340; color: white; display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
            <div>
                <span style="font-weight: bold; font-size: 0.75rem; letter-spacing: 1.5px; opacity: 0.85;">GOBIERNO DE CHILE</span><br>
                <span style="font-size: 1.4rem; font-weight: 700; color: white;">Subsecretaría de Transportes — División de Fiscalización</span>
            </div>
            <div style="text-align: right; opacity: 0.95;">
                <span style="font-size: 0.85rem; font-weight: 500; display: block;">Perímetro de Exclusión Rancagua</span>
                <span style="font-size: 0.75rem; font-weight: 300; display: block; background: rgba(255,255,255,0.15); padding: 2px 8px; border-radius: 3px; margin-top: 3px; text-align: center;">Módulo S.V.R Regulado</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Botón de desconexión institucional
    c_vacia, c_logout = st.columns([8.5, 1.5])
    with c_logout:
        if st.button("🔒 Cerrar Sesión", key="btn_logout"):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.rerun()

    # Barra Lateral Administrativa
    st.sidebar.markdown("<h3 style='color: #0033A0; margin-bottom: 0;'>⚙️ Parámetros</h3>", unsafe_allow_html=True)
    st.sidebar.markdown("<p style='font-size:0.85rem; color:gray; margin-top: 0; margin-bottom: 15px;'>Ingesta de Datos y Cartografía</p>", unsafe_allow_html=True)
    
    archivos_kmz_procesar = []
    archivo_padron = None

    if st.session_state.role == "admin":
        st.sidebar.markdown("<span style='background-color: #E6F0FA; color: #0033A0; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 500; display: block; text-align: center;'>Perfil: Administrador</span><br>", unsafe_allow_html=True)
        archivos_kmz_crudos = st.sidebar.file_uploader("1. Cartografía Oficial (KMZ)", type=["kmz"], accept_multiple_files=True)
        if archivos_kmz_crudos:
            archivos_kmz_procesar = [(f.name, f) for f in sorted(archivos_kmz_crudos, key=lambda f: f.name)]
        archivo_gtfs = st.sidebar.file_uploader("2. GTFS Regulado (.zip)", type=["zip"])
        archivo_padron = st.sidebar.file_uploader("3. Padrón de Patentes (.xlsx)", type=["xlsx"])
    elif st.session_state.role == "visor":
        st.sidebar.markdown("<span style='background-color: #F0F0F0; color: #444444; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: 500; display: block; text-align: center;'>Perfil: Visor Institucional</span><br>", unsafe_allow_html=True)
        carpeta_datos = "datos"
        if os.path.exists(carpeta_datos):
            archivos_locales = os.listdir(carpeta_datos)
            kmz_locales = sorted([f for f in archivos_locales if f.lower().endswith('.kmz')])
            padron_local = [f for f in archivos_locales if f.lower().endswith('.xlsx') or f.lower().endswith('.xls')]
            archivos_kmz_procesar = [(nombre, os.path.join(carpeta_datos, nombre)) for nombre in kmz_locales]
            if padron_local: archivo_padron = os.path.join(carpeta_datos, padron_local[0])
        else:
            st.sidebar.error("Carpeta local de datos no encontrada en el servidor.")

    # Procesar archivos e Ingesta de Datos
    lineas_dict = {}
    if archivos_kmz_procesar:
        for nombre_archivo, archivo_o_ruta in archivos_kmz_procesar:
            nombre_servicio = nombre_archivo.split(".")[0].upper()
            datos_kmz = extraer_coordenadas_kmz(archivo_o_ruta)
            if datos_kmz: lineas_dict[nombre_servicio] = datos_kmz

    nombres_servicios_reales = list(lineas_dict.keys())
    df_padron = cargar_padron_matricial(archivo_padron, nombres_servicios_reales) if archivo_padron else None
    
    if df_padron is not None:
        st.sidebar.success(f"📊 Flota Vinculada: {len(df_padron)} Patentes")

    if st.sidebar.button("🚀 Iniciar Análisis de Cumplimiento Red", key="btn_motor"):
        if not lineas_dict:
            st.sidebar.error("Por favor, cargue la cartografía para iniciar el motor.")
        else:
            st.session_state.alerta_focus = None
            st.session_state.alertas = []
            st.session_state.historial_ok = []

            hora_actual_dt = datetime.now()
            hora_actual_str = hora_actual_dt.strftime("%H:%M:%S")
            buses_calculados = []
            
            es_horario_comercial = 5 <= hora_actual_dt.hour < 22

            if df_padron is not None and not df_padron.empty:
                flota_muestra = df_padron.sample(min(20, len(df_padron))) if len(df_padron) > 20 else df_padron
                
                for _, fila in flota_muestra.iterrows():
                    patente = str(fila['Patente'])
                    linea_asignada = str(fila['Servicio_Oficial'])
                    es_electrico = fila.get('Es_Electrico', False)
                    
                    if linea_asignada not in lineas_dict: continue 
                    rutas_obj = lineas_dict[linea_asignada]['rutas']
                    paraderos_obj = lineas_dict[linea_asignada]['paraderos']
                    if not rutas_obj: continue
                        
                    trazado_puntos = [pt for seg in rutas_obj for pt in seg['trazado']]
                    punto_base = random.choice(trazado_puntos)
                    
                    if not es_horario_comercial:
                        comportamiento = random.choices(["OK", "TERMINAL"], weights=[50, 50])[0]
                    else:
                        comportamiento = random.choices(["OK", "TERMINAL", "ACORTE", "ABANDONO", "VELOCIDAD"], weights=[65, 5, 10, 10, 10])[0]
                    
                    limite_zona = 50
                    
                    if comportamiento == "OK":
                        lat_actual = punto_base[0] + random.uniform(-0.0001, 0.0001)
                        lon_actual = punto_base[1] + random.uniform(-0.0001, 0.0001)
                        vel = random.randint(25, 48)
                    elif comportamiento == "TERMINAL":
                        punto_base = trazado_puntos[0] if random.choice([True, False]) else trazado_puntos[-1]
                        lat_actual = punto_base[0]
                        lon_actual = punto_base[1]
                        vel = 0
                    elif comportamiento == "VELOCIDAD":
                        lat_actual = punto_base[0]
                        lon_actual = punto_base[1]
                        vel = random.randint(55, 75)
                    elif comportamiento == "ACORTE":
                        lat_actual = punto_base[0] + random.uniform(-0.0007, 0.001) 
                        lon_actual = punto_base[1] + random.uniform(-0.0007, 0.001)
                        vel = random.randint(30, 48)
                    elif comportamiento == "ABANDONO":
                        lat_actual = punto_base[0] + random.uniform(-0.002, 0.003) 
                        lon_actual = punto_base[1] + random.uniform(-0.002, 0.003)
                        vel = random.randint(30, 48)
                        
                    estado, dist_error = evaluar_operacion(lat_actual, lon_actual, rutas_obj, vel, limite_zona, paraderos_obj)
                    lat_snap, lon_snap, variante_exacta, trazado_infractor = snap_punto_a_ruta(lat_actual, lon_actual, rutas_obj)

                    buses_calculados.append({
                        "id": patente, "linea": linea_asignada, "lat": lat_actual, "lon": lon_actual,
                        "estado": estado, "color": "green" if estado == "Operación Normal" else ("orange" if "Terminal" in estado else "red"), 
                        "vel": vel, "limite": limite_zona, "electrico": es_electrico
                    })

                    sector = determinar_sector(lat_snap, lon_snap)
                    tiempo_abandono_simulado = random.randint(3, 25)
                    tramo_preciso = generar_tramo_realista_por_sector(sector)

                    datos_evento = {
                        "ID Alerta": f"ALT-{random.randint(100,999)}", "Patente": patente, "Servicio": linea_asignada,
                        "Variante": variante_exacta, "Infracción": estado, "Tramo Afectado": tramo_preciso,
                        "Sector Comuna": sector, "Hora Control": hora_actual_str, "Tiempo de Abandono": f"{tiempo_abandono_simulado} min",
                        "Latitud": lat_snap, "Longitud": lon_snap, "Segmento_Ruta": trazado_infractor
                    }

                    if estado == "Operación Normal": st.session_state.historial_ok.append(datos_evento)
                    else: st.session_state.alertas.append(datos_evento)
            
            st.session_state.buses_en_vivo = buses_calculados
            st.toast(f"Análisis finalizado. Historial operativo actualizado.", icon="✅")

    # Alertas Rápidas en la Sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("<h4 style='color: #EF3340;'>🔔 Alertas de Red</h4>", unsafe_allow_html=True)
    if st.session_state.alertas:
        for a in st.session_state.alertas:
            with st.sidebar.container(border=True):
                st.markdown(f"<p style='color:#EF3340; font-weight:bold; margin-bottom:2px; font-size:0.8rem;'>{a['Infracción']}</p>", unsafe_allow_html=True)
                st.caption(f"**PPU:** {a['Patente']} | **Línea:** {a['Servicio']}")
                if st.button("📍 Enfocar", key=f"focus_{a['ID Alerta']}", use_container_width=True):
                    st.session_state.alerta_focus = a
                    st.rerun()
    else:
        st.sidebar.info("Sin anomalías de trazado reportadas.")

    # --- CUADRO DE MANDOS: TARJETAS MÉTRICAS (KPI GRID) ---
    total_buses = len(st.session_state.buses_en_vivo)
    buses_fuera_norma = len(st.session_state.alertas)
    buses_normales = total_buses - buses_fuera_norma

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.markdown(f"<div class='kpi-container'><div class='kpi-title'>Total Flota Controlada</div><div class='kpi-value'>{total_buses}</div></div>", unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"<div class='kpi-container' style='border-left-color: #2ca02c;'><div class='kpi-title'>Operación Normal</div><div class='kpi-value' style='color:#2ca02c;'>{max(0, buses_normales)}</div></div>", unsafe_allow_html=True)
    with col_m3:
        st.markdown(f"<div class='kpi-container' style='border-left-color: #EF3340;'><div class='kpi-title'>Alertas / Anomalías</div><div class='kpi-value' style='color:#EF3340;'>{buses_fuera_norma}</div></div>", unsafe_allow_html=True)
    with col_m4:
        servicios_activos = len(nombres_servicios_reales)
        st.markdown(f"<div class='kpi-container' style='border-left-color: #7f7f7f;'><div class='kpi-title'>Servicios en Sistema</div><div class='kpi-value' style='color:#444444;'>{servicios_activos}</div></div>", unsafe_allow_html=True)

    # --- FILTROS DE BÚSQUEDA ---
    st.markdown("<h4 style='color:#0033A0; margin-top:15px;'>🔍 Filtros de Fiscalización Territorial</h4>", unsafe_allow_html=True)
    with st.container(border=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: filtro_linea = st.selectbox("📋 Unidad de Negocio / Servicio", ["Todas"] + opciones_lineas)
        with col_f2: filtro_infraccion = st.selectbox("🚦 Tipo de Incumplimiento", ["Todas"] + opciones_infracciones)
        with col_f3: buscar_patente_input = st.text_input("🔎 Placa Patente Única (P.P.U)", placeholder="ej: BBBB-11")

    buscar_patente = buscar_patente_input.strip().upper()

    # Filtrado de Colecciones
    buses_filtrados = st.session_state.buses_en_vivo
    alertas_filtradas = st.session_state.alertas
    historial_ok_filtrado = st.session_state.historial_ok

    if filtro_linea != "Todas":
        buses_filtrados = [b for b in buses_filtrados if b["linea"] == filtro_linea]
        alertas_filtradas = [a for a in alertas_filtradas if a["Servicio"] == filtro_linea]
        historial_ok_filtrado = [h for h in historial_ok_filtrado if h["Servicio"] == filtro_linea]
    if filtro_infraccion != "Todas":
        buses_filtrados = [b for b in buses_filtrados if b["estado"] == filtro_infraccion]
        alertas_filtradas = [a for a in alertas_filtradas if a["Infracción"] == filtro_infraccion]
        historial_ok_filtrado = [h for h in historial_ok_filtrado if h["Infracción"] == filtro_infraccion]
    if buscar_patente:
        buses_filtrados = [b for b in buses_filtrados if buscar_patente in b["id"].upper()]
        alertas_filtradas = [a for a in alertas_filtradas if buscar_patente in a["Patente"].upper()]
        historial_ok_filtrado = [h for h in historial_ok_filtrado if buscar_patente in h["Patente"].upper()]

    # --- TABS / PESTAÑAS PRINCIPALES ---
    tab1, tab2 = st.tabs(["🛰️ Monitoreo Satelital en Tiempo Real", "🔥 Historial Estadístico e Infracciones"])

    with tab1:
        mapa_vivo = folium.Map(location=[-34.1708, -70.7444], zoom_start=13)
        folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite Gubernamental').add_to(mapa_vivo)

        colores_lineas = ["#0033A0", "#EF3340", "#2ca02c", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"] 

        for idx, (lbl, datos) in enumerate(lineas_dict.items()):
            if filtro_linea == "Todas" or filtro_linea == lbl:
                for segmento_obj in datos['rutas']:
                    folium.PolyLine(segmento_obj['trazado'], color=colores_lineas[idx % len(colores_lineas)], weight=4, opacity=0.85).add_to(mapa_vivo)

        for bus in buses_filtrados:
            es_electrico = bus.get('electrico', False)
            icon_color = "green" if es_electrico and bus['estado'] == "Operación Normal" else bus['color']
            icon_tipo = "bolt" if es_electrico else "bus"
            tec_text = "⚡ Eléctrico" if es_electrico else "⚙️ Diésel"
            
            html_pop = f"<div style='font-family: Roboto, sans-serif; font-size:12px; width:180px;'><b>PPU:</b> {bus['id']}<br><b>Línea:</b> {bus['linea']}<br><b>Motor:</b> {tec_text}<br><b>Estado:</b> {bus['estado']}</div>"
            folium.Marker([bus["lat"], bus["lon"]], icon=folium.Icon(color=icon_color, icon=icon_tipo, prefix='fa'), popup=folium.Popup(html_pop, max_width=250)).add_to(mapa_vivo)
        
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_vivo)
        st_folium(mapa_vivo, width="100%", height=550, returned_objects=[], key="mapa_vivo_unico")

    with tab2:
        st.markdown("#### 🗺️ Cartografía de Incidentes y Cobertura Territorial")
        
        centro_mapa = [-34.1708, -70.7444]
        zoom_mapa = 13
        if st.session_state.alerta_focus is not None:
            centro_mapa = [st.session_state.alerta_focus["Latitud"], st.session_state.alerta_focus["Longitud"]]
            zoom_mapa = 16 
            st.info(f"📍 Marcador posicionado en infracción: **{st.session_state.alerta_focus['Infracción']}** de la unidad **{st.session_state.alerta_focus['Patente']}**")
        
        mapa_calor = folium.Map(location=centro_mapa, zoom_start=zoom_mapa, tiles=None)
        folium.TileLayer('CartoDB dark_matter', name='Capa Operativa Nocturna', control=True).add_to(mapa_calor)
        folium.TileLayer('OpenStreetMap', name='Capa Vial Estándar', control=True).add_to(mapa_calor)
        
        eventos_completos = historial_ok_filtrado + alertas_filtradas

        for evt in eventos_completos:
            segmento_infractor = evt.get("Segmento_Ruta", [])
            if not segmento_infractor: segmento_infractor = [[evt["Latitud"], evt["Longitud"]], [evt["Latitud"]+0.0001, evt["Longitud"]+0.0001]]

            if evt["Infracción"] == "Operación Normal":
                folium.PolyLine(segmento_infractor, color="#2ca02c", weight=4, opacity=0.7).add_to(mapa_calor)
            else:
                color_linea = "#ff7f0e" if "Terminal" in evt["Infracción"] else "#EF3340"
                icono_marker = "info-sign" if "Terminal" in evt["Infracción"] else "exclamation-triangle"

                html_popup = f"""
                <div style='font-family: Arial, sans-serif; font-size:13px; width:240px;'>
                    <b style='color: {color_linea};'>{evt['Infracción']}</b><br><br>
                    <b>Servicio:</b> {evt['Servicio']}<br>
                    <b>Tramo Vial:</b> <span style='color: #0033A0; font-weight: bold;'>{evt['Tramo Afectado']}</span><br>
                    <b>Sector Comuna:</b> {evt['Sector Comuna']}<br>
                    <b>Hora Registro:</b> {evt['Hora Control']}<br>
                    <hr style='margin: 5px 0; border-color: #ccc;'>
                    <b>Patente:</b> {evt['Patente']}
                </div>
                """
                folium.PolyLine(segmento_infractor, color=color_linea, weight=5, opacity=0.85).add_to(mapor_calor if 'mapor_calor' in locals() else mapa_calor)
                folium.Marker(location=[evt["Latitud"], evt["Longitud"]], icon=folium.Icon(color="red" if color_linea=="#EF3340" else "orange", icon=icono_marker, prefix='fa'), popup=folium.Popup(html_popup, max_width=280)).add_to(mapa_calor)
            
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_calor)
        st_folium(mapa_calor, width="100%", height=450, returned_objects=[], key="mapa_calor_unico")
        
        st.markdown("---")
        if alertas_filtradas:
            df_alertas_f = pd.DataFrame(alertas_filtradas)
            st.subheader("Libro de Registro de Infracciones Operativas")
            st.dataframe(df_alertas_f.drop(columns=['Latitud', 'Longitud', 'Segmento_Ruta'], errors='ignore'), use_container_width=True)
            
            # Exportar Reporte en Excel estructurado
            def generar_excel_multitaba(df_completo):
                out = BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as w:
                    df_completo.drop(columns=['Latitud', 'Longitud', 'Segmento_Ruta'], errors='ignore').to_excel(w, index=False, sheet_name='Fiscalizacion_SVR')
                return out.getvalue()
            
            st.download_button(
                "📥 Exportar Reporte Institucional S.V.R (.xlsx)", 
                data=generar_excel_multitaba(df_alertas_f), 
                file_name="Reporte_Oficial_SVR_ValidacionEnRed.xlsx"
            )
        else:
            st.info("No se registran datos estadísticos. Ejecute el Motor en la barra lateral.")