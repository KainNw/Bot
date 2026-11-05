# Turnos de mercenarios 0.12.1

El panel puede aplicar el perfil durante las batallas con Auto Battle apagado.
Ordena una acción por mercenario y turno, siguiendo la prioridad configurada y
usando solo los miembros presentes y vivos. Si llevas dos miembros, omite los otros
siete. Cuando no observa enemigos vivos, deja de enviar acciones, aunque todavía
queden mercenarios sin actuar. Espera el final real del combate y el regreso estable
al mapa para reanudar la caza. Los tiempos de persecución y ataque de 0.7 se conservan.

El usuario confirmó visualmente el básico individual de 0.9 y la magia Q de 0.10.
En la primera prueba automática de 0.11, PID 21076, el cliente seleccionó al miembro
1 y encoló Q (acción 207) en el turno 0, sin excepción. Se leyeron nueve miembros
presentes. El usuario confirmó que Q derrotó a todos los enemigos; el bot omitió las
órdenes de los otros ocho y quedó esperando el final real de la batalla, sin exigir
reconexión. Esa captura aún no comprueba el regreso al mapa, una secuencia entre
varios miembros, los básicos posteriores, un equipo de dos ni varias ventanas.
La recogida con X sigue pendiente.

Desde 0.12, **Vista general** abre el resumen flotante inspirado en la referencia
del usuario. El puesto 1 se llama **Main (1)** en el resumen, tabla, editor,
objetivos propios y órdenes; los demás conservan **Mercenario 2–9**. Esto identifica
el puesto nativo y no cambia la prioridad configurada. La vida procede de las unidades
presentes leídas; fuera de la batalla se limpia. Detalles: [Vista general](overview.md).

## Configurar y empezar

1. Con el bot detenido, abre **Configurar mercenarios** en el perfil elegido.
2. Habilita los puestos que quieras usar. Los miembros que llevas se eligen dentro
   del juego; el perfil no añade ni retira mercenarios de la batalla.
3. Elige **Ataque básico** o **Magia Q/W/E/R/T** por miembro. Para magia, elige
   **Enemigo**, **Sí mismo** o un puesto de tu equipo como objetivo. Solo usa vivos.
4. Usa **Subir/Bajar** para ordenar las filas. Primero solicita la acción de la
   primera fila habilitada y presente, después la siguiente.
5. Mantén **Magia configurada solo en primer turno; básicos después** para lanzar
   la magia en el primer turno propio de cada batalla y básicos en los posteriores.
   Desmarca esa opción para repetir la acción configurada cada turno.
6. Guarda el perfil. En **Control**, activa **Ejecutar turnos según el perfil
   (experimental)** y pulsa **Iniciar bot**, con Auto Battle y caza nativa apagados.
7. Abre **Mercenarios** durante el combate: muestra siempre los puestos 1–9,
   presencia, estado vivo/caído, **Usar bot**, prioridad, acciones y última orden.
   **Actualizar equipo** consulta; **Usar/omitir seleccionado en bot** modifica
   el perfil solo con el bot detenido. Los nombres son los del perfil, no nombres
   de clase reconocidos automáticamente. La numeración es la del registro nativo.
8. Tras una batalla, pulsa **Parar bot**, comprueba el orden en pantalla y comparte
   **Copiar estado PID …**. No hace falta adjuntar x32dbg.

Ejemplo: coloca Mercenario 2 primero con Q y objetivo Enemigo; Main (1) después
con básico. Si ambos están presentes, solicita Q del 2 y luego básico del 1; en los
turnos siguientes, básicos en ese mismo orden. Si el primer ataque elimina al último
enemigo, no solicita la segunda acción.

## Disponibilidad, espera y parada

La [recuperación de 0.12.1](recovery.md) prioriza el combate durante un desplazamiento,
consulta el índice actual del contexto normal en lugar de fijarlo a cero y permite
comprobar de nuevo los estados nativos 27–29, que retornan antes del envío. Son como
máximo tres comprobaciones por miembro y turno, separadas por al menos 250 ms y una
lectura nueva. Los envíos aceptados y los resultados inciertos conservan la política
de no duplicar la orden.

Desde 0.11.1, después de seleccionar al mercenario se releen de inmediato el turno,
las unidades y la barra, y se puede pedir Q/W/E/R/T en esa misma iteración. Se elimina
la pausa de un ciclo que separaba selección y magia; el registro de 0.11 mostraba
563 ms entre ambas. Nunca se usa la barra anterior a la selección.

Desde 0.22.0, la revisión pasa a 100 ms cuando se espera la preparación del combate,
una orden propia o el resultado de una solicitud ya encolada. También revisa a ese
ritmo el botín restante cuando está habilitado. Los turnos enemigos posteriores sin
orden pendiente conservan la frecuencia anterior. Cada iteración ejecuta como máximo dos
llamadas: selección y acción, o dos selecciones si cambia la disponibilidad del plan.
La primera acción encolada termina esa iteración. Desde 0.12.1, la carga inicial de
enemigos y las lecturas transitorias de combate también pueden recuperarse a 100 ms.
La tolerancia de lectura se mide en tiempo: con turnos automáticos, no se detiene
tras solo tres intentos rápidos; permite hasta tres segundos de lecturas fallidas
consecutivas. Los tiempos normales de caza en el mapa no cambian.

El objetivo de adelantar Q es dejar más tiempo al robot NeoACA de la formación para
recoger dentro del primer turno. El registro de 0.11.1 mostró 63 ms entre selección y
solicitud de Q, frente a 563 ms en 0.11.0, estado 32 sin excepción y solicitud en el
turno 0. Se observó el regreso al mapa y una parada solicitada durante la reanudación.
El usuario confirmó que NeoACA recogió y la batalla terminó en el primer turno.
La animación, recogida y cierre del combate siguen dependiendo del juego; la prueba
no valida todavía otras formaciones, habilidades o secuencias entre varios miembros.

La ejecución espera el turno del grupo y el estado nativo del mercenario. Para magia,
selecciona ese miembro con el selector del cliente, lee su barra actual y solicita
la tecla configurada. No usa teclas globales ni cambia el foco entre ventanas.
El cliente comprueba puntos de acción, coste, recarga y objetivo; el bot no modifica
esos valores ni obliga a actuar a los nueve puestos.

Hay como máximo una orden pendiente. Una respuesta de cola no confirma un golpe:
se esperan cambios observables de animación, vida, valor del miembro o turno antes
de continuar. Esos cambios tampoco se etiquetan como impacto confirmado. Si no hay
progreso en doce segundos, se detiene sin repetir la solicitud y exige reconectar.
También se detiene ante selección cambiada durante la solicitud o resultados inciertos.
Si se ha observado la animación completa, espera 200 ms de reposo antes de pasar
al siguiente miembro. Un cambio de vida o recursos sin animación observada mantiene
la espera de 500 ms. Una respuesta de cola por sí sola nunca inicia esta espera.

**Básico alternativo** se aplica si falta la magia de esa tecla/objetivo o si la
función nativa rechaza la magia sin enviarla. Si lo desmarcas, omite ese mercenario
durante ese turno. No usa básico alternativo después de un envío incierto. Los
rechazos de básico se acotan a cada par mercenario/objetivo; no repite ese par en
el mismo turno. La reserva de una orden por miembro/turno se comparte con las pruebas
individuales y los reinicios del bot dentro de la conexión.

Si inicias el bot en mitad de una batalla avanzada, usa básicos hasta la siguiente
batalla en modo de magia inicial; no lanza tarde la apertura. Si el enemigo actúa
primero en una batalla que el bot vio empezar, espera el primer turno propio.
La opción queda desmarcada al abrir el panel. Guardar el perfil no activa acciones.
Parar bot cancela nuevas solicitudes; una ya aceptada puede terminar.

`combat` en **Copiar estado** contiene el equipo, última orden por puesto, historial
acotado, respuestas nativas y acción pendiente. La exportación de código incluye
ese diagnóstico sin los nombres personales del perfil. El perfil usa esquema 7;
carga los esquemas 1–6 sin reescribirlos hasta que guardes. Se conservan sus nombres,
orden, acciones y selección; los perfiles anteriores mantienen una espera de 1 s
para el NeoACA. Las comprobaciones de recogida tienen su propio límite de tres
rechazos sin envío por miembro/turno, separado del de ataque.

Las pruebas individuales siguen disponibles tras **Parar bot**:
[básico](basic-battle-trial.md) y [selección/magia](magic-battle-trial.md).
Actualizar, elegir listas y copiar solo leen; **Probar acción (experimental)** sí
solicita la acción. **Seleccionar en juego** cambia el miembro activo sin atacar.

## Controles comunicados por el usuario

| Acción | Entrada manual |
| --- | --- |
| Seleccionar mercenario | Números 1–9 |
| Ataque básico | Clic izquierdo en el enemigo |
| Magia | Q, W, E, R o T y el enemigo |
| Recoger botín | X |

Estas entradas orientan la búsqueda de funciones nativas. No establecen direcciones
de memoria ni confirman que exista una unidad habilitada para actuar. La selección
de objetivo, turno, puntos de acción, maná, disponibilidad y alcance de la magia
todavía requieren análisis. Tampoco se ha implementado la recogida automática.

## Exportar el código de combate

1. Abre el panel 0.12.1 y conecta con la ventana elegida.
2. Mantén Auto Battle y caza nativa apagados.
3. Entra en combate manualmente o con el ciclo de caza que ya funciona. El panel
   permite exportar en batalla. Para facilitar la captura, para el bot antes.
4. Durante el combate, pulsa **Exportar combate** y guarda un archivo nuevo.
5. Adjunta al chat el ZIP `Atlantica-PID…-combate-….zip`.

**Ver mercenarios** consulta los nueve puestos durante esa batalla. El tipo se
obtiene del cliente y los nombres proceden del perfil; un nombre del perfil no
confirma la identidad leída. **Actualizar** repite la consulta y **Copiar mercenarios**
incluye el contexto y los valores sin asignarles todavía puntos de acción o maná.
La exportación incorpora esta misma información, también si no pudo leer los puestos.

La exportación solo lee código, constantes del ejecutable y observaciones. No
selecciona mercenarios, envía teclas ni ejecuta funciones del juego. Comprueba que
la instancia siga en combate antes y después de la lectura; si sale de la batalla o la lectura falla, no crea
una captura etiquetada como válida. No hace falta adjuntar x32dbg.

Desde fuentes también se puede exportar con:

```powershell
py -3 diagnosticar.py capture --pid 1234 --combat --output combate.zip
```

## Contenido y siguiente análisis

El manifiesto de combate usa esquema 4 y contiene PID/creación, hash de la
compilación, observaciones antes/después, detector y los controles comunicados.
Cada bloque indica `kind=code` o `kind=readonly_constants`.
El contexto básico de la exportación conserva `turn_state_verified=false` y
`turn_execution_available=false`: resolver ese contexto por sí solo no establece
disponibilidad para actuar. El visor ampliado y el ejecutor leen además unidades,
grupos y turno; el puente comprueba la disponibilidad y el ataque con las funciones
del cliente. El perfil y el visor ampliado anuncian la capacidad nueva; la opción
**Ejecutar turnos** es la que permite usarla durante la ejecución.

Añade estos bloques a la exportación normal de hasta 100 KiB:

| Bloque | Dirección | Tamaño |
| --- | --- | --- |
| Acciones de personajes de batalla | `00520000` | 64 KiB |
| Datos y consultas de personajes de batalla | `00530000` | 64 KiB |
| Gestor de información de miembros | `004EC000` | 16 KiB |
| Selección de personajes | `00444000` | 8 KiB |

Estos bloques de 0.8.0 suman 152 KiB. Cubren
referencias observadas a `CanAttackObject`, `IsInAttackRange`, `CanMoveAttack` y
`IsEnableRangeAttackByMan`. Sus nombres son pistas para el análisis, no funciones
de ejecución ya verificadas. El ejecutable en disco tiene código protegido y
no proporciona por sí solo estas instrucciones cargadas.

La [primera captura](combat-analysis-20261103-074421.md) identificó llamadas a
implementaciones del cliente fuera de esos bloques. La versión 0.8.1 añade
232 KiB de sus dependencias de código y 8 KiB de tablas de métodos/cadenas
constantes en la sección de solo lectura de la imagen. El total máximo es
492 KiB más el manifiesto; la exportación normal conserva su máximo de 100 KiB.
El cambio no habilitó acciones ni recogió bloques de memoria de objetos del juego.

La [segunda captura](normal-combat-analysis-20261103-081115.md) mostró la diferencia
entre esa ruta BF y la que utiliza el contexto local observado. Desde 0.8.2 se añaden
192 KiB de código del gestor normal y constantes, junto con un informe
estructurado de su contexto y los nueve miembros. No se ejecutan sus funciones.
Los valores de miembro `4C` y `50` conservan sus nombres de diagnóstico; no se usan
para decidir si se puede atacar o lanzar magia.

La [captura del PID 21076](normal-combat-analysis-20261103-085549.md) confirmó los
nueve puestos, pero mostró que el contexto comienza con datos. En 0.8.3 se lee
la tabla candidata desde el gestor de `owner+091C`, cuyo despacho virtual aparece
en `0050064F`, y desde el objeto de cliente de `owner+16358`, usado por `004FDDD7`.
La primera palabra del contexto se conserva como dato; no se sigue como tabla.

Se añaden 192 KiB de código en `00590000–005C0000`, que incluyen la llamada
`005A481F`, y se corrigen las constantes normales a `042D8000–042DC000` (16 KiB).
Para cada uno de los dos objetos, si la tabla señala la sección de solo lectura
y sus tres primeras entradas señalan código, se exportan sus 256 bytes y hasta
64 regiones de código de 8 KiB. Se reutilizan los bloques ya capturados.
Estas comprobaciones acotan candidatos para el análisis; no identifican por sí
solas qué hace cada función. No se llama a sus métodos.
El manifiesto registra por separado `normal_method_resolution` y
`normal_client_method_resolution`, sus límites y entradas resueltas.
El total fijo es 892 KiB y el máximo con métodos es 1916,5 KiB, más el manifiesto.
La exportación normal sigue limitada a 100 KiB. No hay volcados de bloques de heap.

Desde 0.10, la colección normal de unidades no se sigue como tabla virtual: su
primera palabra es un dato que cambió de 0 a `00120000` en los informes recibidos.
Se conserva como diagnóstico y se excluye del vínculo de identidad. Los punteros
de colección, personaje, contexto y gestor siguen comprobándose.

El ZIP no incluye nombres de los perfiles, chat ni contenido de paquetes de red.
Los bloques tienen tamaño fijo y SHA-256; se conserva el archivo de destino si
ya existe. La captura 0.8.3 permitió incorporar la primera prueba de básico por PID.
El registro del PID 21076 de las 10:01:43 y la respuesta del usuario confirmaron
el primer básico. La lectura de los nueve miembros, siete enemigos y turno local
se completó y el cliente encoló el ataque sin excepción. El golpe fue comprobado
visualmente por el usuario; el programa todavía no lo confirma por sí solo.
