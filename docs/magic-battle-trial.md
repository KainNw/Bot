# Selección nativa y prueba de magia 0.10.0

El básico nativo de 0.9 y la magia Q de 0.10 fueron comprobados visualmente por el
usuario. Esta guía conserva el procedimiento individual para seleccionar al miembro
y probar una acción. Desde 0.11, el [ciclo de turnos](mercenary-turns.md) también
puede ejecutar el perfil en orden si activas su opción antes de iniciar el bot.

El informe recibido de 0.10 en PID 21076 registró puesto 1, Q, acción 207 de la barra
`207/222/440/1014/1205`, estado 32 y excepción 0. El usuario confirmó que lanzó la
magia. Eso valida esa habilidad en esa sesión; todavía no prueba las otras teclas,
otros mercenarios ni la secuencia automática completa.

## Uso

1. Entra en combate con Auto Battle y caza nativa apagados. Pulsa **Parar bot**
   y espera a que termine.
2. Abre **Ver mercenarios**, pulsa **Actualizar** y elige el mercenario por puesto
   y tipo. Los nombres siguen procediendo del perfil.
3. Pulsa **Seleccionar en juego**. Ese botón cambia el mercenario activo y lee su
   barra de magia; no solicita un ataque.
4. En **Acción de la prueba**, elige **Magia Q**, **W**, **E**, **R** o **T** entre
   las entradas de la barra que se hayan leído. Para el básico, elige **Ataque básico**.
5. Elige un enemigo para una magia ofensiva, o **Tu equipo** para una magia que
   permita ese objetivo. Las habilidades que solo actúan sobre el propio lanzador
   requieren elegir ese mismo mercenario. Solo se ofrecen unidades vivas.
6. Cuando sea tu turno, pulsa **Probar acción (experimental)** una vez.
7. Comprueba el lanzamiento y usa **Copiar mercenarios** para revisar el resultado.

Seleccionar listas, actualizar y copiar no lanzan la magia. La prueba no usa teclas
globales ni mueve el foco a otra ventana. Si seleccionas otro mercenario directamente
en el juego, vuelve a actualizar antes de probar su magia. Los registros de miembros
todavía no se presentan como equivalentes comprobados a los números del teclado.

La restricción de una solicitud por mercenario y lectura de turno es compartida
entre básico y magia; seleccionar el mercenario no consume esa prueba. Un rechazo
nativo no provoca un básico alternativo ni reintentos. Después de un resultado incierto
hay que comprobar el juego y reconectar. El básico alternativo del perfil se aplica
solo en el ciclo automático de 0.11; la prueba individual no lo ejecuta.

## Resultados

| Estado | Significado |
| --- | --- |
| 31 | El cliente dejó seleccionado el mercenario pedido y se leyó la barra. |
| 32 | La función de magia aceptó la solicitud y se copiaron 33 bytes a la cola. |
| 33 | Cambió el mercenario seleccionado o su barra; hay que seleccionar/actualizar. |
| 34 | La función nativa rechazó la magia por sus condiciones actuales. |
| 35 | La habilidad usa una ruta especial no habilitada para esta prueba. |

Un estado 32 no prueba el impacto, curación ni recepción por el servidor.
`attack_confirmed` permanece en `false`. La disponibilidad final, coste, recarga,
condiciones y relación con el objetivo los comprueba la función del cliente.

## Ruta comprobada en el código capturado

Se utiliza el código del ZIP de combate de las 09:27:15, validado anteriormente.
`005A44AE` selecciona una unidad por el índice de la colección. Su llamada a
`004F49C5` reconstruye la interfaz mediante `004F428D` para ese miembro.

En `004F44FF` aparecen las teclas Q/W/E/R/T. El bucle recorre cinco entradas de
habilidad y añade al contador `gestor+25E8` solo las que resuelven una acción.
Guarda esas acciones, en el mismo orden de las teclas, en `gestor+25EC`.
Se lee esa barra ya construida; no se equipara el índice físico de habilidad con
una tecla cuando faltan entradas. La lectura exige que la unidad seleccionada y
la barra permanezcan estables durante la consulta.

`004F20B0` recibe, mediante `thiscall`, gestor, identificador del personaje,
miembro propio desde cero, índice gráfico del objetivo, argumento reservado cero
y acción de la barra. Su retorno limpia 20 bytes de argumentos. Resuelve habilidad
y nivel, comprueba la magia mediante `00432759`/`00432250` y construye `0F49` con
24 bytes y acción 4. Usa el generador nativo de identificación de acción.

Se comprueban las firmas del selector, las teclas, el inicio, la rama de envío y
el retorno de la función de magia contra la captura. Se vuelve a validar el
gestor, contexto, turno, personajes, miembros y unidad seleccionada en el hilo
del cliente antes de invocar esa función.

La entrada de acción debe ser de tipo `10` hexadecimal y corresponde a la posición
de Q/W/E/R/T leída. Las acciones especiales reconocidas por `005445C1` se rechazan
en esta prueba: la ruta observada puede sustituir al miembro elegido por el principal.
No se asigna una habilidad a otro mercenario para sortear esa condición.

La reserva por PID y cancelación se conservan. El protocolo helper/DLL pasa a 7,
408 bytes; las operaciones 0–6 mantienen su función y se añaden selección 7 y
magia 8. La función de magia se ejecuta bajo el bloqueo de la cola, con comprobación
de capacidad y aumento exacto de 33 bytes. El ejecutor de caza y sus tiempos
no cambian. La prueba con varios clientes sigue pendiente.

Las pruebas automatizadas cubren barras comprimidas, cambios de selección/barra,
objetivo propio, instancias y respuestas de otra magia, y ausencia de reintentos
o básico alternativo. Windows comprueba la cancelación de las dos operaciones
sobre una ventana propia; esas pruebas no ejecutan Atlantica.
