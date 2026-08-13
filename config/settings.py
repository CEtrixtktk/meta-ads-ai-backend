from pathlib import Path
from decouple import config  # Lee variables desde .env; mantiene los secretos fuera del código versionado
import os 

# Ruta base del proyecto. Se calcula de forma relativa al archivo, no hardcodeada,
# para que el proyecto funcione igual en cualquier máquina (Windows, Linux, CI, etc.).
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Seguridad ---
# La SECRET_KEY y DEBUG nunca deben tener valores reales en el código.
# En producción DEBUG=False es obligatorio: con DEBUG=True se filtran trazas internas al cliente.
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)  # cast=bool convierte el texto "True"/"False" del .env en booleano
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]  # Dominios autorizados a servir la app; se amplía en producción

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
# Todos los valores vienen del .env para no exponer credenciales.
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

# --- CORS ---
# Solo se permite el origen del frontend de desarrollo (Vite/Sakai en el puerto 5173).
# Restringir orígenes evita que sitios de terceros consuman la API desde el navegador.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]