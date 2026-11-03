# Acercamiento opcional 0.6.3

El usuario confirmó dos encuentros con 0.5: entró en combate sin Auto Battle,
reconoció la batalla por `local_context` y volvió a buscar. El límite restante era
el alcance: solo atacaba los mobs cercanos. La versión 0.6 añade una ruta normal
del cliente hacia objetivos lejanos; su efecto en el juego sigue pendiente de prueba.

## Uso

1. Conecta con la ventana elegida. Tras verificar la compilación compatible, prepara
   el detector local ya contrastado; no hace falta repetir la calibración anterior.
2. Deja Auto Battle apagado y el personaje quieto. Marca **Acercamiento automático
   (experimental)** y ajusta **Radio de búsqueda**, inicialmente 60 casillas.
3. Pulsa **Iniciar bot**. El punto de inicio fija el centro del área de esa ejecución.
   El radio usa distancia de rejilla (|ΔX| + |ΔY|), entre 5 y 120; no representa metros.
4. El bot prefiere un objetivo ya en alcance. Si no hay uno disponible, solicita
   acercarse al más próximo dentro del área. Al alcanzar el margen de ataque,
   solicita parar, espera dos segundos de posición estable y vuelve a consultar.
5. **Parar bot** cancela nuevas acciones y solicita detener una ruta propia conocida.
   Espera el estado detenido antes de moverlo manualmente o cambiar de ventana.
6. **Copiar estado del bot** incluye `approach`: punto de inicio, configuración,
   solicitudes, llegadas, fallos, motivo de parada, ruta y respuestas nativas.

La casilla abre desmarcada para conservar el comportamiento cercano ya comprobado.
Los controles de radio y movimiento quedan bloqueados durante la ejecución. Los
perfiles de mercenarios siguen guardando solo el plan de turnos, que aún son manuales.

## Funciones y validación

La ruta usa la misma sesión, PID, creación, HWND e hilo de ventana que el ataque.
El puente verifica el hash y el código cargado; el hook valida el personaje local,
contextos locales negativos, identidad/lista activa del objetivo, mapa y radio.
Respeta el bloqueo de movimiento `player+0x338` y el estado vinculado de mapa.
No amplía la distancia de ataque ni activa Auto Battle o archivos compartidos.
El detector por defecto usa la comparación local validada y se vincula de nuevo al
PID y fecha de creación de cada conexión. La calibración manual sigue disponible.

## Corrección de la lectura inicial en 0.6.1

El informe de 0.6.0 del PID 10192 se detuvo con cero observaciones, consultas y
acciones: «El estado de desplazamiento del cliente no es válido». El lector exigía
que ambos bytes de navegación fuesen 0/1 y descartaba toda la observación si no
lo eran. El informe no incluía sus valores originales, por lo que no permite
identificar cuál de los dos provocó el rechazo.

La revisión conserva `active_raw` y `moving_raw`, incluso cuando tienen otro valor.
`active` sigue la comparación exacta con 1 encontrada en el consumidor de ruta
`0043E35F`. Para `moving`, un byte diferente de 0/1 se representa como `null`
(desconocido), nunca como prueba de inactividad. La primera observación se conserva
además de las últimas 24. **Ver objetivos → Copiar resultados** permite obtener
estos valores mediante una consulta sin iniciar movimientos.

El inicio de acercamiento no depende de tratar `+0xB78` como booleano: mantiene
posición estable, contexto, radio, identidad y ausencia de ruta activa. La orden
lleva el objeto y tick leídos; el hook exige que sigan coincidiendo justo antes de
llamar al método normal. Una revisión diferente rechaza la acción y no se reintenta
automáticamente. La parada mantiene su comparación de propiedad completa y solo
confirma flags desactivados cuando ambos bytes son exactamente cero. Un valor
desconocido no autoriza detener una ruta ajena ni se considera una ruta terminada.

## Mantener el objetivo después de acercarse

El informe 0.6.1 del PID 10192 mostró dos rutas aceptadas, una llegada y una ruta
contada como no completada. La última ruta pasó de distancia al cuadrado 78.4067
a 6.71245, se confirmó parada 16 y se encoló un ataque a distancia 1.00211, con
umbral 20. Se observó un combate; el segundo no comenzó según confirmó el usuario.
Su última comprobación indica que el clic manual sí inicia combate. El informe
anterior no conserva el motivo de la primera ruta no completada ni el objetivo
completo de cada solicitud, por lo que no permite atribuir el fallo a una causa única.

En 0.6.1, al terminar una ruta se liberaba el objetivo y se elegía de nuevo entre
los candidatos cercanos. 0.6.2 conserva puesto e identidad completa durante la parada
y estabilización, y exige encontrar ese mismo candidato actualizado antes de atacar.
Si desaparece, cambia de identidad o queda fuera de alcance, descarta esa elección;
no lo sustituye por otro en esa misma consulta. Esta corrección evita una selección
incoherente y necesita contrastarse con el fallo observado; no se presenta como
prueba de haber resuelto la aceptación del servidor.

Una ruta terminada por el cliente se verifica después de la parada antes de
contarla como llegada o fallo. El informe conserva el último fallo y una secuencia
acotada de 32 eventos, con tiempos, identidad, posiciones y resultados. Cada ataque
incluye el candidato completo y si procede de un acercamiento o de la búsqueda cercana.

Mientras espera combate, consulta una vez por segundo únicamente metadatos del
transporte: contexto disponible, instancia de cola, capacidad, ocupación y formato,
así como el identificador y tiempos del control de comandos usado por `0095E871`.
No copia el contenido del búfer, no fuerza su vaciado y no reenvía ataques.
Una ocupación cero no acredita que el servidor haya aceptado el combate. Activar
la ventana sin pulsar el mob tampoco inició la batalla en la prueba del usuario.

**Exportar diagnóstico** añade los bloques de navegación `0043B000` (16 KiB) y
despacho de movimiento `00443000` (8 KiB), hasta 100 KiB contando el envío global.
El segundo contiene la función `00443382` usada por la parada; no estaba en las
capturas anteriores. El manifiesto versión 2 incorpora la traza del bot de ese mismo
PID y fecha de creación. Descarta campos ajenos, nombres de perfiles y contexto de
otra instancia; el contexto tiene un límite de 128 KiB. La exportación solo consulta.

## Evitar volver a un mob ya combatido

La captura `Atlantica-PID10192-contexto-20261103-045410.zip`, generada con 0.6.2,
registró dos solicitudes de acercamiento, dos llegadas y dos combates observados.
El tercer ataque se encoló con distancia al cuadrado 7.01439 y umbral 20, pero no
se confirmó el combate. Durante los treinta segundos de espera la cola permaneció
vacía, con envío habilitado y control de comandos `0000`. Estos datos no prueban
aceptación del servidor. El usuario observó que se acercó a un mob ya derrotado.

El ciclo anterior solo imponía diez segundos de espera al objetivo atacado; tras
una batalla podía volver a seleccionarlo aunque fuera el mismo actor derrotado.
0.6.3 recuerda el puesto y los tres identificadores del objetivo cuando confirma
la entrada en combate. Mientras esa identidad permanezca, lo excluye tanto de la
selección cercana como del acercamiento, sin caducidad por tiempo durante la
ejecución. Si el puesto contiene una identidad nueva, vuelve a estar disponible;
no se excluye a otros mobs de la misma especie. La memoria está limitada a una
identidad por puesto y no se comparte entre procesos ni entre ejecuciones del bot.

La confirmación de combate no indica victoria. Esta medida evita repetir los
objetivos ya combatidos en el ciclo; no demuestra un detector general de cadáveres
ni permite identificar los derrotados antes de iniciar. El informe incluye
`target_history` y `range.excluded_previously_engaged` para contrastar el descarte.
Se mantienen el alcance, el envío individual y la parada si no comienza el combate.

En la misma captura, los cambios de `client_tick` generaban un evento cada segundo
y expulsaban la historia de los primeros combates del límite de 32 eventos.
0.6.3 conserva las muestras recientes del reloj pero solo añade eventos de transporte
cuando cambia otro campo. Así se mantienen las selecciones, llegadas y confirmaciones
en un diagnóstico de este mismo tipo.

| Operación | Función del cliente | Comprobación |
| --- | --- | --- |
| Solicitar ruta | `0043C9D3`, this=jugador, args mapa/X/Y, ret 12. | Envuelve `0043B145`, conserva la navegación normal del cliente. |
| Interrumpir ruta | `0043B211`, this=jugador, sin args. | Usa `0043B1E7`, `00443382` y `0043B145(-1,0,0)` y desactiva flags de ruta. |

Las funciones y su convención de llamada proceden del bloque de código aportado
por el usuario. Se comprueban sus bytes completos y los de los setters relacionados
antes de llamarlas. No se ejecuta el cliente en la nube. Las llamadas nativas
del puente se hacen en el hilo de la ventana seleccionada, sin clics ni teclas.

El descriptor de ruta incluye el objeto local, el tick de solicitud en `+0x1014`
y el destino en `+0x1018/+0x101A/+0x101C`. Antes de detener una ruta viva compara
esos valores; si cambiaron, no llama al método de parada. Si el cliente ya está
inactivo, lo registra sin enviar otra acción. La observación de movimiento usa
los flags `+0x1012` y `+0xB78` y admite progreso de posición durante las lecturas;
mantiene las comprobaciones de instancia, mapa, contexto e índices activos.

La solicitud de ruta aceptada (15) solo demuestra que el cliente publicó la ruta.
La parada (16) verifica flags inactivos y exige después posición estable; no se
presenta por sí sola como prueba de llegada física o aceptación del servidor.
El código nuevo necesita confirmar en el juego movimiento, llegada y Parar bot.

## Límites del ciclo

Durante el acercamiento solo consulta la ruta y el objetivo; no envía ataques.
Solicita parar cuando el objetivo entra en el 80 % del umbral de distancia al
cuadrado, para dejar margen. Después usa el filtro normal y la revalidación nativa
antes de pedir un ataque. Una identidad desaparecida, cambio importante del destino,
cinco segundos sin progreso o veinte segundos de duración terminan el acercamiento.
Los acercamientos no completados tienen una espera por objetivo; tras tres fallos
se detiene. Al superar el área se detiene también. El centro no se desplaza tras
cada combate.

Un cambio de personaje, escena, mapa, modo nativo o ruta ajena no permite sustituir
ese movimiento. La ruta propia conocida se intenta detener antes de soltar el
mutex del PID, con un canal de cancelación distinto al que acaba de cancelar la
ejecución. Una llamada de resultado incierto no se repite. Si no se recibió un
descriptor válido, no se inventa la propiedad de una ruta: se informa resultado
desconocido y se exige comprobar el juego/reconectar. Parar no deshace un ataque
ya encolado ni cancela un combate iniciado.

El protocolo es versión 4, con mensajes de 300 bytes y operaciones distintas para
consulta, ataque, acercamiento y parada. La respuesta debe coincidir en PID, hilo,
operación y objetivo. Las pruebas cubren el ciclo de estados, límites, cancelación
durante la aceptación, limpieza antes de liberar el PID, falta de progreso,
identidad/ruta cambiada y ausencia de reintentos ante una parada incierta. El self-test
de Windows comprueba cancelación y aislamiento sobre una ventana propia; no ejecuta
las funciones del juego.
