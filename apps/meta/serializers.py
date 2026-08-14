"""
Serializers de la app meta.

Definen y validan la frontera de datos de la API: qué parámetros se aceptan
en las peticiones y qué forma tienen las respuestas. Nada entra ni sale de
las vistas sin pasar por aquí.
"""

from rest_framework import serializers

# Valores de date_preset que Meta acepta. Validarlos aquí produce un error claro
# e inmediato para el frontend, en lugar de un 400 críptico devuelto por Meta.
# Fuente: parámetros del endpoint de Insights de la Marketing API.
VALID_DATE_PRESETS = [
    "today", "yesterday", "last_3d", "last_7d", "last_14d", "last_28d",
    "last_30d", "last_90d", "this_month", "last_month", "this_quarter",
    "this_year", "last_year", "maximum",
]


class InsightsRequestSerializer(serializers.Serializer):
    """
    Valida los parámetros de consulta del endpoint de insights (la ENTRADA).

    No se ata a ningún modelo: valida parámetros sueltos de la URL
    (?date_preset=last_30d&account_id=act_123).
    """

    # ChoiceField rechaza automáticamente cualquier valor fuera de la lista,
    # con un mensaje que incluye las opciones válidas. required=False permite
    # omitirlo y usar el default.
    date_preset = serializers.ChoiceField(
        choices=VALID_DATE_PRESETS,
        required=False,
        default="last_30d",
    )

    # Opcional: si el usuario tiene varias cuentas conectadas, puede indicar cuál.
    # Si no lo manda, la vista usará su primera cuenta.
    # NOTA de seguridad: este ID NUNCA se usa a ciegas; la vista verifica que la
    # cuenta pertenezca al usuario autenticado (aislamiento multi-tenant).
    account_id = serializers.CharField(required=False, allow_blank=False)


class CampaignInsightSerializer(serializers.Serializer):
    """
    Da forma a cada fila de métricas en la respuesta (la SALIDA).

    Declarar los campos explícitamente garantiza que la API devuelve exactamente
    esto y nada más, y sirve de contrato documentado para el frontend.
    """

    campaign_name = serializers.CharField(default="")
    spend = serializers.FloatField(default=0.0)
    impressions = serializers.FloatField(default=0.0)
    clicks = serializers.FloatField(default=0.0)
    reach = serializers.FloatField(default=0.0)
    ctr = serializers.FloatField(default=0.0)
    cpc = serializers.FloatField(default=0.0)
    # Fechas del rango que Meta reporta para la fila. Se exponen para que el
    # frontend pueda mostrar el periodo real de los datos (lección aprendida:
    # con 'maximum' las fechas importan).
    date_start = serializers.CharField(required=False)
    date_stop = serializers.CharField(required=False)

    objective = serializers.CharField(required=False, default="")
    frequency = serializers.FloatField(default=0.0)
    cpm = serializers.FloatField(default=0.0)
    roas = serializers.FloatField(default=0.0)
    # Diccionarios de conversiones e ingresos. DictField acepta estructura variable,
    # ya que los tipos de conversión dependen de cómo esté configurada cada cuenta.
    conversions = serializers.DictField(required=False, default=dict)
    conversion_values = serializers.DictField(required=False, default=dict)