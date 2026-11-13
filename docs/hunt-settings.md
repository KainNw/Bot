# Caza y botín — 0.30.1

La pestaña **Caza y botín** está en el panel y en **Vista general**. Comparte los
valores de la misma conexión. Guarda las opciones en el perfil elegido (1–3),
junto con sus mercenarios y orden. Iniciar también guarda los valores válidos.
Durante la ejecución quedan fijos; para cambiarlos pulsa **Parar bot**.

Desde 0.14.0, **Modo de ataque al mob** permite elegir:

- **Perseguir y atacar (nativo)**: comportamiento habitual, con desplazamiento del cliente.
- **Atacar desde mi posición (experimental)**: selecciona el más cercano por distancia
  3D dentro del radio y solicita combate sin enviar acercamiento, aunque esté fuera
  del umbral habitual. La aceptación del servidor sigue pendiente de prueba.
- **Atacar solo a mobs en alcance**: solicita ataques dentro del umbral nativo y espera
  si no hay candidatos disponibles.

Se conserva el modo nativo al cargar perfiles anteriores. El modo nuevo se guarda
con el perfil. Consulta [su uso y límites](stationary-attack.md).

## Espera antes del encuentro

Elige 0, 1, 3 o escribe un número entre 0 y 60 segundos; admite decimales con punto
o coma. Es una espera adicional antes de iniciar la persecución/ataque al mob del
mapa. No se añade a las actualizaciones de una persecución ni a las órdenes de
mercenarios; Q conserva los tiempos de 0.11.1.

La cuenta no bloquea el trabajador. Relee posición, escena e identidad del mob.
Una desaparición, un movimiento manual, un combate o una parada cancelan la cuenta.
Si cambia de puesto conservando su identidad, utiliza el puesto actualizado.
La estabilidad del mapa y las comprobaciones nativas siguen siendo necesarias con 0 s.

### Ataque inmediato (con 0 s)

Desde **0.30.1** hay una casilla en el panel y en **Vista general**, compartida
entre ambas ventanas y guardada por personaje y perfil. Comienza desmarcada,
también al cargar perfiles anteriores. Para usarla, para el bot, configura
**Espera antes de atacar = 0** y marca **Ataque inmediato (con 0 s)**.

- Al iniciar o volver del combate exige dos lecturas consecutivas de una posición
  estable, sin añadir la pausa fija de 2 segundos del ciclo anterior.
- Consulta el mapa, los candidatos y el alcance durante una persecución cada
  50 ms como mínimo, en vez de los 100–500 ms del ciclo anterior. El trabajo de
  lectura y del puente se añade a ese intervalo; no es una garantía de latencia.
- Al entrar en el alcance nativo solicita el ataque sin esperar el plazo de
  2 segundos que se usa para actualizar el destino de persecución. Mantiene
  ese límite para las actualizaciones de movimiento si el mob sigue lejos.
- Omite la pausa de búsqueda de 1,5 segundos posterior a una respuesta del
  puente. Si hubo envío, sigue bloqueando nuevos ataques hasta confirmar el
  combate; los rechazos conservan la exclusión temporal del objetivo.
- No añade una cuenta de espera ni activa Auto Battle. Mantiene identidad,
  alcance, límites, cancelación y bloqueo de nuevos ataques mientras se espera
  confirmar un envío. El movimiento manual conserva sus 2 segundos de pausa.

Si la desmarcas, vuelve al ritmo anterior. Si la espera es mayor que 0,
la casilla queda guardada pero no aplica estas reducciones: se respeta el tiempo
configurado. Ninguna de las dos ventanas permite cambiarla con el bot ejecutándose.

**Copiar estado** incluye `attack_delay.instant_attack_enabled` y
`instant_attack_active`. `last_request_timing` separa
`panel_before_bridge_ms` (lectura, selección y publicación de estado de la
iteración que envía la solicitud) de `bridge_roundtrip_ms` (llamada al puente y
registro de su resultado). La espera previa entre iteraciones no forma parte
de estos dos tiempos. La cola aceptada y el tiempo del puente no demuestran
un ataque aceptado por el servidor; `seconds_to_observed_battle` mide aparte
hasta observar la entrada en combate.

La ruta sigue reutilizando las órdenes de Auto Battle descritas en
[ataque nativo](native-attack.md). No se ha modificado el mensaje ni el puente
nativo para obtener estas reducciones. La mejora corresponde a las pausas del
panel; su efecto real en el cliente de Windows requiere prueba en el juego.

## Radio y calibración

El radio admite 5–500 casillas, con 60 por defecto, medidas como `|ΔX| + |ΔY|`.
**Calibrar radio** lee los mobs cargados por el cliente. Selecciona uno y pulsa
**Incluir mob seleccionado**; relee su identidad y posición antes de proponer la
distancia más dos casillas de margen, limitada al máximo de 500. Después guarda
las opciones o inicia el bot. Calibrar no envía ataques ni movimientos.

La medida parte de la posición al iniciar; el movimiento manual vuelve a centrarla
cuando el personaje queda quieto. El radio amplía la selección y la persecución;
el cliente mantiene el alcance real del golpe. No descubre entidades que el juego
no haya cargado, no atraviesa obstáculos y conserva el límite temporal de persecución.

## Bonus y botín restante: experimental

El usuario indica que el bonus aparece dentro de la batalla después de eliminar
a todos los mobs, cada ciertos minutos, y se recoge con X. La opción comienza
desactivada para los perfiles anteriores. Al habilitarla:

1. Espera que no haya enemigos vivos. **Recogida inmediata (sin espera)** viene
   activada y omite la espera fija del NeoACA, incluidos perfiles anteriores.
   Si la desmarcas, se aplica la **Espera del NeoACA** guardada: de 0 a 5 s,
   con decimales. Su valor anterior se conserva aunque quede inactivo.
   El ajuste no modifica el temporizador del robot ni retrasa la magia inicial.
2. En el turno propio y la fase normal, elige un miembro presente y habilitado,
   con la señal de disponibilidad del cliente, y un enemigo derrotado. En modo
   inmediato aprovecha el miembro seleccionado si está habilitado y disponible;
   después conserva el orden del perfil entre los demás. Las órdenes de ataque
   y magia conservan su prioridad habitual.
3. Selecciona ese miembro y vuelve a leer el combate. Solicita la búsqueda nativa
   solo si el cliente confirma su disponibilidad y la elegibilidad del cadáver.
4. No repite una búsqueda encolada sobre el mismo cadáver, aunque cambie de miembro,
   turno o se reinicie el trabajador con el mismo registro de sesión.

Puede usarse con turnos manuales: desmarca **Ejecutar turnos** y deja habilitada
la recogida. Solo los miembros presentes y habilitados pueden recibirla. Desde
0.22.0, omitir un miembro por un ataque o una magia rechazados no lo excluye de
la recogida: el cliente vuelve a comprobar la elegibilidad propia de la búsqueda.
Los límites de tres comprobaciones sin envío por miembro/turno son independientes
para combate y recogida. Las órdenes ya encoladas no se vuelven a enviar.
Desde 0.27.0 omite de entrada los miembros sin el bit nativo de disponibilidad
`0x8000`, evitando solicitudes condenadas a ser rechazadas. Si la búsqueda devuelve
un rechazo definitivo sin envío (37), puede consultar el siguiente cadáver con una
lectura fresca dentro del mismo ciclo; mantiene el máximo de dos solicitudes.
Una solicitud encolada o incierta corta ese avance.

La observación durante la recogida inmediata y las acciones pendientes revisa cada
50 ms, más el tiempo que tarden las lecturas. Si desaparece el cadáver, cambia su
estado o se observa el ciclo ocupado→disponible del recolector, continúa sin los 200–500 ms adicionales
que antes se añadían. Una unidad aún ocupada o una orden sin progreso siguen esperando.
La aceptación del servidor y la duración real de la animación siguen dependiendo
del cliente; no se prometen cero milisegundos ni recepción de inventario.
No envía X global ni cambia el foco de otras ventanas. Cada solicitud conserva
PID, fecha de creación, ventana, contexto, turno y las identidades elegidas.

La orden de búsqueda está identificada en el código del cliente. El usuario
informó de recogidas de bonus EXP, pero armas/equipamiento y libros de EXP siguen
pendientes de una captura que permita comprobar el fallo. Tampoco se ha identificado
una señal específica de aparición o de tipo del bonus. Busca botín restante sobre cadáveres
elegibles, por lo que también puede recoger botín normal pendiente. No modifica
el temporizador del NeoACA ni la probabilidad del bonus.

El estado distingue solicitudes de búsqueda encoladas de cambios observados; ni
una cola ni una animación demuestran que se recibió un objeto. Si no observa
progreso tras una orden en 12 s, se detiene sin repetirla. Para validar, prueba
cuando aparezca el bonus y comprueba el inventario. Si falla, conserva **Copiar
estado PID…** y **Exportar combate** antes de parar.

`combat.loot` incluye el número de cuerpos conocidos, el motivo de espera
(`neo_grace`, `enemy_turn`, `no_known_corpses`, `no_eligible_collector`,
`pending_result` o `all_corpses_requested`) y las comprobaciones sin envío.
También indica `instant`, la espera efectiva y el tiempo observado desde los
primeros cadáveres hasta la primera búsqueda encolada.
`combat.pending` indica el tiempo pendiente y si se observó animación o cambio
de estado; ninguno de esos datos confirma la recepción en el inventario.
Para comparar un bonus de armas/equipamiento o libros que no se recoge, utiliza
[Capturar bonus (memoria)](bonus-memory.md) antes y después de una X manual.

## Evidencia nativa y pruebas

Análisis estático del código descifrado capturado en
`Atlantica-PID21076-combate-20261103-092715.zip`, compilación SHA-256 admitida:

- `004F2540`: el despachador deriva la acción `0x2A` a `004F1B21`.
- `00433701`: elegibilidad de búsqueda; exige fuente viva, objetivo muerto,
  grupo enemigo y comprueba restricciones/propiedades del cliente.
- `004F1B21`: toma la fuente seleccionada y el índice gráfico del objetivo;
  construye acción 3 con `004F102F`, mensaje `0xF49`, carga de 24 bytes y envío
  de 33 bytes. Conserva sus comprobaciones y efecto local `0059D21D`.
- El puente verifica anclas, todas las unidades publicadas sin enemigos vivos,
  selección, turno y elegibilidad antes de llamar al envoltorio completo.
  Resultado 36: aumentó la cola en 33 bytes. Resultado 37: no hubo envío.
  Una excepción o un resultado incierto detiene el ciclo.

Desde 0.13.1, un cambio de selección sin envío (33) durante la recogida o su selección
previa pausa solo la recogida restante hasta el siguiente combate. No repite esa
orden ni detiene la caza. El modo **Combate automático / Turnos manuales** se muestra
por separado: activar recogida no activa básicos ni magias.

La recogida conserva la operación 9 y el IPC 14 de 700 bytes de 0.26.0; esta mejora
no modifica el puente nativo ni las operaciones de ataque, magia o persecución.
Se prueban persistencia/migración,
límites y calibración del radio, cuenta interrumpible, guardas de cadáveres,
rechazos, registro contra duplicados y respuestas ligadas al PID/turno. El workflow
de Windows compila x86 y comprueba cancelación y arranque de la interfaz empaquetada;
esas pruebas no sustituyen la validación en el servidor del usuario.
