# Interfaz del panel 0.20.0

El panel usa un tema oscuro compartido con la vista general, con controles
agrupados y una barra de acciones que permanece visible en todas las pestañas.

## Main y ventana conectada

En **Control**, conecta la ventana del juego y completa **Nombre del Main
(alias de esta ventana)**. El nombre se introduce manualmente y aparece arriba,
en el título de Windows y en la vista general, junto al PID de la conexión.
Esto permite identificar el panel desde la barra de tareas o con Alt+Tab.

El alias se conserva para esa instancia mientras el panel esté abierto. Al
cambiar de cliente se muestra su propio alias; si el juego se reinicia, la nueva
instancia comienza sin nombre asignado. Puedes editar el alias durante la caza.

## Pestañas

- **Control:** ventana, PID, conexión, alias del Main, perfil y estado de la sesión.
- **Mercenarios:** los nueve puestos, Main (1) destacado, vida, presencia, prioridad
  y órdenes del perfil. La tabla tiene desplazamiento horizontal y vertical.
- **Caza y botín:** búsqueda y ataque a la izquierda; Speed y recogida a la
  derecha. **Guardar opciones del perfil** queda debajo.
- **Diagnóstico:** consultas, exportaciones y pruebas individuales. Los controles
  avanzados de caza nativa se despliegan desde esta pestaña.

Abajo se mantienen **Iniciar bot**, **Parar bot** y **Copiar estado**. El resumen
indica el estado del bot, combates observados y Speed informado por la ejecución.
La cabecera conserva el Main y el PID al cambiar de pestaña.

La disposición se ha comprobado también a 920 × 650. La comprobación de Windows
verifica que las acciones principales y el guardado sean accesibles, el cambio
de pestañas, los nueve puestos y el aislamiento del alias entre instancias.
