from pathlib import Path
from decouple import config  # Lee variables desde .env; mantiene los secretos fuera del código versionado
import os 
import dj_database_url  # traduce la DATABASE_URL de Railway al formato de Django

# Ruta base del proyecto. Se calcula de forma relativa al archivo, no hardcodeada,
# para que el proyecto funcione igual en cualquier máquina (Windows, Linux, CI, etc.).
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Seguridad ---
# La SECRET_KEY y DEBUG nunca deben tener valores reales en el código.
# En producción DEBUG=False es obligatorio: con DEBUG=True se filtran trazas internas al cliente.
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)  # cast=bool convierte el texto "True"/"False" del .env en booleano
# ALLOWED_HOSTS define qué dominios pueden servir esta app (protección contra
# ataques de Host header). En desarrollo, localhost. En producción, se añade el
# dominio que Railway asigna, leído desde una variable de entorno.
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]  # Dominios autorizados a servir la app; se amplía en producción

# Railway expone el dominio público de la app en esta variable. Si existe
# (o sea, si estamos en Railway), lo añadimos a la lista de hosts permitidos.
RAILWAY_HOST = config("RAILWAY_PUBLIC_DOMAIN", default="")
if RAILWAY_HOST:
    ALLOWED_HOSTS.append(RAILWAY_HOST)

# Respaldo robusto: permitir cualquier subdominio de railway.app.
# Esto garantiza que el dominio asignado por Railway siempre sea aceptado,
# incluso si la variable anterior no estuviera disponible al arrancar.
ALLOWED_HOSTS.append(".railway.app")

# --- Aplicaciones registradas ---
INSTALLED_APPS = [
    # Apps propias de Django (admin, autenticación, sesiones, etc.)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Librerías de terceros
    "rest_framework",   # Framework para construir la API REST
    "corsheaders",      # Permite que el frontend (otro origen/puerto) consuma la API

    # Aplicaciones del proyecto. El prefijo "apps." coincide con la ruta real de importación.
    "apps.users",
    "apps.meta",
    "apps.ai",
]

# --- Middleware ---
# Cada petición atraviesa esta pila en orden. El orden importa.
MIDDLEWARE = [
    # CORS debe ir lo más arriba posible para poder añadir sus cabeceras
    # antes de que otro middleware corte la respuesta.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
     "whitenoise.middleware.WhiteNoiseMiddleware",   # WhiteNoise
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ROOT_URLCONF = "config.urls"  # Punto de entrada del enrutador

# --- Base de datos ---
# Todos los valores vienen del .env para no exponer credenciales. Original Django
#DATABASES = {
#    "default": {
#        "ENGINE": "django.db.backends.postgresql",
#        "NAME": config("DB_NAME"),
#        "USER": config("DB_USER"),
#        "PASSWORD": config("DB_PASSWORD"),
#        "HOST": config("DB_HOST", default="localhost"),
#        "PORT": config("DB_PORT", default="5432"),
#    }
#}

# Configuración de base de datos que se adapta al entorno:
# - En producción, Railway provee DATABASE_URL (una cadena con todo). La usamos.
# - En desarrollo local, esa variable no existe, así que caemos a los campos
#   sueltos de tu .env (los de siempre).
DATABASE_URL = config("DATABASE_URL", default="")

if DATABASE_URL:
    # Producción (Railway): parseamos la URL única.
    # conn_max_age mantiene conexiones abiertas para eficiencia.
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    # Desarrollo local: los campos sueltos de siempre.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }

# --- Configuración de Django REST Framework ---
REST_FRAMEWORK = {
    # Autenticación por JWT: el cliente envía un token en cada petición
    # en lugar de depender de sesiones/cookies. Ideal para un frontend desacoplado como Vue.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Por defecto, toda vista exige usuario autenticado.
    # Las vistas públicas (login, registro) sobrescriben esto explícitamente.
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

# Configuración de archivos estáticos.
STATIC_URL = "static/"
# Carpeta donde Django recolecta los estáticos para producción (el admin, etc.).
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoise comprime y cachea los estáticos para servirlos eficientemente.
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
# --- CORS ---
# Solo se permite el origen del frontend de desarrollo (Vite/Sakai en el puerto 5173).
# Restringir orígenes evita que sitios de terceros consuman la API desde el navegador.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
# Orígenes permitidos para peticiones del navegador (el frontend Vue).
# En desarrollo, localhost:5173. En producción, la URL del frontend desplegado,
# que configuraremos como variable de entorno cuando despleguemos el frontend.


FRONTEND_URL = config("FRONTEND_URL", default="")
if FRONTEND_URL:
    CORS_ALLOWED_ORIGINS.append(FRONTEND_URL)

    # --- Ajustes de seguridad que solo aplican en producción ---
# En desarrollo (DEBUG=True) se omiten para no complicar el trabajo local.
if not DEBUG:
    # Fuerza HTTPS: redirige cualquier petición HTTP a HTTPS.
    SECURE_SSL_REDIRECT = True
    # Railway sirve tras un proxy; esto le dice a Django que confíe en su
    # cabecera para saber que la conexión original era segura.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Las cookies de sesión y CSRF solo viajan por HTTPS.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True