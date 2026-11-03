# Seleccionar una de varias ventanas

El panel 0.3 muestra ventanas de `Atlantica.exe` con título, PID y HWND. Puedes
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

La prueba requiere validación en el juego real. Una solicitud encolada no demuestra
que empezó un combate. No mueve al personaje ni juega turnos; los controles normales
de las otras ventanas permanecen bajo control del usuario.
