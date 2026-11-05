# Investigación de la velocidad de combate

La revisión usa los 35 bloques de memoria de la captura
`Atlantica-PID21076-combate-20261103-092715.zip`, de la compilación admitida cuyo
SHA-256 termina en `3FE04E6`. Sus 946 432 bytes incluyen código del combate normal
cargado en memoria. El ejecutable en disco está protegido y no sustituye las
regiones descifradas que faltan. No se ejecutó el archivo aportado.

El usuario confirma que su cliente no muestra un ajuste de velocidad de combate
en las opciones. Eso no determina si existe un control interno utilizable.

## Ruta localizada

| Instrucciones capturadas | Observación |
| --- | --- |
| `004F53E9`–`004F541F` | Lee el entero global `0822F524`, suma la constante de 64 bits en `042C11E8`, redondea a float, divide por el entero `08230E14` y guarda el resultado en el gestor normal `+265C`. También lo pasa a `00A14AFD` mediante el objeto obtenido de `00A0481E` y su campo `+18`. |
| `0059C225`–`0059C359` | Usa el tiempo transcurrido desde el inicio de la animación. Divide una constante por el valor de `gestor+265C`, convierte el intervalo y calcula con él el avance de fotogramas, antes de llamar a `00427EAC`. |
| `005A0D74`–`005A0EB2` | Limita el incremento de tiempo usado por el desplazamiento de la unidad y multiplica su factor por el mismo `gestor+265C`. Es movimiento dentro del combate, distinto de la búsqueda de mobs en el mapa. |
| `0059C236`–`0059C314` y `005A0DA8`–`005A0E75` | Comparan la escala y el resultado de `00A14B10` con la constante `042C11D4`. Una rama restablece el campo con `042F320C`, llama a `00A14AFD` y construye un mensaje `1247`. Los valores concretos y la finalidad de esa rama siguen sin validar. |
| `0040C4E9`–`0040C548` | La función usada para construir ese mensaje rellena cabecera y copia datos. Esta llamada por sí sola no demuestra un envío al servidor. |
| `008BCA82`–`008BCAA6` | Otra ruta de batalla calcula y pasa una escala con los mismos dos enteros globales. No demuestra que esa ruta sea la que usa el combate normal del usuario. |

Esto identifica una escala consumida por rutinas de presentación y movimiento.
Todavía no identifica un comando de chat, un selector disponible, límites
admisibles ni un control exclusivamente visual. No demuestra que acelerar esa
escala acorte el turno que autoriza el servidor. La espera configurable del bot
y la espera del servidor son mecanismos distintos de este valor.

## Datos que faltan y captura en 0.15.1

La captura anterior no contiene `00A14AFD`, `00A14B10`, `00A0481E`, `00A047F2` ni
`00554C1B`, ni las páginas de constantes necesarias para interpretar las
comparaciones. No se asignan valores como «1x» o «2x» a constantes sin leerlas.
Tampoco se ha seguido aún la restauración al mapa ni el alcance real del objeto
que recibe la escala.

**Exportar combate** añade seis regiones fijas, 32 KiB en total: `00A04000/2000`,
`00A14000/2000`, `00554000/1000`, `042C1000/1000`, `042C6000/1000` y
`042F3000/1000`. Las tres últimas se etiquetan como constantes de solo lectura.
Si una región adicional no está disponible, queda anotada sin impedir la
exportación de los datos de combate anteriores.

El manifiesto incluye `combat.speed_diagnostic`: lecturas antes y después de los
dos enteros globales, del índice de contexto gráfico, de las constantes referidas
y del campo candidato del gestor validado. Conserva los bytes originales; los
valores no finitos o inaccesibles quedan sin valor numérico. No sigue punteros a
otros objetos gráficos ni ejecuta getters o setters. Verifica la misma instancia
y el mismo contexto al completar la exportación.

Para continuar, abre **0.15.1**, detén el bot, deja Auto Battle apagado, entra
manualmente en combate y pulsa **Exportar combate**. Adjunta el ZIP resultante.
Primero hay que resolver los auxiliares y límites; después podrá determinarse
si existe una prueba acotada que restaure el estado al salir del combate o parar.
Esta versión solo recoge evidencia; no activa velocidad adicional ni cambia
relojes, turnos, solicitudes de ataque o controles de comprobación del cliente.

## Captura 232004: valores y accesos confirmados

Se verificaron los 37 bloques, sus SHA-256 y el CRC del ZIP
`Atlantica-PID21076-combate-20261103-232004.zip`, generado por 0.15.1. Son
946 432 bytes de la misma compilación e instancia. Antes y después sigue en
combate normal, con Auto Battle apagado y sin bloques adicionales inaccesibles.

| Dato observado antes y después | Valor |
| --- | --- |
| Entrada entera `0822F524` | 130 |
| Divisor entero `08230E14` | 100 |
| Sesgo `042C11E8` | 10,0 |
| Escala de `gestor+265C` | 1,399999976158142, representación float de 1,4 |
| Umbral `042C11D4` | 1,5 |
| Restablecimiento `042F320C` | 1,399999976158142 |
| Numerador de intervalo `042F31E8` | 33,0 |
| Divisor de movimiento `042F3688` | 160,0 |
| Índice gráfico seleccionado | 1 |

El cálculo `(130 + 10) / 100` coincide con el campo observado. El salto de la
comprobación se activa si ese campo supera 1,5 o si el getter gráfico supera
1,5. La rama restablece 1,4 y construye un mensaje que contiene la cadena
`SpeedHackUser`, ahora disponible en `042F31F0`. Esto confirma la comprobación
local; no demuestra por sí solo que ese mensaje se transmita o qué haga el
servidor. La escala no equivale necesariamente a un multiplicador del tiempo
total de la batalla.

Los nuevos bloques resolvieron estas funciones:

- `00A0481E` devuelve `base[1539CE10] + índice[1539CE18] * 274`.
- `00A14AFD` toma el objeto recibido, sigue su campo `+0C` y delega en `00A6FA3E`.
- `00A14B10` sigue el mismo campo y delega la consulta en `00A6FA50`.
- `00554C1B` suma `34` al objeto y deriva en `005FA247`. Es un auxiliar compartido;
  todavía no se le atribuye la restauración de un reloj.

La inicialización normal selecciona el contexto gráfico 1, toma su objeto en
`+18` y pasa a él la escala. Falta la implementación final en `00A6FA3E/00A6FA50`
y el auxiliar `005FA247`. La captura anterior incluyó sus envoltorios, no estos
destinos. Tampoco contiene el valor gráfico final ni una observación al volver al mapa.

## Comparación preparada en 0.15.2

Los dos exportadores añaden `00A6F000/2000` y `005FA000/1000`. Las regiones
adicionales de velocidad suman ahora 44 KiB. **Exportar diagnóstico** también
registra los estados antes/después y permite obtener la muestra fuera de combate;
sus datos están en `speed_diagnostic`. **Exportar combate** conserva el informe
en `combat.speed_diagnostic`.

El lector verifica los bytes de los accesos capturados y admite la implementación
del getter final solo si es una carga de float/double desde un desplazamiento
alineado menor de 4 KiB seguida de retorno. Lee los campos correspondientes de
los contextos gráficos 0 y 1 por la ruta comprobada `tabla → contexto+18 → objeto+0C`.
Registra punteros, bytes y valores, y descarta una lectura si los punteros cambian.
Un getter distinto, una dirección inválida o un campo inaccesible queda como no
resuelto; no se ejecuta la función para obtener su valor. No cambia el índice gráfico.

Para completar esta fase, con **0.15.2** y el bot detenido:

1. Deja Auto Battle apagado, entra manualmente en combate y guarda **Exportar combate**.
2. Al terminar y volver al mapa, guarda **Exportar diagnóstico**.
3. Adjunta ambos ZIP para contrastar las rutinas finales, posibles objetos compartidos
   y el estado fuera del combate.

Esta versión no modifica escalas ni desactiva comprobaciones. El techo local de
1,5 deja un margen nominal pequeño respecto a 1,4; no constituye una garantía de
sincronización ni de recogida de botín. Antes de preparar una prueba hay que
resolver la función final y el comportamiento al salir del combate.

## Comparación 234222–234316 y lector 0.15.3

Se verificaron los SHA-256 y el CRC de las capturas de 0.15.2:

| Captura | Bloques | Bytes | Estado local | Índice gráfico |
| --- | --- | --- | --- | --- |
| `combate-20261103-234222` | 39 | 958 720 | 33, contexto 0 | 1 |
| `contexto-20261103-234316` | 19 | 147 456 | 1, contexto −1 | 0 |

Pertenecen al mismo PID 21076 y fecha de creación `134381859857067996`.
Los 19 bloques que comparten son idénticos. El gestor en combate sigue en 1,4;
las entradas, divisor y constantes conservan los valores de la captura anterior.
Esto confirma el cambio de selector al salir de la batalla. Todavía no confirma
que los dos contextos usen objetos finales distintos ni que sus escalas difieran.

El lector anterior registró correctamente `getter_shape_not_resolved`: no presentó
un valor gráfico como leído. `00A6FA50` no es una carga directa; contiene
`mov ecx,[ecx]` seguido de un salto a `00A46DEA`. El setter `00A6FA3E` sigue el
mismo primer puntero y llama a `00A46DDA`. Esas implementaciones no estaban en los
bloques anteriores. Además, `00554C1B → 005FA247` vacía una colección en `objeto+34`;
esa ruta no demuestra una restauración de escala o reloj.

0.15.3 añade `00A46000/2000` a ambos exportadores, con lo que las regiones
adicionales fijas suman 52 KiB. El lector resuelve desde `00A6FA50` hasta cuatro
saltos directos, opcionalmente precedidos de una carga del receptor desde sí mismo.
Exige destinos dentro de la región de código y desplazamientos no negativos,
alineados y acotados. Detecta ciclos y detiene la lectura ante otras instrucciones;
conserva los bytes y direcciones de cada paso, hasta 16 bytes por función.
Solo sigue los punteros de objetos si la cadena termina en el getter simple
admitido. Después relee todos los enlaces, descarta cambios y compara el receptor
final de los contextos 0 y 1. No deduce aislamiento solo porque los envoltorios
tengan direcciones distintas.

Para completar la comparación pendiente, usa **0.15.3**, con bot detenido y Auto
Battle apagado: guarda **Exportar combate** dentro de la batalla y **Exportar
diagnóstico** al regresar al mapa. Esas lecturas permitirán resolver el campo
gráfico y comprobar su separación y estado fuera del combate. La versión sigue
sin aplicar cambios de velocidad.

## Capturas 001441–001517 y función final resuelta

Se verificaron los CRC, tamaños y SHA-256 de los ZIP de 0.15.3 del 4 de noviembre:
40 bloques / 966 912 bytes en combate y 20 bloques / 155 648 bytes en mapa.
La instancia sigue siendo PID 21076, creación `134381859857067996`, y el selector
gráfico cambia de 1 a 0. El lector acotado guardó la función final completa sin
seguir un patrón que todavía no reconocía; no fabricó valores gráficos.

`00A46DEA` contiene `mov eax,[ecx+120]; fld dword[eax+50]; ret`.
`00A46DDA` toma el mismo miembro y almacena el argumento float en `[eax+50]`.
Esto completa la ruta de datos:
`tabla → contexto+18 → envoltorio+0C → backend[0] → objeto+120 → campo+50`.
El lector admite ahora esa expresión exacta y vuelve a comprobar cada enlace.

0.16.0 prepara una prueba manual a 1,45 con validación en vivo de ambos receptores,
lectura de los originales y restauración. Si el valor gráfico no es 1,40 o el
receptor se comparte con el mapa, no aplica el cambio. Esto evita necesitar otro
volcado para decidir si esa instancia cumple las condiciones. El efecto visible
y la estabilidad siguen pendientes de prueba. Véase [la prueba manual](speed-trial.md).

## Prueba 0.16.0: cambio confirmado sin aceleración visible

El informe aportado por el usuario pertenece a la misma instancia PID 21076.
El getter resolvió ambos receptores finales y encontró que son distintos:
mapa en 1,00 y combate en 1,40. La operación 11 devolvió estado 38, con gestor
y gráfico en 1,45000005; la operación 12 devolvió 39, con ambos en 1,39999998.
Todas las lecturas reportadas del mapa permanecieron en 1,00, sin excepciones.
El usuario indicó «No siguieron igual todo igua»: no observó aceleración.

Las respuestas prueban la aplicación y restauración, pero no la persistencia
entre ellas ni un efecto perceptible. El incremento nominal es aproximadamente
3,6 %. Las rutinas capturadas consumen `gestor+265C`: `0059C319` calcula un
intervalo `33 / escala` antes de convertirlo a entero y `005A0EAC` multiplica
el avance de movimiento. Esas instrucciones no demuestran que una acción
concreta del usuario haya pasado por ellas durante la prueba. La captura tampoco
establece que el campo se reescribiera: esa hipótesis requiere observación.

0.16.1 registra muestras durante los mismos 10 segundos, comprueba enlaces
antes y después, y termina la prueba si ve un cambio de escala. Conserva la
restauración y no insiste en aplicar el valor. Esto permite investigar la
persistencia sin subir el ajuste ni sustituir los relojes de Windows.

## Prueba 0.16.1: persistencia observada durante una magia

El informe posterior de PID 21076 contiene 46 muestras válidas, desde 0 hasta
9906 ms. Todas leen 1,4500000476837158 en gestor y gráfico, y 1,00 en el mapa.
El selector sigue en 1 y la fase en 3. La petición de restauración ocurrió a
10110 ms y su respuesta, estado 39, a 10188 ms, con ambos campos de nuevo en
1,40. No hubo excepciones. El usuario confirmó que lanzó magia dentro de esos
10 segundos. La prueba no registra inicio/final de esa animación ni permite
medir su velocidad; tampoco demuestra constancia entre muestras.

El contador de `owner+BA4` avanzó 9906 mientras el tiempo del panel avanzó
9906 ms entre primera y última muestra. No se modificó ese contador ni se
atribuye a este dato una medición de FPS. El turno publicado permaneció en 0;
eso no contradice la acción manual confirmada por el usuario.

El aumento nominal 1,40 → 1,45 es de aproximadamente 3,6 %. Incluso 1,50 sería
solo un 7,1 % respecto a 1,40, no 1,5×. El umbral observado de 1,50 se conserva;
esta ruta no proporciona los multiplicadores solicitados 1,5×–4× dentro de ese
margen. No se presenta como una solución de aceleración comprobada.

La revisión encontró otro paso concreto: `00A46DF4` usa el objeto `this+120`
y llama a `00A1A82E` para actualizarlo. `00A46D9E` y `00A46DC1` resuelven registros
mediante `00A19CC0` y consultan miembros `+44`/`+2C`. Los bloques aportados no
incluyen esos destinos. Se comprobó que el ejecutable en disco no contiene
instrucciones equivalentes al código descifrado; no se usan sus bytes protegidos
para deducir el comportamiento de las funciones que faltan.

0.16.3 añade un bloque fijo de solo lectura `00A19000/3000`, que contiene los dos
destinos y espacio posterior para su inspección. Las regiones adicionales de
velocidad suman 64 KiB. Ambos exportadores lo incluyen con tamaño y SHA-256;
una región inaccesible queda anotada según el mecanismo anterior. No ejecuta
esas funciones ni cambia sus instrucciones, relojes, turnos o controles.

Para obtenerlo, usa **Exportar combate** en una batalla con el bot detenido y
Auto Battle apagado. No hace falta volver a aplicar 1,45 ni repetir la magia.
Este bloque permitirá seguir la actualización del objeto gráfico y determinar
qué avance consume el campo, sin deducir una aceleración visual de su valor.

## Captura 085806 y dependencias acotadas en 0.16.4

El ZIP de 0.16.3 del 4 de noviembre contiene 41 bloques, 979 200 bytes, con CRC,
tamaños y SHA-256 verificados. Sigue en la misma instancia PID 21076; la escala
vuelve a 1,40 en ambas muestras y el mapa conserva 1,00. El bloque nuevo resuelve
`00A19CC0` y `00A1A82E`.

`00A19CC0` busca un registro en la colección `this+5C`. `00A1A82E` elige entre
`00A19FA0` y `00A1A66C` según el estado de `1539CE00`. La primera rama recorre
objetos y delega en `00A523EF`, `00A527C0`, `00A5282F`, `00A52876`, `00A52A4B`
y `00A52AD7`. La segunda distribuye grupos de objetos y usa `00A041DE/00A04229`.
En esas tres rutinas de actualización no se observa una carga directa del
campo `this+50` probado. Esto no demuestra que el campo no intervenga en otros
consumidores ni que las funciones delegadas tengan un ajuste de velocidad.
Falta resolver las dependencias; no se ha localizado otro multiplicador.

0.16.4 usa Capstone 5.0.7 para decodificar instrucciones x86 de 32 bits, sin
ejecutarlas. **Exportar combate** y **Exportar diagnóstico** añaden
`animation_dependencies`. Primero exigen los bytes completos observados en la
entrada `00A1A82E` y sus dos llamadas de selección de rama; si no coinciden,
conservan el diagnóstico fijo y anotan que el recorrido no está disponible.

El recorrido reúne candidatos desde `00A1A82E`: hasta cuatro saltos de llamadas
desde la raíz de profundidad cero, 64 entradas,
256 instrucciones por entrada y 4096 bytes desde cada entrada. Sigue saltos
directos locales, detiene cada camino en retorno o salto indirecto, y registra
las llamadas indirectas sin adivinar sus receptores. Las llamadas fuera del
intervalo del motor `00980000`–`00C00000` y tres auxiliares comunes se anotan pero
no se recorren. No se certifican los límites de una función ni la semántica de
código protegido a partir de una decodificación candidata.

Reutiliza los bloques ya capturados. Los intentos de lectura nuevos se limitan
a 48 páginas de código y ocho de datos estáticos, de 4096 bytes: un máximo de
224 KiB adicionales. Los datos deben estar en `03F85000`–`044F9000` y aparecer
como direcciones inmediatas o accesos absolutos en las instrucciones decodificadas.
No sigue punteros del montón. También limita los registros de referencias a
1024. Los intentos fallidos consumen su presupuesto, se anotan y no se repiten.

El informe conserva los límites alcanzados, páginas inaccesibles, bytes y hashes;
siempre marca la cobertura y las semánticas como no completas/verificadas.
La validación de instancia y del contexto al finalizar la exportación sigue
rechazando una captura mezclada. El trabajador de caza y la prueba a 1,45 no
reciben nuevos comandos. No se modifican relojes, controles o turnos.

El ejecutable de Windows incluye la biblioteca del decodificador y comprueba su
carga durante el arranque automatizado con bytes fijos, sin acceder al juego.
Al usar los fuentes sin instalar esa dependencia, la exportación fija continúa
y registra `decoder_unavailable`. Esta fase necesita una nueva exportación de
combate con 0.16.4; no necesita otra prueba de escala.

## Captura 021811: tabla de métodos del personaje y tiempo de animación

El ZIP de 0.16.4 del 5 de noviembre pertenece a otra instancia, PID 10852,
creación `134383363734202228`, de la misma compilación admitida. Se verificaron
CRC, tamaños y SHA-256 de sus 57 bloques, 1 044 736 bytes. El grafo contiene 28
entradas, nueve páginas nuevas de código y siete de datos, sin páginas
inaccesibles. Registra límites de profundidad e instrucciones, sin certificar
cobertura completa. El gestor sigue en 1,40 en ambas muestras.

Los datos estáticos identifican `N3DCCharManager::ManagedFullUpdate` y las fases
`PreUpdate`, `Update` y `PostUpdate`, además de clases Gamebryo/NiAnimation.
La delegación `00A527C0 → 00A1AB93 → 00A72619` pertenece a
`N3DCChar::GetCommandManager`: procesa órdenes temporizadas y no se presenta
como un multiplicador de animaciones por su argumento float.

La actualización por `00A5282F` llama al método virtual `+A4`; `00A52876` llama
a `+A8`. La tabla estática `043E2C34`, contenida en la captura, publica:

| Desplazamiento | Destino observado |
| --- | --- |
| `4C` | `00A1E68F` |
| `50` | `00A1E540` |
| `A4` | `00A52DCC` |
| `A8` | `00A52939` |
| `AC` | `00A52AA9` |

`00A52DCC` pasa un float del contexto de actualización `+0C` a `00AAC680`
con el receptor obtenido de `personaje+6C → +0C`. `00A52939` delega también
en `00A76C74`. Esos destinos no están en el ZIP. Las etiquetas de NiAnimation
no bastan para asignar semánticas o campos de velocidad a código que falta.
Tampoco se deduce que todos los personajes vivos utilicen esta tabla base.

0.16.5 añade cuatro raíces candidatas de esa tabla (`A4`, `A8`, `4C`, `50`) al
grafo de solo lectura. Antes lee su página dentro de la sección estática admitida
y exige coincidencia exacta de las cinco entradas. Una tabla distinta o
inaccesible se registra y no aporta raíces; el recorrido directo anterior sigue
disponible. Las raíces comparten el presupuesto de nodos y código, y el informe
conserva `runtime_receiver_verified=false`. No sigue objetos del montón para
resolver llamadas ni ejecuta estas funciones.

Los límites siguen en 64 entradas, cuatro saltos, 256 instrucciones por entrada
y 48 intentos de página de código. El presupuesto de datos estáticos pasa a 16
páginas, con un máximo total de 256 KiB nuevos. La exportación mantiene las
comprobaciones de instancia y contexto. Se necesita **Exportar combate** con
0.16.5 para obtener las nuevas dependencias. La prueba de escala sigue siendo
opcional y no es necesaria para esta exportación; no se activa un SpeedHack.
