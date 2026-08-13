"""
Management command para guardar manualmente un token de Meta durante el desarrollo.

Permite inyectar un token generado a mano (p. ej. desde el Graph API Explorer) en un
MetaAccount, saltándose el flujo OAuth completo. Es una herramienta de DESARROLLO:
en producción, los tokens llegan por OAuth, no por este comando.

Uso:
    python manage.py set_meta_token --account act_123456789 --token EAAxxxx --user admin

El token se cifra automáticamente al asignarlo (vía la propiedad access_token del modelo),
así que este comando también sirve para verificar que el cifrado funciona de extremo a extremo.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.meta.models import MetaAccount

# get_user_model() obtiene el modelo de usuario activo del proyecto, en vez de
# importar User directamente. Así el comando funciona aunque uses un usuario personalizado.
User = get_user_model()


class Command(BaseCommand):
    # Texto que aparece al correr: python manage.py help set_meta_token
    help = "Guarda manualmente un token de Meta en un MetaAccount (solo para desarrollo)."

    def add_arguments(self, parser):
        """
        Define los argumentos que el comando acepta desde la línea de comandos.
        Hacerlos explícitos evita hardcodear valores sensibles dentro del código.
        """
        parser.add_argument(
            "--account",
            required=True,
            help="Ad Account ID de Meta, con formato act_XXXXXXXXX.",
        )
        parser.add_argument(
            "--token",
            required=True,
            help="El token de acceso de Meta a guardar (se cifrará automáticamente).",
        )
        parser.add_argument(
            "--user",
            required=True,
            help="Username del usuario de la plataforma que será dueño de esta conexión.",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Nombre legible de la cuenta (opcional, solo para mostrar en la UI).",
        )
        parser.add_argument(
            # Los tokens del Graph API Explorer suelen durar ~1-2 horas. Para desarrollo
            # asumimos 60 días por defecto, pero se puede ajustar si conoces la duración real.
            "--days",
            type=int,
            default=60,
            help="Días hasta la expiración del token (por defecto 60).",
        )

    def handle(self, *args, **options):
        """
        Lógica principal del comando. Se ejecuta al invocarlo.
        Valida que el usuario exista, calcula la expiración, y guarda el token cifrado.
        """
        # --- Localizar al usuario dueño ---
        # Si el username no existe, cortamos con un error claro en vez de fallar feo.
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(
                f"No existe un usuario con username '{options['user']}'. "
                "Créalo primero con createsuperuser."
            )

        # --- Calcular el momento de expiración ---
        expires_at = timezone.now() + timedelta(days=options["days"])

        # --- Crear o actualizar el MetaAccount ---
        # update_or_create respeta la restricción unique_together (user, ad_account_id):
        # si ya existía esta conexión, la actualiza; si no, la crea. Así el comando es
        # seguro de correr varias veces (idempotente).
        meta_account, created = MetaAccount.objects.update_or_create(
            user=user,
            ad_account_id=options["account"],
            defaults={
                "account_name": options["name"],
                "token_expires_at": expires_at,
            },
        )

        # El token se asigna aparte porque debe pasar por el setter que lo cifra.
        # Esta es la línea donde el cifrado ocurre de verdad.
        meta_account.access_token = options["token"]
        meta_account.save()

        # Mensaje de confirmación. self.style.SUCCESS lo pinta en verde en la terminal.
        accion = "creada" if created else "actualizada"
        self.stdout.write(
            self.style.SUCCESS(
                f"Conexión {accion} para '{user.username}' → cuenta {options['account']}."
            )
        )