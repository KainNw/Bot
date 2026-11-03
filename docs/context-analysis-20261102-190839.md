# Tercera captura y primera prueba individual

Entrada: `Atlantica-contexto-20261102-190839.zip`, 46 355 bytes, panel 0.2.1.
Se verificaron tamaños y SHA-256 de los nueve bloques. El usuario adjuntó otra copia
del mismo nombre y tamaño. El manifiesto mantiene el cliente admitido y PID 16244,
escena 2, Auto Battle apagado, B=50 y HUNT=0. Los siete bloques anteriores conservan
sus hashes. Los archivos se analizaron como datos y no se ejecutaron en la nube.

El segundo resumen de candidatos confirma una consulta sin lecturas fallidas ni
cambios de puntero detectados. La lista activa contiene tres índices, incluido el
personaje; el barrido inspecciona otros dos y conserva el candidato 6/12053.
Omite 443 punteros ajenos a la lista. La nueva posición (193,340) y el candidato
(202,267) producen distancia de rejilla 82. Esto valida la coherencia del lector en
esa consulta, no el alcance de ataque, identidad visible o comportamiento del servidor.

## Validación nativa

`00431A86` construye un objeto temporal con índice, tres shorts de mapa/X/Y,
un dword y un word adicionales. `00431AC0` valida pertenencia del índice, estado y
flags del objetivo. En escena 2 continúa comprobando:

- Que el objetivo sea diferente del personaje.
- La máscara 0x8000 del personaje, mediante `0043166E`.
- Igualdad del mapa del comando, personaje y objetivo.
- Relaciones y permisos mediante `004317C2`, que consulta flags, objetos asociados
  y campos del cliente; su resultado no se sustituye por el rango del ID.
- Un método virtual del objetivo en `vtable+0x74` y flags adicionales.

El auxiliar puede modificar un estado local y mostrar mensajes del cliente en
determinados rechazos. Se confirma que no es una función de solo lectura. La prueba
experimental llama al flujo nativo en el hilo de la ventana, después de los filtros;
el visor de candidatos sigue sin invocar esos métodos.

## Mensaje y cola

`009A5550` mantiene dos contadores por conexión y transforma el mensaje a un buffer
auxiliar del cliente. Inicializa el byte de cabecera que el constructor no escribía.
Por ello la prueba conserva este método del cliente y no implementa un emisor de
paquetes propio ni modifica sus contadores.

`009A2C40` copia el mensaje a un buffer circular bajo dos llamadas importadas que
encajan con entrada/salida de una sección crítica en `cola+0x20`. Se distinguen
capacidad (`+4`), índice de escritura (`+0xC`), bytes ocupados (`+0x10`), longitud
temporal (`+0x38`) y formato (`+0x44`). La prueba valida en ejecución las importaciones
contra Enter/LeaveCriticalSection o sus destinos Rtl, y admite solo formato 0.

El método exterior no propaga todos los fallos de la cola. La prueba comprueba
espacio y verifica un incremento de 25 bytes bajo el mismo bloqueo recursivo.
Ese resultado se informa como solicitud encolada; no confirma que el servidor haya
aceptado un combate. La copia síncrona permite descartar el buffer temporal tras
retornar. No se guarda ni comparte el estado de conexión entre procesos.

## Puente y límites de la prueba 0.3

Se implementó un auxiliar y DLL de 32 bits porque el panel Python es de 64 bits y
el cliente es x86. El auxiliar comprueba el SHA-256 del ejecutable, PID, fecha de
creación y propietario de HWND. Usa WH_GETMESSAGE únicamente en el hilo de esa
ventana y un mensaje registrado con un identificador aleatorio por solicitud.
No instala un hook global, envía entradas de ratón/teclado, cambia Auto Battle,
modifica el reloj ni escribe instrucciones del juego.

La DLL valida la imagen y varias instrucciones conocidas, escena, pertenencia,
identidad de tres dwords y estado local; exige caza nativa y Auto Battle apagados.
Compara distancia 3D al cuadrado con el umbral nativo de `045079EC`, con comprobaciones
de valores finitos. Si el candidato está lejos, retorna sin mover al personaje.
Para una prueba autorizada desde el botón llama `00433A4A`, `0043BC26`, `0040C4E9`
y `0043652D` en ese hilo. No crea un hilo remoto para ejecutar esas funciones.

Un mutex por PID impide superponer dos auxiliares sobre un mismo cliente. El
comando y respuesta identifican PID y objetivo; se rechazan cambios de instancia,
ventana e identidad. No hay reintentos automáticos. Tras encolar o recibir un
resultado incierto, hace falta comprobar el juego y reconectar antes de otra prueba.

El test de Windows crea una ventana dentro del propio auxiliar, comprueba la entrega
en su hilo y exige rechazo de compilación antes de leer direcciones del juego.
El ejecutable empaquetado repite esa prueba en su smoke test. Esos controles no
sustituyen la validación del ataque en el cliente real. El cierre manual comunicado
por el usuario sigue sin causa confirmada. El modo autónomo, movimiento hacia mobs
lejanos y turnos de mercenarios no se consideran completados por esta prueba.
