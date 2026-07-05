import sqlite3
import json
import os
from datetime import datetime

# Ruta absoluta anclada a la carpeta de este archivo (modulos/), no al directorio
# desde el que se ejecute streamlit. Evita errores de "unable to open database
# file" cuando el CWD no tiene permisos o cambia según cómo se lance la app.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivo_svr.db")

# Campos del "datos_evento" que ya genera el motor de análisis en app.py.
# Segmento_Ruta es una lista de coordenadas -> se guarda serializada en JSON.
CAMPOS = [
    "id_alerta", "patente", "servicio", "variante", "infraccion",
    "tramo_afectado", "sector_comuna", "hora_control", "tiempo_abandono",
    "latitud", "longitud", "segmento_ruta", "tipo", "fecha_hora_archivo"
]


def init_db():
    """Crea la tabla si no existe. Se llama una vez al iniciar la app."""
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS registros_historicos (
                id_registro INTEGER PRIMARY KEY AUTOINCREMENT,
                id_alerta TEXT, patente TEXT, servicio TEXT, variante TEXT,
                infraccion TEXT, tramo_afectado TEXT, sector_comuna TEXT,
                hora_control TEXT, tiempo_abandono TEXT,
                latitud REAL, longitud REAL, segmento_ruta TEXT,
                tipo TEXT, fecha_hora_archivo TEXT
            )
        """)
        con.commit()
        con.close()
    except sqlite3.OperationalError as e:
        import streamlit as st
        st.error(f"⚠️ No se pudo crear/abrir la base de datos en '{DB_PATH}': {e}")


def guardar_evento(datos_evento: dict, tipo: str):
    """
    Archiva UN evento (OK o Alerta) de forma permanente. tipo = "OK" | "ALERTA".
    Se llama automáticamente cada vez que el motor de análisis genera un evento,
    para que ningún registro se pierda aunque se reinicie la sesión o el servidor.
    """
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """INSERT INTO registros_historicos
           (id_alerta, patente, servicio, variante, infraccion, tramo_afectado,
            sector_comuna, hora_control, tiempo_abandono, latitud, longitud,
            segmento_ruta, tipo, fecha_hora_archivo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            datos_evento.get("ID Alerta"), datos_evento.get("Patente"),
            datos_evento.get("Servicio"), datos_evento.get("Variante"),
            datos_evento.get("Infracción"), datos_evento.get("Tramo Afectado"),
            datos_evento.get("Sector Comuna"), datos_evento.get("Hora Control"),
            datos_evento.get("Tiempo de Abandono"), datos_evento.get("Latitud"),
            datos_evento.get("Longitud"), json.dumps(datos_evento.get("Segmento_Ruta")),
            tipo, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    con.commit()
    con.close()


def contar_registros_archivados() -> int:
    """Total histórico guardado en el archivador (para mostrarlo en pantalla)."""
    con = sqlite3.connect(DB_PATH)
    total = con.execute("SELECT COUNT(*) FROM registros_historicos").fetchone()[0]
    con.close()
    return total


def cargar_historico(limite: int = 500) -> list[dict]:
    """Trae los últimos N registros archivados (para auditoría/consulta)."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    filas = con.execute(
        "SELECT * FROM registros_historicos ORDER BY id_registro DESC LIMIT ?", (limite,)
    ).fetchall()
    con.close()
    return [dict(f) for f in filas]