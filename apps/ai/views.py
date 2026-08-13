"""
Vistas de la app ai.

Exponen la interpretación de métricas con Claude. La vista de análisis ORQUESTA
dos servicios (insights de meta + análisis de ai), pero la lógica de cada uno vive
en su servicio. La app ai no conoce Meta: es la vista quien conecta ambos mundos.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.meta.services import insights as insights_service
from .serializers import AnalyzeRequestSerializer
from .services import analyzer as analyzer_service


class AnalyzeCampaignsView(APIView):
    """
    POST /api/ai/analyze/

    Genera un análisis en lenguaje llano del rendimiento de las campañas del
    usuario autenticado, para el periodo indicado.

    Flujo (Opción 2, orquestación en la vista):
      1. Valida la entrada (periodo, cuenta opcional).
      2. Resuelve la cuenta del usuario (multi-tenant).
      3. Obtiene métricas frescas vía el servicio de insights (Meta).
      4. Se las pasa al servicio de análisis (Claude).
      5. Devuelve el texto del análisis.
    """

    def post(self, request):
        # --- 1. Validar la entrada ---
        # Los datos llegan en el cuerpo (request.data), no en la URL, por ser POST.
        params = AnalyzeRequestSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        date_preset = params.validated_data["date_preset"]
        requested_account = params.validated_data.get("account_id")

        # --- 2. Resolver la cuenta del usuario (mismo patrón multi-tenant) ---
        # La consulta SIEMPRE parte de request.user: un usuario no alcanza cuentas ajenas.
        user_accounts = request.user.meta_accounts.all()
        if requested_account:
            account = user_accounts.filter(ad_account_id=requested_account).first()
        else:
            account = user_accounts.first()

        if account is None:
            return Response(
                {"detail": "No tienes una cuenta de Meta conectada con ese criterio."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- 3. Obtener métricas frescas (servicio de meta) ---
        # Un fallo de Meta se traduce a 502: el proveedor externo falló, no nosotros.
        try:
            campaigns = insights_service.get_campaign_insights(
                access_token=account.access_token,
                ad_account_id=account.ad_account_id,
                date_preset=date_preset,
            )
        except Exception:
            return Response(
                {"detail": "Meta no respondió correctamente. Intenta de nuevo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # --- 4. Analizar con Claude (servicio de ai) ---
        # Se separa de la llamada anterior para distinguir cuál servicio falló:
        # aquí un error es de Anthropic, no de Meta, y merece su propio 502.
        try:
            analysis_text = analyzer_service.analyze_campaigns(campaigns)
        except Exception:
            return Response(
                {"detail": "El servicio de análisis no está disponible. Intenta de nuevo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # --- 5. Responder ---
        # Devolvemos también las métricas y metadatos para que el frontend tenga
        # todo el contexto en una sola respuesta si lo necesita.
        return Response(
            {
                "account_id": account.ad_account_id,
                "account_name": account.account_name,
                "date_preset": date_preset,
                "campaigns_analyzed": len(campaigns),
                "analysis": analysis_text,
            }
        )