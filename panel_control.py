import streamlit as st
import pandas as pd
from io import BytesIO
import folium
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium
import random
from datetime import datetime
import os

# --- IMPORTACIÓN DE NUESTROS MÓDULOS SEPARADOS ---
from modulos.ingesta_datos import extraer_coordenadas_kmz, cargar_padron_matricial
import concurrent.futures
from modulos.motor_gps import (
    snap_punto_a_ruta, evaluar_operacion, determinar_sector,
    obtener_calle_real, elegir_puntos_desviacion, calcular_ruta_desviada
)
from modulos.almacenamiento import init_db, guardar_evento, guardar_lote, contar_registros_archivados, cargar_historico, vaciar_historico
from modulos.informes import calcular_metricas, generar_pdf_informe, grafico_barras

init_db()  # Se asegura que el archivador SQLite exista antes de usarlo.


@st.cache_data(show_spinner="📂 Procesando archivo KMZ...")
def procesar_kmz_cacheado(archivo_o_ruta, marca_tiempo=None):
    """Cachea el parseo de cada KMZ. marca_tiempo (mtime del archivo) fuerza
    recalcular si el archivo local cambió; para archivos subidos no se necesita
    porque Streamlit ya cachea por contenido."""
    return extraer_coordenadas_kmz(archivo_o_ruta)


@st.cache_data(show_spinner="📂 Procesando padrón de patentes...")
def cargar_padron_cacheado(archivo_padron, nombres_servicios_reales, marca_tiempo=None):
    return cargar_padron_matricial(archivo_padron, nombres_servicios_reales)

# 1. Configuración de la plataforma
st.set_page_config(layout="wide", page_title="Sistema de Validación en Red (S.V.R)", page_icon="🖥️")

# Inicialización segura de variables de estado
for key in ['logged_in', 'role', 'alertas', 'buses_en_vivo', 'historial_ok', 'alerta_focus']:
    if key not in st.session_state:
        st.session_state[key] = False if key == 'logged_in' else None if key in ['role', 'alerta_focus'] else []

def pantalla_login():
    st.markdown("""
        <style>
        [data-testid="stAppViewContainer"] { 
            background-image: url('https://github.com/ricardoaguileracarriel-ai/svr-rancagua/blob/cf5c24d4ef44549ef679e8ee31ab419731fb76c5/fondo_bus.png?raw=true'); 
            background-size: cover; background-position: center; background-attachment: fixed;
        }
        [data-testid="stHeader"] { background-color: transparent; }
        .block-container { padding-top: 3rem !important; max-width: 900px; }
        [data-testid="stForm"] {
            background-color: rgba(13, 22, 41, 0.35) !important;
            backdrop-filter: blur(6px);
            border: 1px solid rgba(255,255,255,0.25) !important;
            padding: 1.5rem 2rem !important; border-radius: 8px !important;
        }
        [data-testid="stForm"] label { color: #FFFFFF !important; }
        [data-testid="stForm"] input {
            color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important;
            background-color: rgba(13, 22, 41, 0.6) !important;
        }
        [data-testid="stForm"] [data-baseweb="input"] { background-color: rgba(13, 22, 41, 0.6) !important; }
        /* El navegador (autocompletar de Chrome) pinta el input de amarillo con letra
           negra al escribir, ignorando nuestro CSS normal. Este es el truco estándar
           para neutralizarlo y mantener el texto blanco sobre fondo oscuro. */
        [data-testid="stForm"] input:-webkit-autofill,
        [data-testid="stForm"] input:-webkit-autofill:hover,
        [data-testid="stForm"] input:-webkit-autofill:focus {
            -webkit-text-fill-color: #FFFFFF !important;
            -webkit-box-shadow: 0 0 0px 1000px rgba(13,22,41,0.85) inset !important;
            transition: background-color 9999s ease-in-out 0s;
        }
        div.stButton > button { background-color: #006FB3 !important; border: none !important; color: white !important; font-weight: bold !important; }
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; font-size: 2rem; color: white; text-shadow: 2px 2px 5px #000; margin-bottom: 15px;'>Sistema de Validación en Red (S.V.R.)</h1>", unsafe_allow_html=True)
        with st.form("Formulario"):
            st.markdown("<p style='text-align: center; font-weight: bold; font-size:1.1rem; color: white;'>INICIAR SESIÓN SEGURA</p>", unsafe_allow_html=True)
            usuario = st.text_input("Usuario Institucional")
            contrasena = st.text_input("Contraseña de Seguridad", type="password")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.form_submit_button("Ingresar a la Plataforma", use_container_width=True):
                if usuario == "admin" and contrasena == "rancagua2026":
                    st.session_state.logged_in = True; st.session_state.role = "admin"; st.rerun()
                elif usuario == "visor" and contrasena == "consulta2026":
                    st.session_state.logged_in = True; st.session_state.role = "visor"; st.rerun()
                else:
                    st.error("Credenciales incorrectas.")

# --- INTERFAZ DE TRABAJO PRINCIPAL ---
if not st.session_state.logged_in:
    pantalla_login()
else:
    # INYECCIÓN DE CSS AVANZADO CON UNSAFE_ALLOW_HTML=TRUE
    st.markdown("""
        <style>
        [data-testid="stAppViewContainer"] { background-image: none !important; background-color: transparent !important; }
        
        /* 1. CONFIGURACIÓN GLOBAL DE BOTONES (#006FB3) */
        div.stButton > button { background-color: #006FB3 !important; color: white !important; border: none !important; font-weight: bold !important; }
        div.stButton > button:hover { background-color: #005A91 !important; }
        
        /* 2. ESTILIZACIÓN COMPLETA DEL PANEL LATERAL (SIDEBAR) */
        [data-testid="stSidebar"] { background-color: #0D1629 !important; border-right: 1px solid #1C2B4B !important;}
        [data-testid="stSidebar"] * { color: #FFFFFF !important; }
        [data-testid="stSidebar"] [data-testid*="stBaseButton"] { background-color: #006FB3 !important; color: white !important; }

        /* Uploaders identificados por su key=".." -> clase .st-key-<key> (estable entre versiones) */
        .st-key-uploader_kmz [data-testid="stFileUploaderDropzone"],
        .st-key-uploader_gtfs [data-testid="stFileUploaderDropzone"],
        .st-key-uploader_padron [data-testid="stFileUploaderDropzone"] {
            background-color: #162448 !important; border: 1px dashed #4a5c8e !important;
        }
        .st-key-uploader_kmz [data-testid="stFileUploaderDropzone"] svg,
        .st-key-uploader_gtfs [data-testid="stFileUploaderDropzone"] svg,
        .st-key-uploader_padron [data-testid="stFileUploaderDropzone"] svg { fill: #A0B0D0 !important; }

        /* Texto de archivos subidos: el fondo ya queda transparente (se ve el navy
           del sidebar detrás); lo que faltaba era forzar color sólido + opacidad
           completa, porque Streamlit aplica opacity reducida a esos textos. */
        :is(.st-key-uploader_kmz, .st-key-uploader_gtfs, .st-key-uploader_padron)
            :is([data-testid*="FileUploaderFile"], [data-testid*="UploadedFile"]) {
            background-color: transparent !important; border: 1px solid #2a3c6e !important; border-radius: 6px !important;
        }
        :is(.st-key-uploader_kmz, .st-key-uploader_gtfs, .st-key-uploader_padron)
            :is([data-testid*="FileUploaderFile"], [data-testid*="UploadedFile"]) * {
            color: #FFFFFF !important; opacity: 1 !important; -webkit-text-fill-color: #FFFFFF !important;
        }
        :is(.st-key-uploader_kmz, .st-key-uploader_gtfs, .st-key-uploader_padron)
            :is([data-testid*="FileUploaderFile"], [data-testid*="UploadedFile"]) small {
            color: #E0E0E0 !important; opacity: 1 !important;
        }
        :is(.st-key-uploader_kmz, .st-key-uploader_gtfs, .st-key-uploader_padron)
            [data-testid*="FileUploaderDeleteBtn"] svg { fill: #FF6B6B !important; }

        /* Testid real confirmado por devtools: data-testid="stFileChip" */
        :is(.st-key-uploader_kmz, .st-key-uploader_gtfs, .st-key-uploader_padron) [data-testid="stFileChip"] {
            background-color: #162448 !important; border: 1px solid #2a3c6e !important; border-radius: 6px !important;
        }
        :is(.st-key-uploader_kmz, .st-key-uploader_gtfs, .st-key-uploader_padron) [data-testid="stFileChip"] * {
            color: #FFFFFF !important; opacity: 1 !important; -webkit-text-fill-color: #FFFFFF !important;
        }

        /* 3. FORZAR PANEL DE FILTROS A AZUL OSCURO (#0A132D) */
        /* .st-key-panel_filtros viene de: st.container(border=True, key="panel_filtros") */
        .st-key-panel_filtros,
        .st-key-panel_filtros > div {
            background-color: #0A132D !important; border: 1px solid #1C2B4B !important; border-radius: 8px !important;
        }
        .st-key-panel_filtros [data-testid="stWidgetLabel"] p,
        .st-key-panel_filtros label,
        .st-key-panel_filtros h4,
        .st-key-panel_filtros p { color: #FFFFFF !important; }

        /* Cajas cerradas de selects e inputs dentro del panel de filtros */
        .st-key-panel_filtros div[data-baseweb="select"] > div,
        .st-key-panel_filtros [data-testid="stTextInput"] div[data-baseweb="input"] {
            background-color: #162448 !important; border: 1px solid #2a3c6e !important;
        }
        .st-key-panel_filtros div[data-baseweb="select"] *,
        .st-key-panel_filtros input {
            color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important;
        }
        .st-key-panel_filtros div[data-baseweb="select"] svg { fill: #FFFFFF !important; }

        /* El menú desplegable del select se inyecta en un portal al final del <body>,
           FUERA del panel de filtros, por eso va sin anidar bajo .st-key-panel_filtros. */
        div[data-baseweb="popover"] ul[role="listbox"] { background-color: #162448 !important; }
        div[data-baseweb="popover"] ul[role="listbox"] li { color: #FFFFFF !important; }
        div[data-baseweb="popover"] ul[role="listbox"] li:hover { background-color: #006FB3 !important; }

        /* 4. CONTROL DE COLORES EN BOTONES DE NOTIFICACIÓN */
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:nth-child(2) [data-testid*="stBaseButton"] { background-color: #2CA02C !important; } /* OK - Verde */
        section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="column"]:nth-child(3) [data-testid*="stBaseButton"] { background-color: #EF3340 !important; } /* DEL - Rojo */

        /* 5. DISEÑO TARJETAS KPI */
        .kpi-container { background-color: #0A132D; color: white; border-radius: 8px; padding: 15px 20px; display: flex; align-items: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.15);}
        .kpi-icon { font-size: 2.2rem; margin-right: 18px; }
        .kpi-title { font-size: 0.85rem; color: #A0B0D0; text-transform: uppercase; margin-bottom: 3px; }
        .kpi-value { font-size: 2rem; font-weight: bold; }
        
        /* 6. BANNER INFERIOR FIJO */
        .banner-inferior { position: fixed; bottom: 0; left: 0; width: 100%; background-color: #0A132D; color: white; text-align: center; padding: 10px 0; font-weight: bold; z-index: 9999; border-top: 3px solid #EF3340; }
        .block-container { padding-bottom: 70px !important; padding-top: 1.5rem !important; }
        </style>
        <div class="banner-inferior">MINISTERIO DE TRANSPORTES Y TELECOMUNICACIONES</div>
    """, unsafe_allow_html=True)

    # --- RED DE SEGURIDAD: FUERZA LOS COLORES POR JS SI EL CSS PIERDE LA ESPECIFICIDAD ---
    # components.html corre en un iframe aislado, por eso se manipula window.parent.document.
    # El MutationObserver reaplica los estilos cada vez que Streamlit vuelve a renderizar
    # (al subir un archivo, cambiar un filtro, etc.), que es justo cuando el CSS estático falla.
    st.components.v1.html("""
        <script>
        function forzarEstilosSVR() {
            const doc = window.parent.document;

            doc.querySelectorAll('[data-testid*="FileUploaderFile"], [data-testid*="UploadedFile"], [data-testid="stFileChip"]').forEach(el => {
                el.style.setProperty('background-color', 'transparent', 'important');
                el.style.setProperty('border', '1px solid #2a3c6e', 'important');
                el.style.setProperty('border-radius', '6px', 'important');
            });
            doc.querySelectorAll('[data-testid*="FileUploaderFile"] *, [data-testid*="UploadedFile"] *, [data-testid="stFileChip"] *').forEach(el => {
                el.style.setProperty('color', '#FFFFFF', 'important');
                el.style.setProperty('opacity', '1', 'important');
            });

            doc.querySelectorAll('div[data-baseweb="select"] > div').forEach(el => {
                el.style.setProperty('background-color', '#162448', 'important');
                el.style.setProperty('border', '1px solid #2a3c6e', 'important');
            });
            doc.querySelectorAll('div[data-baseweb="select"] *').forEach(el => {
                el.style.setProperty('color', '#FFFFFF', 'important');
            });

            doc.querySelectorAll('div[data-baseweb="popover"] ul[role="listbox"]').forEach(el => {
                el.style.setProperty('background-color', '#162448', 'important');
            });
            doc.querySelectorAll('div[data-baseweb="popover"] ul[role="listbox"] li').forEach(el => {
                el.style.setProperty('color', '#FFFFFF', 'important');
            });

            // Fondo del panel de filtros (container con key="panel_filtros")
            doc.querySelectorAll('.st-key-panel_filtros').forEach(el => {
                el.style.setProperty('background-color', '#0A132D', 'important');
                el.style.setProperty('border', '1px solid #1C2B4B', 'important');
                el.style.setProperty('border-radius', '8px', 'important');
                const hijo = el.querySelector(':scope > div');
                if (hijo) hijo.style.setProperty('background-color', '#0A132D', 'important');
            });
            doc.querySelectorAll('.st-key-panel_filtros label, .st-key-panel_filtros p, .st-key-panel_filtros h4').forEach(el => {
                el.style.setProperty('color', '#FFFFFF', 'important');
            });
        }

        // Streamlit a veces NO agrega/quita nodos al terminar una subida: solo cambia
        // el "style" o "class" del MISMO nodo (por eso antes se volvía a ver blanco:
        // el observer solo escuchaba childList y nunca se volvía a disparar).
        // Aquí se observan también atributos, con una bandera para no entrar en un
        // bucle infinito (nosotros mismos modificamos "style" al forzar los colores).
        let aplicando = false;
        const observer = new MutationObserver(() => {
            if (aplicando) return;
            aplicando = true;
            forzarEstilosSVR();
            // Se libera en el siguiente frame, una vez que el navegador ya aplicó
            // los estilos que acabamos de setear.
            requestAnimationFrame(() => { aplicando = false; });
        });
        observer.observe(window.parent.document.body, {
            childList: true, subtree: true,
            attributes: true, attributeFilter: ['style', 'class']
        });
        forzarEstilosSVR();

        // Red de seguridad adicional: reintento periódico por si algún cambio
        // se escapa del observer (p.ej. animaciones o timers internos de React).
        setInterval(forzarEstilosSVR, 800);
        </script>
    """, height=0)

    col_tit, col_log = st.columns([9, 1.2])
    with col_tit:
        st.markdown("<h1 style='color: #0A132D; margin-top: -15px;'>Sistema de Validación en Red (S.V.R.)</h1>", unsafe_allow_html=True)
    with col_log:
        st.write("")
        if st.button("🔒 Cerrar Sesión", use_container_width=True):
            st.session_state.logged_in = False; st.session_state.role = None; st.rerun()

    st.sidebar.header("⚙️ Ingesta de Datos Regulados")
    archivos_kmz_procesar = []
    archivo_padron = None

    if st.session_state.role == "admin":
        st.sidebar.info("👑 Modo Administrador: Carga manual habilitada.")
        archivos_kmz_crudos = st.sidebar.file_uploader("1. Archivos KMZ Oficiales", type=["kmz"], accept_multiple_files=True, key="uploader_kmz")
        if archivos_kmz_crudos:
            archivos_kmz_procesar = [(f.name, f) for f in sorted(archivos_kmz_crudos, key=lambda f: f.name)]
        archivo_gtfs = st.sidebar.file_uploader("2. GTFS Regulado (.zip)", type=["zip"], key="uploader_gtfs")
        archivo_padron = st.sidebar.file_uploader("3. Padrón de Patentes (.xlsx)", type=["xlsx"], key="uploader_padron")
        
    elif st.session_state.role == "visor":
        st.sidebar.info("👁️ Modo Visor: Lectura automática desde la base de datos central.")
        carpeta_datos = "datos"
        if os.path.exists(carpeta_datos):
            archivos_locales = os.listdir(carpeta_datos)
            kmz_locales = sorted([f for f in archivos_locales if f.lower().endswith('.kmz')])
            padron_local = [f for f in archivos_locales if f.lower().endswith('.xlsx') or f.lower().endswith('.xls')]
            
            if not kmz_locales: st.sidebar.warning("⚠️ No se detectaron archivos KMZ en la carpeta 'datos'.")
            if not padron_local: st.sidebar.warning("⚠️ No se detectó un archivo Excel en la carpeta 'datos'.")
                
            archivos_kmz_procesar = [(nombre, os.path.join(carpeta_datos, nombre)) for nombre in kmz_locales]
            if padron_local: archivo_padron = os.path.join(carpeta_datos, padron_local[0])
        else:
            st.sidebar.error("❌ La carpeta 'datos' no existe en tu proyecto.")

    lineas_dict = {}
    if archivos_kmz_procesar:
        for nombre_archivo, archivo_o_ruta in archivos_kmz_procesar:
            nombre_servicio = nombre_archivo.split(".")[0].upper()
            # Si es una ruta local (visor), paso el mtime para invalidar el caché
            # automáticamente cuando el archivo cambie en disco.
            mtime = os.path.getmtime(archivo_o_ruta) if isinstance(archivo_o_ruta, str) else None
            datos_kmz = procesar_kmz_cacheado(archivo_o_ruta, mtime)
            if datos_kmz: lineas_dict[nombre_servicio] = datos_kmz

    nombres_servicios_reales = list(lineas_dict.keys())
    mtime_padron = os.path.getmtime(archivo_padron) if isinstance(archivo_padron, str) else None
    df_padron = cargar_padron_cacheado(archivo_padron, nombres_servicios_reales, mtime_padron) if archivo_padron else None
    
    if df_padron is not None:
        total_electricos = df_padron['Es_Electrico'].sum() if 'Es_Electrico' in df_padron.columns else 0
        st.sidebar.success(f"✅ Familias de Líneas: {len(nombres_servicios_reales)}")
        st.sidebar.success(f"⚡ Flota Eléctrica: {int(total_electricos)}")
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
            eventos_para_archivar = []
            
            es_horario_comercial = 5 <= hora_actual_dt.hour < 22
            if not es_horario_comercial: st.toast("🌙 Sistema operando en horario nocturno.", icon="🌙")

            if df_padron is not None and not df_padron.empty:
                flota_muestra = df_padron.sample(min(20, len(df_padron))) if len(df_padron) > 20 else df_padron
                contextos_buses = []  # Fase 1: todo lo que NO necesita internet (rápido)
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

                    if not es_horario_comercial: comportamiento = random.choices(["OK", "TERMINAL"], weights=[50, 50])[0]
                    else: comportamiento = random.choices(["OK", "TERMINAL", "ACORTE", "ABANDONO", "VELOCIDAD"], weights=[65, 5, 10, 10, 10])[0]

                    limite_zona = 50
                    segmento_correcto = []
                    p_inicio_desv, punto_medio_desv, p_fin_desv = None, None, None

                    if comportamiento == "OK":
                        lat_actual, lon_actual, vel = punto_base[0] + random.uniform(-0.0001, 0.0001), punto_base[1] + random.uniform(-0.0001, 0.0001), random.randint(25, 48)
                    elif comportamiento == "TERMINAL":
                        lat_actual, lon_actual, vel = (trazado_puntos[0][0], trazado_puntos[0][1], 0) if random.choice([True, False]) else (trazado_puntos[-1][0], trazado_puntos[-1][1], 0)
                    elif comportamiento == "VELOCIDAD":
                        lat_actual, lon_actual, vel = punto_base[0], punto_base[1], random.randint(55, 75)
                    elif comportamiento in ("ACORTE", "ABANDONO"):
                        # Solo se ELIGEN los puntos acá (sin red); la consulta a OSRM
                        # se hace después, en paralelo con la de todos los demás buses.
                        seg_correcto, p_inicio_desv, punto_medio_desv, p_fin_desv, idx_ini, idx_fin = elegir_puntos_desviacion(trazado_puntos)
                        segmento_correcto = seg_correcto
                        lat_actual, lon_actual = punto_medio_desv[0], punto_medio_desv[1]
                        vel = random.randint(30, 48)

                    estado, dist_error = evaluar_operacion(lat_actual, lon_actual, rutas_obj, vel, limite_zona, paraderos_obj)
                    lat_snap, lon_snap, variante_exacta, trazado_infractor = snap_punto_a_ruta(lat_actual, lon_actual, rutas_obj)
                    sector = determinar_sector(lat_snap, lon_snap)

                    buses_calculados.append({"id": patente, "linea": linea_asignada, "lat": lat_actual, "lon": lon_actual, "estado": estado, "color": "green" if estado == "Operación Normal" else ("orange" if "Terminal" in estado else "red"), "vel": vel, "limite": limite_zona, "electrico": es_electrico})

                    contextos_buses.append({
                        "patente": patente, "linea_asignada": linea_asignada, "es_electrico": es_electrico,
                        "comportamiento": comportamiento, "estado": estado, "variante_exacta": variante_exacta,
                        "sector": sector, "lat_actual": lat_actual, "lon_actual": lon_actual,
                        "lat_snap": lat_snap, "lon_snap": lon_snap, "trazado_infractor": trazado_infractor,
                        "segmento_correcto": segmento_correcto,
                        "p_inicio_desv": p_inicio_desv, "punto_medio_desv": punto_medio_desv, "p_fin_desv": p_fin_desv,
                    })

                # Fase 2: TODAS las consultas de red (geocodificación + OSRM) de golpe,
                # en paralelo — antes eran ~20 consultas en fila, una por una, y eso
                # era lo que hacía tan lenta la plataforma al iniciar el motor.
                def _resolver_red(ctx):
                    if ctx["estado"] == "Operación Normal":
                        return f"Sector {ctx['sector']}", f"Sector {ctx['sector']}", [], False

                    # Siempre calles reales (Nominatim + OSRM): solo aplica a las
                    # alertas de esta corrida (normalmente pocas), no a los 20 buses,
                    # por eso se mantiene razonablemente rápido.
                    tramo_correcto = obtener_calle_real(ctx["lat_snap"], ctx["lon_snap"], ctx["sector"])
                    if ctx["comportamiento"] in ("ACORTE", "ABANDONO"):
                        segmento_desviado, es_aproximado = calcular_ruta_desviada(ctx["p_inicio_desv"], ctx["punto_medio_desv"], ctx["p_fin_desv"])
                        # Se geocodifica un punto de la RUTA REAL que devolvió OSRM
                        # (no el punto geométrico crudo) — así el texto "Realizó"
                        # describe la calle por la que efectivamente pasa la línea
                        # roja dibujada, evitando que diga la misma calle que
                        # "Debía circular" cuando en realidad sí hay un desvío.
                        punto_geocodificar = segmento_desviado[len(segmento_desviado) // 2]
                        tramo_desviado = obtener_calle_real(punto_geocodificar[0], punto_geocodificar[1], ctx["sector"])
                        if tramo_desviado == tramo_correcto:
                            # Si aun así coincide (calle real corta o desvío muy leve),
                            # se aclara en el texto en vez de mostrar una falsa
                            # coincidencia sin contexto.
                            tramo_desviado = f"{tramo_desviado} (tramo distinto de la misma calle)"
                    else:
                        tramo_desviado = tramo_correcto
                        segmento_desviado, es_aproximado = [], False
                    return tramo_correcto, tramo_desviado, segmento_desviado, es_aproximado

                # Máximo 3 consultas a la vez, para respetar el límite de uso de
                # Nominatim/OSRM (piden ~1 consulta/segundo) — mandar más en
                # paralelo puede hacer que bloqueen temporalmente, dejando todo
                # MÁS lento en vez de más rápido.
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    resultados_red = list(executor.map(_resolver_red, contextos_buses))

                # Fase 3: ensamblar los eventos con los resultados ya resueltos (rápido)
                for ctx, (tramo_correcto, tramo_desviado, segmento_desviado, es_aproximado) in zip(contextos_buses, resultados_red):
                    patente = ctx["patente"]; linea_asignada = ctx["linea_asignada"]; es_electrico = ctx["es_electrico"]
                    estado = ctx["estado"]; variante_exacta = ctx["variante_exacta"]; sector = ctx["sector"]
                    lat_actual = ctx["lat_actual"]; lon_actual = ctx["lon_actual"]
                    trazado_infractor = ctx["trazado_infractor"]; segmento_correcto = ctx["segmento_correcto"]

                    datos_evento = {
                        "ID Alerta": f"ALT-{random.randint(100,999)}", "Patente": patente,
                        "Servicio": linea_asignada, "Variante": variante_exacta,
                        "Infracción": estado,
                        "Tramo Afectado": tramo_correcto,
                        "Tramo Correcto": tramo_correcto,
                        "Tramo Desviado": tramo_desviado,
                        "Sector Comuna": sector, "Hora Control": hora_actual_str,
                        "Tiempo de Abandono": f"{random.randint(3, 25)} min",
                        "Latitud": lat_actual, "Longitud": lon_actual,
                        "Segmento_Ruta": trazado_infractor,
                        "Segmento_Correcto": segmento_correcto,
                        "Segmento_Desviado": segmento_desviado,
                        "Es_Aproximado": es_aproximado,
                        "Es_Electrico": es_electrico,
                        "oculta": False
                    }

                    if estado == "Operación Normal":
                        st.session_state.historial_ok.append(datos_evento)
                        eventos_para_archivar.append((datos_evento, "OK"))
                    else:
                        st.session_state.alertas.append(datos_evento)
                        nuevas_notificaciones.append(datos_evento)
                        eventos_para_archivar.append((datos_evento, "ALERTA"))
            
            st.session_state.buses_en_vivo = buses_calculados
            guardar_lote(eventos_para_archivar)
            if nuevas_notificaciones: st.toast(f"📱 Se han consolidado nuevas alertas en la fila.", icon="📲")

    st.sidebar.caption(f"🗄️ Archivador SQLite: {contar_registros_archivados()} registros permanentes.")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔔 Centro de Notificaciones")
    alertas_visibles = [a for a in st.session_state.alertas if not a.get("oculta", False)]
    
    if alertas_visibles:
        for idx, a in enumerate(st.session_state.alertas):
            if not a.get("oculta", False):
                color_borde = "#ff7f0e" if "Terminal" in a['Infracción'] else "#EF3340"
                icono_noti = "⚠️" if "Terminal" in a['Infracción'] else "🚨"
                with st.sidebar.container(border=True):
                    st.markdown(f"<p style='color:{color_borde} !important; font-weight:bold; margin-bottom:2px;'>{icono_noti} {a['Infracción']}</p>", unsafe_allow_html=True)
                    tramo_correcto = a.get("Tramo Correcto", a.get("Tramo Afectado", ""))
                    tramo_desviado = a.get("Tramo Desviado", "")
                    detalle_noti = f"**PPU:** {a['Patente']} | **Línea:** {a['Servicio']}"
                    if tramo_desviado and tramo_desviado != tramo_correcto:
                        detalle_noti += f" | ✅ {tramo_correcto} | ❌ {tramo_desviado}"
                    st.caption(detalle_noti)
                    if st.session_state.role == "admin":
                        c_ver, c_ok, c_del = st.columns([2, 1, 1])
                        with c_ver:
                            if st.button("📍 Ver", key=f"loc_{a['ID Alerta']}", use_container_width=True):
                                st.session_state.alerta_focus = a
                                st.session_state.vista_activa = "🔥 Análisis de Cobertura y Trazados"
                                st.rerun()
                        with c_ok:
                            if st.button("✅", key=f"ok_{a['ID Alerta']}", use_container_width=True):
                                st.session_state.alertas[idx]["oculta"] = True; st.rerun()
                        with c_del:
                            if st.button("❌", key=f"del_{a['ID Alerta']}", use_container_width=True):
                                st.session_state.alertas[idx]["oculta"] = True; st.rerun()
                    else:
                        if st.button("📍 Localizar Infracción", key=f"loc_visor_{a['ID Alerta']}", use_container_width=True):
                            st.session_state.alerta_focus = a
                            st.session_state.vista_activa = "🔥 Análisis de Cobertura y Trazados"
                            st.rerun()
    else:
        st.sidebar.info("No hay incidentes reportados.")

    # --- TARJETAS KPI ---
    total_buses = len(st.session_state.buses_en_vivo)
    buses_alertas = len(st.session_state.alertas)
    buses_normales = total_buses - buses_alertas
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='kpi-container'><div class='kpi-icon'>🚍</div><div class='kpi-content'><div class='kpi-title'>Total Flota Activa</div><div class='kpi-value'>{total_buses}</div></div></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='kpi-container'><div class='kpi-icon'>✅</div><div class='kpi-content'><div class='kpi-title'>Operación en Norma</div><div class='kpi-value'>{max(0, buses_normales)}</div></div></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='kpi-container'><div class='kpi-icon'>🚨</div><div class='kpi-content'><div class='kpi-title'>Alertas Críticas</div><div class='kpi-value'>{buses_alertas}</div></div></div>", unsafe_allow_html=True)

    # --- PANEL DE FILTROS ---
    opciones_lineas = list(lineas_dict.keys()) if lineas_dict else []
    opciones_infracciones_set = set(a["Infracción"] for a in st.session_state.alertas)
    if st.session_state.historial_ok: opciones_infracciones_set.add("Operación Normal")
    opciones_infracciones = sorted(opciones_infracciones_set)

    with st.container(border=True, key="panel_filtros"):
        st.markdown("<h4 style='margin-top: 0; margin-bottom: 10px; color: white;'>🔍 Filtros de Operación</h4>", unsafe_allow_html=True)
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
    if filtro_tecnologia != "Todas":
        quiere_electrico = (filtro_tecnologia == "Solo Eléctricos")
        buses_filtrados = [b for b in buses_filtrados if b.get("electrico", False) == quiere_electrico]
        alertas_filtradas = [a for a in alertas_filtradas if a.get("Es_Electrico", False) == quiere_electrico]
        historial_ok_filtrado = [h for h in historial_ok_filtrado if h.get("Es_Electrico", False) == quiere_electrico]

    st.write("") 
    etiquetas_tabs = ["🛰️ Monitoreo en Tiempo Real", "🔥 Análisis de Cobertura y Trazados", "🗄️ Archivo Histórico (SQLite)"]
    es_admin = st.session_state.role == "admin"
    if es_admin: etiquetas_tabs.append("📊 Informe Ejecutivo")

    # st.tabs() no se puede cambiar por código (no existe "tab.select()" en Streamlit),
    # por eso el botón "Ver" de una notificación no podía saltar de pestaña solo.
    # Con un st.radio "atado" a session_state (key="vista_activa") sí se puede: el
    # botón deja el valor deseado en session_state ANTES del rerun, y el radio lo
    # adopta como su selección al volver a dibujarse.
    if "vista_activa" not in st.session_state or st.session_state.vista_activa not in etiquetas_tabs:
        st.session_state.vista_activa = etiquetas_tabs[0]
    vista_activa = st.radio("Navegación", etiquetas_tabs, horizontal=True,
                             label_visibility="collapsed", key="vista_activa")

    if vista_activa == etiquetas_tabs[0]:
        mapa_vivo = folium.Map(location=[-34.1708, -70.7444], zoom_start=13)
        folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite (Híbrida)', show=False).add_to(mapa_vivo)
        colores_lineas = ["#E6194B", "#4363D8", "#469990", "#F58231", "#911EB4", "#00FFFF", "#F032E6"] 

        for idx, (lbl, datos) in enumerate(lineas_dict.items()):
            if filtro_linea == "Todas" or filtro_linea == lbl:
                for segmento_obj in datos['rutas']:
                    var_name = segmento_obj.get('variante', '').upper()
                    if filtro_variante != "Todas" and filtro_variante != var_name: continue
                    folium.PolyLine(segmento_obj['trazado'], color=colores_lineas[idx % len(colores_lineas)], weight=4, opacity=0.9, tooltip=f"Línea: {lbl} | Variante: {segmento_obj.get('variante', '')}").add_to(mapa_vivo)

        # disableClusteringAtZoom evita que se agrupen los buses cuando el usuario
        # ya hizo zoom a nivel de calle (ahí sí quiere verlos separados).
        cluster_buses = MarkerCluster(name="🚌 Buses en Circulación", disableClusteringAtZoom=15).add_to(mapa_vivo)
        for bus in buses_filtrados:
            es_electrico = bus.get('electrico', False)
            icon_color = "green" if es_electrico and bus['estado'] == "Operación Normal" else bus['color']
            icon_tipo = "bolt" if es_electrico else "bus"
            tec_text = "⚡ Eléctrico" if es_electrico else "Diésel"
            html_pop = f"<div style='font-size: 12px; width: 200px;'><b>Patente:</b> {bus['id']}<br><b>Servicio:</b> {bus['linea']}<br><b>Tecnología:</b> {tec_text}<br><b>Estado:</b> {bus['estado']}</div>"
            folium.Marker([bus["lat"], bus["lon"]], icon=folium.Icon(color=icon_color, icon=icon_tipo, prefix='fa'), popup=folium.Popup(html_pop, max_width=250)).add_to(cluster_buses)
        
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_vivo)
        Fullscreen(position='topleft').add_to(mapa_vivo)
        st_folium(mapa_vivo, width="100%", height=550, returned_objects=[], key="mapa_vivo_unico")

    if vista_activa == etiquetas_tabs[1]:
        st.markdown("#### 🗺️ Análisis de Operación y Trazados Inteligentes")
        centro_mapa = [-34.1708, -70.7444]
        zoom_mapa = 13
        if st.session_state.alerta_focus is not None:
            centro_mapa = [st.session_state.alerta_focus["Latitud"], st.session_state.alerta_focus["Longitud"]]
            zoom_mapa = 16
            col_info, col_btn = st.columns([4, 1])
            with col_info:
                st.info(f"📍 Mostrando solo: **{st.session_state.alerta_focus['Infracción']}** de la patente **{st.session_state.alerta_focus['Patente']}**")
            with col_btn:
                if st.button("↺ Ver todas", use_container_width=True):
                    st.session_state.alerta_focus = None
                    st.rerun()
        
        mapa_calor = folium.Map(location=centro_mapa, zoom_start=zoom_mapa, tiles=None)
        folium.TileLayer('CartoDB dark_matter', name='Modo Oscuro (Gris/Negro)', control=True, show=True).add_to(mapa_calor)
        folium.TileLayer('OpenStreetMap', name='Modo Claro (Estándar)', control=True, show=False).add_to(mapa_calor)
        folium.TileLayer(
            tiles='https://{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
            attr='Google', subdomains=['mt0', 'mt1', 'mt2', 'mt3'],
            name='Híbrido (Satélite)', control=True, show=False,
        ).add_to(mapa_calor)
        
        # Si hay una alerta enfocada (botón "Ver"), el trazado verde se limita a
        # la LÍNEA Y VARIANTE exactas de esa alerta — antes solo filtraba por
        # línea, y si esa línea tenía varias variantes (ida/vuelta u otros
        # recorridos), se seguían mostrando todas mezcladas.
        linea_en_foco = st.session_state.alerta_focus.get("Servicio") if st.session_state.alerta_focus is not None else None
        variante_en_foco = st.session_state.alerta_focus.get("Variante", "").upper() if st.session_state.alerta_focus is not None else None

        for idx, (lbl, datos) in enumerate(lineas_dict.items()):
            if linea_en_foco is not None and lbl != linea_en_foco: continue
            if filtro_linea == "Todas" or filtro_linea == lbl:
                for segmento_obj in datos['rutas']:
                    var_name = segmento_obj.get('variante', '').upper()
                    if variante_en_foco and variante_en_foco != "DESCONOCIDA" and var_name != variante_en_foco: continue
                    if filtro_variante != "Todas" and filtro_variante != var_name: continue
                    folium.PolyLine(segmento_obj['trazado'], color="#2ca02c", weight=4, opacity=0.75,
                                    tooltip=f"Trazado oficial — Línea {lbl}").add_to(mapa_calor)

        cluster_alertas = MarkerCluster(name="🚨 Alertas e Infracciones", disableClusteringAtZoom=16).add_to(mapa_calor)

        # Si se llegó acá presionando "Ver" en una notificación, se muestra SOLO esa
        # alerta (para que no se mezcle con el resto y sea clara). Sin foco, se ven
        # todas las que pasan los filtros, como antes.
        alertas_a_dibujar = alertas_filtradas
        if st.session_state.alerta_focus is not None:
            id_foco = st.session_state.alerta_focus.get("ID Alerta")
            alertas_a_dibujar = [a for a in alertas_filtradas if a.get("ID Alerta") == id_foco]

        for evt in alertas_a_dibujar:
            seg_desviado = evt.get("Segmento_Desviado", [])
            segmento_infractor = evt.get("Segmento_Ruta", [])

            color_linea = "#ff7f0e" if "Terminal" in evt["Infracción"] else "#d62728"
            icono_marker = "info-sign" if "Terminal" in evt["Infracción"] else "exclamation-triangle"

            tramo_correcto = evt.get("Tramo Correcto", evt.get("Tramo Afectado", ""))
            tramo_desviado = evt.get("Tramo Desviado", "")

            if seg_desviado:
                # ACORTE / ABANDONO: el trazado correcto ya está en verde (capa base);
                # solo se dibuja encima el camino real (por calles, vía OSRM) que
                # tomó el bus, que sale y vuelve a unirse al trazado oficial.
                # Si OSRM no pudo resolverlo (Es_Aproximado=True), se dibuja delgada
                # y punteada para no aparentar precisión que no se tiene.
                es_aproximado = evt.get("Es_Aproximado", False)
                dash = "10,8" if es_aproximado else None
                linea_desvio = folium.PolyLine(
                    seg_desviado, color="#d62728", weight=3 if es_aproximado else 5,
                    opacity=0.6 if es_aproximado else 0.9, dash_array=dash,
                    tooltip="Desviación aproximada (sin datos de calle)" if es_aproximado else "Desviación real (acorte/abandono)",
                ).add_to(mapa_calor)

                # Punto donde se sale del trazado oficial ("salida") y punto donde
                # vuelve a unírsele ("reingreso") — para que quede claro el patrón
                # "salió aquí, volvió acá" sin tener que seguir la línea con la vista.
                folium.CircleMarker(
                    location=seg_desviado[0], radius=8, color="#ffffff", weight=3,
                    fill=True, fill_color="#d62728", fill_opacity=1,
                    tooltip="🔴 Salida del trazado oficial",
                ).add_to(mapa_calor)
                folium.CircleMarker(
                    location=seg_desviado[-1], radius=8, color="#ffffff", weight=3,
                    fill=True, fill_color="#2ca02c", fill_opacity=1,
                    tooltip="🟢 Reingreso al trazado oficial",
                ).add_to(mapa_calor)

                html_popup = (
                    f"<div style='font-family: Arial; font-size: 13px; width: 260px;'>"
                    f"<b style='color: {color_linea}; font-size: 14px;'>{evt['Infracción']}</b><br><br>"
                    f"<b>Línea:</b> {evt['Servicio']}<br>"
                    f"<b>✅ Debía circular:</b> {tramo_correcto}<br>"
                    f"<b>❌ Realizó:</b> {tramo_desviado}<br>"
                    f"<b>Sector:</b> {evt['Sector Comuna']}<br>"
                    f"<b>Patente:</b> {evt['Patente']}</div>"
                )
            else:
                # TERMINAL / VELOCIDAD: el bus sigue sobre el trazado oficial, solo se
                # resalta en rojo el tramo real puntual donde ocurrió la infracción
                # (segmento_infractor ya viene de snap_punto_a_ruta, es calle real).
                if not segmento_infractor:
                    segmento_infractor = [[evt["Latitud"], evt["Longitud"]], [evt["Latitud"]+0.0001, evt["Longitud"]+0.0001]]
                folium.PolyLine(segmento_infractor, color=color_linea, weight=5, opacity=0.9,
                                tooltip=evt["Infracción"]).add_to(mapa_calor)

                # Exceso de Velocidad: marcar dónde empezó y dónde terminó el tramo con
                # exceso, para ver de un vistazo el largo real del tramo infringido
                # (Terminal no lleva estos marcadores: es un punto fijo, no un tramo).
                if "Exceso de Velocidad" in evt["Infracción"] and len(segmento_infractor) >= 2:
                    folium.CircleMarker(
                        location=segmento_infractor[0], radius=5, color="#ffffff", weight=2,
                        fill=True, fill_color="#d62728", fill_opacity=1,
                        tooltip="🔴 Inicio del exceso de velocidad",
                    ).add_to(mapa_calor)
                    folium.CircleMarker(
                        location=segmento_infractor[-1], radius=5, color="#ffffff", weight=2,
                        fill=True, fill_color="#ff7f0e", fill_opacity=1,
                        tooltip="🟠 Término del exceso de velocidad",
                    ).add_to(mapa_calor)
                html_popup = (
                    f"<div style='font-family: Arial; font-size: 13px; width: 240px;'>"
                    f"<b style='color: {color_linea}; font-size: 14px;'>{evt['Infracción']}</b><br><br>"
                    f"<b>Línea:</b> {evt['Servicio']}<br>"
                    f"<b>Calles/Rutas:</b> {evt.get('Tramo Afectado', '')}<br>"
                    f"<b>Sector:</b> {evt['Sector Comuna']}<br>"
                    f"<b>Patente:</b> {evt['Patente']}</div>"
                )

            # El marcador va en la posición REAL observada del bus (lat_actual/lon_actual,
            # guardada en Latitud/Longitud), que es lo que se dibujó en rojo — antes
            # quedaba en el punto corregido/verde, por eso se veía "fuera de lugar".
            folium.Marker(location=[evt["Latitud"], evt["Longitud"]],
                          icon=folium.Icon(color="red" if color_linea == "#d62728" else "orange",
                                           icon=icono_marker, prefix='fa'),
                          popup=folium.Popup(html_popup, max_width=300)).add_to(cluster_alertas)
            
        folium.LayerControl(position='topright', collapsed=False).add_to(mapa_calor)
        Fullscreen(position='topleft').add_to(mapa_calor)
        st_folium(mapa_calor, width="100%", height=450, returned_objects=[], key="mapa_calor_unico")
        
        st.markdown("---")
        st.markdown("#### 🚨 Alertas Estratégicas: Puntos Ciegos y Fallas de Cobertura Vial")
        
        if alertas_filtradas:
            df_alertas_f = pd.DataFrame(alertas_filtradas)
            df_abandonos = df_alertas_f[df_alertas_f["Infracción"].isin(["Abandono de Trazado", "Acorte/Cambio de Recorrido"])]
            if not df_abandonos.empty:
                agrupado = df_abandonos.groupby(["Sector Comuna", "Tramo Correcto", "Tramo Desviado"]).agg(
                    Servicios=('Servicio', lambda x: ", ".join(sorted(x.unique()))),
                    Ultimo_Registro=('Hora Control', 'max')
                ).reset_index()
                for _, row in agrupado.iterrows():
                    tramo_correcto = row.get("Tramo Correcto", row.get("Tramo Afectado", ""))
                    tramo_desviado = row.get("Tramo Desviado", "")
                    warning_html = (
                        f"<div style='background-color: #1A0505; border: 1px solid #FF3333; "
                        f"border-left: 5px solid #FF3333; padding: 15px; border-radius: 5px; "
                        f"margin-bottom: 12px;'>"
                        f"<h5 style='color: #FF3333; margin: 0 0 5px 0;'>🚨 ALERTA DE COBERTURA: EJE VIAL ABANDONADO</h5>"
                        f"<p style='color: #E0E0E0; margin: 0;'>"
                        f"Sector: {row['Sector Comuna']}<br>"
                        f"✅ <b>Debía circular:</b> {tramo_correcto}<br>"
                    )
                    if tramo_desviado and tramo_desviado != tramo_correcto:
                        warning_html += f"❌ <b>Realizó desvío:</b> {tramo_desviado}<br>"
                    warning_html += (
                        f"🚌 <b>Servicios:</b> {row['Servicios']}<br>"
                        f"🕐 {row['Ultimo_Registro']}"
                        f"</p></div>"
                    )
                    st.markdown(warning_html, unsafe_allow_html=True)
            else:
                st.success("✅ No se registran desvíos críticos.")
            
            st.markdown("---")
            st.subheader("Libro Estadístico de Infracciones Operativas")
            columnas_a_quitar = ['Latitud', 'Longitud', 'Segmento_Ruta', 'Segmento_Correcto', 'Segmento_Desviado', 'oculta']
            df_limpio = df_alertas_f.drop(columns=[c for c in columnas_a_quitar if c in df_alertas_f.columns], errors='ignore')
            st.dataframe(df_limpio, use_container_width=True)
            
            def generar_excel_multitaba(df_completo, df_ab):
                out = BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as w:
                    df_completo.to_excel(w, index=False, sheet_name='Fiscalizacion_Detallada')
                    if not df_ab.empty:
                        grupo_cols = ["Sector Comuna", "Tramo Correcto", "Tramo Desviado"]
                        grupo_existentes = [c for c in grupo_cols if c in df_ab.columns]
                        resumen = df_ab.groupby(grupo_existentes).agg(
                            Servicios_Ausentes=('Servicio', lambda x: ", ".join(sorted(x.unique()))),
                            Casos_Registrados=('ID Alerta', 'count')
                        ).reset_index()
                        resumen.to_excel(w, index=False, sheet_name='Resumen_Calles_Abandonadas')
                return out.getvalue()
            
            if st.session_state.role == "admin":
                st.download_button("📥 Exportar Libro S.V.R a Excel (.xlsx)", data=generar_excel_multitaba(df_limpio, df_abandonos), file_name="Reporte_SVR_ValidacionEnRed.xlsx")
            else:
                st.info("🔒 La exportación del Libro Operativo (Excel) es una función exclusiva del Administrador.")
        else:
            st.info("Inicie el motor de análisis en vivo para consolidar el reporte territorial.")

    if vista_activa == etiquetas_tabs[2]:
        st.markdown("#### 🗄️ Consulta de Archivo Histórico Permanente (SQLite)")
        total_bd = contar_registros_archivados()
        st.caption(f"Total de registros archivados permanentemente: **{total_bd}**")

        col_a, col_b = st.columns([1, 3])
        with col_a:
            limite = st.number_input("Cantidad a mostrar", min_value=10, max_value=5000, value=200, step=50)
        with col_b:
            etiqueta_a_valor = {"Todas": "Todas", "Operación Normal": "OK", "Alerta": "ALERTA"}
            etiqueta_elegida = st.selectbox("Filtrar por tipo", list(etiqueta_a_valor.keys()))
            tipo_filtro = etiqueta_a_valor[etiqueta_elegida]

        registros = cargar_historico(limite=limite)
        if tipo_filtro != "Todas":
            registros = [r for r in registros if r["tipo"] == tipo_filtro]

        if registros:
            df_historico = pd.DataFrame(registros).drop(columns=["segmento_ruta"], errors="ignore")
            if "tipo" in df_historico.columns:
                df_historico["tipo"] = df_historico["tipo"].replace({"OK": "Operación Normal", "ALERTA": "Alerta"})
            st.dataframe(df_historico, use_container_width=True)
            st.download_button(
                "📥 Exportar Archivo Histórico a Excel (.xlsx)",
                data=(lambda b: (df_historico.to_excel(b, index=False, engine="openpyxl"), b.getvalue())[1])(BytesIO()),
                file_name="Archivo_Historico_SVR.xlsx",
            )
        else:
            st.info("Aún no hay registros archivados en la base de datos.")

        if st.session_state.role == "admin":
            st.markdown("---")
            with st.expander("🗑️ Zona de riesgo: vaciar archivo histórico"):
                st.warning("Esto borra **permanentemente** todos los registros archivados. No se puede deshacer.")
                confirmar = st.text_input("Escribe BORRAR para confirmar:", key="confirmar_borrado_historico")
                if st.button("🗑️ Vaciar Archivo Histórico Ahora", disabled=(confirmar != "BORRAR")):
                    vaciar_historico()
                    st.success("Archivo histórico vaciado.")
                    st.rerun()

    if es_admin and vista_activa == etiquetas_tabs[3]:
        if True:
            st.markdown("#### 📊 Informe Ejecutivo — Solo Administrador")
            registros_completos = cargar_historico(limite=None)
            if not registros_completos:
                st.info("Aún no hay registros suficientes para emitir el informe.")
            else:
                df_hist_completo = pd.DataFrame(registros_completos)
                m = calcular_metricas(df_hist_completo, df_padron)

                c1, c2, c3 = st.columns(3)
                c1.metric("Total Registros", m["total_registros"])
                c2.metric("Total Infracciones", m["total_alertas"])
                pct = f"{m['pct_flota_electrica']:.1f}%" if m["pct_flota_electrica"] is not None else "N/D"
                c3.metric("% Flota Eléctrica Circulando", pct)

                st.markdown("##### 📍 Lugares con Más Abandono de Servicio")
                st.pyplot(grafico_barras(m["top_sectores_abandono"], "Top Sectores con Más Abandono", horizontal=True))
                st.markdown("##### 🚌 Servicio con Más Infracciones")
                st.pyplot(grafico_barras(m["top_servicios_infracciones"], "Servicios con Más Infracciones", horizontal=True))
                st.markdown("##### 🔁 Patentes con Más Reincidencias")
                st.pyplot(grafico_barras(m["top_patentes_infractoras"], "Patentes con Más Reincidencias", horizontal=True))
                st.markdown("##### 🥧 Distribución por Tipo de Infracción")
                st.pyplot(grafico_barras(m["distribucion_infracciones"], "Distribución por Tipo de Infracción", horizontal=True))

                col_dia, col_hora = st.columns(2)
                with col_dia:
                    st.markdown("##### 📅 Infracciones por Día")
                    st.pyplot(grafico_barras(m["infracciones_por_dia"], "Infracciones por Día de la Semana", color="#EF3340"))
                    st.markdown("##### 📅 Abandonos por Día")
                    st.pyplot(grafico_barras(m["abandono_por_dia"], "Abandonos por Día de la Semana", color="#EF3340"))
                with col_hora:
                    st.markdown("##### 🕐 Infracciones por Hora")
                    st.pyplot(grafico_barras(m["infracciones_por_hora"], "Infracciones por Hora del Día", color="#2CA02C"))
                    st.markdown("##### 🕐 Abandonos por Hora")
                    st.pyplot(grafico_barras(m["abandono_por_hora"], "Abandonos por Hora del Día", color="#2CA02C"))

                st.download_button(
                    "📥 Descargar Informe Ejecutivo Completo (PDF)",
                    data=generar_pdf_informe(df_hist_completo, df_padron),
                    file_name="Informe_Ejecutivo_SVR.pdf", mime="application/pdf",
                )