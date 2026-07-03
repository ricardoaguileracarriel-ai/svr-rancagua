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

# 1. Configuración de la página (Framework Digital Gob.cl)
st.set_page_config(layout="wide", page_title="S.V.R. — Gobierno de Chile", page_icon="🇨🇱")

# Estilos CSS del Framework Digital de Chile (Colores oficiales Azul #0033A0 y Rojo #EF3340)
st.markdown("""
    <style>
        /* Estilización general basada en framework.digital.gob.cl */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
        
        html, body, [data-testid="stSidebar"] {
            font-family: 'Roboto', sans-serif;
        }
        
        /* Modificar el botón principal del sistema */
        div.stButton > button:first-child {
            background-color: #0033A0 !important;
            color: white !important;
            border-radius: 4px !important;
            border: none !important;
            font-weight: 500 !important;
            padding: 0.6rem 1.2rem !important;
            transition: background-color 0.2s ease;
        }
        div.stButton > button:first-child:hover {
            background-color: #002266 !important;
            border: none !important;
        }
        
        /* Botones secundarios o de alerta lateral */
        .stDownloadButton > button {
            background-color: #ffffff !important;
            color: #0033A0 !important;
            border: 1px solid #0033A0 !important;
            border-radius: 4px !important;
        }
        .stDownloadButton > button:hover {
            background-color: #f4f6f9 !important;
            color: #002266 !important;
        }
    </style>
""", unsafe_allow_html=True)

# Inicialización de Estados
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'role' not in st.session_state: st.session_state.role = None
if 'alertas' not in st.session_state: st.session_state.alertas = []
if 'buses_en_vivo' not in st.session_state: st.session_state.buses_en_vivo = []
if 'historial_ok' not in st.session_state: st.session_state.historial_ok = []
if 'alerta_focus' not in st.session_state: st.session_state.alerta_focus = None

# --- PANTALLA DE LOGIN INSTITUCIONAL ---
def pantalla_login():
    # Header del Gobierno para el Login
    st.markdown("""
        <div style="background-color: #0033A0; padding: 20px; border-bottom: 5px solid #EF3340; text-align: center; color: white; border-radius: 6px 6px 0 0; margin-top: 40px;">
            <span style="font-weight: 300; font-size: 0.9rem; letter-spacing: 2px;">GOBIERNO DE CHILE</span><br>
            <h2 style="margin: 5px 0 0 0; color: white; font-size: 1.8rem; font-weight: 700;">Plataforma de Validación en Red (S.V.R)</h2>
            <p style="margin: 5px 0 0 0; opacity: 0.8; font-size: 0.9rem;">División de Transporte Público Regional — Región de O'Higgins</p>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<p style='text-align: center; font-weight: 500; color: #333; margin-top: 10px;'>Control de Acceso de Funcionarios</p>", unsafe_allow_html=True)
            with st.form("Formulario_Gob"):
                usuario = st.text_input("📍 Identificador Institucional (Usuario)", placeholder="ejemplo.r")
                contrasena = st.text_input("🔒 Contraseña de Seguridad", type="password", placeholder="••••••••")
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("Autenticar e Ingresar al Sistema", use_container_width=True):
                    if usuario == "admin" and contrasena == "rancagua2026":
                        st.session_state.logged_in = True
                        st.session_state.role = "admin"
                        st.rerun()
                    elif usuario == "visor" and contrasena == "consulta2026":
                        st.session_state.logged_in = True
                        st.session_state.role = "visor"
                        st.rerun()
                    else:
                        st.error("Credenciales del sistema incorrectas. Intente nuevamente.")
            st.caption("⚠️ Uso estrictamente reservado para personal analista del Ministerio de Transportes y Telecomunicaciones.")

# --- INICIO DE INTERFAZ AUTENTICADA ---
if not st.session_state.logged_in:
    pantalla_login()
else:
    # --- BANNER SUPERIOR OFICIAL (DISEÑO FRAMEWORK DIGITAL DE CHILE) ---
    st.markdown("""
        <div style="background-color: #0033A0; padding: 16px 24px; border-bottom: 4px solid #EF3340; color: white; display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.08);">
            <div>
                <span style="font-weight: bold; font-size: 0.8rem; letter-spacing: 1.5px; opacity: 0.9;">GOBIERNO DE CHILE</span><br>
                <span style="font-size: 1.3rem; font-weight: 700; color: white;">Sistema de Validación en Red — S.V.R Rancagua</span>
            </div>
            <div style="text-align: right; opacity: 0.9;">
                <span style="font-size: 0.85rem; font-weight: 400; display: block;">Ministerio de Transportes y Telecomunicaciones</span>
                <span style="font-size: 0.75rem; font-weight: 300; display: block; background: rgba(255,255,255,0.15); padding: 2px 6px; border-radius: 3px; margin-top: 3px; text-align: center;">Regulación Perímetro de Exclusión</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Botón de cierre de sesión reposicionado arriba de manera discreta
    col_vacia, col_logout = st.columns([8.5, 1.5])
    with col_logout:
        if st.button("🔒 Cerrar Sesión Segura", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.rerun()

    # Barra lateral de Ingesta Institucional
    st.sidebar.markdown("<h3 style='color: #0033A0; margin-bottom:0;'>⚙️ Ingesta de Datos</h3>", unsafe_allow_html=True)
    st.sidebar.markdown("<p style='font-size:0.85rem; color:gray; margin-top:0;'>Marco Regulado de Electromovilidad</p>", unsafe_allow_html=True)
    
    archivos_kmz_procesar = []
    archivo_padron = None
    archivo_gtfs = None 

    if st.session_state.role == "admin":
        st.sidebar.markdown("<span style='background-color: #e6f0fa; color: #0033A0; padding: 3px 8px; border-radius: 3px; font-size: 0.8rem; font-weight: 500;'>Rol: Administrador Central</span>", unsafe_allow_html=True)
        st.sidebar.write("")
        archivos_kmz_crudos = st.sidebar.file_uploader("1. Archivos KMZ Oficiales", type=["kmz"], accept_multiple_files=True)
        if archivos_kmz_crudos:
            archivos_kmz_procesar = [(f.name, f) for f in sorted(archivos_kmz_crudos, key=lambda f: f.name)]
        archivo_gtfs = st.sidebar.file_uploader("2. GTFS Regulado (.zip)", type=["zip"])
        archivo_padron = st.sidebar.file_uploader("3. Padrón de Patentes (.xlsx)", type=["xlsx"])
        
    elif st.session_state.role == "visor":
        st.sidebar.markdown("<span style='background-color: #f5f5f5; color: #333; padding: 3px 8px; border-radius: 3px; font-size: 0.8rem; font-weight: 500;'>Rol: Inspector / Visor</span>", unsafe_allow_html=True)
        st.sidebar.write("")
        carpeta_datos = "datos"
        if os.path.exists(carpeta_datos):
            archivos_locales = os.listdir(carpeta_datos)
            kmz_locales = sorted([f for f in archivos_locales if f.lower().endswith('.kmz')])
            padron_local = [f for f in archivos_locales if f.lower().endswith('.xlsx') or f.lower().endswith('.xls')]
            
            if not kmz_locales: st.sidebar.warning("⚠️ Sin archivos KMZ en servidor.")
            if not padron_local: st.sidebar.warning("⚠️ Sin Padrón Excel en servidor.")
                
            archivos_kmz_procesar = [(nombre, os.path.join(carpeta_datos, nombre)) for nombre in kmz_locales]
            if padron_local: archivo_padron = os.path.join(carpeta_datos, padron_local[0])
        else:
            st.sidebar.error("❌ Carpeta de datos del servidor ausente.")

    # --- PROCESAMIENTO DE ARCHIVOS ---
    lineas_dict = {}
    if archivos_kmz_procesar:
        for nombre_archivo, archivo_o_ruta in archivos_kmz_procesar:
            nombre_servicio = nombre_archivo.split(".")[0].upper()
            datos_kmz = extraer_coordenadas_kmz(archivo_o_ruta)
            if datos_kmz: lineas_dict[nombre_servicio] = datos_kmz

    nombres_servicios_reales = list(lineas_dict.keys())
    df_padron = cargar_padron_matricial(archivo_padron, nombres_servicios_reales) if archivo_padron else None
    
    if df_padron is not None:
        st.sidebar.success(f"📊 Flota Vinculada: {len(df_padron)} Buses")

    if st.sidebar.button("🚀 Iniciar Motor de Fiscalización Territorial", use_container_width=True):
        if not lineas_dict:
            st.sidebar.error("Cargue cartografía regulada (KMZ) para operar.")
        else:
            st.session_state.alerta_focus = None
            st.session_state.alertas = []
            st.session_state.historial_ok = []

            hora_actual_dt = datetime.now()
            hora_actual_str = hora_actual_dt.strftime("%H:%M:%S")
            buses_calculados = []
            nuevas_notificaciones = []
            
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

                    if estado == "Operación Normal": historial_ok_filtrado.append(datos_evento)
                    else:
                        st.session_state.alertas.append(datos_evento)
                        nuevas_notificaciones.append(datos_evento)
            
            st.session_state.buses_en_vivo = buses_calculados
            if nuevas_notificaciones: st.toast(f"🚨 Se han consolidado {len(nuevas_notificaciones)} eventos fuera de norma.", icon="🚨")

    # --- CENTRO DE NOTIFICACIONES LATERAL ---
    st.sidebar.markdown("---")
    st.sidebar.markdown("<h4 style='color: #EF3340; margin-bottom: 5px;'>🔔 Alertas Activas</h4>", unsafe_allow_html=True)
    if st.session_state.alertas:
        for a in st.session_state.alertas:
            color_borde = "#ff7f0e" if "Terminal" in a['Infracción'] else "#EF3340"
            with st.sidebar.container(border=True):
                st.markdown(f"<p style='color:{color_borde}; font-weight:bold; margin-bottom:2px; font-size:0.85rem;'>⚠️ {a['Infracción']}</p>", unsafe_allow_html=True)
                st.caption(f"**PPU:** {a['Patente']} | **Línea:** {a['Servicio']}")
                if st.button("📍 Geolocalizar", key=f"btn_loc_{a['ID Alerta']}", use_container_width=True):
                    st.session_state.alerta_focus = a
                    st.rerun()
    else:
        st.sidebar.info("Flota operando bajo parámetros normales.")

    # --- PANEL DE CONTROL CON FILTROS LIMPIOS (MÓDULO DE BÚSQUEDA) ---
    st.markdown("### 🔍 Módulos de Filtro Avanzado")
    opciones_lineas = list(lineas_dict.keys()) if lineas_dict else []
    opciones_infracciones = list(set([a["Infracción"] for a in st.session_state.alertas])) if st.session_state.alertas else ["Todas"]

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1: filtro_linea = st.selectbox("📋 Unidad de Negocio / Línea", ["Todas"] + opciones_lineas)
        opciones_variantes_crudas = set()
        if lineas_dict:
            for lbl, datos in lineas_dict.items():
                if filtro_linea == "Todas" or filtro_linea == lbl:
                    for seg in datos['rutas']:
                        if 'variante' in seg: opciones_variantes_crudas.add(seg['variante'].upper())
        opciones_variantes = sorted(list(opciones_variantes_crudas))
        with col2: filtro_variante = st.selectbox("🔀 Trazado / Variante Colectiva", ["Todas"] + opciones_variantes)
        
        col3, col4, col5 = st.columns(3)
        with col3: filtro_infraccion = st.selectbox("🚦 Estado de Cumplimiento", ["Todas"] + opciones_infracciones)
        with col4: filtro_tecnologia = st.selectbox("⚡ Segmentación Energética", ["Todas", "Solo Eléctricos", "Solo Diésel"])
        with col5: buscar_patente_input = st.text_input("🔎 Filtrar por Patente (P.P.U)", placeholder="ABCD-12")

    buscar_patente = buscar_patente_input.strip().upper()

    # Filtros de datos en memoria
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

    # --- PESTAÑAS INSTITUCIONALES ---
    tab1, tab2 = st.tabs(["🛰️ Cartografía y Posicionamiento GPS", "🔥 Análisis de Desvíos e Historial Normativo"])

    with tab1:
        mapa_vivo = folium.Map(location=[-34.1708, -70.7444], zoom_start=13)
        folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite Regulador').add_to(mapa_vivo)

        colores_lineas = ["#0033A0", "#EF3340", "#469990", "#F58231", "#911EB4", "#00FFFF", "#F032E6"] 

        for idx, (lbl, datos) in enumerate(lineas_dict.items()):
            if filtro_linea == "Todas" or filtro_linea == lbl:
                for segmento_obj in datos['rutas']:
                    var_name = segmento_obj.get('variante', '').upper()
                    if filtro_variante != "Todas" and filtro_variante != var_name: continue
                    folium.PolyLine(
                        segmento_obj['trazado'], color=colores_lineas[idx % len(colores_lineas)], 
                        weight=4, opacity=0.8, tooltip=f"Línea: {lbl}"
                    ).add_to(mapa_vivo)

        for bus in buses_filtrados:
            es_electrico = bus.get('electrico', False)
            icon_color = "green" if es_electrico and bus['estado'] == "Operación Normal" else bus['color']
            icon_tipo = "bolt" if es_electrico else "bus"
            tec_text = "⚡ Eléctrico" if es_electrico else "⚙️ Diésel"
            
            html_pop = f"<div style='font-family: Roboto, sans-serif; font-size: 12px; width: 180px;'><b>PPU:</b> {bus['id']}<br><b>Servicio:</b> {bus['linea']}<br><b>Tecnología:</b> {tec_text}<br><b>Estado:</b> {bus['estado']}</div>"
            folium.Marker([bus["lat"], bus["lon"]], icon=folium.Icon(color=icon_color, icon=icon_tipo, prefix='fa'), popup=folium.Popup(html_pop, max_width=250)).add_to(mapa_vivo)
        
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_vivo)
        st_folium(mapa_vivo, width="100%", height=550, returned_objects=[], key="mapa_vivo_unico")

    with tab2:
        st.markdown("#### 🗺️ Reporte Territorial de Modificaciones de Trazado")
        
        centro_mapa = [-34.1708, -70.7444]
        zoom_mapa = 13
        if st.session_state.alerta_focus is not None:
            centro_mapa = [st.session_state.alerta_focus["Latitud"], st.session_state.alerta_focus["Longitud"]]
            zoom_mapa = 16 
            st.info(f"📍 Foco cartográfico establecido en: **{st.session_state.alerta_focus['Infracción']}** — Patente **{st.session_state.alerta_focus['Patente']}**")
        
        mapa_calor = folium.Map(location=centro_mapa, zoom_start=zoom_mapa, tiles=None)
        folium.TileLayer('CartoDB dark_matter', name='Modo Nocturno / Operativo', control=True).add_to(mapa_calor)
        folium.TileLayer('OpenStreetMap', name='Modo Técnico / Vial', control=True).add_to(mapa_calor)
        
        for idx, (lbl, datos) in enumerate(lineas_dict.items()):
            if filtro_linea == "Todas" or filtro_linea == lbl:
                for segmento_obj in datos['rutas']:
                    var_name = segmento_obj.get('variante', '').upper()
                    if filtro_variante != "Todas" and filtro_variante != var_name: continue
                    folium.PolyLine(segmento_obj['trazado'], color="#aaaaaa", weight=1.5, opacity=0.5).add_to(mapa_calor)

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
                <div style='font-family: Arial, sans-serif; font-size: 13px; width: 240px;'>
                    <b style='color: {color_linea}; font-size: 14px;'>{evt['Infracción']}</b><br><br>
                    <b>Servicio Asociado:</b> {evt['Servicio']}<br>
                    <b>Variante:</b> {evt['Variante']}<br>
                    <b>Eje Vial Afectado:</b> <span style='color: #0033A0; font-weight: bold;'>{evt['Tramo Afectado']}</span><br>
                    <b>Sector:</b> {evt['Sector Comuna']}<br>
                    <b>Hora Registro:</b> {evt['Hora Control']}<br>
                    <hr style='margin: 6px 0; border-color: #ccc;'>
                    <b>PPU Involucrada:</b> {evt['Patente']}
                </div>
                """
                folium.PolyLine(segmento_infractor, color=color_linea, weight=5, opacity=0.85).add_to(mapa_calor)
                folium.Marker(location=[evt["Latitud"], evt["Longitud"]], icon=folium.Icon(color="red" if color_linea=="#EF3340" else "orange", icon=icono_marker, prefix='fa'), popup=folium.Popup(html_popup, max_width=280)).add_to(mapa_calor)
            
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_calor)
        st_folium(mapa_calor, width="100%", height=450, returned_objects=[], key="mapa_calor_unico")
        
        st.markdown("---")
        st.markdown("#### 🚨 Alertas Estratégicas: Puntos Ciegos y Fallas de Cobertura Vial")
        
        if alertas_filtradas:
            df_alertas_f = pd.DataFrame(alertas_filtradas)
            df_abandonos = df_alertas_f[df_alertas_f["Infracción"].isin(["Abandono de Trazado", "Acorte/Cambio de Recorrido"])]
            
            if not df_abandonos.empty:
                agrupado = df_abandonos.groupby(["Sector Comuna", "Tramo Afectado"]).agg(
                    Servicios=('Servicio', lambda x: ", ".join(sorted(x.unique()))),
                    Ultimo_Registro=('Hora Control', 'max')
                ).reset_index()
                
                for _, row in agrupado.iterrows():
                    st.error(f"📍 **Informe Operativo Comuna:** El tramo **{row['Tramo Afectado']}** ({row['Sector Comuna']}) registra abandono temporal de la flota de servicios: **{row['Servicios']}** (Último control: {row['Ultimo_Registro']}).")
            else:
                st.success("✅ Cobertura de la red en Rancagua operando con frecuencias estables de trazado.")
            
            st.markdown("---")
            st.subheader("Libro Estadístico de Infracciones Operativas")
            st.dataframe(df_alertas_f.drop(columns=['Latitud', 'Longitud', 'Segmento_Ruta'], errors='ignore'), use_container_width=True)
            
            def generar_excel_multitaba(df_completo, df_ab):
                out = BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as w:
                    df_completo.drop(columns=['Latitud', 'Longitud', 'Segmento_Ruta'], errors='ignore').to_excel(w, index=False, sheet_name='Fiscalizacion_Detallada')
                    if not df_ab.empty:
                        resumen = df_ab.groupby(["Sector Comuna", "Tramo Afectado"]).agg(
                            Servicios_Ausentes=('Servicio', lambda x: ", ".join(sorted(x.unique()))),
                            Ultimo_Registro_Control=('Hora Control', 'max'),
                            Casos_Registrados=('ID Alerta', 'count')
                        ).reset_index()
                        resumen.to_excel(w, index=False, sheet_name='Resumen_Ejes_Abandonados')
                return out.getvalue()
            
            st.download_button(
                "📥 Exportar Libro S.V.R Regulado (.xlsx)", 
                data=generar_excel_multitaba(df_alertas_f, df_abandonos), 
                file_name="Reporte_Oficial_SVR_ValidacionEnRed.xlsx"
            )
        else:
            st.info("Inicie el motor de análisis en vivo para consolidar el reporte territorial.")