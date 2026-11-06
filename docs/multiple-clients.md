# Seleccionar una de varias ventanas

El panel muestra ventanas de `Atlantica.exe` con título, PID y HWND. Puedes
elegir una en la lista y pulsar **Conectar**. Si los títulos son iguales, **Elegir
ventana** minimiza el panel durante tres segundos: activa el cliente con Alt+Tab
o desde su barra de título. Al volver, el panel muestra su PID; Conectar es explícito.
El campo PID manual sigue disponible. No se elige automáticamente el primero si
hay varios procesos.

La conexión queda vinculada al PID y a la fecha de creación del proceso. Si termina,
no se sustituye por otro cliente; incluso un PID reutilizado exige reconectar.
Cambiar la selección desconecta los controles. Un visor de objetivos abierto para
otro cliente no cambia de destino: exige abrir un nuevo visor. Los resúmenes y
exportaciones identifican el PID.

Cada panel controla una instancia. Para ejecutar tres bots simultáneos, abre tres
copias del panel y conecta cada una al PID de su juego. Activa **Ejecutar turnos del
perfil** en cada panel que deba jugar las batallas. Mover un personaje no pausa los
otros PIDs. En 0.12.1, caminar pone en pausa la búsqueda de esa instancia y la
reanuda cuando queda quieta. Las entradas en batalla interrumpen esa pausa.

En 0.4, mientras el trabajador esté activo, la selección queda bloqueada hasta que
Parar bot termine. También se vincula el hilo de la ventana y se comprueba en cada
solicitud. Un mutex por PID evita dos ciclos/controladores simultáneos del mismo
cliente; otro PID usa su propia reserva y cancelación.

## Marcador compartido de caza nativa

`HuntingMode.txt` pertenece a una carpeta de trabajo. Si dos clientes usan la misma
carpeta, crear o retirar ese archivo puede afectar a ambos. El panel y los comandos
de marcador en Windows vuelven a enumerar los procesos antes de cambiarlo y rechazan
el cambio si comparten carpeta o si no puede comprobarse la carpeta de alguno.
El panel mantiene las lecturas del cliente elegido, pero bloquea Iniciar/Parar nativos.

Esto no convierte el archivo en un control por PID: un cliente que se abra después
también puede leer un marcador ya existente. Las instalaciones con carpetas de
trabajo diferentes tienen marcadores distintos. No se borran archivos ni se cambia
Auto Battle en otras ventanas para resolver un conflicto.

## Prueba individual independiente

**Probar un ataque** no utiliza el marcador. La prueba experimental emite una sola
solicitud de ataque hacia el candidato cercano del PID conectado. Exige Auto Battle
y caza nativa apagados; no se los desactiva automáticamente.

El auxiliar comprueba que HWND pertenece a ese PID y que la instancia no cambió.
El hook se limita al hilo de esa ventana. No se usan teclas, clics, la ventana activa
ni búsquedas posteriores del primer proceso para dirigir la acción. Un mutex
individual por PID impide dos pruebas simultáneas del panel sobre el mismo cliente.

## Código 20 del puente

Desde **0.24.1**, minimizar la ventana del juego no provoca el código 20 ni
detiene el bot. Las órdenes se entregan al mismo hilo mediante su mensaje interno;
el puente no restaura la ventana ni cambia el foco. Minimizar el panel tampoco
cambia el cliente conectado ni envía una parada.

El auxiliar rechaza una ventana bloqueada por un diálogo, un HWND
que ya no existe, un proceso distinto o un hilo que cambió. Lo comprueba antes
de instalar el hook y enviar cualquier orden. La versión 0.15 muestra la causa
concreta; las versiones anteriores mostraban un aviso genérico sobre permisos
y resultado desconocido. Un auxiliar anterior que no devuelve la causa sigue
identificándose como rechazo previo al envío.

Cierra los diálogos del cliente. La ventana seleccionada puede quedar
detrás de otras ventanas o minimizada. Si su proceso o hilo
cambió, vuelve a elegirla y conectar. No se cambia el foco ni se restaura otra
ventana automáticamente. Un fallo de permisos en la instalación del hook es otro
error; el código 20 no lo demuestra.

El bot se detiene sin reintentar. Este rechazo por sí solo no exige reconexión.
Si existía una orden anterior pendiente o la parada de una persecución no puede
confirmarse, sigue exigiendo comprobar el juego y reconectar. El **estado nativo
20** de una respuesta válida es distinto: significa que el personaje ya tenía
un desplazamiento activo, y no se sustituye ese movimiento.

La restauración de la prueba de velocidad 0.16 es una excepción deliberada a la
comprobación de ventana deshabilitada: solo permite revertir sus dos
campos ya guardados, con las demás comprobaciones de instancia y propiedad.
La versión 0.24.1 admite el estado minimizado para todas las órdenes; los diálogos
bloqueantes siguen impidiendo ataques y movimiento.

El diagnóstico nativo añade `window_minimized` para indicar el estado de la ventana
al responder. La prueba propia de Windows comprueba un HWND minimizado real:
entrega el mensaje al hilo original, verifica las cancelaciones y comprueba que
la ventana sigue minimizada sin cambiar el foco. Se ejecuta sobre la ventana de
prueba del auxiliar; la compilación del juego se rechaza antes de leer sus direcciones.
Esto no prueba el comportamiento del motor gráfico del cliente de Atlantica ni
convierte un resultado incierto o una orden sin progreso en permiso para repetirla.

Los auxiliares antiguos pueden devolver todavía `reason: minimized`: hay que
actualizar el panel completo para quitar ese rechazo.

El usuario confirmó el inicio del ataque individual con Auto Battle apagado y una
sola ventana. El ciclo 0.4 añade Iniciar bot/Parar bot usando la misma ruta y sin
modificar marcadores. El usuario ya empezó las pruebas con varias ventanas y reportó
lag, recogida variable del NeoACA y pausas al caminar. La versión 0.12.1 mejora la
recuperación y el diagnóstico; no se dispone de una captura del fallo con lag para
confirmar su causa concreta. Una solicitud encolada no demuestra por sí sola que
empezó un combate. La persecución nativa y los turnos opcionales se explican en
[el ciclo](independent-hunt.md) y [los turnos](mercenary-turns.md).
