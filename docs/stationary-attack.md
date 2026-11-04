# Ataque desde la posición — 0.14.0

El usuario pidió elegir el mob más cercano e iniciar el encuentro desde la posición
del personaje, sin acercarse. **Atacar desde mi posición (experimental)** añade la
solicitud directa a un objetivo del radio, sin utilizar las órdenes de persecución.
El usuario confirmó el resultado en 0.14.0. Su registro mostró cuatro solicitudes
y cuatro combates, tres fuera del umbral de cercanía de 20 unidades al cuadrado,
con la misma posición 3D en los cuatro envíos. Eso describe esa sesión y compilación.

## Uso

1. Conecta con el PID elegido, deja Auto Battle apagado y pulsa **Parar bot** si está activo.
2. Abre **Caza y botín → Modo de ataque al mob** y elige **Atacar desde mi posición
   (experimental)**. La misma opción está en **Vista general**.
3. Ajusta el radio de selección (5–500 casillas) o usa **Calibrar radio**. Solo considera
   mobs cargados por el cliente. Guarda el perfil o pulsa **Iniciar bot**, que también guarda.
4. Para ejecutar Q y básicos dentro del encuentro, marca **Ejecutar turnos según el
   perfil** y comprueba **Combate automático**. El modo de inicio del encuentro y las
   órdenes de los mercenarios son configuraciones independientes.

Elige el candidato elegible de menor distancia 3D al personaje, después de excluir
identidades ya combatidas y aplicar el radio de rejilla. La espera configurable se
aplica antes de enviar. Relee identidad y posición al vencer la espera.

El radio selecciona objetivos; no establece una distancia máxima aceptada por el
servidor. La opción permite enviar la solicitud fuera del umbral habitual del cliente,
pero no cambia ese umbral, las estadísticas, la posición ni el código del juego.
Se conserva **Perseguir y atacar (nativo)** como modo predeterminado y como alternativa.

## Solicitud y observación

El trabajador usa exclusivamente la operación 10, con la identidad completa del mob,
área de selección y posición 3D actual. El puente comprueba nuevamente escena, mapa,
PID/creación, ventana/hilo, código, estados y elegibilidad nativa. Exige al personaje
quieto y compara la posición esperada antes de preparar y enviar la orden.

Emplea la carga de 16 bytes de `0043BC26`, mensaje `0x0AE2` con controles `1,0`,
constructor `0040C4E9` y envío `0043652D`, como el inicio de combate cercano. Copia
exactamente 25 bytes bajo el bloqueo de cola. **No emite `0x0AE5`, no llama a las
rutas `0043C9D3`/`0043B211` y no escribe el destino nativo ni las coordenadas.**

Los 23 bytes completos de `0043652D` se contrastaron con el código descifrado capturado:
solo comprueba disponibilidad mediante `004355EC` y deriva al envío global. Se mantiene
`00433A4A` como comprobación de elegibilidad; no se sustituye por un resultado forzado.
El umbral de alcance leído sigue apareciendo en el diagnóstico, sin bloquear la
selección directa por esa distancia. El IPC es versión 9, con 408 bytes.

Una respuesta de cola no demuestra aceptación del servidor. Se esperan dos
observaciones de combate. Desde 0.16.2, si no aparecen en 30 s, avisa de la demora
y sigue vigilando esa misma solicitud sin enviar otra ni exigir reconexión solo
por el tiempo transcurrido.
En 0.15.1, si el personaje se mueve después del envío mientras todavía se observa
mapa, conserva la conexión y espera ese combate pendiente sin repetir el ataque.
El movimiento no reinicia el plazo del aviso. Si llega el combate, lo procesa y
después retoma la búsqueda desde la nueva posición estable. La espera prolongada
conserva el envío y no permite seleccionar otro objetivo. **Parar bot** detiene
el trabajador y mantiene el aviso de resultado pendiente si aún no se observó
combate. No
cancela ni corrige movimientos manuales. El juego o el servidor podrían rechazar
la distancia o producir un movimiento; se debe observar el resultado real.

Una vez confirmado el combate, las órdenes del perfil y la recogida conservan su
funcionamiento. Los combates recibidos también tienen prioridad. Al regresar al
mapa espera estabilidad y puede elegir otro objetivo sin crear una persecución.
La pausa por caminar manualmente se conserva antes de enviar nuevas solicitudes.
Un estado transitorio del cliente durante el sondeo ya no elimina la conexión;
mantiene el PID y deja las acciones deshabilitadas hasta una lectura completa.
Un proceso terminado o reutilizado sigue exigiendo conectar de nuevo.

## Diagnóstico y pruebas

**Copiar estado PID…** y **Exportar diagnóstico** incluyen:

- `world_attack_mode=stationary` y `stationary_attack` con radio y límites de validación.
- `last_attack.operation=10`, identidad, distancia, umbral y posición solicitada.
- `battle_confirmed`, que requiere observaciones del juego.
- `stationary_movement_observed` si hubo desplazamiento tras el envío.

Las pruebas cubren objetivo más cercano fuera del alcance habitual, radio e historial,
cuenta interrumpible, posición cambiada, ausencia de duplicados, respuestas de otras
operaciones/posiciones, compatibilidad con Q y ausencia de llamadas de movimiento
desde el trabajador. El self-test nativo prueba la cancelación de la operación 10
sobre una ventana propia. La comprobación de Windows abre la interfaz empaquetada.
Estas pruebas no confirman la aceptación real del servidor ni una distancia efectiva.
