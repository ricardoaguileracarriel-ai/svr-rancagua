import math
import random
import requests

def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    rad = math.pi / 180
    a = math.sin(((lat2 - lat1)*rad)/2)**2 + math.cos(lat1*rad) * math.cos(lat2*rad) * math.sin(((lon2 - lon1)*rad)/2)**2
    return 6371000 * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

def snap_punto_a_ruta(lat, lon, rutas_obj):
    mejor_dist = float('inf')
    mejor_pt = (lat, lon)
    mejor_var = "Desconocida"
    mejor_trazado_segmento = []
    
    for seg in rutas_obj:
        for idx, pt in enumerate(seg['trazado']):
            d = calcular_distancia_metros(lat, lon, pt[0], pt[1])
            if d < mejor_dist:
                mejor_dist = d
                mejor_pt = (pt[0], pt[1])
                mejor_var = seg.get('variante', 'Desconocida')
                
                inicio = max(0, idx - 15)
                fin = min(len(seg['trazado']), idx + 15)
                mejor_trazado_segmento = seg['trazado'][inicio:fin]
                
    return mejor_pt[0], mejor_pt[1], mejor_var, mejor_trazado_segmento

def evaluar_operacion(lat_bus, lon_bus, lineas_rutas, velocidad_bus, limite_velocidad, paraderos_linea):
    if not lineas_rutas: return "Operación Normal", 0
    
    if velocidad_bus == 0 and paraderos_linea:
        distancia_paradero_mas_cercano = min([calcular_distancia_metros(lat_bus, lon_bus, p['lat'], p['lon']) for p in paraderos_linea])
        if distancia_paradero_mas_cercano <= 40:
            return "Uso No Autorizado como Terminal (Estadía Prolongada)", distancia_paradero_mas_cercano

    todos_los_puntos = [pt for segmento in lineas_rutas for pt in segmento['trazado']]
    distancia_minima = min([calcular_distancia_metros(lat_bus, lon_bus, pt[0], pt[1]) for pt in todos_los_puntos])
    
    if distancia_minima > 150: 
        return "Abandono de Trazado", distancia_minima
    elif distancia_minima > 60:
        return "Acorte/Cambio de Recorrido", distancia_minima
    if velocidad_bus == 0:
        return "Sin Movimiento en Ruta", distancia_minima
    elif velocidad_bus > limite_velocidad:
        return f"Exceso de Velocidad (Máx {limite_velocidad} km/h)", distancia_minima
    return "Operación Normal", distancia_minima

def determinar_sector(lat, lon):
    lat_centro, lon_centro = -34.1708, -70.7444
    dlat = lat - lat_centro
    dlon = lon - lon_centro
    umbral = 0.008
    if abs(dlat) < umbral and abs(dlon) < umbral:
        return "Sector Centro"
    if dlat > umbral and abs(dlon) < umbral:
        return "Sector Norte"
    if dlat < -umbral and abs(dlon) < umbral:
        return "Sector Sur"
    if abs(dlat) < umbral and dlon > umbral:
        return "Sector Oriente"
    if abs(dlat) < umbral and dlon < -umbral:
        return "Sector Poniente"
    if dlat > umbral and dlon > umbral:
        return "Sector Nororiente"
    if dlat > umbral and dlon < -umbral:
        return "Sector Norponiente"
    if dlat < -umbral and dlon > umbral:
        return "Sector Suroriente"
    return "Sector Surponiente"

_CACHE_RUTEO = {}

def _rutear_por_calles(puntos):
    """
    puntos: lista de 2+ coordenadas [lat, lon]. OSRM calcula el camino REAL por
    calles pasando en orden por cada una — con 3 puntos (inicio, punto medio
    desviado, fin) fuerza un desvío real que sale y vuelve a la ruta oficial,
    en vez de una línea recta cruzando manzanas.
    """
    clave = tuple(round(c, 5) for p in puntos for c in p)
    if clave in _CACHE_RUTEO:
        return _CACHE_RUTEO[clave]

    ruta = None
    try:
        coords_url = ";".join(f"{lon},{lat}" for lat, lon in puntos)
        url = f"http://router.project-osrm.org/route/v1/driving/{coords_url}"
        resp = requests.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=3)
        if resp.ok:
            datos = resp.json()
            if datos.get("code") == "Ok":
                coords = datos["routes"][0]["geometry"]["coordinates"]  # [[lon, lat], ...]
                ruta = [[c[1], c[0]] for c in coords]
    except requests.RequestException:
        ruta = None

    _CACHE_RUTEO[clave] = ruta
    return ruta


def generar_desviacion(trazado, idx_inicio=None, idx_fin=None):
    """
    segmento_correcto: tramo REAL del trazado oficial de la línea.
    segmento_desviado: camino REAL por calles (vía OSRM) que SALE del trazado
    oficial en p_inicio y VUELVE a unírsele en p_fin (ambos puntos están sobre
    la ruta real) — se fuerza un punto medio desviado hacia un costado para
    que el camino calculado tome calles reales distintas, en vez de coincidir
    exactamente con la ruta oficial o cortar en línea recta por manzanas.
    """
    if idx_inicio is None:
        idx_inicio = random.randint(5, max(10, len(trazado) - 15))
    if idx_fin is None:
        idx_fin = min(idx_inicio + random.randint(4, 12), len(trazado) - 1)
    if idx_fin <= idx_inicio:
        idx_fin = min(idx_inicio + 4, len(trazado) - 1)

    segmento_correcto = trazado[idx_inicio:idx_fin + 1]

    p_inicio = trazado[idx_inicio]
    p_fin = trazado[idx_fin]

    dlat = p_fin[0] - p_inicio[0]
    dlon = p_fin[1] - p_inicio[1]
    largo = math.hypot(dlat, dlon) or 1e-9
    perp_lat, perp_lon = -dlon / largo, dlat / largo  # vector perpendicular al trazado
    offset = random.uniform(0.0008, 0.0018) * random.choice([-1, 1])
    punto_medio = [
        (p_inicio[0] + p_fin[0]) / 2 + perp_lat * offset,
        (p_inicio[1] + p_fin[1]) / 2 + perp_lon * offset,
    ]

    ruta_real = _rutear_por_calles([p_inicio, punto_medio, p_fin])
    segmento_desviado = ruta_real if ruta_real else [list(p_inicio), punto_medio, list(p_fin)]

    return segmento_correcto, segmento_desviado, idx_inicio, idx_fin


INTERSECCIONES_POR_SECTOR = {
    "Sector Centro": [
        (("Av. O'Higgins", "Calle Estado"), -34.1665, -70.7442),
        (("Calle San Martín", "Calle Ibieta"), -34.1715, -70.7470),
        (("Calle Bueras", "Calle Mujica"), -34.1740, -70.7410),
        (("Av. España", "Calle Cáceres"), -34.1680, -70.7390),
    ],
    "Sector Norte": [
        (("Av. Recreo", "Av. Circunvalación"), -34.1600, -70.7480),
        (("Av. Kennedy", "Av. República de Chile"), -34.1570, -70.7420),
        (("Av. La Compañía", "Av. Salvador Allende"), -34.1540, -70.7550),
        (("Av. Parque Intercomunal", "Camino Tuniche"), -34.1490, -70.7450),
    ],
    "Sector Sur": [
        (("Av. Millán", "Carretera El Cobre"), -34.1785, -70.7440),
        (("Av. Freire", "Av. Membrillar"), -34.1820, -70.7410),
        (("Av. Río Loco", "Bombero Villalobos"), -34.1830, -70.7480),
        (("Miguel Ramírez", "Eduardo Freí Montalba"), -34.1840, -70.7390),
    ],
    "Sector Oriente": [
        (("Av. Diego de Almagro", "Av. San Juan"), -34.1620, -70.7350),
        (("Av. El Sol", "Av. Las Torres"), -34.1650, -70.7320),
        (("Camino a Machalí", "Bombero Villalobos"), -34.1700, -70.7300),
        (("Av. Parque José Miguel Carrera", "Población Manso de Velasco"), -34.1600, -70.7280),
    ],
    "Sector Poniente": [
        (("Av. Viña del Mar", "Av. Provincial"), -34.1680, -70.7550),
        (("Av. Baquedano", "Calle San Martín Poniente"), -34.1700, -70.7600),
        (("Av. Los Alpes", "Paseo Estado"), -34.1720, -70.7580),
        (("Av. Las Torres", "Ruta H-10"), -34.1750, -70.7620),
    ],
    "Sector Nororiente": [
        (("Av. La Compañía", "Calle Los Floristas"), -34.1550, -70.7380),
        (("Av. Kennedy", "Av. Diego de Almagro"), -34.1580, -70.7360),
        (("Av. Recreo", "Av. Circunvalación Nororiente"), -34.1560, -70.7400),
        (("Av. San Juan", "Calle El Sol"), -34.1590, -70.7340),
    ],
    "Sector Norponiente": [
        (("Av. Salvador Allende", "Av. Viña del Mar"), -34.1560, -70.7560),
        (("Av. Baquedano", "Av. Provincial"), -34.1580, -70.7600),
        (("Av. Illanes", "Calle Victoria"), -34.1590, -70.7580),
        (("Ruta Travesía Norte", "Camino a Chancón"), -34.1530, -70.7620),
    ],
    "Sector Suroriente": [
        (("Carretera El Cobre", "Bombero Villalobos Oriente"), -34.1800, -70.7340),
        (("Av. Freire", "Camino a Machalí"), -34.1830, -70.7330),
        (("Av. San Juan", "Av. Membrillar Sur"), -34.1840, -70.7360),
        (("Río Cachapoal", "Av. Parque José Miguel Carrera"), -34.1860, -70.7300),
    ],
    "Sector Surponiente": [
        (("Av. Cachapoal", "Av. Río Loco"), -34.1820, -70.7560),
        (("Av. Los Alpes", "Av. Las Torres Poniente"), -34.1830, -70.7600),
        (("Ruta H-10", "Av. Koke"), -34.1840, -70.7620),
        (("Camino Rabanal", "Torres del Paine"), -34.1860, -70.7580),
    ],
}

def _tramo_aproximado_por_sector(lat, lon, sector):
    """Respaldo cuando no hay internet o la geocodificación falla: intersección
    aproximada más cercana dentro del sector (menos precisa, pero no depende
    de conexión). Se usa como fallback, ya no como método principal."""
    pares = INTERSECCIONES_POR_SECTOR.get(sector, [])
    if not pares:
        return "Eje Vial Principal con Vía Local"
    mejor_par = pares[0]
    mejor_dist = float('inf')
    for par, slat, slon in pares:
        d = calcular_distancia_metros(lat, lon, slat, slon)
        if d < mejor_dist:
            mejor_dist = d
            mejor_par = (par, slat, slon)
    calle_inicio, calle_fin = mejor_par[0]
    return f"{calle_inicio} con {calle_fin}"


_CACHE_GEOCODIFICACION = {}

def obtener_calle_real(lat, lon, sector=None):
    """
    Geocodificación inversa REAL vía Nominatim (OpenStreetMap): consulta el
    nombre real de la calle en esa coordenada exacta, usando la misma fuente
    de datos que el mapa que se muestra en pantalla — por eso ahora sí van a
    coincidir. Se cachea por coordenada redondeada para no repetir consultas
    y respetar el límite de uso de Nominatim (máx. ~1 consulta/segundo).
    Si falla (sin internet, timeout, rate limit), cae a la aproximación por
    sector para que la app nunca se rompa, especialmente útil en una demo.
    """
    clave = (round(lat, 5), round(lon, 5))
    if clave in _CACHE_GEOCODIFICACION:
        return _CACHE_GEOCODIFICACION[clave]

    calle = None
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 17, "addressdetails": 1},
            headers={"User-Agent": "SVR-Rancagua/1.0 (sistema-validacion-red)"},
            timeout=2.5,
        )
        if resp.ok:
            direccion = resp.json().get("address", {})
            calle = direccion.get("road") or direccion.get("pedestrian") or direccion.get("footway")
    except requests.RequestException:
        calle = None

    if not calle:
        calle = _tramo_aproximado_por_sector(lat, lon, sector or determinar_sector(lat, lon))

    _CACHE_GEOCODIFICACION[clave] = calle
    return calle
