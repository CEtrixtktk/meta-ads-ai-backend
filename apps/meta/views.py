"""
(Agregar estos imports junto a los existentes al inicio del archivo)
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import InsightsRequestSerializer, CampaignInsightSerializer
from .services import insights as insights_service


class CampaignInsightsView(APIView):
    """
    GET /api/meta/insights/

    Devuelve las métricas de campañas de la cuenta publicitaria del usuario
    autenticado. Vista deliberadamente delgada: valida con el serializer,
    delega en el servicio, responde. La lógica de Meta vive en services/insights.py.

    Autenticación: JWT (configurada globalmente en settings). Un request sin
    token válido recibe 401 automáticamente, sin código adicional aquí.
    """

    def get(self, request):
        # --- 1. Validar la entrada ---
        # raise_exception=True corta aquí con un 400 detallado si algo no valida;
        # el código que sigue puede confiar en validated_data.
        params = InsightsRequestSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        date_preset = params.validated_data["date_preset"]
        requested_account = params.validated_data.get("account_id")

        # --- 2. Resolver la cuenta del usuario (núcleo multi-tenant) ---
        # REGLA DE ORO: la consulta SIEMPRE parte de request.user. Aunque el
        # cliente envíe un account_id, solo se busca DENTRO de las cuentas del
        # usuario autenticado. Un usuario jamás puede alcanzar cuentas ajenas:
        # si el ID no es suyo, el filtro simplemente no encuentra nada.
        user_accounts = request.user.meta_accounts.all()
        if requested_account:
            account = user_accounts.filter(ad_account_id=requested_account).first()
        else:
            account = user_accounts.first()

        if account is None:
            # 404 y no 403: no revelamos si esa cuenta existe para otro usuario,
            # solo que este usuario no la tiene. Menos información para un atacante.
            return Response(
                {"detail": "No tienes una cuenta de Meta conectada con ese criterio."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- 3. Delegar en el servicio ---
        # El try/except traduce fallos de Meta a una respuesta HTTP clara.
        # 502 (Bad Gateway) es el código correcto: "un servicio externo del que
        # dependo falló", distinto de un error nuestro (500) o del cliente (4xx).
        try:
            data = insights_service.get_campaign_insights(
                access_token=account.access_token,   # se descifra solo al leer
                ad_account_id=account.ad_account_id,
                date_preset=date_preset,
            )
        except Exception:
            return Response(
                {"detail": "Meta no respondió correctamente. Intenta de nuevo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # --- 4. Dar forma a la salida ---
        # many=True indica que serializamos una lista de filas, no una sola.
        output = CampaignInsightSerializer(data, many=True)
        return Response(
            {
                "account_id": account.ad_account_id,
                "account_name": account.account_name,
                "date_preset": date_preset,
                "campaigns": output.data,
            }
        )