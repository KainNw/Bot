# TBS: investigación de Scourge

0.29.0 añade una pestaña **TBS** y una captura de memoria por etapas. La primera
misión elegida por el usuario es **Scourge**, inicialmente con solo el Main.
Esta versión permite investigar sus estados; todavía no mueve ni ataca en TBS.
El nombre de la misión y cada etapa se guardan como indicaciones del usuario,
no como identificaciones automáticas de la memoria.

## Evidencia disponible

Se comprobaron los tamaños y SHA-256 de los 37 bloques de la captura
`combat-20261103-232004`. Su código cargado permite distinguir dos rutas:

| Ruta | Accesos observados |
| --- | --- |
| Combate normal, ya utilizado por el bot | Contexto `actor+318`, gestor `owner+091C`, colección `owner+16358`. |
| Familia BF, candidata para TBS | Contexto `actor+254`, objeto `owner+16360`, subobjeto de control situado **8 bytes después**. |

`008B0092` obtiene `owner+16360`, suma 8 y llama a `008BC9C3`.
`008B8A48` construye el subobjeto en `objeto+8`; `008BEF80` sitúa su colección en
`subobjeto+850`. La selección en `008BC8AD` consulta el contexto B del personaje
y compara el campo de fase `subobjeto+798` con 3. Esto demuestra una condición
del código, no que ese valor por sí solo confirme el turno del jugador en TBS.

La colección usa una base en `colección+0C`, capacidad en `+08` y registros de
`33B0` bytes. `0052892C` considera una entrada publicada cuando su entero
`unidad+2194` difiere de −1. `00528979` busca por los campos `2198` y `219C`;
`008B3BD3` relaciona nueve entradas de selección con ese último campo.
`005220D6` y `005220DE` leen los valores cortos de `unidad+21A4/+21A6`; las
comparaciones de `005227EF` los usan como posiciones. Su correspondencia con
las casillas visibles se contrastará moviendo el Main una casilla manualmente.

Las tablas construidas por el código son `04368DB0` para el objeto exterior,
`043691DC` para el subobjeto, `04368C9C` para la colección y `0436803C` para la
unidad del cliente. El lector comprueba estas tablas y siete firmas de código
antes de interpretar sus campos. Una tabla distinta se informa como desconocida.

La búsqueda ASCII/UTF-16 del texto `Scourge` no encontró coincidencias en los
92 bloques únicos de las capturas aportadas ni en el ejecutable en disco. El
ejecutable está protegido y faltan archivos/cadenas cargados durante esa misión;
esta ausencia no demuestra que el juego no tenga ese nombre. La cadena
`TBS_indonesia` en `042DA820` pertenece a nombres de mapa y tampoco identifica
por sí sola una misión activa. Recursos y etiquetas `NBattleField` son pistas,
no pruebas de equivalencia completa entre BF y TBS.

## Capturar desde el panel

1. Conecta el PID de la ventana que usará Scourge. Detén la caza, Auto Battle y
   los controles de Speed para observar los estados sin otras acciones automáticas.
2. En **TBS → Abrir captura TBS**, deja misión **Scourge** y formación **Solo Main**.
3. Selecciona **Mapa antes de entrar** y pulsa **Capturar etapa**.
4. Entra manualmente en Scourge y captura **TBS: al entrar en la misión**.
5. Selecciona el Main. Captura **Main seleccionado** y **antes de mover una casilla**;
   muévelo una casilla y captura **después de mover una casilla** cuando se detenga.
6. Si es posible, captura **mi turno**, **turno del enemigo**, antes/después de un
   básico y antes/después de una magia. En la nota indica la tecla y el resultado.
7. Guarda el ZIP. Se puede guardar con pocas etapas; no es necesario terminar
   la misión. Después se pueden añadir el resultado y el regreso al mapa.

El archivo incluye fechas UTC, PID y creación del proceso, contextos A/B,
selección, campos de unidades, posiciones candidatas y bloques fijos del código
con sus hashes. La posición del mapa se identifica por separado como `world_grid`.
Los campos cuya semántica aún no se ha probado conservan sus offsets en el nombre:
no se presentan como puntos de acción, turnos disponibles ni objetivos atacables.

La captura admite hasta 32 muestras y examina como máximo 512 entradas por muestra,
indicando truncamiento y lecturas incompletas. Revalida actor, identidad, contexto,
tablas, colección, selección y encabezados al finalizar. Un cambio durante la
lectura exige repetirla. No mezcla muestras de distintas instancias, aunque se
reutilice el PID. Los bloques exportables están limitados a páginas de la imagen;
no se exportan regiones arbitrarias del heap. Se conserva un ZIP existente.

Mientras la captura está abierta, se bloquean el cambio de cliente, los perfiles,
el inicio de la caza y la activación de Speed. Cerrar la captura libera esos
controles. No se modifican el ejecutor de combate normal, sus tiempos, el botín,
los perfiles, el puente nativo ni los controladores de velocidad.

## Pendiente antes de automatizar

Falta obtener una secuencia real de Scourge para confirmar el modo TBS, el Main
de la formación, coordenadas, límites y obstáculos, turno del jugador, puntos y
costes de acción, alcance, elegibilidad de objetivos, órdenes de movimiento,
ataque/magia y condiciones de éxito/fracaso. Las capturas actuales no acreditan
estos estados. El lector no ejecuta funciones candidatas ni habilita aún un bot
TBS. Las pruebas usan memoria simulada; no sustituyen la captura del juego.
