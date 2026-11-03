# Próximas etapas acordadas

## Panel entregado y estabilidad

- Implementados el control conservador del archivo y el panel nativo con estados de
  solicitud/confirmación. La lógica tiene pruebas; el panel requiere prueba en Windows.
- El PID no es persistente: al perder la lectura, el panel descarta la sesión y exige
  reconectar. La búsqueda por nombre identifica el nuevo PID y verifica la compilación.
- Pendiente diagnosticar el cierre comunicado al mover el personaje con caza activa
  y x32dbg adjunto. No hay un registro conservado ni una causa confirmada.
- El usuario respondió que el clic manual también cierra el cliente con Auto Battle
  apagado, el marcador desactivado y sin x32dbg. Ese resultado amplía la reproducción;
  todavía no permite asignar una causa. Después pidió priorizar la entrega del panel.
- El panel se publicó en `codex/panel-caza`; su compilación Windows y prueba de arranque
  del ejecutable terminaron correctamente. El usuario conectó el panel, consultó
  candidatos y exportó dos ZIP de contexto. La acción independiente sigue pendiente.

## Caza independiente de Auto Battle — objetivo activo

Requisito del usuario: Iniciar bot debe iniciar la caza mientras Auto Battle permanezca
apagado. El modo nativo hallado exige ese indicador y no cumple este requisito.

El usuario pidió también automatizar los turnos de sus mercenarios y después
confirmó priorizar primero el ataque/inicio de encuentros con mobs. Los turnos
y la aceleración quedan como etapas posteriores.

La línea base solicitada fue: marcador desactivado, sin x32dbg adjunto, Auto Battle
apagado y un clic manual sobre un mob. El usuario informó que también se cierra.
Falta obtener evidencia del error antes de considerar ese flujo una base estable.

Después hay que identificar la ruta normal del clic y validar selección de objetivo,
contexto de ejecución y acción. Ya se analizó el constructor `0040C4E9` y el
despachador `0043652D`, que delega en un método virtual no incluido en la primera
captura. No se deben presentar como una API de ataque disponible.

La primera exportación de 28 KiB ya se recibió, validó y analizó. Se implementó una
vista de candidatos de solo lectura que no exige Auto Battle y se amplió la captura
a los auxiliares faltantes y el método virtual de envío. La segunda captura y el
resumen real se recibieron: el barrido 0.2.1 consulta ahora la lista activa y corrige
el contador de cambios. Se identificó `0095EC3A`, pero faltan sus auxiliares de
preparación y la validación `00431AC0`; la exportación añade esos bloques (hasta
76 KiB). Todavía no hay acción de ataque independiente. Detalles en
[independent-mode.md](independent-mode.md).

No se considera modo independiente el cambio artificial del indicador Auto Battle
ni saltarse su comprobación en la rutina nativa. El controlador actual no hace ninguno
de esos cambios. La versión 0.3 añade una prueba individual que llama a los métodos
analizados en el hilo de la ventana seleccionada, con controles de identidad, escena,
alcance y cola. Requiere validar el resultado en el cliente real antes del ciclo
automático. No hay movimiento hacia candidatos lejanos ni automatización de turnos.

El panel selecciona ventana/PID y fecha de creación, evita reconectar automáticamente
a otra instancia y bloquea el marcador nativo compartido por varios clientes. La
prueba individual no cambia ese archivo ni introduce entradas en otras ventanas.

## Velocidad durante combate — mejora posterior

El usuario solicitó estudiar un speedhack al entrar en batalla y mejorar el bot por
etapas. Aún hay que concretar si el efecto deseado es visual o sobre el ritmo de acciones.

Antes de implementarlo se necesitan detección fiable de entrada/salida de combate,
control configurable desactivado por defecto, recuperación de la velocidad normal
al salir del combate/parar/reconectar y comprobaciones de interacción con los tiempos
del servidor. No hay actualmente modificación de relojes, animaciones o velocidad.
