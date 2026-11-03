# Turnos de mercenarios 0.8

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

1. Abre el panel 0.8 y conecta con la ventana elegida.
2. Mantén Auto Battle y caza nativa apagados.
3. Entra en combate manualmente o con el ciclo de caza que ya funciona. El panel
   permite exportar mientras el ciclo está pausado dentro de la batalla.
4. Durante el combate, pulsa **Exportar combate** y guarda un archivo nuevo.
5. Adjunta al chat el ZIP `Atlantica-PID…-combate-….zip`.

La exportación solo lee código y observaciones. No selecciona mercenarios, envía
teclas ni ejecuta funciones del juego. Comprueba que la instancia siga en combate
antes y después de la lectura; si sale de la batalla o la lectura falla, no crea
una captura etiquetada como válida. No hace falta adjuntar x32dbg.

Desde fuentes también se puede exportar con:

```powershell
py -3 diagnosticar.py capture --pid 1234 --combat --output combate.zip
```

## Contenido y siguiente análisis

El manifiesto de combate usa esquema 3 y contiene PID/creación, hash de la
compilación, observaciones antes/después, detector y los controles comunicados.
Conserva `turn_state_verified=false` y `turn_execution_available=false`: detectar
la batalla no identifica el turno del mercenario.

Añade estos bloques a la exportación normal de hasta 100 KiB:

| Bloque | Dirección | Tamaño |
| --- | --- | --- |
| Acciones de personajes de batalla | `00520000` | 64 KiB |
| Datos y consultas de personajes de batalla | `00530000` | 64 KiB |
| Gestor de información de miembros | `004EC000` | 16 KiB |
| Selección de personajes | `00444000` | 8 KiB |

El máximo total es 252 KiB de código, más el manifiesto. Los bloques cubren
referencias observadas a `CanAttackObject`, `IsInAttackRange`, `CanMoveAttack` y
`IsEnableRangeAttackByMan`. Sus nombres son pistas para el análisis, no funciones
de ejecución ya verificadas. El ejecutable en disco tiene código protegido y
no proporciona por sí solo estas instrucciones cargadas.

El ZIP no incluye nombres de los perfiles, chat ni contenido de paquetes de red.
Los bloques tienen tamaño fijo y SHA-256; se conserva el archivo de destino si
ya existe. El siguiente paso es localizar los objetos de batalla y seguir sus
validaciones antes de incorporar una primera orden nativa comprobable por PID.
