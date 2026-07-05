import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO

DIAS_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
ORDEN_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
INFRACCIONES_ABANDONO = ["Abandono de Trazado", "Acorte/Cambio de Recorrido"]


def calcular_metricas(df_hist: pd.DataFrame, df_padron) -> dict:
    """Calcula todos los indicadores del informe ejecutivo a partir del histórico completo."""
    df = df_hist.copy()
    df["fecha_hora_archivo"] = pd.to_datetime(df["fecha_hora_archivo"])
    df["dia_semana"] = df["fecha_hora_archivo"].dt.day_name().map(DIAS_ES)
    df["hora"] = df["fecha_hora_archivo"].dt.hour

    df_alertas = df[df["tipo"] == "ALERTA"]
    df_abandono = df_alertas[df_alertas["infraccion"].isin(INFRACCIONES_ABANDONO)]

    pct_flota_electrica = None
    if df_padron is not None and "Es_Electrico" in df_padron.columns:
        electricas_padron = set(df_padron[df_padron["Es_Electrico"] == True]["Patente"].astype(str))
        circularon = set(df["patente"].astype(str))
        if electricas_padron:
            pct_flota_electrica = len(electricas_padron & circularon) / len(electricas_padron) * 100

    return {
        "top_sectores_abandono": df_abandono["sector_comuna"].value_counts().head(10),
        "top_servicios_infracciones": df_alertas["servicio"].value_counts().head(10),
        "top_patentes_infractoras": df_alertas["patente"].value_counts().head(10),
        "distribucion_infracciones": df_alertas["infraccion"].value_counts(),
        "infracciones_por_dia": df_alertas["dia_semana"].value_counts().reindex(ORDEN_DIAS).fillna(0),
        "infracciones_por_hora": df_alertas["hora"].value_counts().sort_index(),
        "abandono_por_dia": df_abandono["dia_semana"].value_counts().reindex(ORDEN_DIAS).fillna(0),
        "abandono_por_hora": df_abandono["hora"].value_counts().sort_index(),
        "pct_flota_electrica": pct_flota_electrica,
        "total_registros": len(df),
        "total_alertas": len(df_alertas),
        "total_abandonos": len(df_abandono),
    }


def grafico_barras(serie, titulo, subtitulo=None, color="#006FB3", horizontal=False):
    """Gráfico de barras legible: ordenado, con valores encima de cada barra y ejes claros."""
    fig, ax = plt.subplots(figsize=(9, 5))
    if serie.empty:
        ax.text(0.5, 0.5, "Sin datos suficientes", ha="center", va="center", fontsize=12)
        ax.axis("off")
        return fig

    if horizontal:
        datos = serie.sort_values()
        barras = datos.plot(kind="barh", ax=ax, color=color)
        for i, v in enumerate(datos.values):
            ax.text(v, i, f" {int(v)}", va="center", fontsize=10, fontweight="bold")
        ax.set_xlabel("Cantidad de casos")
    else:
        barras = serie.plot(kind="bar", ax=ax, color=color, width=0.7)
        for i, v in enumerate(serie.values):
            ax.text(i, v, f"{int(v)}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Cantidad de casos")
        plt.xticks(rotation=30, ha="right")

    ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
    if subtitulo:
        ax.text(0.5, 1.05, subtitulo, transform=ax.transAxes, ha="center", fontsize=9, color="gray")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return fig


# Se mantiene el alias interno para compatibilidad con generar_pdf_informe.
def _grafico_barras(serie, titulo, color="#006FB3", horizontal=False):
    return grafico_barras(serie, titulo, color=color, horizontal=horizontal)


def generar_pdf_informe(df_hist: pd.DataFrame, df_padron) -> bytes:
    """Genera el informe ejecutivo completo (portada + gráficos) como PDF."""
    m = calcular_metricas(df_hist, df_padron)
    buffer = BytesIO()

    with PdfPages(buffer) as pdf:
        # Portada con resumen ejecutivo
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")
        pct = f"{m['pct_flota_electrica']:.1f}%" if m["pct_flota_electrica"] is not None else "N/D"
        resumen = (
            "INFORME EJECUTIVO\nSistema de Validación en Red (S.V.R.)\n\n"
            f"Total de registros archivados: {m['total_registros']}\n"
            f"Total de alertas/infracciones: {m['total_alertas']}\n"
            f"Total de abandonos de trazado: {m['total_abandonos']}\n"
            f"Porcentaje de flota eléctrica que circuló: {pct}\n"
        )
        ax.text(0.05, 0.95, resumen, fontsize=13, va="top", family="monospace")
        pdf.savefig(fig); plt.close(fig)

        graficos = [
            (m["top_sectores_abandono"], "Top 10 Sectores/Tramos con Más Abandono", True),
            (m["top_servicios_infracciones"], "Servicios con Más Infracciones", True),
            (m["top_patentes_infractoras"], "Patentes con Más Reincidencias", True),
            (m["distribucion_infracciones"], "Distribución por Tipo de Infracción", True),
            (m["infracciones_por_dia"], "Infracciones por Día de la Semana", False),
            (m["infracciones_por_hora"], "Infracciones por Hora del Día", False),
            (m["abandono_por_dia"], "Abandonos por Día de la Semana", False),
            (m["abandono_por_hora"], "Abandonos por Hora del Día", False),
        ]
        for serie, titulo, horizontal in graficos:
            if not serie.empty:
                fig = _grafico_barras(serie, titulo, horizontal=horizontal)
                pdf.savefig(fig); plt.close(fig)

    return buffer.getvalue()