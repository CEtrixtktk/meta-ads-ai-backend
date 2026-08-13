"""
Servicio de autenticación OAuth con Meta.

Contiene la lógica pura del flujo OAuth 2.0: construir la URL de autorización,
canjear el código temporal por un token, y extender ese token a larga duración.

Diseño: estas funciones NO dependen de Django. Reciben y devuelven datos simples,
lo que las mantiene aisladas, testeables y reutilizables. La integración con las
vistas y la base de datos ocurre fuera de aquí.
"""

import secrets
from urllib.parse import urlencode

import requests
from decouple import config


# --- Configuración leída del .env ---
# Se centraliza aquí la lectura de credenciales para que el resto del módulo
# trabaje con constantes claras. Si algún día cambian, se ajustan en un solo lugar.
APP_ID = config("META_APP_ID")
APP_SECRET = config("META_APP_SECRET")
REDIRECT_URI = config("META_REDIRECT_URI")
GRAPH_VERSION = config("META_GRAPH_VERSION", default="v26.0")

# URL base de la Graph API. Todas las llamadas cuelgan de aquí, incluyendo la versión.
# Construirla una vez evita repetir la versión en cada función.
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Diálogo de OAuth: la página de Facebook donde el usuario ve "¿autorizas esta app?".
# Vive en www.facebook.com, no en graph.facebook.com, porque es una pantalla para humanos.
OAUTH_DIALOG_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"

# Permisos que solicitamos. Para gestionar y leer anuncios necesitamos estos dos.
# Pedir solo lo necesario es buena práctica: Meta rechaza en App Review los scopes de más.
SCOPES = ["ads_management", "ads_read"]


def generate_state_token() -> str:
    """
    Genera un valor aleatorio e impredecible para el parámetro 'state' de OAuth.

    El 'state' protege contra ataques CSRF: se guarda en la sesión del usuario ANTES
    de mandarlo a Meta, y al volver se compara. Si no coincide, la petición de vuelta
    no es legítima (alguien intenta inyectar un callback ajeno) y se rechaza.

    Se usa secrets (no random) porque es criptográficamente seguro: sus valores no
    son predecibles, requisito para que sirva como defensa.
    """
    return secrets.token_urlsafe(32)


def build_authorization_url(state: str) -> str:
    """
    Construye la URL a la que se redirige al usuario para que autorice la app (Paso 1).

    Parámetros:
        state: token anti-CSRF generado por generate_state_token(). La vista lo guarda
               en la sesión y lo pasa aquí para incrustarlo en la URL.

    Devuelve:
        La URL completa del diálogo de OAuth de Facebook, lista para redirigir.
    """
    # Parámetros que Meta espera en el diálogo de OAuth.
    params = {
        "client_id": APP_ID,                 # identifica tu app ante Meta
        "redirect_uri": REDIRECT_URI,        # a dónde vuelve el usuario tras autorizar
        "state": state,                      # defensa CSRF (se valida en el callback)
        "response_type": "code",             # pedimos un "code", no un token directo
        "scope": ",".join(SCOPES),           # permisos, separados por coma
    }
    # urlencode arma el "?client_id=...&redirect_uri=..." de forma segura,
    # escapando caracteres especiales para que la URL sea válida.
    return f"{OAUTH_DIALOG_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    """
    Canjea el 'code' temporal por un token de acceso de corta duración (Paso 4).

    El 'code' que Meta devuelve en el callback es de un solo uso y caduca en ~10 minutos,
    por lo que esta llamada debe hacerse de inmediato al recibirlo.

    Parámetros:
        code: el valor recibido en el parámetro 'code' del callback de Meta.

    Devuelve:
        El diccionario de respuesta de Meta, que incluye 'access_token' (corto)
        y 'expires_in' (segundos hasta que expira).

    Lanza:
        requests.HTTPError si Meta responde con error (code inválido, redirect_uri
        que no coincide, etc.). La vista capturará esto para informar al usuario.
    """
    params = {
        "client_id": APP_ID,
        "client_secret": APP_SECRET,         # prueba que la petición viene de tu servidor
        "redirect_uri": REDIRECT_URI,        # debe coincidir EXACTO con el del Paso 1
        "code": code,
    }
    # Esta llamada es servidor-a-servidor: el App Secret viaja aquí, nunca en el navegador.
    response = requests.get(f"{GRAPH_URL}/oauth/access_token", params=params)
    # raise_for_status convierte una respuesta de error HTTP en una excepción,
    # para no seguir trabajando con datos inválidos silenciosamente.
    response.raise_for_status()
    return response.json()


def exchange_for_long_lived_token(short_lived_token: str) -> dict:
    """
    Intercambia un token de corta duración por uno de larga duración (Paso 5).

    El token corto dura ~1 hora, inservible para producción. El largo dura ~60 días
    (y para apps con acceso Standard a la Marketing API, puede no expirar por tiempo).

    Parámetros:
        short_lived_token: el 'access_token' obtenido en exchange_code_for_token().

    Devuelve:
        El diccionario de Meta con el 'access_token' de larga duración y su 'expires_in'.

    Lanza:
        requests.HTTPError si Meta rechaza el intercambio.
    """
    params = {
        "grant_type": "fb_exchange_token",   # indica a Meta que queremos extender el token
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "fb_exchange_token": short_lived_token,
    }
    response = requests.get(f"{GRAPH_URL}/oauth/access_token", params=params)
    response.raise_for_status()
    return response.json()