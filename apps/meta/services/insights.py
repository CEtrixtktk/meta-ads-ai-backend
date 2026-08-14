"""
Servicio de lectura de métricas (Insights) de Meta.

Consulta el endpoint de Insights de la Marketing API para obtener el rendimiento
de las campañas: gasto, alcance, conversiones y retorno de inversión. Es una
operación de SOLO LECTURA, por lo que no puede modificar ni gastar nada en la cuenta.

Diseño: funciones puras, sin dependencias de Django. Reciben el token y los parámetros,
devuelven los datos ya normalizados (texto convertido a número y estructuras anidadas
aplanadas), listos para consumir por una vista o por el servicio de análisis.
"""

import requests
from decouple import config
import json
import logging

# Logger de este módulo. El nombre "apps.meta.services.insights" hereda la
# configuración del logger "apps" definido en settings, así que su nivel de
# detalle cambia automáticamente según el entorno.
logger = logging.getLogger(__name__)

# Reutilizamos la misma construcción de URL base que en auth.py. Se relee aquí para
# que este módulo sea autónomo y no dependa de importar constantes de otro servicio.
# .strip() protege contra espacios accidentales en el valor del .env.
GRAPH_VERSION = config("META_GRAPH_VERSION", default="v26.0").strip()
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Métricas solicitadas por defecto.
#
# La selección es deliberada: Meta expone más de 70 métricas, pero su documentación
# recomienda pedir solo las necesarias, ya que cada campo extra aumenta el tiempo de
# respuesta y consume cuota de la API. Estas cubren las tres preguntas que importan
# a un anunciante: cuánto gasté, a cuánta gente llegué, y qué obtuve a cambio.
DEFAULT_FIELDS = [
    "campaign_name",   # nombre de la campaña, para identificarla en el reporte
    "objective",       # objetivo configurado (TRAFFIC, SALES...): sin esto no se puede
                       # juzgar si el rendimiento es bueno, porque cada objetivo se mide distinto
    "spend",           # gasto total en el periodo
    "impressions",     # veces que se mostró el anuncio
    "clicks",          # clics totales
    "reach",           # personas únicas alcanzadas
    "frequency",       # veces promedio que cada persona vio el anuncio; una frecuencia
                       # alta indica fatiga publicitaria (la audiencia se satura)
    "ctr",             # click-through rate: % de impresiones que resultaron en clic
    "cpc",             # cost per click: costo promedio por clic
    "cpm",             # costo por cada mil impresiones: mide el precio del alcance
    "actions",         # conversiones por tipo (compras, leads...). Requiere que la cuenta
                       # tenga configurado el Píxel de Meta o la API de Conversiones
    "action_values",   # valor monetario asociado a esas conversiones (ingresos)
    "purchase_roas",   # retorno de la inversión publicitaria en compras
]

# Campos que Meta devuelve como texto pero representan un número simple.
# Se listan explícitamente porque el resto (nombres, estructuras anidadas) no se convierte.
NUMERIC_FIELDS = {
    "spend", "impressions", "clicks", "reach",
    "frequency", "ctr", "cpc", "cpm",
}

# Tipos de acción relevantes para el análisis de negocio, con su nombre legible.
#
# Meta devuelve decenas de tipos de acción mezclados (desde clics en enlaces hasta
# reacciones a publicaciones). Filtrar a este subconjunto evita ruido y mantiene el
# reporte centrado en lo que impacta al negocio. Ampliar este diccionario es la forma
# de soportar nuevos tipos de conversión sin tocar el resto del código.
RELEVANT_ACTIONS = {
    # --- Conversión por conversación (venta asistida por chat) ---
    "onsite_conversion.messaging_conversation_started_7d": "Conversaciones iniciadas",
    "onsite_conversion.messaging_first_reply": "Primeras respuestas en chat",

    # --- Conversión transaccional (e-commerce) ---
    "purchase": "Compras",
    "add_to_cart": "Añadir al carrito",
    "initiate_checkout": "Checkouts iniciados",

    # --- Captación de contactos ---
    "lead": "Leads",
    "complete_registration": "Registros",

    # --- Intención sobre el sitio ---
    "landing_page_view": "Vistas de página de destino",
    "link_click": "Clics en el enlace",
}


def _extract_conversions(row: dict) -> dict:
    """
    Aplana las conversiones desde la estructura anidada que devuelve Meta.

    A diferencia de las métricas simples, Meta no devuelve las conversiones como un
    número: entrega una lista de objetos {action_type, value} con decenas de tipos
    mezclados. Esta función la convierte en un diccionario legible con solo los tipos
    relevantes, y hace lo propio con sus valores monetarios.

    Parámetros:
        row: fila de insights tal como la devuelve Meta.

    Devuelve:
        Diccionario con dos claves: 'conversions' (cantidad por tipo) y
        'conversion_values' (ingresos por tipo). Ambos vacíos si la cuenta no tiene
        seguimiento de conversiones configurado, lo cual es en sí mismo un dato útil.
    """
    conversions = {}
    conversion_values = {}

    # 'actions' contiene las CANTIDADES por tipo de acción.
    for action in row.get("actions", []):
        action_type = action.get("action_type")
        if action_type in RELEVANT_ACTIONS:
            try:
                conversions[RELEVANT_ACTIONS[action_type]] = float(action.get("value", 0))
            except (ValueError, TypeError):
                # Un valor malformado en un tipo no debe invalidar los demás.
                continue

    # 'action_values' contiene los INGRESOS asociados a esas mismas acciones.
    for action in row.get("action_values", []):
        action_type = action.get("action_type")
        if action_type in RELEVANT_ACTIONS:
            try:
                conversion_values[RELEVANT_ACTIONS[action_type]] = float(action.get("value", 0))
            except (ValueError, TypeError):
                continue

    return {"conversions": conversions, "conversion_values": conversion_values}


def _parse_numeric_values(row: dict) -> dict:
    """
    Normaliza una fila de insights para que sea directamente utilizable.

    Realiza dos transformaciones necesarias sobre la respuesta cruda de Meta:
    convierte a número las métricas que llegan como texto (p. ej. "5339.5"), y aplana
    las estructuras anidadas de conversiones y ROAS. Sin esta normalización los datos
    no se podrían sumar, comparar, graficar ni presentar de forma legible.

    Todas las conversiones se hacen de forma defensiva: un valor inesperado se degrada
    a 0.0 en lugar de propagar una excepción, para que un campo problemático no invalide
    todo el reporte.

    Parámetros:
        row: diccionario de métricas tal como lo devuelve Meta.

    Devuelve:
        El diccionario normalizado, con las estructuras crudas ya procesadas y retiradas.
    """
    parsed = dict(row)  # copia para no mutar el original

    # --- Métricas numéricas simples: de texto a float ---
    for field in NUMERIC_FIELDS:
        if field in parsed:
            try:
                parsed[field] = float(parsed[field])
            except (ValueError, TypeError):
                parsed[field] = 0.0

    # --- ROAS: también llega anidado como lista de objetos con su valor ---
    roas_list = parsed.get("purchase_roas", [])
    if roas_list:
        try:
            parsed["roas"] = float(roas_list[0].get("value", 0))
        except (ValueError, TypeError, AttributeError, IndexError):
            parsed["roas"] = 0.0
    else:
        parsed["roas"] = 0.0

    # --- Conversiones e ingresos, aplanados a diccionarios legibles ---
    parsed.update(_extract_conversions(parsed))

    # Se retiran las estructuras crudas ya procesadas para no arrastrar ruido
    # hacia el serializer ni hacia el prompt de análisis.
    parsed.pop("actions", None)
    parsed.pop("action_values", None)
    parsed.pop("purchase_roas", None)

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
                     "today", "yesterday", "last_7d", "last_90d", "maximum".
        fields: métricas a pedir. Si es None, usa DEFAULT_FIELDS.

    Devuelve:
        Lista de diccionarios, uno por campaña, con las métricas ya normalizadas.
        Lista vacía si la cuenta no tuvo actividad en el periodo (respuesta válida,
        no un error: conviene ampliar el date_preset antes de concluir que no hay datos).

    Lanza:
        requests.HTTPError si Meta rechaza la petición (token inválido, sin permisos,
        límite de peticiones alcanzado). La vista que llama traduce este fallo a un 502.
    """
    fields_to_request = fields if fields is not None else DEFAULT_FIELDS

    params = {
        "access_token": access_token,
        "fields": ",".join(fields_to_request),
        # level=campaign agrupa los resultados por campaña (una fila por campaña).
        # Otros niveles posibles: "adset" y "ad", para mayor granularidad.
        "level": "campaign",
        "date_preset": date_preset,
    }

    # El endpoint de insights cuelga de la cuenta publicitaria: /act_XXX/insights
    response = requests.get(
        f"{GRAPH_URL}/{ad_account_id}/insights",
        params=params,
    )
    # Convierte una respuesta de error HTTP en excepción, para no seguir trabajando
    # con datos inválidos de forma silenciosa.
    response.raise_for_status()

    # Meta envuelve los resultados en la clave "data". Cada elemento es una campaña.
    payload = response.json()
    raw_rows = payload.get("data", [])

    # Registro de depuración: la respuesta completa de Meta.
    # Solo se emite en desarrollo (nivel DEBUG), nunca en producción, porque puede
    # contener identificadores de cuenta y datos de negocio del cliente.
    # indent=2 la formatea de forma legible en la terminal.
    logger.debug(
        "Respuesta de Meta para %s (%s):\n%s",
        ad_account_id,
        date_preset,
        json.dumps(payload, indent=2, ensure_ascii=False),
    )

    # Registro informativo resumido: útil también fuera de desarrollo.
    logger.info(
        "Insights obtenidos: %d campañas para %s (%s)",
        len(raw_rows), ad_account_id, date_preset,
    )

    # Se normaliza cada fila antes de devolverla al llamador.
    return [_parse_numeric_values(row) for row in raw_rows]

    # Meta envuelve los resultados en la clave "data". Cada elemento es una campaña.
    raw_rows = response.json().get("data", [])

    # Se normaliza cada fila antes de devolverla al llamador.
    return [_parse_numeric_values(row) for row in raw_rows]