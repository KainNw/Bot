# Próximas etapas acordadas

## Entrega del panel y estabilidad — prioridad actual

- Implementados el control conservador del archivo y el panel nativo con estados de
  solicitud/confirmación. La lógica tiene pruebas; el panel requiere prueba en Windows.
- El PID no es persistente: al perder la lectura, el panel descarta la sesión y exige
  reconectar. La búsqueda por nombre identifica el nuevo PID y verifica la compilación.
- Pendiente diagnosticar el cierre comunicado al mover el personaje con caza activa
  y x32dbg adjunto. No hay un registro conservado ni una causa confirmada.
- El usuario respondió que el clic manual también cierra el cliente con Auto Battle
  apagado, el marcador desactivado y sin x32dbg. Ese resultado amplía la reproducción;
  todavía no permite asignar una causa. Después pidió priorizar la entrega del panel.

## Caza independiente de Auto Battle — siguiente etapa

Requisito del usuario: Iniciar bot debe iniciar la caza mientras Auto Battle permanezca
apagado. El modo nativo hallado exige ese indicador y no cumple este requisito.

La línea base solicitada fue: marcador desactivado, sin x32dbg adjunto, Auto Battle
apagado y un clic manual sobre un mob. El usuario informó que también se cierra.
Falta obtener evidencia del error antes de considerar ese flujo una base estable.

Después hay que identificar la ruta normal del clic y validar selección de objetivo,
contexto de ejecución y acción. El bloque recibido contiene llamadas a auxiliares
en `0040C4E9` y `0043652D`, pero sus implementaciones no se han capturado y sus
efectos no están confirmados. No se deben presentar como una API de ataque disponible.

No se considera modo independiente el cambio artificial del indicador Auto Battle
ni saltarse su comprobación en la rutina nativa. El controlador actual no hace ninguno
de esos cambios ni escribe en la memoria del cliente.

## Velocidad durante combate — mejora posterior

El usuario solicitó estudiar un speedhack al entrar en batalla y mejorar el bot por
etapas. Aún hay que concretar si el efecto deseado es visual o sobre el ritmo de acciones.

Antes de implementarlo se necesitan detección fiable de entrada/salida de combate,
control configurable desactivado por defecto, recuperación de la velocidad normal
al salir del combate/parar/reconectar y comprobaciones de interacción con los tiempos
del servidor. No hay actualmente modificación de relojes, animaciones o velocidad.
