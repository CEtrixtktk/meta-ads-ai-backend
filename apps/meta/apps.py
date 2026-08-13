from django.apps import AppConfig


class MetaConfig(AppConfig):
    # Tipo de clave primaria por defecto para los modelos de esta app.
    # BigAutoField usa enteros de 64 bits, evitando quedarse sin IDs en tablas grandes.
    default_auto_field = "django.db.models.BigAutoField"

    # Ruta de importación REAL de la app. Como vive dentro de la carpeta "apps/",
    # su nombre completo es "apps.meta" y no solo "meta".
    # Este era el origen del error "Cannot import 'meta'": Django buscaba la app
    # en la raíz del proyecto en lugar de dentro de apps/.
    name = "apps.meta"