from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,  # Endpoint que entrega el par de tokens (access + refresh) al hacer login
    TokenRefreshView,     # Endpoint que renueva el access token cuando expira, sin volver a pedir credenciales
)

# Enrutador raíz. Django recorre esta lista de arriba abajo y usa la primera coincidencia.
# La estrategia es delegar: cada app expone sus propias rutas y aquí solo se "montan"
# bajo un prefijo, manteniendo el proyecto modular y desacoplado.
urlpatterns = [
    path("admin/", admin.site.urls),  # Panel de administración de Django

    # Autenticación JWT. Estas dos rutas son la puerta de entrada de todo el sistema:
    # el frontend obtiene el token aquí y lo adjunta en las siguientes peticiones.
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),

    # Rutas específicas de cada app. include() importa el urls.py interno de la app.
    # NOTA: estas líneas requieren que exista apps/ai/urls.py y apps/meta/urls.py;
    # coméntalas si aún no los has creado y necesitas arrancar el servidor.
    path("api/ai/", include("apps.ai.urls")),
    path("api/meta/", include("apps.meta.urls")),
]