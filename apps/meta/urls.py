from django.urls import path

from . import views

# Rutas de la app meta. Se montan bajo el prefijo "api/meta/" definido en config/urls.py.
urlpatterns = [
    # Métricas de campañas del usuario autenticado.
    # URL completa: GET /api/meta/insights/?date_preset=last_30d
    path("insights/", views.CampaignInsightsView.as_view(), name="meta_insights"),

    # NOTA: las rutas del flujo OAuth (oauth/start/ y oauth/callback/) se agregarán
    # cuando retomemos esa fase del plan (paso 5). Sus vistas aún no están en views.py.
]