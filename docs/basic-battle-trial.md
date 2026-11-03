# Prueba individual de ataque básico 0.9.0

**Ver mercenarios** permite elegir un miembro propio y una unidad enemiga viva y
solicitar un único ataque básico, con Auto Battle apagado. El ciclo de caza sigue
sin ejecutar el plan del perfil. Las magias Q/W/E/R/T, el básico alternativo y X
todavía no se ejecutan. Falta comprobar esta primera solicitud en el cliente real.

## Uso

1. Conecta el panel 0.9 con la ventana elegida y mantén Auto Battle y caza nativa
   apagados. No minimices el juego.
2. Entra en combate manualmente o mediante la caza. Pulsa **Parar bot** y espera
   a que termine; la batalla puede continuar para la prueba.
3. Abre **Ver mercenarios** y pulsa **Actualizar** cuando sea el turno de tu grupo.
4. Elige el mercenario por el puesto y tipo leídos y un enemigo por su grupo y
   puesto. Los nombres vienen del perfil. La relación entre estos registros y las
   teclas 1–9 todavía no está comprobada; no se envían esas teclas.
5. Pulsa **Probar básico (experimental)** una vez y comprueba el golpe en el juego.
6. **Copiar mercenarios** incluye la lectura y el resultado de la prueba. El
   resultado también queda disponible en **Copiar prueba** del panel principal.

Actualizar, abrir el visor y copiar no ejecutan ataques. Después de la prueba
el botón queda deshabilitado hasta actualizar. Se conserva el resultado al
actualizar, y se impide otra solicitud del mismo mercenario para la misma lectura
de número y comienzo de turno, aunque se elija otro enemigo o se reabra el visor.
Un rechazo nativo sin envío permite actualizar y corregir el objetivo. Si el
resultado es incierto, hay que comprobar el juego y reconectar antes de continuar.

`status=26` significa que se copiaron 33 bytes a la cola de envío del cliente,
no que el servidor aceptó el golpe. `attack_confirmed` permanece en `false`.
Los estados 27–30 indican combate no listo, turno cambiado, unidad cambiada o
rechazo de la comprobación nativa, respectivamente. No hay reintentos automáticos.

## Evidencia de la captura

Se verificaron los SHA-256 de los 35 bloques de
`Atlantica-PID21076-combate-20261103-092715.zip`, panel 0.8.3, esquema 4,
946432 bytes. PID 21076, creación `134381859857067996`, Auto Battle y caza nativa
apagados, contexto A = 0 y B = −1. Los nueve miembros se leyeron sin error.
La tabla real del gestor es `042D8AA4`.

La captura contiene 13 métodos válidos de `cltBattleManagerClient`. Después empieza
la cadena UTF-16 `$leftturn`; sus primeras parejas de caracteres parecían
direcciones de código y provocaron cuatro bloques adicionales en 0.8.3. Se limita
esa tabla conocida a 13 entradas. El objeto de `owner+16358` empieza con cero en
esta muestra: es una colección de unidades, no una tabla virtual resuelta.

| Código | Uso observado |
| --- | --- |
| `004F5923` | `MouseOperation`; al soltar el clic llama a `004F2540`. |
| `004F2540` | Despacha la acción `1E` a `004F1CDF`, separada de magia y botín. |
| `004F1CDF` | Comprueba el básico y construye/envía `0F49`, carga de 24 bytes, acción 1. |
| `00431D81` | Comprueba miembro propio, enemigo vivo, estados, propiedades y protección de filas. |
| `005A2955` | Comprueba vida, grupo que tiene turno, estado del miembro y propiedad `8000`. |
| `005A439F` | Vincula unidad gráfica con personaje y miembro, y guarda sus punteros `21C`/`230`. |
| `005A4519` | Recorre hasta 100 unidades y compara personaje y miembro para resolver su índice. |
| `004FDC86` | Genera el dato opaco de identificación de acción desde `unidad+C` y su contador. |
| `004F102F` | Construye la carga nativa con acción, personaje/miembro propios y enemigo/miembro. |

La solicitud usa los identificadores de personaje de la ruta manual. La carga
no es la orden de caza `0AE2` ni el mensaje `0D80` de la ruta BF.

## Lectura y envío

La lectura exige el gestor conocido, contexto índice 0 y coincidencia entre
`gestor+25E0` y `owner+16358`. Lee seis participantes de 12 bytes desde `contexto+B4`,
sus grupos en `+11A` y hasta 100 indicadores/punteros desde `colección+D4`/`+138`.
Verifica las identidades completas contra los personajes del mundo y la colección
de información de miembros. Solo ofrece como objetivos miembros vivos de otro
grupo con identificadores de mob dentro del rango utilizado por la caza.

El grupo actual viene de `contexto+6C5C`, siguiendo `004FEBAF`. Se vinculan también
`+6C74` y `+6C60`, usados por la sincronización y el comienzo del turno. Se descarta
la lectura si cambian el contexto, turno, participantes o colección. Esto no
implica que todas las unidades del grupo puedan actuar: se comprueba otra vez
en el hilo del cliente antes de cada envío.

El puente vuelve a comprobar PID/creación, ventana/hilo, código cargado, gestor,
contexto, turno, identidades completas, alias de miembros, vida y estado de la
unidad. Ejecuta `005A2955` y `00431D81` antes de generar el dato de acción y construir
la carga mediante `004F102F`. Construye el mensaje mediante `0040C4E9` y lo envía
con el despachador verificado `0095EC3A`, bajo el bloqueo de la cola y comprobando
capacidad, cancelación y aumento exacto de 33 bytes.

Se reutiliza la construcción y envío de la rama manual, sin invocar su envoltorio
`004F1CDF`, que depende del mercenario seleccionado en la interfaz y del foco.
El miembro elegido viaja explícitamente en la carga. No se selecciona otro
mercenario en pantalla, se cambian estadísticas ni se activan flags de turno.
El generador nativo sí avanza su contador de acción como en el clic manual.

El protocolo helper/DLL es 6, con 376 bytes y operación 6. La reserva por PID
excluye la prueba si hay un ciclo u otro controlador en ese cliente. No se cambia
el foco ni se usa entrada global; la prueba real con varias ventanas sigue pendiente.

Las pruebas automatizadas cubren lectura, aliados y muertos excluidos, cambios de
turno, alias incorrectos, firmas distintas, instancia/turno/mercenario de la respuesta
y una sola invocación al puente. Las firmas se contrastaron con este ZIP. La prueba
aislada de Windows verifica el puente y la cancelación sobre una ventana propia;
no sustituye la comprobación del ataque en Atlantica. La caza conserva sus tiempos.
