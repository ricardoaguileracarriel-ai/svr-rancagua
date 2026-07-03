import math
import random

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
    eje_y = "Norte" if lat > lat_centro else "Sur"
    eje_x = "Oriente" if lon > lon_centro else "Poniente"
    return f"{eje_y}-{eje_x}".replace("Norte-Oriente", "Nororiente").replace("Norte-Poniente", "Norponiente").replace("Sur-Oriente", "Suroriente").replace("Sur-Poniente", "Surponiente")

def generar_tramo_realista_por_sector(sector):
    diccionario_rancagua = {
        "Nororiente": [
            ("Av. Kennedy", "Calle El Sol"), 
            ("Av. Recreo", "Av. Circunvalación"), 
            ("Av. Diego de Almagro", "Av. San Juan"),
            ("Av. La Compañía", "Calle Los Floristas")
        ],
        "Norponiente": [
            ("Av. Baquedano", "Calle San Martín"), 
            ("Ruta Travesía", "Av. Salvador Allende"), 
            ("Av. Illanes", "Calle Victoria"),
            ("Av. Provincial", "Calle Pedro de Valdivia")
        ],
        "Suroriente": [
            ("Carretera El Cobre", "Bombero Villalobos"), 
            ("Calle Einstein", "Av. Membrillar"), 
            ("Av. Freire", "Calle Millán"),
            ("Av. San Juan", "Camino a Machalí")
        ],
        "Surponiente": [
            ("Av. Cachapoal", "Av. Río Loco"), 
            ("Av. Los Alpes", "Paseo Estado"), 
            ("Av. Las Torres", "Av. Millán"),
            ("Ruta H-10", "Av. Koke")
        ]
    }
    pares_disponibles = diccionario_rancagua.get(sector, [("Eje Vial Principal", "Vía Local")])
    calle_inicio, calle_fin = random.choice(pares_disponibles)
    return f"Desde {calle_inicio} hasta {calle_fin}"