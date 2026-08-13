"""
Tests del servicio de insights de Meta.

Se prueban dos cosas por separado:
  1. La lógica pura de parseo (sin dependencias externas).
  2. La función que llama a Meta (con la llamada HTTP simulada vía mocking).

El mocking permite probar NUESTRA lógica sin depender de Meta: sin tokens vivos,
sin costo, sin red, y con resultados predecibles.
"""

from unittest.mock import patch, MagicMock

import pytest

from apps.meta.services import insights


class TestParseNumericValues:
    """
    Tests de _parse_numeric_values: la conversión de texto a número.
    Es lógica pura, así que no necesita mocking. Ideal para empezar.
    """

    def test_convierte_strings_a_numeros(self):
        """Los campos numéricos que Meta manda como texto deben quedar como float."""
        # Arrange: una fila tal como la devuelve Meta (todo en texto).
        row = {"campaign_name": "Test", "spend": "150.50", "clicks": "42"}

        # Act: ejecutamos la función bajo prueba.
        result = insights._parse_numeric_values(row)

        # Assert: los números ahora son float, el texto se mantiene.
        assert result["spend"] == 150.50
        assert result["clicks"] == 42.0
        assert result["campaign_name"] == "Test"  # el nombre NO se convierte

    def test_valores_invalidos_se_vuelven_cero(self):
        """Si Meta manda basura en un campo numérico, se usa 0.0 en vez de fallar."""
        # Arrange: un valor no convertible a número.
        row = {"spend": "no-es-un-numero"}

        # Act
        result = insights._parse_numeric_values(row)

        # Assert: en lugar de reventar, la función se defiende con 0.0.
        assert result["spend"] == 0.0

    def test_no_modifica_el_diccionario_original(self):
        """La función debe devolver una copia, no mutar la entrada (buena práctica)."""
        # Arrange
        row = {"spend": "100"}

        # Act
        insights._parse_numeric_values(row)

        # Assert: el original sigue intacto (aún es el texto "100").
        assert row["spend"] == "100"


class TestGetCampaignInsights:
    """
    Tests de get_campaign_insights: la función que llama a Meta.

    Usamos mocking para simular la respuesta de Meta. Así probamos NUESTRA lógica
    (que arma bien la petición y procesa bien la respuesta) sin depender de la API real.
    """

    @patch("apps.meta.services.insights.requests.get")
    def test_devuelve_campanias_parseadas(self, mock_get):
        """
        Con una respuesta simulada de Meta, la función debe devolver las campañas
        con sus valores numéricos ya convertidos.

        El argumento 'mock_get' lo inyecta el decorador @patch: es el impostor que
        reemplaza a requests.get durante este test.
        """
        # --- Arrange: preparamos la respuesta falsa de Meta ---
        # Creamos un objeto mock que imita lo que devuelve requests.get: un objeto
        # con un método .json() y un método .raise_for_status().
        fake_response = MagicMock()
        # Cuando el código llame a response.json(), devolverá esta estructura,
        # idéntica en forma a la real de Meta (datos envueltos en "data", todo en texto).
        fake_response.json.return_value = {
            "data": [
                {"campaign_name": "Campaña A", "spend": "100.5", "clicks": "20"},
                {"campaign_name": "Campaña B", "spend": "250.0", "clicks": "55"},
            ]
        }
        # raise_for_status no debe hacer nada (simula una respuesta exitosa, sin error).
        fake_response.raise_for_status.return_value = None
        # Le decimos al mock de requests.get que, al ser llamado, devuelva esa respuesta falsa.
        mock_get.return_value = fake_response

        # --- Act: ejecutamos la función real con datos de prueba ---
        result = insights.get_campaign_insights(
            access_token="token-falso",
            ad_account_id="act_123",
            date_preset="last_30d",
        )

        # --- Assert: verificamos nuestra lógica ---
        # Llegaron dos campañas.
        assert len(result) == 2
        # Y los valores numéricos fueron convertidos de texto a float (nuestra lógica).
        assert result[0]["spend"] == 100.5
        assert result[0]["clicks"] == 20.0
        assert result[1]["campaign_name"] == "Campaña B"

    @patch("apps.meta.services.insights.requests.get")
    def test_respuesta_vacia_devuelve_lista_vacia(self, mock_get):
        """Si Meta no devuelve campañas, la función debe devolver una lista vacía."""
        # Arrange: una respuesta sin datos (Meta devuelve "data": []).
        fake_response = MagicMock()
        fake_response.json.return_value = {"data": []}
        fake_response.raise_for_status.return_value = None
        mock_get.return_value = fake_response

        # Act
        result = insights.get_campaign_insights(
            access_token="token-falso",
            ad_account_id="act_123",
        )

        # Assert: lista vacía, sin errores.
        assert result == []

    @patch("apps.meta.services.insights.requests.get")
    def test_construye_la_peticion_correctamente(self, mock_get):
        """
        Verifica que la función arma la petición a Meta con los parámetros correctos.
        Esto prueba que el 'contrato' con Meta es el esperado, sin llamar a Meta.
        """
        # Arrange
        fake_response = MagicMock()
        fake_response.json.return_value = {"data": []}
        fake_response.raise_for_status.return_value = None
        mock_get.return_value = fake_response

        # Act
        insights.get_campaign_insights(
            access_token="mi-token",
            ad_account_id="act_999",
            date_preset="last_7d",
        )

        # Assert: inspeccionamos CÓMO se llamó al mock.
        # mock_get.call_args captura los argumentos con que se invocó requests.get.
        called_url = mock_get.call_args[0][0]           # primer argumento posicional: la URL
        called_params = mock_get.call_args[1]["params"] # el argumento 'params'

        # La URL debe apuntar a la cuenta correcta y al endpoint de insights.
        assert "act_999" in called_url
        assert called_url.endswith("/insights")
        # Los parámetros deben incluir lo que pasamos.
        assert called_params["access_token"] == "mi-token"
        assert called_params["date_preset"] == "last_7d"
        assert called_params["level"] == "campaign"