"""
Servicio de interpretación de métricas de campañas mediante Claude (Anthropic).

Toma las métricas crudas que devuelve el servicio de insights de Meta y las convierte
en un análisis en lenguaje llano, comprensible para alguien sin experiencia en marketing.

Diseño: función pura, sin dependencias de Django. Recibe los datos de las campañas,
devuelve el texto del análisis. La integración con vistas/BD ocurre fuera de aquí.
"""

import anthropic
from decouple import config

# El cliente de Anthropic lee la API key. Se instancia una sola vez a nivel de módulo
# por eficiencia (reutiliza la conexión). Si la key falta, fallará al arrancar, que es
# el comportamiento correcto para un secreto crítico.
_client = anthropic.Anthropic(api_key=config("ANTHROPIC_API_KEY").strip())

# Modelo a usar, leído del .env para poder cambiarlo sin tocar el código.
# .strip() como blindaje contra espacios accidentales (lección aprendida con Meta).
MODEL = config("ANTHROPIC_MODEL", default="claude-sonnet-4-6").strip()


def _format_campaigns_for_prompt(campaigns: list[dict]) -> str:
    """
    Convierte la lista de campañas en un texto estructurado y legible para el prompt.

    En lugar de pasarle a Claude un diccionario crudo de Python, le damos un texto
    ordenado campaña por campaña. Esto mejora la calidad del análisis: el modelo
    entiende mejor datos bien presentados que una estructura técnica en bruto.

    Parámetros:
        campaigns: lista de dicts con las métricas (salida de get_campaign_insights).

    Devuelve:
        Un string con cada campaña y sus métricas, listo para insertar en el prompt.
    """
    lines = []
    for i, c in enumerate(campaigns, start=1):
        # Se usa .get con valores por defecto para no fallar si falta alguna métrica.
        lines.append(
            f"Campaña {i}: {c.get('campaign_name', 'Sin nombre')}\n"
            f"  - Gasto: ${c.get('spend', 0):.2f}\n"
            f"  - Impresiones: {int(c.get('impressions', 0)):,}\n"
            f"  - Clics: {int(c.get('clicks', 0)):,}\n"
            f"  - Alcance: {int(c.get('reach', 0)):,}\n"
            f"  - CTR (tasa de clics): {c.get('ctr', 0):.2f}%\n"
            f"  - CPC (costo por clic): ${c.get('cpc', 0):.2f}\n"
        )
    return "\n".join(lines)


def analyze_campaigns(campaigns: list[dict]) -> str:
    """
    Genera un análisis en lenguaje llano del rendimiento de las campañas.

    Parámetros:
        campaigns: métricas de las campañas (salida directa de get_campaign_insights).

    Devuelve:
        El texto del análisis generado por Claude, listo para mostrar al usuario.

    Lanza:
        anthropic.APIError si la llamada a la API falla (key inválida, límite, etc.).
    """
    # Si no hay campañas, no tiene sentido llamar a la API: ahorramos una llamada
    # (y su costo) devolviendo un mensaje claro de inmediato.
    if not campaigns:
        return "No hay campañas con actividad en el periodo seleccionado para analizar."

    # Formateamos los datos para el prompt.
    campaigns_text = _format_campaigns_for_prompt(campaigns)

    # --- El prompt del sistema: define QUIÉN es Claude en esta tarea ---
    # Establece el rol (analista que explica a un no experto), lo que fija el tono
    # y el nivel de tecnicismo de toda la respuesta.
    system_prompt = (
        "Eres un analista de marketing digital que explica el rendimiento de campañas "
        "publicitarias a dueños de negocio SIN experiencia en marketing. Usas lenguaje "
        "claro y cotidiano, evitas jerga técnica, y cuando debes usar un término lo "
        "explicas en pocas palabras. Eres honesto: si algo va mal, lo dices con tacto "
        "pero con claridad, y siempre propones acciones concretas."
    )

    # --- El mensaje del usuario: los datos y QUÉ queremos ---
    # Pedimos una estructura de salida específica para obtener algo accionable
    # y no un muro de texto genérico.
    user_prompt = (
        "Estas son las métricas de mis campañas publicitarias en Meta (Facebook/Instagram):\n\n"
        f"{campaigns_text}\n\n"
        "Por favor analiza este rendimiento y responde con esta estructura:\n"
        "1. RESUMEN GENERAL: en 2-3 frases, ¿cómo van las campañas en general?\n"
        "2. LO QUE VA BIEN: los puntos positivos concretos.\n"
        "3. LO QUE HAY QUE MEJORAR: los problemas, explicados de forma sencilla.\n"
        "4. QUÉ HACER AHORA: 2-3 acciones concretas y prácticas.\n\n"
        "Recuerda: la persona que lee esto no sabe de marketing. Explícale como si "
        "fuera su primera vez viendo estos números."
    )

    # --- Llamada a la API de Claude (Messages API) ---
    # max_tokens limita la longitud de la respuesta; 1500 es amplio para un análisis.
    message = _client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=system_prompt,             # el rol va en el parámetro 'system'
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )

    # La respuesta viene como una lista de bloques de contenido. Para una respuesta
    # de texto simple, el texto está en el primer bloque.
    return message.content[0].text