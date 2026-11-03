# Ciclo de ataque independiente

El usuario confirmó que la prueba 0.3 inició el ataque con Auto Battle desactivado.
Su resultado: PID 16244, hilo 18440, objetivo 8, status=1, excepción=0,
distancia 3D al cuadrado 1.45173 y umbral 20. `battle_confirmed=false` era un campo
sin observación automática en esa versión. El usuario solo tenía un cliente abierto;
no se da por validada una prueba real con tres ventanas.

También confirmó que 0.4 inició el combate aunque el panel agotara su espera sin
observarlo. Una captura posterior siguió mostrando contexto 2. El detector anterior
asumía contexto 1; 0.5 sustituye esa suposición por una
[calibración mapa → combate → mapa](combat-calibration.md) ligada a la instancia.

El registro de 0.5 recibido después de calibrar tuvo `attempts=2`, `queued=2`,
`battles_observed=2`, cero lecturas transitorias y `needs_reconnect=false`. Las 96
observaciones mantuvieron `scene_code=2`, con 14 clasificadas como mapa y 82 como
combate por el contexto local. El usuario confirmó el fin de batalla y la búsqueda
siguiente. La parada registrada corresponde a la orden de parar/cerrar el panel.

## Comportamiento

Iniciar bot crea un trabajador ligado a la sesión, HWND e hilo elegidos. Requiere
Auto Battle, caza nativa y marcador apagados y un detector para esa
instancia; la conexión compatible prepara la señal local ya comprobada y
mantiene la calibración como diagnóstico opcional. No cambia esos controles. Consulta la
lista activa, identidad, filtros conocidos y distancia 3D. El cliente vuelve a validar
el objetivo y el alcance cuando ejecuta la solicitud. No se emiten clics ni teclas.

| Estado | Acción |
| --- | --- |
| Esperando mapa | Observa; no solicita ataques fuera de escena 2. |
| Estabilizando | Exige el mismo mapa y posición estable durante dos segundos. |
| Buscando | Consulta candidatos y elige uno dentro del umbral nativo. |
| Persecución nativa (0.7) | Usa la orden de desplazamiento de Auto Battle dentro del radio y observa el progreso. |
| Objetivo en alcance | Usa el mismo umbral del cliente y solicita el ataque; no crea una ruta por rejilla. |
| Solicitud enviada | Espera dos observaciones de combate según la calibración; no duplica la solicitud. |
| Combate | Pausa solicitudes; los turnos son manuales. |
| Regreso al mapa | Vuelve a estabilizar y buscar en el mismo mapa. |
| Detenido | No inicia más solicitudes. |

La calibración requiere una diferencia en los tres grupos etiquetados y un retorno
al mismo mapa; si no la encuentra, permite copiar los datos y bloquea el ciclo.
Puede usar la transición global 2/1/2 o el predicado de contexto local, si se observa
solo en combate y desaparece al regresar. Los demás valores se tratan como desconocidos.
`battle_confirmed` pasa a true tras dos observaciones de combate después de una
solicitud. No confirma victoria, daño o finalización de turnos. El ciclo cercano
está observado en dos encuentros; el movimiento nuevo requiere su propia prueba.

Si no se observa el combate en treinta segundos, se detiene y exige comprobar el
cliente/reconectar antes de otra solicitud. Los rechazos de objetivo, cambios de
identidad y movimientos de rango tienen una espera antes de probar de nuevo con
datos frescos. Nunca se reenvía una solicitud cuyo resultado sea incierto.

Cambiar de mapa, mover manualmente al personaje mientras busca, activar Auto Battle
o caza nativa, perder la instancia o fallar la validación detiene el ciclo. Los datos
interrumpidos por un cambio de escena se descartan; tras tres lecturas consecutivas
sin estabilizar, se detiene. Una posición distinta al volver del combate se admite
tras la estabilización. Con ataque nativo por radio puede solicitar la persecución
del cliente hacia objetivos fuera de alcance. Las condiciones de radio, atasco, parada y límites se
explican en [ataque nativo por radio](native-attack.md).

## Parada, cancelación y cierre

El trabajador no usa Tkinter. Publica instantáneas para que la interfaz conserve
respuesta mientras el auxiliar espera al cliente. Parar bot señala un evento manual
de Windows exclusivo de esa ejecución. La DLL comprueba la cancelación antes de
validar/solicitar el ataque y otra vez bajo el bloqueo de cola, antes del envío.
Si no puede abrir el canal de cancelación, rechaza la solicitud.

Una función de envío que ya comenzó o una solicitud ya encolada puede completarse;
no se modifica ni deshace el combate. La interfaz muestra Deteniendo hasta que
termina el trabajador. Cerrar solicita la misma parada y espera. Toda salida del
trabajador señala la cancelación antes de cerrar el evento y liberar la reserva del PID,
también cuando el auxiliar agota su tiempo de respuesta.

Cada ejecución crea un evento nuevo; no se restablece un evento cancelado para otra
ejecución. Así, un mensaje antiguo no se habilita al volver a iniciar el bot. La prueba
individual también cancela su canal al terminar o fallar. El protocolo helper/DLL
es versión 6 y comprueba su tamaño (376 bytes), identificador, operación y PID.
Las operaciones de caza 0–5 conservan su comportamiento; la operación 6 añade
la [prueba individual de básico en combate](basic-battle-trial.md).
Al parar con una ruta conocida, cancela primero nuevas solicitudes y utiliza un
canal nuevo para detener esa ruta antes de liberar la reserva del PID. No repite
una parada cuyo resultado sea incierto.

## Instancias y comprobaciones

Un mutex por PID se mantiene durante toda la ejecución y excluye otros controladores
del mismo cliente. La reserva es recursiva en el hilo trabajador para permitir cada
solicitud sin liberarla entre combates. Los clientes con otros PID usan reservas distintas.
La acción verifica fecha de creación del proceso, propietario de HWND e hilo esperado;
la respuesta debe identificar ese mismo PID, hilo y objetivo.

Las pruebas cubren ausencia de duplicados, espera de combate, regreso al mapa,
movimiento manual, cambio de PID/fecha/mapa, tiempo sin confirmación, rango, rechazos,
cancelación de una solicitud en curso y falta de reintentos. En Windows se comprueban
reservas entre hilos y que un evento de una ejecución cerrada no cancele una nueva.
El self-test C++ usa una ventana propia y exige rechazo de compilación, cancelación
de una solicitud marcada como ataque y rechazo de un canal de cancelación ausente,
sin ejecutar código del juego. El smoke test empaquetado repite ese self-test.

El ataque y el ciclo de dos encuentros están confirmados por el usuario. El
acercamiento y las varias ventanas siguen pendientes de validación en el cliente real.
Los informes incluyen las últimas 24 observaciones y sus contadores, alcance y
perfil. Los tres perfiles guardan puestos, nombres, participación y prioridad de
mercenarios; el ciclo sigue esperando turnos manuales.
