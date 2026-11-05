# Prueba manual de temporizadores con Cheat Engine — 0.17.1

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
3. Desde **esa misma ventana de CE**, usa el icono de carpeta para abrir
   `Atlantica-SpeedTrial.CT`. Un doble clic en el CT desde el Explorador puede
   abrir otro CE sin proceso seleccionado. Permite ejecutar **el Lua de esta tabla**
   cuando CE lo pregunte. Se abrirá la ventana de prueba; abrirla no cambia
   la velocidad. Como alternativa, carga el `.lua` en el editor Lua de CE y ejecútalo.
4. Deja **1,25×** para la primera prueba. Elige **10 segundos** y pulsa
   **Probar 10 segundos**, o elige **Hasta salir del combate (máx. 60 s)** y pulsa
   **Probar hasta salir del combate**. Ejecuta una magia manual y observa su duración. Están
   disponibles 1,25×, 1,5×, 2×, 3× y 4×. Los valores mayores requieren su propia
   comprobación; no se presentan como ajustes estables.
5. La prueba solicita **1×** al terminar el plazo, salir de ese combate, perder
   su lectura, pulsar **Restaurar 1× / parar** o cerrar su ventana. Si aparece
   **Restauración pendiente**, conserva CE abierto y pulsa Restaurar. No se
   inicia otra prueba mientras haya una restauración pendiente.
6. Pulsa **Copiar registro** y pégalo en la conversación. El texto incluye la
   versión, el PID, el factor solicitado, el modo y el motivo de restauración.

## Comprobar la restauración al terminar el combate

El usuario confirmó aceleración visual y una vuelta inmediata a velocidad normal
al usar la parada manual. También informó un aparente regreso a 1× después de
terminar una batalla. Las capturas recibidas muestran que CE informó 1× al
vencer el plazo de 10 s; ese registro no permite atribuir la vuelta al detector
de salida del combate. La estabilidad de una batalla completa y de la recogida
de botín con este método sigue sin estar confirmada.

Para distinguir los motivos, 0.17.1 ofrece **Hasta salir del combate (máx. 60 s)**:
actívalo una vez dentro del combate y deja que la batalla termine, sin pulsar
Restaurar durante ese ensayo. Al reconocer el mapa, el registro debe mostrar
**Salida del combate detectada …; CE informa 1×**. Comprueba además que el
personaje camine a velocidad normal al volver al mapa. El factor informado no
sustituye esa comprobación visual.

Si vence el límite, aparece **Límite de 60 s cumplido sin confirmar salida del
combate**. Si pierde una lectura o cambia el contexto, solicita también 1× y
conserva ese motivo; no los presenta como una salida de combate confirmada.
El estado que leyó antes de restaurar queda en el registro: escena, contextos
locales, fase del gestor y contexto gráfico. La lectura del mapa exige dos
instantáneas coincidentes, con el personaje local validado y ambos contextos
locales en −1. No sigue el gestor de combate retirado para clasificar el mapa.

La parada manual registra cuándo CE **recibe el manejador del botón** y cuándo
informa 1×; no mide cuándo el usuario presionó físicamente el ratón. Si CE recibe
una parada mientras procesa una lectura, la conserva y le da prioridad frente
al vencimiento del plazo. Una pulsación posterior a la restauración conserva el
motivo anterior. El contador de la ventana muestra segundos transcurridos y el
límite del modo elegido. El registro solo se redibuja cuando cambia, para poder
seleccionar y copiar su texto.

Cada prueba requiere pulsar el botón. No se activa automáticamente en el próximo
combate y no se conecta al ejecutor de turnos del panel. El modo de salida
mantiene un máximo de 60 s por ensayo y no se vuelve a activar por sí solo.
Esta fase sirve para
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
Los comentarios del usuario confirman un efecto visual inicial, sin mediciones
de duración ni una prueba de estabilidad prolongada. El nuevo modo de salida
de 0.17.1 tiene pruebas automatizadas con procesos y relojes simulados; sigue
pendiente su verificación en el cliente real. Compara la misma magia a 1× y al
factor elegido y usa **Copiar registro** para evaluar el ensayo.

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
