# Movimiento, combates recibidos y recuperación 0.12.1

El usuario comunicó tres incidencias al probar varias ventanas: parar al caminar
con un clic, falta de respuesta cuando un mob iniciaba combate durante lag y recogida
variable del NeoACA. Confirmó que se movía el personaje, y que no podía reproducir
fácilmente el caso con lag para obtener un registro. Las siguientes correcciones
tienen pruebas automatizadas; la causa exacta de aquel episodio sigue sin confirmar.

## Movimiento manual

Caminar en el mismo mapa pone la búsqueda en **Movimiento manual**, sin cerrar el
trabajador ni emitir un ataque nuevo. Cuando termina la ruta y la posición permanece
estable dos segundos, vuelve a buscar y toma esa posición como centro del radio.
Se conserva el historial de identidades de mobs ya combatidos.

Si un clic sustituye un destino nativo propio, el bot abandona la referencia anterior
sin cancelar ni sobrescribir la ruta manual. Lo mismo se aplica a una ruta por rejilla
con estado conocido. Un estado de ruta desconocido o una instancia/personaje cambiado
sigue deteniendo el control. Un cambio de mapa también lo detiene.

El movimiento del ratón por sí solo no se consulta: esta pausa se decide con la
posición y navegación del personaje del PID conectado. Una ventana que camina no
modifica la pausa ni el objetivo de otra instancia.

Una solicitud de ataque que ya estaba encolada puede terminar en batalla; se sigue
esperando su resultado sin repetirla ni retirar el envío. **Parar bot** conserva
la cancelación explícita y la parada de una persecución que aún se identifica como propia.

## Combate iniciado por un mob

Dos observaciones de combate tienen prioridad sobre pausa manual, persecución o ruta.
Se libera el recorrido anterior y se aplica el perfil si está marcado **Ejecutar turnos**,
aunque el bot no haya solicitado ese encuentro. Si el enemigo tiene la iniciativa,
espera el grupo propio; la primera magia sigue correspondiendo al primer turno propio
observado de una batalla que el bot vio empezar desde el mapa.
También conserva esa apertura si se inicia ya durante el turno inicial del enemigo:
haber observado el turno 0 permite reconocer el primer turno propio siguiente. Empezar
en una batalla avanzada sigue usando básicos hasta el próximo encuentro en el modo
de magia inicial.

El ejecutor ya no fija el contexto normal al índice cero. El código capturado
`00431769` resuelve `gestor + 8 + índice*4`, usando el índice de `actor+318`.
Se aplica ese mismo cálculo en lector y puente, limitado a 0–127, y se comprueban
puntero, gestor normal, colección, identidades y turno antes de llamar al cliente.
La ruta alternativa BF continúa sin habilitarse. No se dispone del registro del
fallo para afirmar que un índice distinto de cero fuese su causa.

### Registro recibido en 0.13.0 y corrección 0.13.1

El estado recibido de un combate iniciado por un mob registra `battle_entry.source=external`,
observación del turno inicial y primer turno propio a los 9,672 s. El grupo propio
era 1. También indica `combat.execute_orders=false`, cero ataques encolados y
recogida restante habilitada. En ese registro, la detección de la batalla y del
turno propio funcionó; los ataques estaban desactivados. `combat.enabled=true`
incluye el trabajador de recogida y no significa que estén habilitados los ataques.

**Ejecutar turnos según el perfil** debe marcarse antes de iniciar para usar básicos
y magias. La recogida puede estar activa con turnos manuales. Desde 0.13.1, el panel
y la vista general muestran el modo de combate; el diagnóstico también incluye
`execute_turns` en la raíz. Mientras el bot funciona, ese indicador refleja el modo
fijado al iniciar.

La parada posterior del registro fue diferente: resultado 33 durante una recogida
(operación 9), después de dos búsquedas encoladas y cambios observados. No demuestra
recepción de bonus. El 33 se produce antes de enviar esa orden. Desde 0.13.1 pausa
la recogida de esa batalla sin detener la caza ni reenviar la búsqueda. También
se aplica si falla la selección previa a una recogida. Al entrar en otro combate
puede volver a recoger. Las excepciones, resultados inciertos y cambios de selección
durante órdenes ofensivas conservan la política de parada anterior.

Las pruebas reproducen grupo propio 1, turno inicial del enemigo y primer turno
propio con recogida activa: con turnos manuales no emite ataques; con turnos
automáticos solicita Q del Main. Este registro no permite atribuir la incidencia
anterior con lag a la misma causa.

## Lecturas y estados transitorios

Antes de observar enemigos vivos, una colección vacía significa **cargando enemigos**;
se revisa a 100 ms. No se presenta como un grupo derrotado. Tras observar enemigos,
su ausencia pone en pausa las nuevas órdenes y espera el final real de la batalla.

Con ejecución de turnos, las lecturas fallidas consecutivas tienen tres segundos
para recuperarse. Los reintentos de preparación pueden ser a 100 ms y descartan la
lectura anterior; no se interpretan tres intentos rápidos como una caída inmediata.
La carga de datos que falla mientras todavía se observa combate se trata como
transitoria. Si termina la tolerancia, se detiene y conserva el motivo; un envío
pendiente exige revisar y reconectar.

Los resultados nativos **27, 28 y 29** retornan antes de construir/enviar la orden.
Permiten hasta tres comprobaciones por miembro/turno, con lectura nueva y separación
mínima de 250 ms. Al agotarse, cede al siguiente miembro. Un cambio real de turno
reinicia ese límite. El básico no elegible y la magia rechazada mantienen su política
de objetivo/alternativa. Los estados de envío aceptado, excepción, cola incierta o
selección cambiada no entran en esos reintentos. Se conserva el registro compartido
de una orden encolada por miembro/turno.

## NeoACA y diagnóstico

La recogida la realiza el cliente mediante el NeoACA. Esta versión elimina esperas
durante preparación y recuperación de Q, pero no modifica un temporizador interno
del robot ni su animación. No puede confirmar la recogida solo por detectar enemigos
muertos. El resultado variable con varias ventanas requiere contrastar esos tiempos
y lo observado en el juego.

**Copiar estado PID…** añade:

- `manual_control`: pausa, número de movimientos y criterio de reanudación.
- `battle_entry`: si se observó una batalla externa o vinculada a una solicitud.
- `last_read_error`: motivo, duración y si las lecturas se recuperaron.
- `combat.frame`: índice normal, grupo/turno y unidades acotadas con vida/estado.
- `combat.unready_attempts`: comprobaciones explícitas sin envío.
- `combat.timing_seconds`: primera lectura, turno propio, enemigos, selección,
  solicitud encolada, primera ausencia posterior de enemigos y primer mapa observado.

Son marcas del programa relativas a la primera lectura del combate, no una medición
del temporizador del NeoACA ni una prueba de victoria. La exportación conserva esos
campos sin los nombres personales del perfil.
