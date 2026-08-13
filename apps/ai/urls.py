from django.urls import path

from . import views

# Rutas de la app ai. Se montan bajo el prefijo "api/ai/" definido en config/urls.py.
urlpatterns = [
    # Análisis de campañas con Claude.
    # URL completa: POST /api/ai/analyze/
    path("analyze/", views.AnalyzeCampaignsView.as_view(), name="ai_analyze"),
]