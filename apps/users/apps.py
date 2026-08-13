from django.apps import AppConfig

class UsersConfig(AppConfig):
    # Tipo de clave primaria por defecto para los modelos de esta app.
    # BigAutoField usa enteros de 64 bits, evitando quedarse sin IDs en tablas grandes.
    default_auto_field = "django.db.models.BigAutoField"

    # Ruta de importación REAL de la app. Como vive dentro de la carpeta "apps/",
    # su nombre completo es "apps.users" y no solo "users".
    # Si esto no coincide con la estructura de carpetas, Django falla al migrar.
    name = "apps.users"