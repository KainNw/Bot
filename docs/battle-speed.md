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
