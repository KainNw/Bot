# Análisis estático del cliente recibido

Fecha del análisis: 2026-11-02. El archivo se obtuvo del RAR adjuntado por el usuario.
Se leyó como datos; el cliente no se ejecutó. El ejecutable y el archivo comprimido
se conservan fuera del checkout del proyecto.

## Identidad comprobada

| Campo | Resultado |
| --- | --- |
| Archivo | `Atlantica.exe` |
| Tamaño extraído | 34 026 496 bytes |
| SHA-256 | `BC87A0CC5826AA7FB5E4FF10B6B7C1A349962BD8B146AD28EC3FFA9453FE04E6` |
| Coincidencia con el informe del usuario | Sí, exacta |
| Formato | PE de Windows, máquina `0x014c`, x86 de 32 bits |
| Versión de archivo en recursos | `1.0` |
| Versión de producto en recursos | `1, 1, 1, 3` |
| Base preferida declarada | `0x00400000` |
| RVA del punto de entrada declarado | `0x15510160`, dentro de `.boot` |

La base preferida y el punto de entrada son metadatos del archivo. No son direcciones
verificadas de mobs, coordenadas ni una rutina de ataque. La versión del recurso no
identifica por sí sola una compilación: se debe conservar la comprobación por hash.

## Observaciones

- La imagen tiene ocho secciones. Las tres primeras tienen nombres formados por espacios.
- Hay secciones `.winlice` y `.boot`. `.winlice` ocupa espacio virtual sin datos crudos
  en disco; `.boot` contiene el punto de entrada declarado.
- La entropía observada en las tres primeras secciones es aproximadamente 7.944, 7.665
  y 7.921 bits por byte; en `.boot`, 7.954. Son valores compatibles con contenido
  comprimido o cifrado; la entropía por sí sola no identifica un protector.
- El comienzo de la entrada contiene un bucle con lectura y copia de bytes y manejo
  de bits, compatible con una rutina de descompresión/carga. No se identificó allí
  una función del sistema de combate.
- La tabla de importaciones visible contiene 28 DLL, con una sola entrada visible
  por DLL. Entre ellas están Direct3D 9, DirectInput 8, FMOD y el runtime de Visual C++ 9.
- El directorio de depuración PE está vacío. La búsqueda realizada no encontró nombres
  de tipo RTTI legibles. Esto no demuestra que no puedan recuperarse referencias por
  otras técnicas.
- Se encontraron textos como `Monster List`, `Make Monster(&M)` y `Monster Group`
  dentro de `.rsrc`. Son etiquetas de recursos de interfaz; no constituyen un mapa de
  entidades ni prueban que esas herramientas de interfaz estén accesibles al jugador.

La combinación de `.winlice`, el cargador y las características anteriores sugiere
empaquetado/protección de la familia WinLicense/Themida. Es una inferencia estática;
no se ha identificado una versión exacta del protector ni su configuración.

## Resultado para el bot

La identidad y la arquitectura del cliente quedaron comprobadas. No se han localizado
ni validado:

- la lista o estructura de entidades/mobs;
- posiciones, identificadores, salud o selección del objetivo;
- el punto de entrada o mecanismo de la acción de ataque.

No se incorporan offsets de combate al bot a partir de estos resultados. El diagnóstico
existente sigue siendo una herramienta de consulta y lectura, sin automatización de ataques.

## Observaciones de Windows aportadas por el usuario

Las siguientes comprobaciones proceden de capturas de x32dbg del usuario; no de una
conexión remota desde esta nube:

- El proceso se pudo adjuntar. El registro de `mod.main()` mostró `00400000` como base.
- Con el cliente pausado, la vista CPU de `00401000` mostró `51 56 8B 74 24 0C`
  (`push ecx`, `push esi`, `mov esi,[esp+0xC]`) al comienzo de la primera sección.
- En el archivo extraído, los seis bytes correspondientes son `5E 2A 37 DB 81 4E`.
  Por tanto, esa zona de la imagen en ejecución difiere del contenido almacenado.

La captura muestra una secuencia de código x86 coherente en esa zona. No demuestra
que toda la imagen esté desempaquetada ni identifica por sí misma una función de
combate.

Una búsqueda posterior con `strref 00401000, 0, 1` produjo referencias del módulo
`atlantica.exe`. En la captura, todavía al 12 % de progreso, aparecen el texto
`Attack Monster -> %d Distance -> %f` en las referencias `0043CDA7` y `0043CEB4`,
y nombres como `cltBFCharCommon::CanAttackObject` e `IsInAttackRange`.
Las direcciones son referencias a textos según la captura, no entradas de función
ni direcciones de entidades verificadas. Aún no se ha comprobado si esas rutas se
ejecutan al hacer clic manualmente sobre un mob.

El siguiente bloque acotado para analizar el contexto de las primeras referencias
es `0043B000`–`0043EFFF` (16 KiB), dentro de la primera sección del módulo. La orden
de exportación de x32dbg es:

```text
savedata ":memdump:", 0043B000, 4000
```

`4000` es el tamaño en hexadecimal. La orden lee memoria y guarda un archivo local;
el registro muestra su ruta. El archivo solo debe tratarse como una lectura completa
si no aparecen errores de lectura o escritura: la implementación de `savedata` puede
crear un archivo incluso cuando informa que no pudo leer toda la región.

### Análisis del bloque de código recibido

Se recibió `memdump_4014_0043B000_4000.bin`, de 16 384 bytes, con SHA-256
`894B2A134E5510525A8AFD7A62E3DAD0D8E38040CD00EFECA41FE2D3C5881F02`.
Su contenido incluye las instrucciones y referencias mostradas en las capturas.
Las cuatro páginas contienen código no nulo. El tamaño y la coherencia del bloque
no sustituyen una comprobación de que `savedata` terminara sin errores de lectura.

El recorrido de saltos desde `0043CA56` identificó 443 instrucciones alcanzables
y un retorno en `0043D0C7`, sin saltos de esa rutina fuera del bloque. No se siguió
el código de las funciones llamadas, muchas de las cuales están fuera de la captura.

| Evidencia del bloque | Interpretación y límites |
| --- | --- |
| `0043CA56`: prólogo, uso de ECX como objeto y retorno sin limpieza de argumentos | Entrada de una rutina compatible con `__thiscall`, no una acción de ataque validada. |
| `0043D697`: llamada a `0043CA56` desde otra rutina con controles temporales | Compatible con actualización periódica del personaje; no parece una entrada directa de clic. |
| `0043CD0A`–`0043CD28`, repetido en la segunda rama | Restas de tres valores float en desplazamientos `+0xB8C`, `+0xB90`, `+0xB94` de dos objetos; candidatos a posiciones, todavía sin comprobar mediante movimiento. |
| `0043CD2B` y `0043CE48` | Llamadas a `0043ADD7` con el vector de diferencias; el resultado se compara con un float global en `045079EC`. El cálculo exacto de la función llamada no está capturado. |
| `0043CCFB` y `0043CE15` | Lectura de una colección indexada de punteros a partir de `EDI + EAX*4 + 0x28`. No se ha validado que sea la lista de mobs ni su rango de índices. |
| `0043CD97` y `0043CEA6` | Llamadas a `0043652D` después de preparar un buffer y antes del registro de texto. Su efecto real todavía no está validado. |
| `0043CDA7` y `0043CEB4` | Ambas referencias al texto `042C6408` pertenecen a la misma rutina. |

También hay controles de estado, flags, tiempos y ramas que actualizan vectores.
La rutina y sus auxiliares no se deben tratar todavía como una API de ataque.
Falta identificar las etiquetas compartidas de registro y los textos de configuración
referenciados desde esta rutina, y después observar qué rutas se ejecutan durante
una selección y un ataque manual.

Los textos pendientes están dentro de la página `042C6000`–`042C6FFF`, que pertenece
a la segunda sección PE declarada como datos de solo lectura. Contiene, entre otras,
las referencias `042C63D8`, `042C6408`, `042C6454`, `042C6478` y `042C6494`.
Su exportación acotada propuesta es:

```text
savedata ":memdump:", 042C6000, 1000
```

### Textos recuperados de la página de constantes

Se recibió `memdump_4014_042C6000_1000.bin`, de 4 096 bytes, SHA-256
`AC81935A3C9114C583961833A9E44F35AAE7F6B9D490737D09EA988E668AFF37`.
Los textos UTF-16 confirman:

| Dirección | Texto |
| --- | --- |
| `042C6318` | `Go Home Distance -> %f` |
| `042C6350` | `Move Character -> %d  Distance -> %f  MyPos(%d,%d) Target( %d, %d)` |
| `042C63D8` | `Config\AutoHunting.txt` |
| `042C6408` | `Attack Monster -> %d  Distance -> %f` |
| `042C6454` | `UseBuffItems.txt` |
| `042C6478` | `HoldMode.txt` |
| `042C6494` | `HuntingMode.txt` |

El bloque vecino también contiene `CrashLogs\AutoHunting.txt` y mensajes de
`AutoUseItem`, coherentes con lógica de automatización ya incorporada al cliente.
La conclusión se limita a la presencia del código: no se ha demostrado que esté
activado o que baste con crear archivos para hacerlo funcionar.

En `0043CB11`, `0043CB54` y `0043CB9F`, la rutina llama al puntero de función
almacenado en `03F85910`, pasando la dirección de una variable local, uno de esos
tres nombres de archivo y un tercer texto constante. Después comprueba el puntero
local y, si no es nulo, llama al puntero almacenado en `03F8590C`. Este patrón es
compatible con `_wfopen_s` seguido de `fclose`. Una captura posterior del registro
de x32dbg confirmó las etiquetas `msvcr90._wfopen_s` y `msvcr90.fclose` para esas
dos importaciones. Las direcciones de las DLL de esa sesión no se usan como offsets
persistentes.

El flujo capturado comprueba la apertura del archivo y lo cierra sin leer su contenido
en ese fragmento. `HuntingMode.txt` condiciona el byte en `04E52C5A` según el resultado
de apertura, `HoldMode.txt` el byte en `04E52C59` y el umbral global,
y `UseBuffItems.txt` el byte en `04E52C58`. Sigue pendiente comprobar el modo de apertura
en `042C3108` y la carpeta de trabajo del proceso antes de interpretar estos archivos
como marcadores de existencia. Existen controles previos de estado y otras condiciones;
no se ha comprobado cómo habilitarlos ni su significado completo.

Los controles anteriores a la apertura incluyen un byte en `[objeto_global+0x16394]`
distinto de cero y un entero con signo en `[objeto_global+0x16398]` mayor que cero,
donde `objeto_global` se lee de `04A9290C`. Sus nombres funcionales todavía no se
han identificado. No se propone cambiarlos directamente en memoria.

`Config\AutoHunting.txt` se pasa al auxiliar de registro de mensajes junto con un
formato y sus argumentos. No está identificado como un archivo de configuración de
entrada y no se recomienda editarlo como tal basándose únicamente en su nombre.
Tampoco se han creado, modificado o eliminado marcadores en el PC del usuario.

Consulta de identidad de funciones propuesta en x32dbg:

```text
log "ABRIR={a:[03F85910]} CERRAR={a:[03F8590C]}"
```

### Comprobaciones posteriores del modo y las condiciones

La captura posterior del usuario mostró:

- `MODO=L"rt"`, con los primeros cuatro bytes representados como `00740072`:
  apertura de texto para lectura.
- La carpeta de trabajo del proceso apunta al directorio del cliente. La ruta personal
  completa no se copia al informe del repositorio.
- El objeto global estaba presente. El byte previo A (`objeto_global+0x16394`) era `0`,
  el entero previo B (`objeto_global+0x16398`) era `16`, y el flag derivado HUNT
  (`04E52C5A`) era `0`.

En esas condiciones, el salto en `0043CACC` sale de la ruta antes de abrir los
marcadores. Por tanto, HUNT=0 no permite deducir si `HuntingMode.txt` existe.
La comprobación de B exige un valor positivo y sí se cumple en la captura.

Con `_wfopen_s` y el modo `rt` confirmados, la apertura correcta de un archivo
`HuntingMode.txt` legible en la carpeta de trabajo fija el flag correspondiente
cuando se alcanzan esas instrucciones. Todavía faltan las demás condiciones
de juego y la validación de comportamiento real.

Una hipótesis pendiente es que A sea un indicador del modo Auto Battle y B su
contador asociado. Se propone contrastarla cambiando únicamente el control normal
de Auto Battle en la interfaz y repitiendo las lecturas. Los valores 0 y 16 son
coherentes con esa hipótesis, pero por sí solos no identifican los campos.

Una captura posterior mostró el mensaje del juego `Auto-Battle Mode has been enabled`
después de usar el control señalado por el usuario, con A=1, B=17 y HUNT=0 en x32dbg.
Esto respalda la asociación de A con el estado Auto Battle. La lectura de B es positiva;
todavía no se ha confirmado su unidad o significado exacto. El experimento de
activación de A no valida por sí solo que la caza automática funcione.

La prueba siguiente consiste en crear exclusivamente un archivo vacío nuevo llamado
`HuntingMode.txt` en la carpeta de trabajo indicada por el proceso, conservando
cualquier archivo preexistente. Con el cliente ejecutándose, se comprobará si HUNT
pasa a 1 y, por separado, si el personaje selecciona, se aproxima a un mob o inicia
un encuentro. Se debe distinguir el reconocimiento del marcador del resultado de juego.

Para la prueba manual, `New-Item` se usa sin `-Force`: si el marcador ya existe, se
detiene la creación sin sobrescribirlo. La desactivación de Auto Battle desde la
interfaz es el control normal de parada que se debe comprobar. El marcador vacío
creado durante la prueba puede retirarse después para deshacer ese cambio local.

### Resultado comunicado de la activación y cierre posterior

El usuario adjuntó una lectura HUNT=1 y confirmó que veía al personaje atacar.
Esto valida el reconocimiento del marcador y un comportamiento de ataque observado
en esa sesión con x32dbg adjunto. La ejecución sin el depurador y la estabilidad
prolongada no están validadas.

Posteriormente comunicó que el juego se cerró cuando intentó mover el personaje.
Confirmó que x32dbg seguía adjunto y que su registro se había borrado. No se dispone
de excepción, pila del cierre ni código de salida; no es posible atribuirlo al
depurador, a la rutina AutoHunting o a otra causa con esas pruebas. Se solicitó
comprobar si persisten líneas relevantes en `CrashLogs\AutoHunting.txt`.

El usuario también respondió que se cierra durante una prueba de clic manual con
Auto Battle apagado, el marcador desactivado y sin x32dbg. No se obtuvo un nuevo
registro ni una excepción de esa reproducción. Se mantiene la causa sin determinar;
no se puede atribuir exclusivamente a la presencia del depurador o al modo de caza.

Se incorporó un controlador del marcador y un panel con lectura real del estado.
El panel no anuncia una parada confirmada basándose solo en renombrar el archivo:
espera a que el cliente deje de indicar HUNT=1. Si Auto Battle está apagado, lo muestra
como un estado diferente porque los indicadores pueden quedar sin actualizar.
El panel no modifica el código del cliente ni ha corregido el cierre comunicado.

Las lecturas de esta compilación están condicionadas a su hash, base esperada y modo
de apertura. El PID se descubre al conectar y se vuelve a seleccionar tras reiniciar
el juego. El objeto global dinámico se lee de nuevo en cada consulta. La carpeta de
trabajo se obtiene mediante las estructuras de parámetros de un proceso de 32 bits,
leyendo únicamente su cadena de directorio. No se vuelca el entorno del proceso.

La lógica de reconexión, estados pendientes y conservación de archivos tiene pruebas
automatizadas en Linux. La interfaz gráfica y las llamadas nativas añadidas para
leer la carpeta del cliente aún requieren comprobación en Windows; se mantienen
separadas de la prueba manual de ataque ya comunicada por el usuario.

## Uso de un asistente de ingeniería inversa

Un asistente conectado a Ghidra o IDA puede ayudar a recorrer referencias, proponer
nombres y resumir funciones. Cada interpretación debe apoyarse en instrucciones y
referencias concretas. Una etiqueta de recurso o el cargador del ejecutable no bastan
para identificar una estructura del juego.

El siguiente paso de validación de la vía de memoria requiere analizar el cliente
cargado en Windows, identificar candidatos y comprobar su comportamiento durante
selecciones y combates manuales. Una herramienta de análisis debe mantener separados
los datos observados y las hipótesis. No hay sesión de Windows ni acceso al proceso
del usuario desde esta nube, y ninguna de esas pruebas dinámicas se ha ejecutado aquí.

Herramientas usadas para esta inspección: libarchive-c 5.3 con la biblioteca libarchive
del sistema para leer el RAR, pefile 2024.8.26 para el PE y Capstone 5.0.9 para
desensamblar el inicio de la entrada x86. No se ha instalado o conectado un producto
específico llamado REA.
