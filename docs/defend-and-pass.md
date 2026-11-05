# Main, defensa y pasar acciones — 0.24.0

En **Configurar mercenarios**, cada puesto puede elegir **Ataque básico**, magia
**Q/W/E/R/T**, **Defender (G)** o **Pasar acción (F)**. Defender y pasar se repiten
en los turnos correspondientes; no se convierten en ataques básicos al activar
la opción de magia del primer turno.

Para una magia inicial, **Después** elige la acción de los siguientes turnos:
básico, defender o pasar. Solo se aplica a las magias cuando está marcada
**Magia solo en primer turno**. Con esa casilla desmarcada se repite la acción
principal. La defensa y el pase no usan objetivo enemigo ni básico alternativo.

## Atacar con el Main y después pasar

1. Pulsa **Solo Main + pasar las acciones restantes** en el editor. Conserva
   la acción que tiene el Main, deshabilita las órdenes propias de los demás
   puestos y activa el pase de las acciones restantes.
2. Elige **Magia Q** para el Main si quieres una apertura con Q. Configura
   **Después** para los turnos posteriores y pulsa **Guardar perfil**.
3. Deja **Ejecutar turnos del perfil** activo e inicia el bot.

El bot espera cambios observables tras la orden del Main. Si quedan enemigos vivos,
pasa con la ruta individual F las acciones de los miembros disponibles, incluidos
los que no tienen una orden habilitada. También puede pasar al propio Main si aún
está disponible después de atacar. Se espera una lectura nueva tras cada selección
y cada orden encolada; no se envían todos los pases de golpe.

Esta opción recorre las acciones individuales F. **No invoca el botón global de
Skip Turn de la captura**: no se ha vinculado ese botón a una ruta nativa verificada.
El cambio al turno enemigo depende de que el juego procese los pases. Si el Main
derrota a todos los mobs, no envía defensas ni pases adicionales: deja paso a la
espera del NeoACA, al botín y al final del combate. No fuerza el cierre de la batalla.

Los ajustes se guardan en el perfil del personaje. Los perfiles de esquemas 1–7
conservan su comportamiento anterior: pase restante desactivado, básicos después
de la magia inicial. La carga no reescribe los archivos antiguos hasta guardar.

## Rutas del cliente y límites de la prueba

El análisis de código capturado identifica el despachador `004F2540`:

- Acción `0x20` llama a `004F1759`, que construye el tipo 5.
- Acción `0x29` llama a `004F1863`, que construye el tipo 8.
- Ambas rutinas usan el miembro seleccionado, conservan las restricciones
  nativas de sus funciones y envían `0xF49`, carga de 24 bytes, mensaje de 33 bytes.

La asociación con las órdenes G/F está pendiente de la prueba visual de esta
versión. Las operaciones 16/17 del puente comprueban instancia, ventana, hilo,
contexto, turno propio, miembro vivo seleccionado y presencia de enemigos vivos;
el objetivo de comprobación debe ser el mismo miembro. Verifican seis anclas de
código y usan las rutinas completas. No envían teclas globales ni cambian el foco
de otra ventana. El IPC pasa a la revisión 12 para que un hook anterior no pueda
interpretar estas operaciones.

51/52 indican defensa/pase encolados; 53/54 indican rechazo sin envío. Una respuesta
de cola no confirma la postura ni el cambio de turno: `stance_confirmed` queda
falso. El motor observa estado, animación, recursos o turno antes de seguir. Si no
hay progreso en 12 s, se detiene sin repetir la orden. Los estados previos al envío
27–29 permiten como máximo tres comprobaciones nuevas, separadas por 250 ms.
Un rechazo de defensa o pase nunca provoca un básico alternativo.

Cada pase tiene su propio registro por miembro y turno: permite pasar después del
ataque del Main, pero impide duplicarlo o volver a atacar después de un pase al
reiniciar el trabajador dentro de la misma conexión. Los turnos manuales no usan
el pase automático. En **Ver mercenarios** se pueden probar G/F con el bot parado,
tras seleccionar el miembro en el cliente y actualizar la lectura.

Para actualizar, cierra el panel anterior y reinicia el cliente una vez. Las pruebas
de planificación, rechazo, cambio de turno, victoria y guardado usan datos
simulados; la comprobación visual debe hacerse con el cliente de Windows.
