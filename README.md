# Control de caza para Atlantica Online

Panel para Windows 10/11 que selecciona un cliente y solicita ataques
con Auto Battle apagado. La versión **0.30.0** amplía la pestaña **TBS** para
investigar **Scourge**, empezando con solo el Main. El visor muestra su posición
interna, HP/MP, unidades y estados de acción. Añade control de turno, terreno
cercano y **Registrar turnos 12 s** para observar la transición al enemigo mientras
juegas manualmente. Solo lee memoria; las órdenes automáticas de TBS requieren
contrastarlas. Consulta [TBS y memoria](docs/tbs-memory.md).

Conserva **Speed en combate independiente** de **0.28.0**:
otra casilla con factor propio que espera a 1× en el mapa, acelera en batalla y
vuelve a 1× al salir, sin iniciar el bot. Usa el controlador de combate existente
con una cancelación independiente. Conserva la lógica y los ajustes del Speed
vinculado a **Iniciar bot**. Consulta [Speed del panel](docs/panel-speed.md).

Conserva **Recogida inmediata (sin espera)** de **0.27.0**,
activada por defecto: omite la espera del NeoACA, elige un recolector disponible y
aprovecha el que ya está seleccionado. Reduce la pausa de observación a 50 ms y
elimina la espera añadida tras observar un cadáver desaparecer o una animación
de recogida completada. Conserva las guardas nativas y no repite órdenes encoladas.
Consulta [caza y botín](docs/hunt-settings.md).

Conserva **Speedhack general** de **0.26.0**, que se activa al
marcar la casilla, sin iniciar el bot, con factor propio de **1,25× a 4×**.
Permanece en mapa y combate del PID seleccionado aunque pares el bot;
al desmarcar o cerrar el panel vuelve a 1×. **Speed en combate** conserva su comportamiento de
acelerar solo la batalla y volver a 1× en el mapa. Se elige un modo a la vez,
conservando el factor de cada uno, y se guarda por personaje. Consulta
[Speed del panel](docs/panel-speed.md).

También añade **Auto Life · MP**: con el bot iniciado, consulta el maná del Main
y de los mercenarios vivos fuera del combate. El umbral inicial es **50 %** y
la tecla se elige entre **F1 y F9**, donde el usuario coloca Potion Life. Espera
recuperación antes de reanudar la búsqueda y pausa solo Auto Life si no la observa,
sin repetir una tecla incierta. La recuperación real de la poción necesita prueba
en el cliente. Consulta [Auto Life](docs/auto-life.md).

Conserva la corrección de **0.24.1**, que permite ejecutar las órdenes con
la ventana del juego minimizada: elimina el rechazo que detenía el bot con código
20. Conserva las comprobaciones de PID, HWND, hilo y diálogos bloqueantes, sin
restaurar la ventana ni cambiar el foco. Consulta [varias ventanas](docs/multiple-clients.md).

Conserva las opciones de **0.24.0**: **Defender (G)** y **Pasar
acción (F)** al perfil y a las pruebas individuales. **Solo Main + pasar las
acciones restantes** permite que el Main ejecute su acción y después se pasen los
miembros disponibles. Si todos los enemigos mueren, omite esos pases para dejar
trabajar al NeoACA y al recolector. Se conserva el guardado por personaje. Las
nuevas acciones necesitan comprobarse visualmente en el cliente; una cola no
confirma el resultado. Consulta [defensa y pases](docs/defend-and-pass.md).

Conserva el guardado de **0.23.0** de la configuración de cada
personaje y la carga al reconocer su **nick** al conectar, aunque cambie el PID.
Recuerda el último perfil, las órdenes de sus mercenarios, caza, botín, Speed y
la opción de ejecutar turnos. Los ajustes de caza se guardan automáticamente;
las órdenes se guardan desde el editor. Conectar carga los ajustes y deja el bot
detenido hasta que pulses **Iniciar bot**. Consulta
[configuración por personaje](docs/character-profiles.md).

Conserva las mejoras de **0.22.0**: revisa las órdenes pendientes de
combate cada 100 ms para observar mejor las animaciones cortas, separa los rechazos
de ataque de las comprobaciones de recogida y permite ajustar la **espera del
NeoACA entre 0 y 5 segundos** en **Caza y botín**. Los perfiles anteriores mantienen
1 segundo de espera. La recogida de bonus de armas/equipamiento y libros de EXP
sigue pendiente de comprobar con capturas del cliente; estos cambios no la dan
por resuelta. Consulta [caza y botín](docs/hunt-settings.md).

Conserva la consulta de 0.21.0 del **nombre del Main al conectar**. El resultado
aparece en la cabecera, en el título de Windows
y en la vista general junto al PID. Si el nombre no está disponible, la lectura
se reintenta y permite un alias manual sin cortar la conexión. Consulta
[la ruta de lectura y su validación](docs/main-identity.md).

Conserva la interfaz oscura de **0.20.0** y sus cuatro pestañas: **Control**,
**Mercenarios**, **Caza y botín** y **Diagnóstico**. **Iniciar bot**, **Parar bot**
y **Copiar estado** permanecen visibles al cambiar de pestaña. Consulta
[la distribución del panel](docs/panel-interface.md).

Conserva el **Speed integrado** de 0.19.0: factores **1,25×, 1,5×, 2×, 3× y 4×**
y vuelta a **1×** en el mapa o al parar. El usuario confirmó la aceleración y la
recuperación de la velocidad normal al terminar su prueba de combate. En la
pestaña **Caza y botín**, se configura desde **Speed en combate → Activar Speed**.
Consulta [las instrucciones](docs/panel-speed.md). El paquete
**AtlanticaPanel-Windows** incluye el ejecutable y la licencia nativa.

Conserva 0.16.5, que extiende la captura de animaciones
con cuatro métodos candidatos de una tabla estática contrastada con el último
ZIP. Valida cinco entradas antes de usarlas como raíces de análisis; no deduce
el tipo de un objeto vivo ni ejecuta métodos virtuales. Esto permite seguir las
llamadas que reciben el tiempo de animación. Conserva los límites del recorrido
y admite hasta 16 páginas nuevas de datos estáticos, con un máximo conjunto de
256 KiB adicionales. Consulta [la investigación](docs/battle-speed.md).

Conserva 0.16.4, que añade una captura acotada de las
dependencias de actualización gráfica: sigue llamadas directas del código ya
verificado, recoge sus páginas y datos estáticos referidos y registra las
llamadas indirectas que no puede resolver. Solo lee; no ejecuta las instrucciones
analizadas. El paquete de Windows incluye el desensamblador. Se conservan los
límites por profundidad, nodos, instrucciones y páginas, y cada bloque tiene
tamaño y SHA-256. Consulta [la investigación](docs/battle-speed.md).

Conserva 0.16.3, que amplía la exportación de memoria
para seguir la actualización gráfica que usa el objeto de la escala. La prueba
0.16.1 mantuvo 1,45 en 46 muestras y el usuario confirmó una magia dentro del
intervalo; no se midió la duración de la animación. El nuevo bloque permite
investigar el consumidor del campo. No añade multiplicadores de velocidad ni
aumenta el valor de la prueba. Consulta [la investigación](docs/battle-speed.md).

Conserva 0.16.2, que mantiene la vigilancia de un ataque
pendiente después de 30 segundos, bloquea nuevos ataques al mapa y procesa el
combate si se observa más tarde. Mantiene el PID conectado y el ejecutor del
perfil disponible; no activa turnos si el usuario los dejó deshabilitados.
**Parar bot** sigue deteniendo el trabajador. Una solicitud todavía sin confirmar
conserva su revisión al detenerlo explícitamente. Consulta [recuperación](docs/recovery.md).

Conserva 0.16.1, que registra lecturas durante la
**prueba manual de velocidad en combate**, de escala 1,40 a 1,45 durante unos
10 segundos. El usuario probó 0.16.0: los campos cambiaron y se restauraron,
pero no observó una diferencia visual. El seguimiento permite comprobar si el
cliente mantiene esos valores durante la acción; si cambian, intenta restaurar
y no vuelve a aplicar la escala. Se abre
desde **Caza y botín → Prueba de velocidad (experimental)**. No cambia nada al
abrir el panel: requiere bot detenido, Auto Battle apagado, lectura válida y
pulsar **Probar**. Comprueba que el mapa tenga un campo separado y verifica su
valor antes/después. Intenta restaurar los originales al vencer el tiempo,
volver al mapa o cerrar la ventana; un fallo conserva la opción Restaurar.
El cambio de campos no demuestra un combate más rápido ni mide las animaciones.
Consulta [la prueba de velocidad](docs/speed-trial.md).

Conserva 0.15.3, que sigue los accesos indirectos que
mostraron las últimas capturas de velocidad. Conserva en el diagnóstico sus
instrucciones y punteros, distingue objetos finales compartidos y limita la
lectura a una cadena corta dentro de la imagen comprobada. No ejecuta esas
funciones ni activa velocidad adicional. Consulta [el análisis](docs/battle-speed.md).

Conserva 0.15.2, que amplía la investigación de velocidad:
**Exportar combate** y **Exportar diagnóstico** recogen los accesos gráficos y sus
valores para comparar el combate con el regreso al mapa. No activa velocidad
adicional. La captura anterior confirmó una escala de 1,4 y una rama del cliente
que restablece 1,4 cuando supera el umbral local de 1,5. Ese umbral no demuestra
un ajuste seguro para el servidor. Consulta [el análisis](docs/battle-speed.md).

Conserva 0.15.1, que mantiene la conexión durante cambios
transitorios de estado y permite caminar en **Atacar desde mi posición** sin la
parada inmediata que exigía reconectar. Al buscar, pausa hasta quedar quieto y
toma el punto nuevo como centro. Si ya envió un ataque, espera el combate pendiente
sin repetirlo. Desde 0.16.2, el plazo original pasa a ser un aviso y continúa
vigilando ese mismo envío. Consulta [ataque desde la posición](docs/stationary-attack.md).

**Exportar combate** incorpora las funciones y valores observados al investigar
la escala de animaciones. Solo los lee: aún no hay un control de velocidad
validado. Consulta [el análisis de velocidad](docs/battle-speed.md) para obtener
la captura que falta.

Conserva 0.15.0, que explica la causa del **código 20
del puente**: ventana bloqueada, desaparecida o vinculada a otro proceso
o hilo. Ese rechazo ocurre antes de enviar la orden; por sí solo ya no exige
reconectar ni presenta el resultado como desconocido. Las solicitudes anteriores
cuya parada no pueda confirmarse conservan sus comprobaciones. Cierra los diálogos
de la ventana elegida; si cambió de proceso o hilo, vuelve a elegirla y conectar.
Consulta [varias ventanas](docs/multiple-clients.md#código-20-del-puente).

Añade **Capturar bonus (memoria)** para comparar el bonus visible con el estado
después de una pulsación manual de X. Permite etiquetar EXP, armas/equipamiento o
libros de EXP y guardar un ZIP de lectura, vinculado a la instancia elegida.
Esta herramienta permite investigar la recogida: todavía no identifica automáticamente
los tipos ni corrige la recogida de armas o libros. Consulta [captura de bonus](docs/bonus-memory.md).

Conserva **Atacar desde mi posición
(experimental)**: elige el mob más cercano dentro del radio y solicita iniciar
combate desde la posición actual, sin enviar persecución ni rutas. La aceptación
de objetivos lejanos se comprobó en la captura del usuario: cuatro solicitudes y
cuatro combates, tres fuera del alcance nativo de cercanía y sin cambio de posición.
Eso confirma esa sesión y compilación; no todos los mapas ni servidores. Se elige
en **Caza y botín → Modo de ataque al mob** y se guarda por perfil.
Consulta [ataque desde la posición](docs/stationary-attack.md).

Conserva los indicadores de 0.13.1, que distinguen claramente **Combate
automático** de **Turnos manuales**, también al tener activa la recogida. Un cambio
de selección que impide enviar una recogida pausa esa función hasta la siguiente
batalla, en vez de detener toda la caza. Consulta [el diagnóstico del combate
recibido](docs/recovery.md#registro-recibido-en-0130-y-corrección-0131).

Conserva **Caza y botín** de 0.13.0: espera
configurable antes de atacar (0, 1, 3 o un valor de 0–60 segundos), radio de búsqueda
de 5–500 casillas con calibración por objetivo y recogida nativa experimental de
botín restante después de derrotar a todos los mobs. Se guarda por perfil.
La espera no retrasa la magia del primer turno. La recogida del bonus todavía necesita
confirmación visual en el juego. Consulta [caza y botín](docs/hunt-settings.md).

Conserva la pausa de búsqueda al caminar manualmente
y la reanuda tras dos segundos quieto, tomando el punto actual como centro del radio.
Prioriza las batallas que interrumpen un desplazamiento y mejora la recuperación de
lecturas durante lag y carga de enemigos. Consulta [movimiento y recuperación](docs/recovery.md).

Incluye **Vista general**, una ventana
flotante oscura con **Main (1)** fijo y **Mercenarios 2–9**. Muestra vida actual en
combate, presencia, habilitación en el perfil, prioridad y acciones, con controles
para iniciar, parar y configurar. Se abre desde **Control** o **Mercenarios**.
Consulta [la vista general](docs/overview.md).

Conserva la reducción de espera de 0.11.1 antes de lanzar
la magia: después de seleccionar al mercenario, relee su barra y solicita la acción
sin esperar otro ciclo. Comprueba la preparación del combate cada 100 ms mientras
hay una orden que preparar. Conserva **Ejecutar turnos según el
perfil (experimental)** y la pestaña **Mercenarios**, con los nueve puestos,
participación real en batalla, selección en el perfil, prioridad y última orden.
Solo ordena actuar a los miembros presentes y habilitados. Puedes llevar dos
miembros sin esperar a los otros siete. Configura básico o **Magia Q/W/E/R/T**
por mercenario, en el orden del perfil; por defecto usa la magia en el primer
turno propio y básicos después. Deja de enviar ataques al no observar enemigos vivos;
si habilitas la recogida restante, permite solicitudes de búsqueda sobre los derrotados.
El usuario confirmó visualmente el básico de 0.9 y la magia Q de 0.10. En la primera
prueba automática de 0.11, Q del puesto 1 derrotó a todos y el bot omitió las órdenes
restantes. La secuencia entre varios miembros y los básicos posteriores siguen
pendientes de prueba. En la prueba de 0.11.1, el usuario confirmó que el NeoACA recogió
el botín y la batalla terminó en el primer turno. La pausa entre selección y solicitud
de Q bajó de 563 a 63 ms en los dos registros; ese intervalo no mide la animación.
Las pruebas individuales siguen en **Ver mercenarios** y requieren **Parar bot**.
Conserva **Ataque nativo por radio (experimental)**, **Calibrar combate**,
observaciones y tres perfiles. Al conectar con la compilación
compatible vincula el detector local ya comprobado a ese PID y fecha de creación.
**Calibrar combate** permite comparar manualmente las señales si hace falta.

El modo **Perseguir y atacar (nativo)** usa las órdenes observadas en Auto Battle: persecución del mob
si está lejos y ataque cuando entra en el mismo alcance que establece el cliente.
El radio de búsqueda selecciona objetivos; no amplía el alcance del golpe ni escribe
el umbral nativo. El panel conserva la identidad del mob aunque cambie de puesto.
Detalles y resultados en [ataque nativo por radio](docs/native-attack.md).

La captura 0.7.0 del usuario confirmó seis solicitudes y seis combates, con Auto
Battle apagado, cuatro persecuciones nativas sin fallos y parada normal sin exigir
reconexión. También inició combate con el objetivo que fallaba antes. La versión
0.11 conserva ese sistema y sus tiempos de persecución y ataque.

**Comprobado por el usuario:** la prueba individual 0.3 inició el ataque con Auto Battle
desactivado. También confirmó un combate iniciado por 0.4 que el detector no reconoció.
La siguiente captura mostró `scene_code=2`: ese valor solo no distingue el combate.
En 0.5, la calibración observó contexto local −1 → 0 → −1. Un registro posterior
mostró dos solicitudes y dos combates confirmados, sin errores de lectura ni necesidad
de reconectar. El usuario confirmó que terminó la batalla y siguió buscando mobs cercanos.
Solo había una ventana abierta; la prueba real con varios clientes sigue pendiente.

**Comprobado por el usuario:** tras activar Auto Battle y crear el marcador, el cliente
mostró HUNT=1 y el personaje atacó mobs. También se comunicó un cierre al moverlo
manualmente con x32dbg adjunto. La causa sigue pendiente y el registro de esa sesión
se perdió. No se presenta ese cierre como corregido.
El usuario también comunicó un cierre al probar el clic manual con Auto Battle
apagado, marcador desactivado y sin x32dbg. No hay todavía registro de ese segundo
cierre que permita identificar su causa.

La lógica tiene pruebas automatizadas. El workflow de Windows prueba las APIs y
sincronización sobre procesos/objetos propios, compila el puente x86 y comprueba el
arranque del ejecutable empaquetado. La captura 0.6.4 confirmó dos combates después
de recorridos completos y registró otro ataque sin combate observado durante veinte
segundos. El clic manual sobre ese mob sí inició combate, según confirmó el usuario.
La prueba 0.7 confirmó el nuevo sistema en esa sesión; no demuestra que se hayan
resuelto todos los posibles rechazos. Usa el cliente sin adjuntar x32dbg.

Solo se admite la compilación cuyo SHA-256 es
`BC87A0CC5826AA7FB5E4FF10B6B7C1A349962BD8B146AD28EC3FFA9453FE04E6`.

## Mejoras solicitadas y límites actuales

El ciclo selecciona candidatos en el radio configurado. Si están fuera del alcance
3D del cliente, solicita su persecución nativa; al entrar en alcance envía el ataque.
Espera dos observaciones de combate
según el detector calibrado antes de permitir otra. Al volver al mismo mapa, exige
una posición estable durante dos segundos. Si no observa el combate en treinta
segundos, avisa y conserva la espera sin repetir el envío ni elegir otro mob.
Si el combate llega tarde, ejecuta el perfil habilitado. El detector se sigue vinculando a cada
instancia. Los objetivos de combates
confirmados quedan excluidos mientras su identidad siga en la colección activa,
aunque cambien de puesto o queden fuera de los candidatos filtrados. Una consulta
completa que ya no encuentre esa identidad permite retirarla del historial de esa ejecución.
Esto no determina si se ganó la batalla ni
detecta por sí solo los mobs derrotados antes de iniciar el bot.
Detalles y límites en [caza independiente](docs/independent-hunt.md).

**Configurar mercenarios** guarda los nueve puestos, sus nombres, participación y
orden de prioridad en el perfil elegido. Cada puesto admite **Ataque básico** o
**Magia Q/W/E/R/T**, con **Básico alternativo** para el plan de respaldo si la magia
no está disponible. Elige también el objetivo de magia: enemigo, el propio lanzador
o un puesto de tu equipo. **Magia configurada solo en primer turno; básicos después**
viene marcado; desmárcalo para repetir la acción configurada cada turno.
Se conserva en `%LOCALAPPDATA%/AtlanticaPanel/profiles`, fuera de la carpeta del juego.
Guardar no envía acciones. Para ejecutarlo, activa **Ejecutar turnos según el perfil
(experimental)** antes de **Iniciar bot**. El perfil activo queda fijado al iniciar.
Detalles de uso y diagnóstico:
[calibración y perfiles](docs/combat-calibration.md).
La secuencia, sus límites y la captura necesaria se describen en
[turnos de mercenarios](docs/mercenary-turns.md).
La prueba individual todavía no ejecuta el perfil ni recoge botín. Las instrucciones
están en [prueba de básico](docs/basic-battle-trial.md) y
[selección y magia](docs/magic-battle-trial.md).

**Perseguir y atacar (nativo)** es el modo predeterminado; corresponde a la opción
**Ataque nativo por radio** de versiones anteriores.
El radio va de 5 a 500 casillas alrededor del inicio de esa ejecución, con valor
inicial 60. **Atacar solo a mobs en alcance** conserva el ciclo cercano.
**Atacar desde mi posición (experimental)** solicita el combate directo con un mob
del radio sin ordenar acercamiento, incluso si supera el umbral habitual del cliente.
No modifica ese umbral y todavía no se ha validado la aceptación del servidor.
El panel no utiliza las
rutas por rejilla del modo anterior. **Parar bot** cancela nuevas órdenes y solicita
parar una persecución que todavía pueda identificar como propia. Un clic de movimiento
pausa la búsqueda hasta que el personaje queda quieto; entonces centra el radio en
su nueva posición. Una orden de ataque ya aceptada puede terminar
en combate. Detalles: [ataque nativo](docs/native-attack.md). El análisis del
[acercamiento anterior](docs/native-approach.md) queda como referencia de 0.6.

Si no marcas **Ejecutar turnos**, los turnos siguen siendo manuales. El control
nativo anterior sigue en **Más controles** y utiliza `HuntingMode.txt` y Auto Battle.
El ciclo nuevo no modifica ese archivo ni activa Auto Battle.

Como mejora posterior se solicitó estudiar una velocidad configurable solo durante
batallas, restaurando la velocidad normal al salir del combate o parar. No está
implementada ni se ha comprobado qué aceleración admitiría el cliente o el servidor.
Se priorizan los controles, la estabilidad y la caza independiente antes de esa función.

## Panel de inicio, parada y estado

Si abres varios clientes, selecciona su ventana en la lista antes de **Conectar**.
**Elegir ventana** permite activarla con Alt+Tab durante tres segundos. El panel
muestra el PID y vincula la conexión también a la fecha de creación de ese proceso.
No cambia automáticamente a otro cliente cuando se cierra el elegido.

Si varios clientes comparten carpeta, **Activar/Parar caza nativa se bloquean** porque
`HuntingMode.txt` es compartido. Las consultas de objetivos siguen siendo por PID.
Detalles: [varias ventanas](docs/multiple-clients.md).

El ejecutable de GitHub Actions ya incluye Python y el puente x86. Para ejecutar
desde fuentes se requiere Python 3.11+ de 64 bits con Tkinter y compilar el puente
de la sección final:

```powershell
py -3 panel_caza.py
```

1. Elige la ventana y pulsa **Conectar**. Con varios procesos no se elige el primero.
2. Mantén Auto Battle y caza nativa apagados y deja el personaje quieto cerca de mobs.
3. El detector queda listo al conectar. Si necesitas contrastarlo, **Calibrar combate**
   permite capturar mapa → combate → regreso. Tras una prueba individual, reconecta
   al mismo PID antes de iniciar el ciclo.
4. En **Caza y botín**, elige **Modo de ataque al mob**: **Perseguir y atacar (nativo)**
   para el recorrido habitual o **Atacar desde mi posición (experimental)** para
   solicitar combate sin acercarse. Elige el radio (60 casillas inicialmente).
   **Calibrar radio** permite incluir un mob de la lista.
   El punto al iniciar será el centro del área de selección. Configura también la espera
   antes de atacar y, si quieres probarla, la recogida de bonus/botín restante.
   **Guardar opciones del perfil** conserva los cambios; iniciar también los guarda.
5. Para jugar los turnos con el bot, configura el perfil y activa **Ejecutar turnos
   según el perfil (experimental)**. Comprueba en **Mercenarios** los presentes
   cuando empiece la batalla. Pulsa **Iniciar bot**: busca un mob y solicita persecución o ataque según el
   alcance nativo. El cliente ejecuta el desplazamiento.
   El perfil se aplica en orden durante la batalla; sin esa opción, juega manualmente.
6. Al regresar al mapa, el bot vuelve a buscar. Caminar manualmente pausa esa búsqueda
   y la reanuda tras dos segundos quieto. Para cambiar de cliente o terminar la ejecución,
   pulsa **Parar bot** y espera el estado detenido.

**Copiar estado del bot** copia el PID, fase, contadores, detector, perfil, alcance,
primera observación, últimas 24 observaciones y resultado de las solicitudes.
El apartado `native_attack` incluye el destino, identidad, solicitudes nativas,
fallos y respuesta de parada. Los estados de navegación anteriores siguen disponibles
en el diagnóstico. `combat` incluye equipo, órdenes, selección, resultado nativo y
una solicitud pendiente como máximo. Una cola confirmada no
demuestra por sí sola que empezó un combate. Si la calibración no encuentra una
señal, usa **Copiar calibración** para revisar los tres grupos antes de cambiar el detector.

**Exportar diagnóstico** incorpora hasta 100 KiB de código, incluyendo el envío de
movimiento, y el historial del bot si pertenece a esa misma instancia. No incorpora
los nombres de perfiles ni el contenido de los paquetes de red. Una cola vacía
indica que salió de ese búfer; no confirma recepción o aceptación del servidor.

**Exportar combate** requiere estar dentro de una batalla con Auto Battle y caza
nativa apagados. Guarda hasta 1917 KiB de regiones del ejecutable, las observaciones
y los campos acotados de los nueve puestos de esa instancia, sin enviar acciones.
Adjunta el archivo `Atlantica-PID…-combate-….zip`
para continuar con la selección nativa, ataque básico y magias. **X** está registrado
como el control manual de botín; aún no hay recogida automática.
El resultado de la primera captura y las dependencias que faltaban están en
[el análisis de combate](docs/combat-analysis-20261103-074421.md).
La captura ampliada mostró que la ruta BF de selección exige un contexto distinto
del observado en esta batalla. La captura 0.8.2 validó la ruta del contexto normal
y los nueve puestos en el PID 21076. La versión 0.8.3 sigue las tablas del gestor
y del cliente relacionado, porque el contexto comienza con datos, y añade el
código de cliente que faltaba. **Ver mercenarios** muestra puesto, nombre
del perfil y tipo leído; no confirma disponibilidad para actuar. El diagnóstico
incluye los errores de lectura si todavía no puede validar los puestos.
La captura 0.8.3 resolvió el gestor `cltBattleManagerClient` y permitió seguir la
ruta del clic manual hasta la solicitud de básico. La versión 0.9 limita esa tabla
a sus 13 entradas comprobadas, antes de una cadena UTF-16 que parecía código por
su valor numérico. Detalles: [prueba de básico en combate](docs/basic-battle-trial.md).

La selección de cliente queda bloqueada mientras termina el trabajador. Si se cierra
el juego, se detiene; abrir otro cliente exige Conectar. Cambios de mapa,
activación de Auto Battle o errores inciertos detienen el ciclo. El movimiento manual
pone la búsqueda en pausa; una entrada en combate tiene prioridad sobre esa pausa.
Cerrar el panel solicita parar y espera al trabajador. Una solicitud ya encolada
puede completarse; Parar bot no cancela un combate que ya empezó.

**Más controles** conserva la prueba individual y el control de la caza nativa.
Para esta última sí hace falta Auto Battle. Sus botones modifican el marcador y
su parada tarda hasta la siguiente comprobación del cliente. Con el juego cerrado,
Seleccionar carpeta permite **Parar caza nativa**. Cerrar el panel no retira ese
marcador; si sigue activo se conserva la advertencia anterior.

## Contexto para la siguiente etapa

En 0.3, **Probar un ataque (experimental)** comprueba el candidato más cercano y
envía como máximo una solicitud desde el hilo de la ventana elegida. Acércate antes
al mob y deja Auto Battle y caza nativa apagados. No mueve al personaje ni repite
ataques. **Copiar prueba** guarda el resultado en el portapapeles para contrastarlo
con lo ocurrido en el juego. Tras encolar o recibir un resultado incierto, comprueba
el cliente y reconecta antes de otra prueba. No se confirma batalla por el mero envío.

El ejecutable incluye un auxiliar y DLL x86 propios para esa solicitud y el ciclo.
Se cargan para solicitar una acción. La conexión normal y Ver objetivos
siguen usando las APIs de consulta y lectura. La prueba no cambia Auto Battle ni
el marcador de ninguna carpeta. El código está en `native/`; sus controles y límites
se explican en [el tercer análisis](docs/context-analysis-20261102-190839.md).

La versión 0.2 añade **Ver objetivos** después de Conectar. La consulta no exige
Auto Battle ni un contador positivo: muestra candidatos del mapa y su distancia
de rejilla. **Copiar resultados** copia un resumen con el personaje y los diez
candidatos más cercanos para contrastarlo con el juego. No envía acciones de ataque
y quedan comprobaciones de selección pendientes.

La versión 0.2.1 consulta la lista activa identificada en la segunda captura y omite
los punteros de la tabla ajenos a ella. Separa las entradas inactivas y los rechazos
por identidad de los cambios de puntero observados. Valida que la lista no cambie
durante la consulta.

El botón **Exportar diagnóstico** está disponible después de Conectar, incluso con
Auto Battle apagado. La captura actual guarda hasta 100 KiB de código más un
manifiesto para estudiar la validación del objetivo y preparación del envío.
La operación solo lee esas regiones y no inicia la caza. Los detalles están en
[el plan del modo independiente](docs/independent-mode.md).

## Control por comandos

Estas órdenes solo gestionan el archivo; no confirman el estado real del proceso:

```powershell
py -3 controlar_caza.py status --directory "C:\ruta\Atlantica"
py -3 controlar_caza.py start --directory "C:\ruta\Atlantica"
py -3 controlar_caza.py stop --directory "C:\ruta\Atlantica"
```

La carpeta debe ser la carpeta de trabajo real del juego. Al parar, el marcador se
renombra a `HuntingMode.txt.disabled.atlantica-bot`; al iniciar, se restaura su contenido.
Los archivos preexistentes se conservan. Si existen simultáneamente el marcador y
la copia desactivada, se informa del conflicto sin sobrescribirlos. Los demás modos
(`HoldMode.txt`, `UseBuffItems.txt`) conservan su configuración.

El cliente tarda hasta su siguiente comprobación en aplicar el marcador. Usa el
estado confirmado del panel y el control Auto Battle del juego para controlar la parada.

## Diagnóstico del cliente

1. Instala [Python 3.11 o posterior de 64 bits](https://www.python.org/downloads/windows/),
   incluyendo el lanzador `py`.
2. Descarga este proyecto y abre Atlantica Online.
3. Haz doble clic en `diagnosticar_cliente.bat`.
4. Conserva el archivo `diagnostico-cliente-*.json` que aparecerá en esta carpeta.

No hace falta instalar paquetes externos para usar el diagnóstico. No se necesita
el token, la contraseña ni el nombre de tu cuenta del juego.

El lanzador primero prueba las APIs de Windows leyendo un buffer de su propio proceso.
Después identifica `Atlantica.exe`, obtiene el hash SHA-256, la arquitectura y la
versión del ejecutable en disco, consulta la base del módulo principal y trata de leer
los dos bytes de su cabecera `MZ`. Una lectura correcta de esa cabecera **no demuestra**
que ya podamos localizar mobs ni ordenar ataques.

El informe incluye el nombre del proceso, PID, versión, hash, arquitectura y dirección
base temporal. No incluye la ruta de instalación, credenciales ni un volcado de memoria.
La dirección base puede cambiar al reiniciar el cliente y no es un offset de un mob.
El informe se guarda localmente y la herramienta no lo envía a ningún servidor.

### Si el ejecutable tiene otro nombre

Abre una terminal en esta carpeta:

```powershell
py -3 diagnosticar.py processes --contains Atlantica
py -3 diagnosticar.py diagnose --process NombreDelCliente.exe
```

Si hay varios clientes abiertos, selecciona el PID que muestra el Administrador de tareas:

```powershell
py -3 diagnosticar.py diagnose --pid 1234
```

La herramienta solicita permisos de consulta y lectura. Si Windows deniega el acceso,
el informe se marca como parcial. El error se conserva como resultado pendiente de
diagnóstico; no se activan privilegios de depuración ni se modifica la protección del proceso.

Los informes no se sobrescriben. Para elegir una salida, usa un archivo que no exista:

```powershell
py -3 diagnosticar.py diagnose --output mi-informe.json
```

Códigos de salida: `0` diagnóstico completo, `1` error que impide completarlo,
`2` informe parcial guardado sin verificación de lectura. En esta etapa, «completo»
se refiere exclusivamente al diagnóstico técnico, no a un bot funcional.

## Qué falta para el bot

Se recibió y analizó estáticamente el ejecutable exacto. Su hash coincide con el
informe del usuario; es un cliente x86 de 32 bits y muestra indicios de
empaquetado/protección. Los resultados y sus límites están en
[el informe de análisis](docs/client-analysis.md).

La ruta encontrada permite consultar candidatos y solicitar persecución/ataque sin
Auto Battle desde el panel. El ciclo nativo 0.7 se observó en seis combates; la
ejecución de turnos sigue pendiente del análisis del código de batalla. Las
actualizaciones del cliente requieren volver a comprobar la compilación, sus lecturas
y el comportamiento del modo nativo antes de reutilizar este control.

## Desarrollo en la nube

La nube actual ejecuta Linux y tiene una copia del ejecutable para análisis estático;
no dispone de un cliente del juego en ejecución. Permite desarrollar y probar el
analizador PE, la selección de procesos, los informes, la CLI y el manejo de las
lecturas mediante una API simulada. La prueba nativa se ejecuta únicamente en Windows.

Usa el checkout existente en `/workspace/Bot`; cada tarea ya tiene un entorno aislado
y no necesita un worktree adicional.

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run atlantica-bot --help
```

En Windows puedes verificar la integración real sin abrir el juego:

```powershell
py -3 diagnosticar.py self-test
```

El diagnóstico no necesita un servidor local, Docker ni servicios en segundo plano.

## Compilar el panel para Windows

El workflow preparado en `.github/workflows/windows-panel.yml` ejecuta los tests en
Windows, compila `AtlanticaPanel.exe` con PyInstaller y prueba su arranque sin conectarse
al juego. Compila además el auxiliar/DLL x86 con MSVC y prueba su hook sobre una
ventana propia, exigiendo el rechazo de la compilación ajena al juego. Se inicia manualmente desde
GitHub Actions o al subir la rama `codex/panel-caza`. Su artefacto será
`AtlanticaPanel-Windows`, con el ejecutable y su SHA-256. La primera compilación
remota terminó correctamente en
[GitHub Actions](https://github.com/KainNw/Bot/actions/runs/41502671707).

También se puede compilar localmente en Windows:

```powershell
uv sync --frozen --group build
cmake -S native -B build/native -A Win32
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
uv run --frozen --group build pyinstaller --noconfirm --clean --onefile --windowed --noupx --name AtlanticaPanel --paths src --add-binary "build/native/Release/AtlanticaBridge.exe;native" --add-binary "build/native/Release/AtlanticaHook.dll;native" panel_caza.py
```

La compilación de Windows debe hacerse en Windows. El ZIP de fuentes se prepara con
`python tools/package_diagnostic.py`; incluye el panel, controles, tests y documentación,
sin el ejecutable del juego ni los bloques de memoria que aportó el usuario.
