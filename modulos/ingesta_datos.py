import zipfile
import re
import pandas as pd
import streamlit as st

@st.cache_data(show_spinner="Procesando archivo KMZ...")
def extraer_coordenadas_kmz(archivo_uploaded):
    try:
        with zipfile.ZipFile(archivo_uploaded) as z:
            kml_archivo = [f for f in z.namelist() if f.endswith('.kml')][0]
            with z.open(kml_archivo) as f:
                contenido_kml = f.read().decode('utf-8', errors='ignore')
        
        rutas_extraidas = []
        paraderos_extraidos = []
        
        chunks_carpetas = contenido_kml.split('<Folder')
        
        for chunk in chunks_carpetas:
            name_folder_match = re.search(r'<name[^>]*>(.*?)</name>', chunk, re.IGNORECASE)
            nombre_carpeta = name_folder_match.group(1).strip() if name_folder_match else "Ruta Base"
            nombre_carpeta = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', nombre_carpeta)
            nombre_carpeta = re.sub(r'<[^>]+>', '', nombre_carpeta).strip().upper()
            
            placemarks = re.findall(r'<Placemark[^>]*>(.*?)</Placemark>', chunk, re.DOTALL | re.IGNORECASE)
            
            for pm in placemarks:
                variante_str = nombre_carpeta
                route_attr = re.search(r'name=["\']ROUTE_NAME["\'][^>]*>([^<]+)', pm, re.I)
                route_html = re.search(r'ROUTE_NAME.*?<td[^>]*>([^<]+)', pm, re.I | re.DOTALL)
                texto_plano_pm = re.sub(r'<[^>]+>', ' ', pm)
                route_txt = re.search(r'ROUTE_NAME\s+([A-Za-z0-9_-]+)', texto_plano_pm, re.I)
                
                if route_attr: variante_str = route_attr.group(1).strip().upper()
                elif route_html: variante_str = route_html.group(1).strip().upper()
                elif route_txt: variante_str = route_txt.group(1).strip().upper()
                    
                variante_str = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', variante_str)
                variante_str = re.sub(r'<[^>]+>', '', variante_str).strip().upper()
                
                if re.search(r'<LineString[^>]*>', pm, re.IGNORECASE) or '<coordinates>' in pm:
                    bloques_coordenadas = re.findall(r'<coordinates[^>]*>(.*?)</coordinates>', pm, re.DOTALL | re.IGNORECASE)
                    for bloque in bloques_coordenadas:
                        puntos_segmento = []
                        for coordenada in bloque.strip().split():
                            partes = coordenada.split(',')
                            if len(partes) >= 2:
                                puntos_segmento.append([float(partes[1]), float(partes[0])])
                        if len(puntos_segmento) > 1:
                            rutas_extraidas.append({
                                'trazado': puntos_segmento,
                                'variante': variante_str
                            })
        return {'rutas': rutas_extraidas, 'paraderos': paraderos_extraidos}
    except Exception:
        return None

@st.cache_data
def cargar_padron_matricial(archivo_excel, nombres_kmz_cargados):
    if archivo_excel is not None:
        try:
            df = pd.read_excel(archivo_excel)
            patentes_extraidas = []
            
            for col_idx in range(len(df.columns)):
                nombre_columna = str(df.columns[col_idx]).strip().upper()
                if "TECNOLOGIA" in nombre_columna or "TECNOLOGÍA" in nombre_columna:
                    continue
                    
                linea_asignada = nombre_columna 
                for kmz in nombres_kmz_cargados:
                    if str(kmz).upper() in nombre_columna:
                        linea_asignada = kmz
                        break
                
                for row_idx in range(len(df)):
                    celda = df.iloc[row_idx, col_idx]
                    if pd.isna(celda): continue
                    
                    celda_str = str(celda).strip().upper()
                    if celda_str != 'NAN' and celda_str != '' and len(celda_str) >= 5 and "PATENTE" not in celda_str:
                        es_electrico = False
                        if col_idx > 0:
                            celda_izq = str(df.iloc[row_idx, col_idx - 1]).strip().upper()
                            if "ELECTRICA" in celda_izq or "ELÉCTRICA" in celda_izq:
                                es_electrico = True

                        patentes_extraidas.append({
                            'Patente': celda_str,
                            'Servicio_Oficial': linea_asignada,
                            'Es_Electrico': es_electrico
                        })
                        
            return pd.DataFrame(patentes_extraidas)
        except Exception as e:
            st.error(f"Error al leer el Padrón: {e}")
            return None
    return None