"""
Servicio de interpretación de métricas de campañas mediante Claude (Anthropic).

Toma las métricas normalizadas que devuelve el servicio de insights de Meta y las
convierte en un análisis en lenguaje llano, comprensible para alguien sin experiencia
en marketing.

Nota sobre el idioma: los prompts y las etiquetas de datos están en inglés porque el
análisis se genera en inglés (el mercado objetivo del producto es angloparlante).
Mantener todo el contexto en el mismo idioma de salida produce resultados más naturales
y consistentes que traducir solo la instrucción final.

Diseño: función pura, sin dependencias de Django ni conocimiento de Meta. Recibe una
lista de métricas y devuelve texto. Este desacoplamiento permite analizar datos de
cualquier plataforma publicitaria sin modificar este módulo.
"""

import logging

import anthropic
from decouple import config

# Logger del módulo. Hereda la configuración del logger "apps" definido en settings,
# de modo que emite detalle completo en desarrollo y solo advertencias en producción.
logger = logging.getLogger(__name__)

# El cliente de Anthropic lee la API key. Se instancia una sola vez a nivel de módulo
# por eficiencia (reutiliza la conexión). Si la key falta, fallará al arrancar, que es
# el comportamiento correcto para un secreto crítico.
_client = anthropic.Anthropic(api_key=config("ANTHROPIC_API_KEY").strip())

# Modelo a usar, leído del .env para poder cambiarlo sin tocar el código.
# .strip() como blindaje contra espacios accidentales en el valor.
MODEL = config("ANTHROPIC_MODEL", default="claude-sonnet-4-6").strip()


def _format_campaigns_for_prompt(campaigns: list[dict]) -> str:
    """
    Convierte las métricas en un texto estructurado y legible para el prompt.

    Presentar los datos de forma ordenada —en lugar de volcar la estructura cruda de
    Python— mejora notablemente la calidad del análisis: el modelo interpreta mejor
    información bien presentada.

    Las etiquetas van en inglés para mantener la coherencia con el idioma de salida.

    Decisión clave: los campos ausentes se declaran explícitamente como "no data"
    en lugar de mostrarse como cero. La diferencia importa: un cero significa "ocurrió
    cero veces", mientras que la ausencia significa "no se está midiendo", y cada caso
    lleva a una recomendación distinta.

    Parámetros:
        campaigns: lista de dicts con las métricas normalizadas (salida de
                   get_campaign_insights, con conversiones ya aplanadas).

    Devuelve:
        Un string con cada campaña y sus métricas, listo para insertar en el prompt.
    """
    lines = []
    for i, c in enumerate(campaigns, start=1):
        block = [
            f"Campaign {i}: {c.get('campaign_name', 'Unnamed')}",
            f"  Objective configured in Meta: {c.get('objective', 'Not specified')}",
            f"  Spend: ${c.get('spend', 0):.2f}",
            f"  Impressions: {int(c.get('impressions', 0)):,}",
            f"  Reach (unique people): {int(c.get('reach', 0)):,}",
            f"  Frequency (average times each person saw the ad): {c.get('frequency', 0):.2f}",
            f"  Clicks: {int(c.get('clicks', 0)):,}",
            f"  CTR: {c.get('ctr', 0):.2f}%",
            f"  CPC (cost per click): ${c.get('cpc', 0):.2f}",
            f"  CPM (cost per 1,000 impressions): ${c.get('cpm', 0):.2f}",
        ]

        # --- Conversiones ---
        # Se incluyen solo si existen. Su ausencia se declara de forma explícita,
        # porque saber que no hay medición configurada es información relevante
        # para el análisis (y suele ser la recomendación más importante).
        conversions = c.get("conversions", {})
        if conversions:
            block.append("  Recorded conversions:")
            for name, value in conversions.items():
                block.append(f"    - {name}: {int(value):,}")
        else:
            block.append(
                "  Conversions: no data recorded "
                "(the account may not have conversion tracking configured)"
            )

        # --- Ingresos atribuidos a esas conversiones ---
        values = c.get("conversion_values", {})
        if values:
            block.append("  Attributed revenue:")
            for name, value in values.items():
                block.append(f"    - {name}: ${value:,.2f}")

        # --- ROAS: retorno de la inversión publicitaria ---
        # Solo se incluye si tiene valor: un ROAS de cero suele significar que no se
        # mide, no que el retorno sea nulo, y mostrarlo induciría a error.
        roas = c.get("roas", 0)
        if roas:
            block.append(f"  ROAS (return per dollar spent): {roas:.2f}x")

        lines.append("\n".join(block))

    return "\n\n".join(lines)


def analyze_campaigns(campaigns: list[dict]) -> str:
    """
    Genera un análisis en lenguaje llano del rendimiento de las campañas.

    Parámetros:
        campaigns: métricas normalizadas de las campañas.

    Devuelve:
        El texto del análisis generado por Claude, en inglés y formato Markdown,
        listo para renderizar en la interfaz.

    Lanza:
        anthropic.APIError si la llamada a la API falla (key inválida, cuota agotada,
        modelo no disponible).
        ValueError si el modelo no devuelve contenido de texto.
        Ambas las traduce la vista a un 502.
    """
    # Sin campañas no tiene sentido llamar a la API: se evita el costo de una
    # generación que no aportaría nada.
    if not campaigns:
        return "No campaigns with activity in the selected period."

    campaigns_text = _format_campaigns_for_prompt(campaigns)

    # Registro de depuración: el texto exacto que recibe el modelo. Permite verificar
    # que los datos llegan completos sin tener que inspeccionar la respuesta.
    # Solo se emite en desarrollo, por el nivel configurado en settings.
    logger.debug("Data sent for analysis:\n%s", campaigns_text)

    # --- Prompt de sistema: define el ROL y los principios del análisis ---
    # Establecer un rol específico con criterios de calidad explícitos produce
    # análisis más consistentes que una instrucción genérica de "analiza estos datos".
    system_prompt = (
        "You are a digital advertising consultant who advises business owners with NO "
        "marketing experience. Your job is to turn technical metrics into clear decisions.\n\n"
        "In your analysis you:\n"
        "- Explain each technical term the first time you use it, in a few words.\n"
        "- State explicitly what to do FIRST and why.\n"
        "- Calculate useful derived metrics when the data allows it, such as cost per "
        "conversion (spend divided by recorded conversions).\n"
        "- Interpret results according to the campaign's actual goal: a messaging "
        "campaign is judged by conversations started, not by web sales.\n"
        "- Point out what the data does NOT show, not only what it shows.\n"
        "- Are honest about uncertainty: when the budget or the period is small, you "
        "note that conclusions are provisional.\n"
        "- Do not invent precise figures or benchmarks: if you cite a reference range, "
        "you present it as approximate."
    )

    # --- Prompt de usuario: los datos y la estructura de salida esperada ---
    user_prompt = (
        "Analyze the performance of these Meta (Facebook/Instagram) advertising "
        "campaigns:\n\n"
        f"{campaigns_text}\n\n"
        "Structure your response with these four sections:\n\n"
        "## The bottom line\n"
        "Two or three sentences with the overall status and the single most important "
        "issue to address.\n\n"
        "## What's working\n"
        "The concrete strengths, with the number that supports each one and what it "
        "means in practical terms.\n\n"
        "## What needs attention\n"
        "The problems or risks, and also what the data does not let you know.\n\n"
        "## Action plan\n"
        "Two to four actions ordered by priority. For each one: what to do, why, and "
        "what result to expect. Indicate which one is most urgent.\n\n"
        "Write in clear English, without marketing jargon."
    )

    # --- Llamada a la API de Claude (Messages API) ---
    # 4000 tokens dan margen para un análisis completo con las cuatro secciones y los
    # cálculos derivados; con límites menores la respuesta se truncaba a mitad del plan.
    message = _client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system_prompt,             # el rol va en el parámetro 'system'
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )

    # Diagnóstico: por qué terminó la generación y qué tipos de bloque devolvió.
    # "end_turn" indica final natural; "max_tokens" que se truncó y conviene ampliar
    # el límite. Registrarlo evita diagnosticar a ciegas cuando algo sale mal.
    logger.debug(
        "Model response: stop_reason=%s, blocks=%s",
        message.stop_reason,
        [getattr(b, "type", "?") for b in message.content],
    )

    # La respuesta puede contener bloques de distinto tipo: texto, razonamiento
    # (ThinkingBlock, en modelos con pensamiento extendido), uso de herramientas.
    # En lugar de asumir que el primer bloque es texto —lo que rompe con esos modelos—,
    # se recorren todos y se concatenan únicamente los de tipo texto. Así el servicio
    # funciona con cualquier modelo, sea cual sea la estructura de su respuesta.
    text_parts = [
        block.text for block in message.content
        if getattr(block, "type", None) == "text"
    ]

    # Salvaguarda: si el modelo no produjo texto —por rechazo del sistema de seguridad,
    # agotamiento del presupuesto de tokens u otra razón— se lanza un error explícito.
    # Devolver un string vacío haría que la interfaz mostrara un panel en blanco sin
    # explicación, un fallo silencioso más difícil de diagnosticar que uno visible.
    if not text_parts:
        raise ValueError(
            f"The model returned no text content. stop_reason={message.stop_reason}"
        )

    return "\n".join(text_parts)