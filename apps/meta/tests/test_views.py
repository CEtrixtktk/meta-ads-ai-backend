"""
Tests de las vistas de la app meta (los endpoints HTTP).

Se prueba la cadena completa: autenticación JWT, permisos, y — lo más importante —
el AISLAMIENTO MULTI-TENANT: que un usuario jamás acceda a datos de otro.

Se usa el APIClient de DRF para simular peticiones sin levantar un servidor real,
y mocking para no llamar a Meta de verdad.
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.meta.models import MetaAccount

User = get_user_model()


# --- Fixtures: preparan datos reutilizables para los tests ---

@pytest.fixture
def api_client():
    """Un cliente HTTP de prueba, limpio para cada test que lo pida."""
    return APIClient()


@pytest.fixture
def user_con_cuenta(db):
    """
    Crea un usuario con una cuenta de Meta conectada.
    El argumento 'db' (fixture de pytest-django) habilita el acceso a la BD de test.
    Devuelve una tupla (usuario, cuenta) para que el test use ambos.
    """
    user = User.objects.create_user(username="alice", password="pass12345")
    cuenta = MetaAccount(
        user=user,
        ad_account_id="act_alice",
        account_name="Cuenta de Alice",
        token_expires_at=timezone.now() + timedelta(days=30),
    )
    cuenta.access_token = "token-de-alice"  # se cifra al asignar
    cuenta.save()
    return user, cuenta


# --- Tests de autenticación ---

class TestInsightsAuthentication:
    """Verifica que el endpoint exige autenticación."""

    def test_sin_token_devuelve_401(self, api_client):
        """Una petición sin JWT debe ser rechazada con 401 (no autorizado)."""
        # Act: pedimos insights sin autenticar.
        response = api_client.get("/api/meta/insights/")

        # Assert: DRF rechaza automáticamente por la config global de permisos.
        assert response.status_code == 401


# --- Tests del endpoint funcionando ---

class TestInsightsEndpoint:
    """Verifica el comportamiento del endpoint con un usuario autenticado."""

    @patch("apps.meta.services.insights.requests.get")
    def test_usuario_autenticado_recibe_sus_insights(self, mock_get, api_client, user_con_cuenta):
        """Un usuario autenticado con cuenta conectada recibe sus métricas."""
        user, cuenta = user_con_cuenta

        # Arrange: simulamos la respuesta de Meta.
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "data": [{"campaign_name": "Campaña de Alice", "spend": "50.0", "clicks": "10"}]
        }
        fake_response.raise_for_status.return_value = None
        mock_get.return_value = fake_response

        # Arrange: autenticamos al cliente como Alice.
        # force_authenticate salta el flujo de login y "loguea" al usuario directamente,
        # útil para aislar la prueba de la vista de la del login.
        api_client.force_authenticate(user=user)

        # Act
        response = api_client.get("/api/meta/insights/?date_preset=last_30d")

        # Assert
        assert response.status_code == 200
        assert response.data["account_id"] == "act_alice"
        assert len(response.data["campaigns"]) == 1
        assert response.data["campaigns"][0]["spend"] == 50.0

    def test_usuario_sin_cuenta_recibe_404(self, api_client, db):
        """Un usuario autenticado pero SIN cuenta conectada recibe 404."""
        # Arrange: usuario sin ninguna MetaAccount.
        user = User.objects.create_user(username="bob", password="pass12345")
        api_client.force_authenticate(user=user)

        # Act
        response = api_client.get("/api/meta/insights/")

        # Assert
        assert response.status_code == 404


# --- EL TEST CLAVE: aislamiento multi-tenant ---

class TestMultiTenantIsolation:
    """
    Verifica que un usuario NUNCA accede a datos de otro.
    Este es el test de seguridad más importante del proyecto.
    """

    @patch("apps.meta.services.insights.requests.get")
    def test_usuario_no_accede_a_cuenta_de_otro(self, mock_get, api_client, user_con_cuenta, db):
        """
        Bob intenta pedir insights de la cuenta de Alice pasando su account_id.
        El sistema NO debe dárselos: la cuenta de Alice no es de Bob.
        """
        alice, cuenta_alice = user_con_cuenta  # Alice ya tiene act_alice

        # Arrange: creamos a Bob, un usuario distinto, sin cuentas.
        bob = User.objects.create_user(username="bob", password="pass12345")

        # Por si acaso el mock se llamara, preparamos una respuesta (no debería usarse).
        fake_response = MagicMock()
        fake_response.json.return_value = {"data": []}
        fake_response.raise_for_status.return_value = None
        mock_get.return_value = fake_response

        # Arrange: autenticamos como Bob.
        api_client.force_authenticate(user=bob)

        # Act: Bob intenta acceder a la cuenta de Alice pasando su ID explícitamente.
        response = api_client.get("/api/meta/insights/?account_id=act_alice")

        # Assert: Bob recibe 404, NO los datos de Alice.
        # La vista buscó "act_alice" DENTRO de las cuentas de Bob y no la encontró.
        assert response.status_code == 404
        # Verificación extra: nunca se llamó a Meta, porque no había cuenta válida
        # de Bob que consultar. El aislamiento cortó antes de tocar la API.
        mock_get.assert_not_called()