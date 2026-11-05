# Control de temporizadores con Cheat Engine — 0.18.0

Este paquete usa el **speedhack de Cheat Engine** como alternativa experimental.
Necesita Cheat Engine **de 64 bits para Windows**, instalado por el usuario;
el Atlantica.exe admitido sigue siendo de 32 bits. No incluye Cheat Engine ni el
cliente del juego. Obtén CE de su [proyecto oficial](https://github.com/cheat-engine/cheat-engine).
No requiere activar un depurador.

## Automático con el bot de ataques

0.18.0 permite activar la velocidad una vez y repetirla en cada combate del
**mismo PID e instancia**. Se apoya en los dos ensayos enviados por el usuario:
0.17.1 detectó una salida a los 6,69 s y el usuario confirmó el regreso a velocidad
normal; 0.17.2 registró otra salida y CE informó 1× a los 5,91 s. Esos ensayos
validan la salida en esas sesiones, sin medir el factor visual ni la estabilidad
del nuevo automático junto a las acciones del bot.

1. Descarga **AtlanticaPanel-Windows** de la compilación 0.18.0. Contiene
   `AtlanticaPanel.exe` y la carpeta `Atlantica-SpeedTrial-CE`. Usa el panel
   actualizado para que sus pruebas nativas compartan la reserva de velocidad.
   Sigue disponible el artefacto CE separado para actualizar solo la tabla.
2. Cierra la ventana anterior de prueba una vez restaurada a 1×. En **la misma
   ventana de CE** donde elegiste el PID del juego, carga el CT nuevo. Su título
   debe mostrar **0.18.0**. Mantén Auto Battle y HuntingMode.txt apagados.
3. Elige el factor y **Automático en cada combate (máx. 60 s)**. Pulsa
   **Activar en cada combate**. Puede activarse desde el mapa: allí espera a 1×,
   sin instalar o cambiar la velocidad antes de un combate válido. La primera
   prueba del uso combinado puede hacerse a 1,25×, el valor predeterminado.
4. En el panel, conecta **ese mismo PID** e inicia tu bot de ataques y su perfil
   de turnos. El bot puede iniciarse antes o después de armar CE. Cada entrada
   de combate conserva las comprobaciones de instancia, personaje, contexto y
   dos observaciones separadas al menos 200 ms antes de solicitar el factor.
5. Al terminar, CE solicita 1× y espera el siguiente combate. Usa **Copiar
   registro** para revisar varias entradas, salidas y factores en una sola copia.

**Restaurar 1× / parar en CE** restaura la tasa si está pendiente y desactiva el
automático de velocidad. **Parar bot en el panel** detiene las acciones del bot;
el complemento CE conserva su propio control. Si quieres detener ambos, usa
ambas paradas. Cerrar normalmente la ventana CE solicita también la restauración.
No fuerces el cierre de CE mientras haya una restauración pendiente.

El control de velocidad usa una reserva **Speed** por PID; el trabajador de
ataques conserva su reserva **Bot**. El automático ocupa solo Speed, por lo que
puede coexistir con ese trabajador. Las pruebas manuales CE y la prueba nativa
de escala del panel reservan ambas: se rechazan mientras otro controlador de
velocidad esté activo. No se permite un segundo automático para ese PID.

Si llega al límite de 60 s o restaura por un cambio gráfico, conserva 1× durante
el resto de ese combate y exige observar el mapa antes de volver a aplicar un
factor. No reinicia otro plazo de 60 s dentro de la misma batalla. Una lectura
indeterminada, otro personaje, otra instancia o un cambio de proceso detienen
el automático, con restauración del cambio propio cuando es posible. Si falla
la restauración, retiene la reserva y deja el botón disponible; no repite el
envío automáticamente. Si aparece **Restauración pendiente**, detén también
el bot y usa **Restaurar 1× / parar** en CE. El PID nuevo nunca recibe una
orden de limpieza ajena.

La tabla sigue dependiendo de CE instalado y abierto. Sus controles están en
la ventana CE; el ejecutable del panel no incorpora los hooks de CE ni inicia
una aceleración por abrirse. La selección de proceso de CE queda bloqueada
mientras esté abierto el control para evitar cambiar de instancia accidentalmente.
La cooperación entre velocidad y ataques se ha probado con simulaciones y mutex
reales de Windows, **sin una prueba combinada en el juego todavía**.

## Pruebas manuales de un solo combate

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
al usar la parada manual. Las primeras capturas mostraban restauraciones por el
plazo de 10 s. El registro posterior de 0.17.1 distingue tres ensayos a 3×:

| Tiempo hasta informar 1× | Estado leído antes de restaurar | Interpretación |
| --- | --- | --- |
| 13,08 s | Contextos locales `0/-1`, fase `3`, gráfico `0` | Vuelta preventiva por el contexto gráfico. |
| 1,42 s | Contextos locales `0/-1`, fase `3`, gráfico `0` | Vuelta preventiva por el contexto gráfico. |
| 6,69 s | Contextos locales `-1/-1`, gráfico `0` | Salida del combate detectada. |

El usuario confirmó que el último ensayo volvió a velocidad normal al terminar
la batalla. Esto valida ese recorrido en su cliente, sin medir cuánto se
aceleró la acción ni establecer estabilidad prolongada, recogida de botín o
funcionamiento simultáneo en otras instancias.

0.17.2 etiqueta los dos primeros estados como **Cambio del contexto gráfico;
vuelta preventiva a 1×**. Un gráfico `0` por sí solo no prueba que terminó la
batalla: podría ser una selección temporal del cliente. Solo se aplica una tasa
mayor de 1× con el contexto gráfico `1` y el resto de las condiciones verificadas.
La clasificación nueva exige dos instantáneas coincidentes y valores reconocidos;
los errores de lectura y las instantáneas mezcladas siguen sin confirmar salida.
La restauración se solicita de inmediato y no se vuelve a aplicar la tasa por
sí sola. Un intento rechazado conserva el resultado de la prueba anterior.

Para distinguir los motivos, está disponible **Hasta salir del combate (máx. 60 s)**:
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

Las dos pruebas manuales requieren pulsar el botón para cada ensayo y mantener
el bot detenido. No se activan automáticamente en el próximo combate. El modo de salida
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
reserva el control de velocidad por PID. Las pruebas manuales reservan además el
control de ataques del panel. Dos lecturas separadas al menos
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
Los comentarios del usuario confirman un efecto visual inicial y una vuelta a
velocidad normal al finalizar una batalla. La clasificación adicional de 0.17.2
y la conservación del último resultado se verificaron con procesos y relojes
simulados, reproduciendo las combinaciones de campos del registro recibido.
No se ha medido la duración de las animaciones ni realizado una prueba de
estabilidad prolongada. Usa **Copiar registro** para evaluar otros ensayos.

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
