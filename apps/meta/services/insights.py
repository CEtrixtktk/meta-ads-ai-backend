"""
Servicio de lectura de métricas (Insights) de Meta.

Consulta el endpoint de Insights de la Marketing API para obtener el rendimiento
de las campañas: gasto, impresiones, clics, etc. Es una operación de SOLO LECTURA,
por lo que no puede modificar ni gastar nada en la cuenta.

Diseño: funciones puras, sin dependencias de Django. Reciben el token y los parámetros,
devuelven los datos ya limpios (convertidos de texto a número), listos para usar.
"""

import requests
from decouple import config

# Reutilizamos la misma construcción de URL base que en auth.py. Se relee aquí para
# que este módulo sea autónomo y no dependa de importar constantes de otro servicio.
GRAPH_VERSION = config("META_GRAPH_VERSION", default="v26.0")
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Métricas que pedimos por defecto. Son las que todo anunciante revisa primero.
# Meta las devuelve como texto; más abajo las convertimos a número.
DEFAULT_FIELDS = [
    "campaign_name",   # nombre de la campaña, para identificarla en el reporte
    "spend",           # gasto total en el periodo
    "impressions",     # veces que se mostró el anuncio
    "clicks",          # clics totales
    "reach",           # personas únicas alcanzadas
    "ctr",             # click-through rate: % de impresiones que resultaron en clic
    "cpc",             # cost per click: costo promedio por clic
]

# Campos que llegan como texto pero representan números. Los listamos explícitamente
# para convertirlos; los que no están aquí (como campaign_name) se dejan como texto.
NUMERIC_FIELDS = {"spend", "impressions", "clicks", "reach", "ctr", "cpc"}


def _parse_numeric_values(row: dict) -> dict:
    """
    Convierte a número los campos numéricos de una fila de insights.

    Meta devuelve TODAS las métricas como texto (p. ej. "5339.5" en vez de 5339.5).
    Sin esta conversión no se podrían sumar, comparar ni graficar. Se hace de forma
    defensiva: si un campo no viene o no es convertible, se deja en 0.0 en vez de fallar.

    Parámetros:
        row: un diccionario de métricas tal como lo devuelve Meta (con valores en texto).

    Devuelve:
        El mismo diccionario con los campos numéricos convertidos a float.
    """
    parsed = dict(row)  # copia para no mutar el original
    for field in NUMERIC_FIELDS:
        if field in parsed:
            try:
                parsed[field] = float(parsed[field])
            except (ValueError, TypeError):
                # Si Meta devuelve algo inesperado en un campo numérico, no reventamos:
                # lo dejamos en 0.0 para que el reporte siga siendo utilizable.
                parsed[field] = 0.0
    return parsed


def get_campaign_insights(
    access_token: str,
    ad_account_id: str,
    date_preset: str = "last_30d",
    fields: list[str] | None = None,
) -> list[dict]:
    """
    Obtiene las métricas de rendimiento por campaña de una cuenta publicitaria.

    Parámetros:
        access_token: token de acceso de Meta (se descifra desde el MetaAccount al llamar).
        ad_account_id: cuenta publicitaria a consultar, formato "act_XXXX".
        date_preset: ventana temporal. Por defecto "last_30d". Otros valores comunes:
                     "today", "yesterday", "last_7d", "last_90d", "this_month".
        fields: métricas a pedir. Si es None, usa DEFAULT_FIELDS.

    Devuelve:
        Lista de diccionarios, uno por campaña, con las métricas ya convertidas a número.
        Lista vacía si la cuenta no tuvo actividad en el periodo.

    Lanza:
        requests.HTTPError si Meta rechaza la petición (token inválido, sin permisos, etc.).
    """
    fields_to_request = fields if fields is not None else DEFAULT_FIELDS

    params = {
        "access_token": access_token,
        "fields": ",".join(fields_to_request),
        # level=campaign agrupa los resultados por campaña (una fila por campaña).
        "level": "campaign",
        "date_preset": date_preset,
    }

    # El endpoint de insights cuelga de la cuenta publicitaria: /act_XXX/insights
    response = requests.get(
        f"{GRAPH_URL}/{ad_account_id}/insights",
        params=params,
    )
    response.raise_for_status()

    # Meta envuelve los resultados en la clave "data". Cada elemento es una campaña.
    raw_rows = response.json().get("data", [])

    # Convertimos los valores numéricos de cada fila antes de devolverlos.
    return [_parse_numeric_values(row) for row in raw_rows]