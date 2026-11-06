# Primera secuencia de Scourge: unidades, posición y acciones

Archivo: `Atlantica-PID14276-TBS-20261106-105227.zip`, panel 0.29.0.
SHA-256 del ZIP: `0afed610d6dcf9d056beb08475bab7e36fc24a5da05f11904b5029111bb1d4db`.
Se comprobaron CRC, nombres de archivo permitidos, los once tamaños y hashes de
los bloques y las firmas de acceso. No se ejecutó código del archivo ni del juego.

Contiene diez muestras de la misma instancia: PID 14276, creación
`134384488154109918`. El usuario etiqueta la misión como Scourge y la formación
como Solo Main. La captura anterior de la interfaz muestra la ruta
**TBS → Three Kingdoms → Scourge**.

## Hechos observados

Las dos primeras muestras, incluso la etiquetada `entered`, siguen en contextos
A/B = `−1/−1`. Desde `before_move`, A = −1 y B = 4416. Esto vincula la familia BF
con esta sesión TBS real. **4416 no se interpreta como identificador fijo de
Scourge ni como índice del gestor del combate normal.**

La colección tiene capacidad 200, sin truncamiento ni errores. Las tres tablas
de objeto/subobjeto/colección coinciden con el código analizado. El Main es la
entrada 0: identidad local coincidente, miembro 0 y primer puesto de la tabla de
formación apuntando a esa entrada. Puede identificarse aunque la selección activa
sea −1, como ocurre después de atacar.

| Etapa | Posición interna del Main | Estado `21A8` | Unidades publicadas |
| --- | --- | --- | --- |
| Antes de mover | 38, 88 | 4 | 1 |
| Después de mover | 38, 84 | 1 | 2 |
| Segundo «antes de básico» | 42, 84 | 1 | 7 |
| Después de básico | 42, 84 | 3 | 7 |
| Antes de magia | 44, 86 | 1 | 8 |
| Después de magia | 44, 86 | 4 | 4 |
| Etapa «mi turno» | 44, 86 | 0 | 4 |

La posición del mapa exterior permanece en `[323,183,258]`. Por tanto no debe
usarse como posición del Main dentro del tablero TBS. La equivalencia exacta
entre el desplazamiento interno de cuatro unidades y las casillas visibles queda
pendiente de confirmación del usuario; no se presupone que haya movido una sola.

Después del básico, las entradas 1–3 tienen vida 0 y bandera `2AC8=1`; posteriormente
se retiran. Es diferente de una unidad viva cuyo estado de acción bloquea una orden.
Los valores actuales vienen de `unidad+1FA8 → miembro+4C/+50`, coherentes con los
getters de vida/maná; los máximos almacenados están en `unidad+2038/+2040`.
Las variaciones entre capturas no se atribuyen automáticamente a un coste fijo:
pueden haber ocurrido otras acciones entre ellas.

## Estados y turno

`00522424` permite el estado 0 o 1 para el básico. `CanMove` en `0052659B` rechaza
1, 3 y 4. Los estados observados 1 tras moverse y 3 tras atacar encajan con esas
condiciones. El estado 2 permite movimiento por esa comprobación y bloquea el
básico; no hay una muestra de estado 2 en este archivo. Son comprobaciones
parciales: no sustituyen vida, turno, alcance, terreno y demás condiciones nativas.

La fase general `common+798` vale 3 en todas las muestras TBS, incluyendo estados
de acción diferentes. No identifica por sí sola el turno del jugador.
La rutina `008BCD1E`, etiquetada `cltBattleFieldRoomInfoClient::OperateTurnInfo`,
actualiza el bando activo en `common+3B9`, el contador de 16 bits en `+3C0` y el
inicio temporal en `+3BC`. `00522237` compara `unidad+21A0` con ese bando activo.
0.29 no leía estos campos: aún falta contrastarlos en una transición de turnos.
0.30 los incluye y mantiene separadas fase general, estado de unidad y bando activo.

No se considera atacable a toda unidad de un bando distinto: hay verificaciones
adicionales de objetivos. El visor distingue Main, mismo bando y otros bandos.

## Casillas verdes y rutas

El usuario confirma con una imagen que la zona verde marca destinos de movimiento.
`CanMove` se identifica por su etiqueta en `00526532`. Comprueba estado, alcance
(`00525785`), ocupación (`00529D5A`) y ruta (`CanAStar`, `005251F0`).
El alcance compara distancia Manhattan con un método virtual de la unidad,
cuya implementación es `008A926E`; depende de datos de personaje y bonificaciones,
por lo que no debe sustituirse por un radio arbitrario. La ruta A* usa funciones
en `00914602/009147E1`; otras comprobaciones consultan terreno en `00A27663`.

`colección+10` enlaza el terreno. Su descriptor contiene las capas `+04/+08`, tabla
de filas `+18`, ancho `+1C` y alto `+20`, con registros de ocho bytes. Se comprueban
límites, vínculo con la sala y coherencia antes de exportar una ventana local de
como máximo 17×17 registros. **Esos registros no se presentan como casillas verdes
confirmadas:** faltan las condiciones completas de movimiento y ruta.

## Cambio de 0.30

La captura muestra una tabla de unidades con Main, coordenadas internas, HP/MP y
estado parcial. Añade el control de turno y terreno cercano, junto con tres regiones
fijas de código correspondientes a las dependencias encontradas. Un seguimiento
de doce segundos registra estados sin capturar terreno en cada muestra y sin
enviar entradas al juego. Se cancela al cerrar, guardar, perder la conexión o llegar
al límite de muestras; los cambios de escena transitorios se omiten y se contabilizan.

La siguiente prueba es registrar ese seguimiento justo antes de pasar al turno
enemigo y guardar el ZIP. Para el terreno, conviene además una captura manual con
las casillas verdes visibles. Los automatismos de TBS siguen sin habilitarse.
