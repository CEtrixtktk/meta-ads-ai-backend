from django.db import models
from django.conf import settings
from django.utils import timezone
from cryptography.fernet import Fernet
from decouple import config


# Se instancia el motor de cifrado UNA sola vez a nivel de módulo, no en cada
# operación, por eficiencia. La clave se lee del .env; si falta, la app debe
# fallar de inmediato al arrancar (comportamiento deseado: es un secreto crítico).
_fernet = Fernet(config("META_TOKEN_ENCRYPTION_KEY").encode())


class MetaAccount(models.Model):
    """
    Representa la conexión OAuth de UN usuario de la plataforma con SU cuenta de Meta.

    Cada fila es la pieza que habilita el modelo multi-tenant: vincula un usuario
    interno con el token que le permite operar sus cuentas publicitarias en Meta.
    El token se almacena cifrado y solo se descifra en el momento de usarlo.
    """

    # --- Vínculo con el dueño (base del aislamiento entre clientes) ---
    # Se referencia el modelo de usuario vía settings.AUTH_USER_MODEL en lugar de
    # importar User directamente: así el código sigue funcionando aunque el proyecto
    # use un modelo de usuario personalizado en el futuro.
    # on_delete=CASCADE: si se elimina el usuario, se eliminan sus conexiones de Meta.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meta_accounts",  # permite hacer user.meta_accounts.all()
    )

    # --- Identificación de la cuenta en Meta ---
    # ID de la cuenta publicitaria en Meta (formato "act_XXXXXXXX"). Es el identificador
    # con el que se harán todas las llamadas de campañas e insights para esta cuenta.
    ad_account_id = models.CharField(max_length=255)

    # Nombre legible de la cuenta, para mostrarlo en la interfaz sin tener que
    # consultar a Meta cada vez. Es un dato de conveniencia, no crítico.
    account_name = models.CharField(max_length=255, blank=True)

    # --- Token cifrado (el dato sensible) ---
    # Campo que almacena el token YA CIFRADO. Nunca se lee ni escribe directamente
    # desde fuera del modelo: para eso existe la propiedad access_token de abajo.
    # El prefijo "_" señala que es de uso interno.
    _encrypted_token = models.BinaryField()

    # Momento exacto en que el token de Meta deja de ser válido. Permite que una
    # tarea programada detecte tokens próximos a expirar y los renueve a tiempo.
    token_expires_at = models.DateTimeField()

    # --- Metadatos de auditoría ---
    created_at = models.DateTimeField(auto_now_add=True)   # se fija al crear
    updated_at = models.DateTimeField(auto_now=True)       # se actualiza en cada save()

    class Meta:
        # Un mismo usuario no debería conectar dos veces la misma cuenta publicitaria.
        # Esta restricción lo impide a nivel de base de datos, no solo de código.
        unique_together = ("user", "ad_account_id")

    # --- Cifrado transparente del token ---
    # Estas dos propiedades son el núcleo de seguridad del modelo. El resto del
    # código trabaja con `cuenta.access_token` en texto claro, sin saber (ni poder
    # provocar) que por debajo el valor viaja cifrado hacia y desde la base de datos.

    @property
    def access_token(self) -> str:
        """
        Devuelve el token descifrado, listo para usar en una llamada a Meta.
        El descifrado ocurre solo aquí, en el instante justo en que se necesita.
        """
        return _fernet.decrypt(self._encrypted_token).decode()

    @access_token.setter
    def access_token(self, raw_token: str) -> None:
        """
        Recibe el token en texto claro y lo guarda cifrado.
        Al forzar el cifrado en el setter, se vuelve IMPOSIBLE almacenar por error
        un token sin cifrar: cualquier asignación pasa obligatoriamente por aquí.
        """
        self._encrypted_token = _fernet.encrypt(raw_token.encode())

    # --- Utilidad de conveniencia ---
    def is_expired(self) -> bool:
        """
        Indica si el token ya caducó. La lógica de renovación consultará esto
        para decidir si debe refrescar el token antes de usarlo.
        """
        return timezone.now() >= self.token_expires_at

    def __str__(self) -> str:
        # Representación legible en el admin de Django y en logs de depuración.
        return f"{self.user} · {self.account_name or self.ad_account_id}"