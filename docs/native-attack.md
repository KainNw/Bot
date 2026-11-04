# Ataque nativo por radio 0.7

El usuario pidió omitir el acercamiento por rutas de 0.6 y probar el mismo sistema
de persecución/ataque de Auto Battle, conservando su alcance y dejándolo apagado.
Desde 0.14.0 se elige como **Perseguir y atacar (nativo)** en **Modo de ataque al mob**,
con radio de selección 60 y límites de 5–500 casillas desde 0.13.0. **Atacar solo a mobs
en alcance** conserva el ciclo cercano. **Atacar desde mi posición** es una opción
experimental [separada de la persecución](stationary-attack.md).
Los turnos de mercenarios dependen de **Ejecutar turnos según el perfil**.

## Qué mostraron las últimas pruebas

La captura `Atlantica-PID10192-contexto-20261103-053320.zip` contiene once bloques
con tamaño y SHA-256 verificados, panel 0.6.4, mismo PID/creación y Auto Battle/caza
nativa apagados. Registró cuatro recorridos: dos permitieron ataques con combate
confirmado, uno se interrumpió porque cambió el destino del mob y otro terminó
fuera de alcance. Después encoló un ataque cercano sin combate observado durante
19.984 segundos; la captura se hizo con el bot todavía esperando, antes de su límite.

Ese objetivo era `(5633, 68108322, 0)`, también presente en el envío sin combate
de 0.6.3. En esta ocasión estaba en el puesto 7; antes estaba en el 9. El usuario
confirmó que un clic manual sobre el mismo mob sí iniciaba el combate. Estos datos
no prueban que fuera un cadáver ni que la causa fuese solo el recorrido anterior.
La corrección de 0.7 cambia el sistema de desplazamiento para la prueba solicitada.

La captura posterior `Atlantica-PID10192-contexto-20261103-063338.zip`, del panel
0.7.0, confirmó seis ataques encolados y seis combates observados. Registró cuatro
solicitudes de persecución nativa, cero fallos y una parada normal, sin necesidad
de reconectar. Auto Battle y caza nativa estaban apagados. El objetivo
`(5633, 68108322, 0)` entró en combate en esta prueba. El usuario confirmó que el
resultado era mucho mejor. Solo se probó una ventana; el informe no demuestra
la parada física durante una persecución activa ni descarta todos los rechazos.

La versión 0.8 conserva estas órdenes y sus tiempos. Su cambio se centra en los
perfiles de mercenarios y la captura de código de combate.

## Órdenes y alcance

La rama nativa de Auto Battle de `0043CA56` distingue distancia al cuadrado mayor
o menor/igual a `[045079EC]`. El panel mantiene esa comparación y lee el mismo
umbral en cada ejecución; no escribe ni incrementa esa variable. El radio de búsqueda
usa `|ΔX| + |ΔY|` desde el punto de inicio y solo limita la selección/persecución.
El candidato próximo se elige por esa distancia de rejilla, como `0044D39F`.

| Situación | Orden reutilizada | Datos |
| --- | --- | --- |
| Fuera del alcance del cliente | `0x0AE5`, carga de 20 bytes. | Posición 3D obtenida por `0043C61A`, control cero y float cero. |
| Dentro del alcance del cliente | `0x0AE2`, carga de 16 bytes. | Los 12 bytes de identidad y controles `1,0`, preparados por `0043BC26`. |
| Parar una persecución propia | `0x0AE5` hacia la posición actual. | Solo si coinciden el objeto local y el destino 3D previamente solicitado. |

La persecución reproduce los campos usados por la rama lejana `0043CED0`:
`owner+1674` guarda el punto obtenido del getter nativo, `+1680=0` y `+1684=1`.
Usa `0040C4E9` para construir el mensaje y el método global `0095EC3A` para enviarlo,
igual que esa rama. El getter `0043C61A` consulta la posición del objeto gráfico;
no se sustituye por una posición de rejilla ni por el vector lógico del actor.
Se validan los bytes completos de esa rama y del getter antes de llamarlo.

Se comprueba el espacio para 29 bytes y su copia bajo el bloqueo de cola. Si no se
copia nada, se restaura el destino anterior solo si sigue siendo el estado escrito
por esa invocación. Una excepción o resultado desconocido detiene el bot; no repite
la solicitud. La orden aceptada por la cola no demuestra movimiento ni aceptación
del servidor: el trabajador observa el progreso real.

Este modo no llama a `0043C9D3` ni a `0043B211`. Tampoco activa Auto Battle,
`HuntingMode.txt` o los globales de selección del bucle de caza anterior. Reutiliza
las órdenes y el umbral; no ejecuta automáticamente los turnos de los mercenarios.

## Seguimiento y parada

El trabajador conserva la identidad completa, vuelve a resolver el puesto actual
y deja que el cliente gestione el movimiento nativo. Si el objetivo se desplaza
más de dos casillas respecto al destino, actualiza el punto con datos frescos. Hay
al menos dos segundos entre órdenes de una misma persecución. El límite total es
20 segundos y el de falta de progreso, cinco. No se reinicia el límite total al
actualizar el punto. Al alcanzar el umbral nativo solicita el ataque sin enviar una
parada por rejilla ni esperar el final del recorrido de 0.6.

Tras encolar un ataque, espera dos muestras de combate y no lo duplica. Conserva
el descriptor de persecución para poder solicitar su parada si se detiene el bot
antes de confirmar batalla. Si observa combate durante la persecución, pausa sin
fabricar una confirmación de ataque enviado. La propiedad del destino se retira
tras dos muestras, para tolerar una muestra transitoria.

Desde 0.12.1, un destino sustituido por un movimiento manual pone la búsqueda en
pausa y libera la referencia del recorrido anterior, sin cancelar la ruta nueva.
Tras dos segundos quieto, reanuda desde la nueva posición y centra allí el radio.
Un personaje/instancia cambiado sigue deteniendo la ejecución. Los estados de
movimiento que no pueden identificarse no se sustituyen por una ruta del bot.
La parada nativa utiliza un canal de cancelación nuevo después de cancelar el de
la ejecución. Compara objeto, mapa y los tres floats del destino dentro del cliente
antes de solicitar el punto actual. El estado `23` solo confirma que se copió esa
orden; el personaje puede estar terminando su movimiento. Durante una parada por
atasco o cambio de objetivo se exige posición estable antes de volver a buscar.
En combate, la parada devuelve `25` y no solicita movimiento. Nunca deshace un
ataque ya aceptado ni repite una parada incierta.

## Instancia, protocolo y prueba

Se conservan las comprobaciones de hash, PID, creación, HWND, hilo, actor, índice,
identidad, mapa, estado, alcance y cola. Un mutex por PID abarca la ejecución y
su limpieza. No usa entradas globales del teclado/ratón ni controles de otras
ventanas. El usuario inició pruebas con varias ventanas y comunicó incidencias de
lag y movimiento; la [recuperación de 0.12.1](recovery.md) incorpora esos casos.

En 0.7 el protocolo helper/DLL pasó a versión 5, mensaje de 312 bytes, con operaciones
`NativeAttack=4` y `StopNativePursuit=5`. La respuesta incluye un descriptor
`pursuit`: actor local, tick informativo, mapa, casilla del objetivo, punto 3D y byte
de destino pendiente. Este byte se conserva como dato; no prueba que el jugador
esté quieto. Los floats se imprimen con nueve dígitos y se normalizan a float32
para comparar el destino sin pérdidas de precisión.

Las pruebas cubren selección por radio, alcance nativo, persecución/ataque/combate,
cambio de puesto, actualización limitada del destino, cancelación, propiedad,
parada tras ataque encolado, resultado incierto y exportación por instancia. El
self-test de Windows comprueba los nuevos tipos de solicitud cancelados sobre
una ventana propia antes de acceder a direcciones del juego. La compilación y
arranque empaquetado no sustituyen la prueba de persecución y parada en Atlantica.
