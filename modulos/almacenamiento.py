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
        con.execute("PRAGMA journal_mode=WAL;")  # Más resistente a cierres abruptos del proceso.
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


def guardar_lote(eventos: list[tuple[dict, str]]):
    """
    Archiva TODOS los eventos de una corrida del motor en una sola conexión/transacción
    (executemany), en vez de abrir+cerrar una conexión por cada bus. Mucho más rápido
    cuando la flota simulada/real crece. eventos = [(datos_evento, "OK"|"ALERTA"), ...]
    """
    if not eventos:
        return
    filas = [
        (
            d.get("ID Alerta"), d.get("Patente"), d.get("Servicio"), d.get("Variante"),
            d.get("Infracción"), d.get("Tramo Afectado"), d.get("Sector Comuna"),
            d.get("Hora Control"), d.get("Tiempo de Abandono"), d.get("Latitud"),
            d.get("Longitud"), json.dumps(d.get("Segmento_Ruta")),
            tipo, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        for d, tipo in eventos
    ]
    con = sqlite3.connect(DB_PATH)
    con.executemany(
        """INSERT INTO registros_historicos
           (id_alerta, patente, servicio, variante, infraccion, tramo_afectado,
            sector_comuna, hora_control, tiempo_abandono, latitud, longitud,
            segmento_ruta, tipo, fecha_hora_archivo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        filas,
    )
    con.commit()
    con.close()


def guardar_evento(datos_evento: dict, tipo: str):
    """
    Archiva UN evento suelto (uso puntual/manual). Para archivar muchos eventos de
    una corrida del motor, usar guardar_lote() en su lugar (mucho más eficiente).
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


def cargar_historico(limite: int | None = 500) -> list[dict]:
    """Trae registros archivados. limite=None trae TODO el histórico (para informes)."""
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        if limite is None:
            filas = con.execute("SELECT * FROM registros_historicos ORDER BY id_registro DESC").fetchall()
        else:
            filas = con.execute(
                "SELECT * FROM registros_historicos ORDER BY id_registro DESC LIMIT ?", (limite,)
            ).fetchall()
        con.close()
        return [dict(f) for f in filas]
    except sqlite3.Error as e:
        import streamlit as st
        st.error(
            f"⚠️ La base de datos '{DB_PATH}' parece dañada ({e}). "
            "Ciérrala si está abierta en otro programa, o bórrala para regenerarla: "
            f"elimina el archivo y vuelve a correr la app."
        )
        return []