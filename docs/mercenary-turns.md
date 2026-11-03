# Turnos de mercenarios 0.8.2

El panel guarda el plan de cada mercenario: puesto, nombre, participación, prioridad,
ataque básico o magia Q/W/E/R/T y la preferencia de usar básico si la magia no está
disponible. Todavía no ejecuta esas acciones; el ciclo de caza pausa durante la
batalla para que juegues los turnos manualmente. El delay de persecución y ataque
de 0.7 se conserva.

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

1. Abre el panel 0.8.2 y conecta con la ventana elegida.
2. Mantén Auto Battle y caza nativa apagados.
3. Entra en combate manualmente o con el ciclo de caza que ya funciona. El panel
   permite exportar mientras el ciclo está pausado dentro de la batalla.
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
Conserva `turn_state_verified=false` y `turn_execution_available=false`: detectar
la batalla no identifica el turno del mercenario.

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
192 KiB de código del gestor normal y 8 KiB de constantes, junto con un informe
estructurado de su contexto y los nueve miembros. No se ejecutan sus funciones.
Los valores de miembro `4C` y `50` conservan sus nombres de diagnóstico; no se usan
para decidir si se puede atacar o lanzar magia.

Si la primera palabra del contexto señala una tabla de métodos dentro de la sección
de solo lectura y sus tres primeras entradas señalan código, se exportan sus 256
bytes y hasta 24 regiones de código de 8 KiB. Se reutilizan los bloques ya capturados.
La tabla se conserva como candidata para el análisis, no como autorización para
llamar a sus métodos. El manifiesto registra el límite y las entradas resueltas.
El total fijo es 692 KiB y el máximo con métodos es 884,25 KiB, más el manifiesto.
La exportación normal sigue limitada a 100 KiB. No hay volcados de bloques de heap.

El ZIP no incluye nombres de los perfiles, chat ni contenido de paquetes de red.
Los bloques tienen tamaño fijo y SHA-256; se conserva el archivo de destino si
ya existe. El siguiente paso es localizar los objetos de batalla y seguir sus
validaciones antes de incorporar una primera orden nativa comprobable por PID.
