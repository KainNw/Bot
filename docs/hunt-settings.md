# Caza y botín — 0.13.0

La pestaña **Caza y botín** está en el panel y en **Vista general**. Comparte los
valores de la misma conexión. Guarda las opciones en el perfil elegido (1–3),
junto con sus mercenarios y orden. Iniciar también guarda los valores válidos.
Durante la ejecución quedan fijos; para cambiarlos pulsa **Parar bot**.

## Espera antes del encuentro

Elige 0, 1, 3 o escribe un número entre 0 y 60 segundos; admite decimales con punto
o coma. Es una espera adicional antes de iniciar la persecución/ataque al mob del
mapa. No se añade a las actualizaciones de una persecución ni a las órdenes de
mercenarios; Q conserva los tiempos de 0.11.1.

La cuenta no bloquea el trabajador. Relee posición, escena e identidad del mob.
Una desaparición, un movimiento manual, un combate o una parada cancelan la cuenta.
Si cambia de puesto conservando su identidad, utiliza el puesto actualizado.
La estabilidad del mapa y las comprobaciones nativas siguen siendo necesarias con 0 s.

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

1. Espera que no haya enemigos vivos y deja 1 s para la recogida del NeoACA.
2. En el turno propio y la fase normal, elige un miembro presente y habilitado,
   en el orden del perfil, y un enemigo derrotado.
3. Selecciona ese miembro y vuelve a leer el combate. Solicita la búsqueda nativa
   solo si el cliente confirma su disponibilidad y la elegibilidad del cadáver.
4. No repite una búsqueda encolada sobre el mismo cadáver, aunque cambie de miembro,
   turno o se reinicie el trabajador con el mismo registro de sesión.

Puede usarse con turnos manuales: desmarca **Ejecutar turnos** y deja habilitada
la recogida. Solo los miembros presentes y habilitados pueden recibirla.
No envía X global ni cambia el foco de otras ventanas. Cada solicitud conserva
PID, fecha de creación, ventana, contexto, turno y las identidades elegidas.

La orden de búsqueda está identificada en el código del cliente; todavía **no se
ha observado una recogida de bonus con esta versión**. Tampoco se ha identificado
una señal específica de aparición del bonus. Busca botín restante sobre cadáveres
elegibles, por lo que también puede recoger botín normal pendiente. No modifica
el temporizador del NeoACA ni la probabilidad del bonus.

El estado distingue solicitudes de búsqueda encoladas de cambios observados; ni
una cola ni una animación demuestran que se recibió un objeto. Si no observa
progreso tras una orden en 12 s, se detiene sin repetirla. Para validar, prueba
cuando aparezca el bonus y comprueba el inventario. Si falla, conserva **Copiar
estado PID…** y **Exportar combate** antes de parar.

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

IPC versión 8, estructura de 408 bytes, operación 9; no cambia las operaciones
de ataque, magia o persecución existentes. Se prueban persistencia/migración,
límites y calibración del radio, cuenta interrumpible, guardas de cadáveres,
rechazos, registro contra duplicados y respuestas ligadas al PID/turno. El workflow
de Windows compila x86 y comprueba cancelación y arranque de la interfaz empaquetada;
esas pruebas no sustituyen la validación en el servidor del usuario.
