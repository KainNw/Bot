# Ciclo de ataque cercano 0.4

El usuario confirmó que la prueba 0.3 inició el ataque con Auto Battle desactivado.
Su resultado: PID 16244, hilo 18440, objetivo 8, status=1, excepción=0,
distancia 3D al cuadrado 1.45173 y umbral 20. `battle_confirmed=false` era un campo
sin observación automática en esa versión. El usuario solo tenía un cliente abierto;
no se da por validada una prueba real con tres ventanas.

## Comportamiento

Iniciar bot crea un trabajador ligado a la sesión, HWND e hilo elegidos. Requiere
Auto Battle, caza nativa y marcador apagados; no cambia esos controles. Consulta la
lista activa, identidad, filtros conocidos y distancia 3D. El cliente vuelve a validar
el objetivo y el alcance cuando ejecuta la solicitud. No se emiten clics ni teclas.

| Estado | Acción |
| --- | --- |
| Esperando mapa | Observa; no solicita ataques fuera de escena 2. |
| Estabilizando | Exige el mismo mapa y posición estable durante dos segundos. |
| Buscando | Consulta candidatos y elige uno dentro del umbral nativo. |
| Solicitud enviada | Espera escena 1; no duplica la solicitud. |
| Combate | Pausa solicitudes; los turnos son manuales. |
| Regreso al mapa | Vuelve a estabilizar y buscar en el mismo mapa. |
| Detenido | No inicia más solicitudes. |

La interpretación de escena 1 procede de los caminos de combate analizados del
cliente. El detector y el ciclo completo todavía requieren la prueba del usuario.
`battle_confirmed` pasa a true tras observar esa escena después de una solicitud,
no por el incremento de bytes en cola. No confirma victoria, daño o finalización de turnos.

Si no se observa el combate en diez segundos, se detiene y exige comprobar el
cliente/reconectar antes de otra solicitud. Los rechazos de objetivo, cambios de
identidad y movimientos de rango tienen una espera antes de probar de nuevo con
datos frescos. Nunca se reenvía una solicitud cuyo resultado sea incierto.

Cambiar de mapa, mover manualmente al personaje mientras busca, activar Auto Battle
o caza nativa, perder la instancia o fallar la validación detiene el ciclo. Los datos
interrumpidos por un cambio de escena se descartan; tras tres lecturas consecutivas
sin estabilizar, se detiene. Una posición distinta al volver del combate se admite
tras la estabilización. El bot no camina hacia objetivos fuera de alcance.

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
es versión 2 y comprueba su tamaño, identificador y PID.

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

El ataque individual está confirmado por el usuario. El ciclo de varios encuentros,
su detector y las varias ventanas siguen pendientes de validación en el cliente real.
