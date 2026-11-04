# Vista general 0.12.1

Desde 0.13.0 también incluye **Caza y botín** para guardar la espera antes de atacar,
el radio calibrable y la recogida restante. Comparte sus valores con el panel principal;
consulta [las opciones y la validación pendiente del bonus](hunt-settings.md).
Desde 0.14.0 comparte también **Modo de ataque al mob**, con la opción experimental
de solicitar combate desde la posición actual sin ordenar acercamiento.

**Vista general** abre una ventana flotante oscura desde **Control** o **Mercenarios**.
Se inspira en la distribución de la imagen aportada por el usuario y muestra los
nueve puestos, con **Main (1)** siempre en la primera fila y **Mercenarios 2–9**
debajo. El Main conserva el número 1 aunque cambies su nombre en el perfil, lo
omitas del bot o le asignes otra prioridad. Su prioridad no se cambia automáticamente.

## Datos de cada fila

La pestaña **Resumen** muestra miembro, nombre del perfil, vida actual, presencia
en combate, uso por el bot, orden y acción inicial. Main aparece destacado y la
vida se muestra en rojo. La presencia distingue **Vivo**, **Caído**, **No presente**
y **Sin batalla**; **Usar bot** es la habilitación del perfil y no altera el equipo
que llevas dentro del juego.

**Órdenes de combate** muestra la acción del primer turno, la de los siguientes,
el objetivo de magia y la última orden de cada puesto. Los nombres los eliges en
el perfil; no son nombres de clase detectados automáticamente.

La vida procede de la unidad local correspondiente a ese puesto en la lectura de
combate. Se muestran los ceros de los miembros caídos. Los puestos ausentes y la
vista fuera del combate muestran **—**, evitando conservar datos como si siguieran
siendo actuales. La tabla de **Mercenarios** también incorpora la vida actual.

Los porcentajes de vida/maná y experiencia de la referencia todavía requieren
identificar sus valores máximos y lecturas. Esta versión utiliza los valores de
vida ya comprobados y no asigna el nombre de maná a un campo todavía sin validar.

## Controles

- **Perfil 1–3** y **Configurar** usan los mismos perfiles que el panel principal.
- **Ejecutar turnos del perfil** comparte la opción de Control; se marca antes de
  **Iniciar bot** para usar la secuencia de batalla.
- **Iniciar bot** y **Parar bot** utilizan el mismo trabajador y sus comprobaciones
  de PID, ventana, creación, compilación y estado del cliente.
- **Actualizar** consulta el equipo. **Copiar estado** copia la última ejecución
  de la instancia elegida y queda deshabilitado si el informe pertenece a otra.

El selector de perfil, su editor y la opción de turnos quedan bloqueados durante
la ejecución. La habilitación de Iniciar/Parar coincide con la del panel principal.
Cerrar esta vista conserva el panel y el bot; utiliza **Parar bot** para detenerlo.
Caminar en el juego pausa la búsqueda y la reanuda tras dos segundos quieto; una
batalla tiene prioridad sobre el movimiento. **Copiar estado** incluye desde 0.12.1
los estados de recuperación, las unidades, grupo/turno y tiempos de la batalla.
Solo se abre una vista general: el botón recupera la existente, o crea otra si la
cerraste. Cambiar de cliente o desconectar limpia la vida y los datos del anterior.

La vista se actualiza cada segundo mientras permanece abierta. Durante los turnos
automáticos consume las filas publicadas por el trabajador. No añade funciones
nativas, selecciona mercenarios ni interviene en el envío de Q. Se conservan los
tiempos de 0.11.1 con los que el usuario confirmó la recogida del NeoACA y el final
de la batalla en el primer turno.

La comprobación de Windows abre la ventana empaquetada, verifica los nueve puestos,
vida/ausencia, limpieza de datos, estados de botones y reapertura. No ejecuta el juego.
