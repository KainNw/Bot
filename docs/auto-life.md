# Auto Life · MP

En **Caza y botín → Auto Life · MP**, activa la casilla, elige el umbral
(50 % inicialmente) y la tecla **F1–F9** donde tienes Potion Life. Guarda por
personaje junto al perfil. Inicia el bot para vigilar al Main y los mercenarios
vivos, aunque sus órdenes de combate estén deshabilitadas.

Solo consulta y usa la poción **fuera de combate**, como indicó el usuario. No
cambia la selección de mercenario: Potion Life recupera al equipo. El disparador
es MP **menor** al porcentaje elegido; exactamente 50 % no activa un umbral de 50.
Los puestos vacíos, caídos o sin un máximo de MP válido no disparan una tecla.

El acceso rápido se envía exclusivamente al HWND y al hilo del PID conectado,
con pulsación y liberación; no envía teclado global, restaura ventanas ni cambia
el foco. Se comprueba otra vez la identidad y que siga en el mapa antes de enviarlo.
El cliente puede ignorar mensajes de teclado si su ruta de entrada no los admite;
la recepción en una ventana de prueba no demuestra uso de la poción en Atlantica.

Tras enviarlo, el bot pausa nuevas búsquedas hasta observar recuperación de MP.
Si no aumenta en diez segundos reales, pausa **solo Auto Life** durante esa
ejecución y continúa el bot. No repite una solicitud cuyo efecto no se vio. Tras
una recuperación observada espera tres segundos antes de una nueva comprobación.
Revisa la poción, su tecla y disponibilidad; reiniciar el bot rearma Auto Life.
Un aumento de MP puede tener otras causas y no se etiqueta como consumo confirmado.

**Copiar estado PID… → auto_life** incluye la tecla, umbral, solicitudes, lecturas
de los nueve puestos y recuperaciones observadas. El diagnóstico de contexto también
incluye estos datos. Los perfiles anteriores cargan Auto Life desactivado.

## Lectura de memoria y validación

La captura de código del cliente muestra en `0043B624–0043B696` la comprobación
original de Life/Mana. Construye estadísticas en un buffer de `0x170` bytes mediante
`0044761A` y `00449AE8`, consulta el HP actual y divide el MP de `registro+50` por
el máximo en `estadísticas+88`. La interfaz de combate usa esas mismas magnitudes
en `0059E0DB–0059E0F8`. Se reutiliza el cálculo nativo sobre un buffer propio,
sin asignar un máximo arbitrario a un campo desconocido.

La operación 19 comprueba firmas de código, escena, personaje, datos de miembros,
ventana, hilo, PID y creación. Comprueba cancelación entre los nueve puestos.
Las pruebas usan memoria simulada, ventanas propias minimizadas y un proceso
ajeno al juego para verificar rechazo por compilación. No ejecutan Atlantica.
Queda pendiente comprobar el porcentaje y la recuperación real en el cliente Windows.
