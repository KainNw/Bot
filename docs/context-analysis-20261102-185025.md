# Segunda captura de contexto y primera lectura de candidatos

Se recibió `Atlantica-contexto-20261102-185025.zip` (31 346 bytes), generado por el
panel 0.2.0. Se verificaron los tamaños y SHA-256 de sus siete bloques. Los cuatro
bloques ya recibidos son idénticos a los de la primera captura. El cliente mantiene
el hash admitido, PID 16244, contexto 2, Auto Battle apagado, B=16 y HUNT=1.
HUNT=1 es un indicador de la caza nativa; no demuestra ataque independiente. Puede
quedar almacenado con Auto Battle apagado.

El resumen de objetivos aportado por el usuario mostró mapa 52, posición (193, 335),
un candidato en el índice 6 con ID observado 12053 y posición (202, 267), sin errores
de lectura. Su distancia de rejilla es 9+68=77; no representa metros, alcance de
ataque ni una ruta transitable. El resumen no confirma su nombre o atacabilidad.

## Corrección del barrido

Las 445 entradas observadas eran punteros no nulos de la tabla, no 445 personajes
activos. El contador `changed_entries=344` incluía los rechazos `slot_mismatch`:
no había una segunda lectura que demostrase esos 344 cambios. La versión 0.2.1
separa esos rechazos de los cambios de puntero realmente observados.

`0044CFED` y `0044D020` obtienen la colección de índices en `[manager+0x24]`.
Los nuevos auxiliares identifican su estructura:

- `0044611C` admite índices 1–0x5BCB y comprueba un dword no nulo en
  `colección+(índice+1)*12`.
- `0044613D` valida una posición de enumeración contra el contador en
  `colección+0x44DA0` y lee el índice de `[colección+0x44D9C]+posición*4`.
- El constructor `0044617D` reserva el vector según la capacidad en `colección+0`,
  y la inserción `00446297` añade el índice al vector e incrementa ese contador.

El panel consulta ahora el vector activo y su pertenencia antes de leer personajes.
Mantiene el límite conservador 1–449 de la inspección de ataque; cuenta los índices
activos fuera de ese rango sin dereferenciar sus objetos. Los punteros fuera de la
lista activa se omiten y no se presentan como lecturas fallidas o cambios.
Se validan capacidad, contador, índices únicos, pertenencia y estabilidad de la
lista antes y después de la consulta. Se conserva la comprobación de identidad del
slot y no se elimina para aumentar artificialmente el número de candidatos.

## Identidad y comprobación del objetivo

`00434F64` copia tres dwords desde su argumento al objeto destino. En la caza nativa,
`0043BC26` recibe `objetivo+0x204`, copia esos 12 bytes y añade dos bytes de control.
El índice de tabla de `+0x200` no es por sí solo el contenido de ese mensaje.
El significado de los tres componentes y del relleno restante no se da por supuesto.

`00433A4A` recibe el índice del objetivo, obtiene sus getters de mapa/X/Y a través
de `[personaje+0x2C]`, construye un objeto temporal mediante `00431A86` y delega en
`00431AC0`. No basta con mirar un booleano del objetivo para reproducir esa
comprobación. Esos dos auxiliares faltan en las capturas recibidas; se añade el
contexto `00431000`–`00432FFF` a la siguiente exportación.

## Método virtual y preparación del envío

La resolución de `[vtable_del_objeto_global+0x64]` identificó `0095EC3A`.
El código está incluido en esta captura:

1. Llama a `0095E871` con el mensaje. Este auxiliar comprueba su opcode y modifica
   campos del cliente en `+0x16544` y `+0x16548`; no es una consulta sin efectos.
2. Exige un byte no nulo en `objeto_global+0x11D8E` y un puntero en `+0x1D70`.
3. Llama a `009A5550` con `[puntero+0x70]`, el mensaje y un auxiliar en
   `objeto_global+0x1FA5`.
4. Llama a `009A2C40` sobre `[puntero+0x6C]` y el mismo auxiliar.

Los dos últimos auxiliares no están en el archivo recibido. No se ha determinado
la propiedad del buffer, transformación del mensaje, sincronización ni el hilo que
debe ejecutar la acción. La siguiente captura añade una región fija de código en
`009A1000`–`009A5FFF`, junto con los bloques anteriores: hasta 76 KiB en total.
No incluye objetos del jugador, credenciales ni rutas de instalación.

La lectura de índices activos y los contadores corregidos están implementados.
La acción independiente de ataque sigue pendiente de los auxiliares indicados y
de su validación en ejecución. No se escriben flags ni instrucciones del cliente.
