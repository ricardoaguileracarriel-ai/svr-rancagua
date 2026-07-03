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

# 1. Configuración e Inicialización
st.set_page_config(layout="wide", page_title="Sistema de Validación en Red (S.V.R)", page_icon="🖥️")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'role' not in st.session_state: st.session_state.role = None  # Puede ser 'admin' o 'visor'
if 'alertas' not in st.session_state: st.session_state.alertas = []
if 'buses_en_vivo' not in st.session_state: st.session_state.buses_en_vivo = []
if 'historial_ok' not in st.session_state: st.session_state.historial_ok = []
if 'alerta_focus' not in st.session_state: st.session_state.alerta_focus = None

def pantalla_login():
    st.markdown("<div style='text-align: center; margin-top: 50px;'><h2>🔒 Sistema de Validación en Red (S.V.R)</h2><p style='color: gray;'>Perímetro de Exclusión y Regulación Operativa</p></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("Formulario"):
            usuario = st.text_input("Usuario Institucional")
            contrasena = st.text_input("Contraseña de Seguridad", type="password")
            if st.form_submit_button("Ingresar a la Plataforma"):
                if usuario == "admin" and contrasena == "rancagua2026":
                    st.session_state.logged_in = True
                    st.session_state.role = "admin"
                    st.rerun()
                elif usuario == "visor" and contrasena == "consulta2026":
                    st.session_state.logged_in = True
                    st.session_state.role = "visor"
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")

# --- INICIO DE INTERFAZ ---
if not st.session_state.logged_in:
    pantalla_login()
else:
    col_tit, col_log = st.columns([9, 1])
    with col_tit:
        st.markdown("<h1 style='white-space: nowrap; font-size: 2.3rem;'>🖥️ Sistema de Validación en Red (S.V.R)</h1>", unsafe_allow_html=True)
    with col_log:
        st.write("")
        if st.button("🔒 Cerrar Sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.rerun()

    st.sidebar.header("⚙️ Ingesta de Datos Regulados")
    
    # --- CONTROL DE ACCESO POR ROLES (RBAC) ---
    archivos_kmz_procesar = []
    archivo_padron = None
    archivo_gtfs = None  # Variable para el GTFS

    if st.session_state.role == "admin":
        st.sidebar.info("👑 Modo Administrador: Carga manual habilitada.")
        archivos_kmz_crudos = st.sidebar.file_uploader("1. Archivos KMZ Oficiales", type=["kmz"], accept_multiple_files=True)
        if archivos_kmz_crudos:
            archivos_kmz_procesar = [(f.name, f) for f in sorted(archivos_kmz_crudos, key=lambda f: f.name)]
        
        # Corrección: Agregado el botón para GTFS
        archivo_gtfs = st.sidebar.file_uploader("2. GTFS Regulado (.zip)", type=["zip"])
        
        archivo_padron = st.sidebar.file_uploader("3. Padrón de Patentes (.xlsx)", type=["xlsx"])
        
    elif st.session_state.role == "visor":
        st.sidebar.info("👁️ Modo Visor: Lectura automática desde la base de datos central.")
        carpeta_datos = "datos"
        if os.path.exists(carpeta_datos):
            archivos_locales = os.listdir(carpeta_datos)
            
            # Corrección: .lower() asegura que lea tanto .kmz como .KMZ
            kmz_locales = sorted([f for f in archivos_locales if f.lower().endswith('.kmz')])
            padron_local = [f for f in archivos_locales if f.lower().endswith('.xlsx') or f.lower().endswith('.xls')]
            
            if not kmz_locales:
                st.sidebar.warning("⚠️ No se detectaron archivos KMZ en la carpeta 'datos'.")
            if not padron_local:
                st.sidebar.warning("⚠️ No se detectó un archivo Excel en la carpeta 'datos'.")
                
            # Preparamos las rutas para que el procesador las lea directamente
            archivos_kmz_procesar = [(nombre, os.path.join(carpeta_datos, nombre)) for nombre in kmz_locales]
            if padron_local:
                archivo_padron = os.path.join(carpeta_datos, padron_local[0])
        else:
            st.sidebar.error("❌ La carpeta 'datos' no existe en tu proyecto. Créala y pon los archivos allí.")

    # --- PROCESAMIENTO DE ARCHIVOS ---
    lineas_dict = {}
    if archivos_kmz_procesar:
        for nombre_archivo, archivo_o_ruta in archivos_kmz_procesar:
            nombre_servicio = nombre_archivo.split(".")[0].upper()
            datos_kmz = extraer_coordenadas_kmz(archivo_o_ruta)
            if datos_kmz: 
                lineas_dict[nombre_servicio] = datos_kmz

    nombres_servicios_reales = list(lineas_dict.keys())
    df_padron = cargar_padron_matricial(archivo_padron, nombres_servicios_reales) if archivo_padron else None
    
    if df_padron is not None:
        total_electricos = df_padron['Es_Electrico'].sum() if 'Es_Electrico' in df_padron.columns else 0
        st.sidebar.success(f"✅ Familias de Líneas: {len(nombres_servicios_reales)}")
        st.sidebar.success(f"✅ Flota Vinculada: {len(df_padron)} patentes listas.")

    if st.sidebar.button("🚀 Iniciar Motor de Análisis en Vivo", use_container_width=True):
        if not lineas_dict:
            st.sidebar.error("No hay archivos KMZ cargados en el sistema para analizar.")
        else:
            st.session_state.alerta_focus = None
            st.session_state.alertas = []
            st.session_state.historial_ok = []

            hora_actual_dt = datetime.now()
            hora_actual_str = hora_actual_dt.strftime("%H:%M:%S")
            buses_calculados = []
            nuevas_notificaciones = []
            
            es_horario_comercial = 5 <= hora_actual_dt.hour < 22
            
            if not es_horario_comercial:
                st.toast("🌙 Sistema operando en horario nocturno. Flota en retorno.", icon="🌙")

            if df_padron is not None and not df_padron.empty:
                flota_muestra = df_padron.sample(min(20, len(df_padron))) if len(df_padron) > 20 else df_padron
                
                for _, fila in flota_muestra.iterrows():
                    patente = str(fila['Patente'])
                    linea_asignada = str(fila['Servicio_Oficial'])
                    es_electrico = fila.get('Es_Electrico', False)
                    
                    if linea_asignada not in lineas_dict:
                        continue 
                    
                    rutas_obj = lineas_dict[linea_asignada]['rutas']
                    paraderos_obj = lineas_dict[linea_asignada]['paraderos']
                    
                    if not rutas_obj:
                        continue
                        
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
                        "ID Alerta": f"ALT-{random.randint(100,999)}", 
                        "Patente": patente, 
                        "Servicio": linea_asignada,
                        "Variante": variante_exacta,
                        "Infracción": estado, 
                        "Tramo Afectado": tramo_preciso,
                        "Sector Comuna": sector, 
                        "Hora Control": hora_actual_str,
                        "Tiempo de Abandono": f"{tiempo_abandono_simulado} min",
                        "Latitud": lat_snap, 
                        "Longitud": lon_snap,
                        "Segmento_Ruta": trazado_infractor
                    }

                    if estado == "Operación Normal":
                        st.session_state.historial_ok.append(datos_evento)
                    else:
                        st.session_state.alertas.append(datos_evento)
                        nuevas_notificaciones.append(datos_evento)
            
            st.session_state.buses_en_vivo = buses_calculados

            if nuevas_notificaciones:
                for idx, notif in enumerate(nuevas_notificaciones):
                    if idx < 3: 
                        icono = "⚠️" if "Terminal" in notif['Infracción'] else "🚨"
                        st.toast(f"**{notif['Infracción']}**\n\nPatente: {notif['Patente']} - Línea: {notif['Servicio']}", icon=icono)
                if len(nuevas_notificaciones) > 3:
                    st.toast(f"📱 ... y {len(nuevas_notificaciones) - 3} alertas adicionales. Revisa el panel lateral.", icon="📲")

    # ==========================================
    # BARRA LATERAL: CENTRO DE NOTIFICACIONES 
    # ==========================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔔 Centro de Notificaciones")
    if st.session_state.alertas:
        for a in st.session_state.alertas:
            color_borde = "#ff7f0e" if "Terminal" in a['Infracción'] else "#d62728"
            icono_noti = "⚠️" if "Terminal" in a['Infracción'] else "🚨"
            
            with st.sidebar.container(border=True):
                st.markdown(f"<p style='color:{color_borde}; font-weight:bold; margin-bottom:2px;'>{icono_noti} {a['Infracción']}</p>", unsafe_allow_html=True)
                st.caption(f"**PPU:** {a['Patente']} | **Línea:** {a['Servicio']}")
                
                if st.button("📍 Localizar Infracción", key=f"btn_loc_{a['ID Alerta']}", use_container_width=True):
                    st.session_state.alerta_focus = a
                    st.rerun()
    else:
        st.sidebar.info("No hay incidentes reportados en este momento.")

    # ==========================================
    # PANEL DE CONTROL ESTRUCTURADO 
    # ==========================================
    st.markdown("### 🔍 Panel de control")
    
    opciones_lineas = list(lineas_dict.keys()) if lineas_dict else []
    opciones_infracciones = list(set([a["Infracción"] for a in st.session_state.alertas])) if st.session_state.alertas else ["Todas"]

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1: filtro_linea = st.selectbox("📋 Línea", ["Todas"] + opciones_lineas)
        opciones_variantes_crudas = set()
        if lineas_dict:
            for lbl, datos in lineas_dict.items():
                if filtro_linea == "Todas" or filtro_linea == lbl:
                    for seg in datos['rutas']:
                        if 'variante' in seg: opciones_variantes_crudas.add(seg['variante'].upper())
        opciones_variantes = sorted(list(opciones_variantes_crudas))
        with col2: filtro_variante = st.selectbox("🔀 Variante", ["Todas"] + opciones_variantes)
        
        col3, col4, col5 = st.columns(3)
        with col3: filtro_infraccion = st.selectbox("🚦 Estado Operativo", ["Todas"] + opciones_infracciones)
        with col4: filtro_tecnologia = st.selectbox("⚡ Tecnología", ["Todas", "Solo Eléctricos", "Solo Diésel"])
        with col5: buscar_patente_input = st.text_input("🔎 Placa Patente (P.P.U)", "")

    buscar_patente = buscar_patente_input.strip().upper()

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

    tab1, tab2 = st.tabs(["🛰️ Monitoreo en Tiempo Real", "🔥 Análisis de Cobertura y Trazados"])

    with tab1:
        mapa_vivo = folium.Map(location=[-34.1708, -70.7444], zoom_start=13)
        folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite (Híbrida)').add_to(mapa_vivo)

        colores_lineas = ["#E6194B", "#4363D8", "#469990", "#F58231", "#911EB4", "#00FFFF", "#F032E6"] 

        for idx, (lbl, datos) in enumerate(lineas_dict.items()):
            if filtro_linea == "Todas" or filtro_linea == lbl:
                for segmento_obj in datos['rutas']:
                    var_name = segmento_obj.get('variante', '').upper()
                    if filtro_variante != "Todas" and filtro_variante != var_name: continue
                        
                    folium.PolyLine(
                        segmento_obj['trazado'], 
                        color=colores_lineas[idx % len(colores_lineas)], 
                        weight=4, opacity=0.9, 
                        tooltip=f"Línea: {lbl} | Variante: {segmento_obj.get('variante', '')}",
                        popup=f"<div style='font-size:12px; width:180px;'><b>Línea Base:</b> {lbl}<br><b>Variante:</b> {segmento_obj.get('variante', '')}</div>"
                    ).add_to(mapa_vivo)

        for bus in buses_filtrados:
            es_electrico = bus.get('electrico', False)
            icon_color = "green" if es_electrico and bus['estado'] == "Operación Normal" else bus['color']
            icon_tipo = "bolt" if es_electrico else "bus"
            tec_text = "⚡ Eléctrico" if es_electrico else "Diésel"
            
            html_pop = f"<div style='font-size: 12px; width: 200px;'><b>Patente:</b> {bus['id']}<br><b>Servicio:</b> {bus['linea']}<br><b>Tecnología:</b> {tec_text}<br><b>Estado:</b> {bus['estado']}</div>"
            folium.Marker([bus["lat"], bus["lon"]], icon=folium.Icon(color=icon_color, icon=icon_tipo, prefix='fa'), popup=folium.Popup(html_pop, max_width=250)).add_to(mapa_vivo)
        
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_vivo)
        st_folium(mapa_vivo, width="100%", height=550, returned_objects=[])

    with tab2:
        st.markdown("#### 🗺️ Análisis de Operación y Trazados Inteligentes")
        
        centro_mapa = [-34.1708, -70.7444]
        zoom_mapa = 13
        if st.session_state.alerta_focus is not None:
            centro_mapa = [st.session_state.alerta_focus["Latitud"], st.session_state.alerta_focus["Longitud"]]
            zoom_mapa = 16 
            st.info(f"📍 Mostrando en el mapa: **{st.session_state.alerta_focus['Infracción']}** de la patente **{st.session_state.alerta_focus['Patente']}**")
        
        mapa_calor = folium.Map(location=centro_mapa, zoom_start=zoom_mapa, tiles=None)
        
        folium.TileLayer('CartoDB dark_matter', name='Modo Oscuro (Gris/Negro)', control=True).add_to(mapa_calor)
        folium.TileLayer('OpenStreetMap', name='Modo Claro (Estándar)', control=True).add_to(mapa_calor)
        folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite (Híbrida)').add_to(mapa_calor)
        
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
                if "Terminal" in evt["Infracción"]:
                    color_linea = "#ff7f0e"
                    titulo_tarjeta = f"⚠️ {evt['Infracción']}"
                    icono_marker = "info-sign"
                else:
                    color_linea = "#d62728"
                    titulo_tarjeta = f"🚨 {evt['Infracción']}"
                    icono_marker = "exclamation-triangle"

                html_popup = f"""
                <div style='font-family: Arial; font-size: 13px; width: 240px;'>
                    <b style='color: {color_linea}; font-size: 14px;'>{titulo_tarjeta}</b><br><br>
                    <b>Línea:</b> {evt['Servicio']}<br>
                    <b>Variante:</b> {evt['Variante']}<br>
                    <b>Calles/Rutas:</b> <span style='color: #1565c0; font-weight: bold;'>{evt['Tramo Afectado']}</span><br>
                    <b>Sector:</b> {evt['Sector Comuna']}<br>
                    <b>Hora Evento:</b> {evt['Hora Control']}<br>
                    <b>Tiempo Estado:</b> <span style='color: #444; font-weight: bold;'>{evt['Tiempo de Abandono']}</span><br>
                    <hr style='margin: 6px 0; border-color: #ccc;'>
                    <b>Patente Involucrada:</b> {evt['Patente']}
                </div>
                """
                
                folium.PolyLine(segmento_infractor, color=color_linea, weight=5, opacity=0.85, popup=folium.Popup(html_popup, max_width=280)).add_to(mapa_calor)
                folium.Marker(
                    location=[evt["Latitud"], evt["Longitud"]],
                    icon=folium.Icon(color="red" if color_linea=="#d62728" else "orange", icon=icono_marker, prefix='fa'),
                    popup=folium.Popup(html_popup, max_width=280)
                ).add_to(mapa_calor)
            
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_calor)
        st_folium(mapa_calor, width="100%", height=450, returned_objects=[])
        
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
                    st.error(f"📍 **Falla en Sector {row['Sector Comuna']}** | El tramo **{row['Tramo Afectado']}** ha sido abandonado por el servicio: **{row['Servicios']}** (Último registro: {row['Ultimo_Registro']}).")
            else:
                st.success("✅ No se registran desvíos críticos que impliquen el abandono de ejes viales en este momento.")
            
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
                        resumen.to_excel(w, index=False, sheet_name='Resumen_Calles_Abandonadas')
                    else:
                        pd.DataFrame([{"Mensaje": "Sin reportes de abandono vial en este período de control."}]).to_excel(w, index=False, sheet_name='Resumen_Calles_Abandonadas')
                return out.getvalue()
            
            st.download_button(
                "📥 Exportar Libro S.V.R a Excel (.xlsx)", 
                data=generar_excel_multitaba(df_alertas_f, df_abandonos), 
                file_name="Reporte_SVR_ValidacionEnRed.xlsx"
            )
        else:
            st.info("Inicie el motor de análisis en vivo para consolidar el reporte territorial.")