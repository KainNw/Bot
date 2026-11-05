# Prueba manual de temporizadores con Cheat Engine — 0.17.0

Este paquete usa el **speedhack de Cheat Engine** como alternativa experimental.
Necesita Cheat Engine **de 64 bits para Windows**, instalado por el usuario;
el Atlantica.exe admitido sigue siendo de 32 bits. No incluye Cheat Engine ni el
cliente del juego. Obtén CE de su [proyecto oficial](https://github.com/cheat-engine/cheat-engine).
No requiere activar un depurador.

## Cómo probar

1. Detén el bot y cualquier otra prueba del PID elegido. Deja Auto Battle y
   HuntingMode.txt desactivados. Entra manualmente en un combate.
2. Abre CE con los permisos necesarios para acceder al juego. En su lista de
   procesos, elige **el PID exacto de esa ventana de Atlantica.exe**. Si hay
   varias ventanas, comprueba su PID en el panel. No selecciones el panel del bot.
3. Abre `Atlantica-SpeedTrial.CT` en CE. Permite ejecutar **el Lua de esta tabla**
   cuando CE lo pregunte. Se abrirá la ventana de prueba; abrirla no cambia
   la velocidad. Como alternativa, carga el `.lua` en el editor Lua de CE y ejecútalo.
4. Deja **1,25×** para la primera prueba y pulsa **Probar 10 segundos**. Dentro
   de ese intervalo, ejecuta una magia manual y observa su duración. Están
   disponibles 1,25×, 1,5×, 2×, 3× y 4×. Los valores mayores requieren su propia
   comprobación; no se presentan como ajustes estables.
5. La prueba solicita **1×** al terminar el plazo, salir de ese combate, perder
   su lectura, pulsar **Restaurar 1× / parar** o cerrar su ventana. Si aparece
   **Restauración pendiente**, conserva CE abierto y pulsa Restaurar. No se
   inicia otra prueba mientras haya una restauración pendiente.

Cada prueba requiere pulsar el botón. No se activa automáticamente en el próximo
combate y no se conecta al ejecutor de turnos del panel. Esta fase sirve para
comprobar el efecto antes de integrarlo. La prueba nativa anterior del panel,
que mueve un campo de 1,40 a 1,45, es un experimento distinto: ese cambio era
aproximadamente del 3,6 %, mientras que **1,25× aquí solicita un 25 % adicional**.

## Qué comprueba y qué significa el resultado

La tabla valida el MD5 conocido del ejecutable, su base, arquitectura, bytes de
la ruta de combate, estado de Auto Battle y contexto normal. Este MD5 corresponde
al cliente de SHA-256
`BC87A0CC5826AA7FB5E4FF10B6B7C1A349962BD8B146AD28EC3FFA9453FE04E6`.
Usa PID y tiempo de creación, conserva un handle de la instancia original y
reserva el mismo mutex por PID que usa el panel. Dos lecturas separadas al menos
200 ms deben reconocer el mismo combate antes de cambiar temporizadores.

El plazo usa el reloj de **CE**, independiente del reloj modificado del cliente.
Se revisa el contexto cada 100 ms aproximadamente; no es un mecanismo de tiempo
real. La carga inicial de CE o un bloqueo del sistema pueden retrasar la revisión
y la restauración. El plazo empieza antes de solicitar el factor.

La ventana de prueba es modal para impedir el cambio normal de proceso dentro
de CE. Si otro script cambia el proceso seleccionado, la limpieza vuelve a
adjuntar **la instancia original todavía viva** antes de solicitar 1×. Nunca
solicita ese cambio al proceso nuevo. Si la instancia terminó, retira la prueba;
un PID reutilizado no autoriza cambios. Mantén esta tabla como único control
del speedhack durante el ensayo y no fuerces el cierre de CE.

**«CE informa …×» es el último factor que informa CE**, no una medición de la
animación ni una confirmación del servidor. La API Lua de CE no proporciona
acuse de aplicación dentro del juego. El registro mantiene esa distinción.
La restauración solicita la tasa normal; no retrocede el tiempo ya transcurrido
en el cliente y conserva los hooks que CE deja instalados a 1×. Terminar CE a
la fuerza puede impedir la limpieza.

Este método afecta los temporizadores consultados por **todo ese proceso**
durante el intervalo, incluidas animaciones y posibles esperas de red. Los demás
PID no reciben solicitudes. El servidor conserva sus propios tiempos y reglas;
un factor local no garantiza que el combate termine antes ni que siga estable.
Todavía no se ha probado esta tabla en un cliente real. Para evaluar el ensayo,
compara la misma magia a 1× y al factor elegido y copia el registro de la ventana.

## Referencias técnicas

Se contrastaron las API con el código oficial de CE, revisión
[`ec45d5f`](https://github.com/cheat-engine/cheat-engine/tree/ec45d5f47f92a239ba0bf51ec5d04a7509c3fd37):

- `bin/celua.txt` y `LuaHandler.pas`: `speedhack_setSpeed`, `speedhack_getSpeed`,
  API local, enumeración de módulos y reloj de CE.
- `pluginexports.pas`: el envoltorio Lua no devuelve el resultado booleano
  interno del cambio de velocidad. Por eso la tabla distingue el factor
  informado de un efecto confirmado en el cliente.
- `speedhack2.pas` y `speedhack/speedhackmain.pas`: cambios de tasa con continuidad
  de los contadores; restaurar 1× no elimina los hooks ni deshace tiempo previo.

El código propio se entrega en el `.lua`; el `.CT` contiene exactamente ese
mismo Lua. `SHA256.txt` permite comprobar los tres archivos del paquete.
