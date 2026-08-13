"""
Serializers de la app ai.

Validan la frontera de datos del endpoint de análisis. La entrada es mínima
(solo el periodo a analizar); la salida es el texto generado por Claude.
"""

from rest_framework import serializers

# Reutilizamos la misma lista de periodos válidos que meta, para ser consistentes.
# Se importa desde el serializer de meta para no duplicar la lista (una sola fuente
# de verdad: si se actualiza allá, este endpoint queda al día automáticamente).
from apps.meta.serializers import VALID_DATE_PRESETS


class AnalyzeRequestSerializer(serializers.Serializer):
    """
    Valida la entrada del endpoint de análisis.

    Deliberadamente pequeña: el frontend solo indica QUÉ periodo analizar y, si
    tiene varias cuentas, cuál. Las métricas NO se reciben del cliente: la vista
    las obtiene del servidor (Opción 2), lo que garantiza datos frescos y confiables.
    """

    date_preset = serializers.ChoiceField(
        choices=VALID_DATE_PRESETS,
        required=False,
        default="last_30d",
    )
    # Opcional: cuál cuenta analizar si el usuario tiene varias conectadas.
    # Igual que en insights, la vista verifica que pertenezca al usuario autenticado.
    account_id = serializers.CharField(required=False, allow_blank=False)