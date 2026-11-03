# Gestor y cliente del combate normal

Se verificaron los 29 bloques y sus SHA-256 de
`Atlantica-PID21076-combate-20261103-085549.zip`: panel 0.8.2, esquema 4,
692 KiB. La instancia es PID 21076, creación `134381859857067996`.
Auto Battle, caza nativa y `native_active` están apagados. Antes y después,
el personaje tiene contexto A (`actor+318`) = 0 y contexto B (`actor+254`) = −1.
El informe del bot registraba dos solicitudes y dos combates observados.

## Lectura comprobada de los puestos

El lector resolvió `owner+091C` y el contexto indexado por A. Los nueve registros
de miembros se leyeron completos y sin error, en esta nueva instancia del juego:

| Puesto | Tipo leído |
| --- | --- |
| 1 | 2318 |
| 2 | 3569 |
| 3 | 3757 |
| 4 | 3575 |
| 5 | 3570 |
| 6 | 3565 |
| 7 | 3777 |
| 8 | 3697 |
| 9 | 3727 |

Esto valida la colección del personaje local en esa muestra. No establece qué
mercenario tiene turno, sus puntos de acción ni los nombres de sus habilidades.
Los valores `+4C` y `+50` conservan sus nombres de diagnóstico. La ruta BF sigue
sin corresponder al contexto observado y sus acciones no se habilitan.

## Diferencia entre el contexto y su gestor

El bloque nuevo `004F0000–00520000` permite comprobar lo siguiente:

| Código | Comportamiento observado |
| --- | --- |
| `004F8903` | Construye el gestor y una colección de contextos de `A498` bytes, inicializados por `004FF041`. |
| `004FDFE0` | Busca una identidad entre seis participantes desde `contexto+B4`, con paso de 12 bytes. |
| `004FE29F` | Resuelve dos participantes y compara sus etiquetas de grupo en `contexto+11A`. |
| `004FE4FA` | Resuelve una unidad por participante y puesto, con paso de `170` bytes desde `contexto+4BC`. |
| `0050064F` | Lee el gestor de `owner+091C` y llama al método virtual `+18` de su tabla. |
| `004FDDD7` | Invoca `005A481F` sobre el objeto de cliente de `owner+16358`. |

El contexto comienza con datos. La primera palabra observada no apunta a la
sección de solo lectura, por lo que 0.8.2 no la siguió. El despacho virtual
comprobado pertenece al gestor, no a ese contexto. La tabla de la construcción
común aparece en `042D8E54`; otra construcción coloca `042D8AA4`. Esas direcciones
quedan fuera de las constantes normales elegidas en 0.8.2.

El objeto de cliente de `owner+16358` es distinto del objeto `owner+16360`
consultado por la ruta BF. La llamada a `005A481F` se identificó en el código
capturado, pero su implementación todavía no está en este ZIP. El ejecutable
protegido en disco no proporciona el código cargado que falta.

También se encontraron colas y constructores de mensajes en el código común.
No se interpretan sus números como órdenes de ataque básico sin resolver antes
la función de cliente, su receptor, argumentos y validaciones de turno/objetivo.

## Corrección de la captura en 0.8.3

El lector comprueba dos firmas adicionales contra esta captura: los 19 bytes del
despacho virtual en `0050064F` y los 15 bytes de la llamada en `004FDDD7`.
Obtiene la tabla desde el gestor y, por separado, la del objeto de cliente
relacionado. Conserva la primera palabra del contexto solo como valor informativo.
Las direcciones de ambos objetos y sus tablas se comprueban de nuevo al terminar.

Se añade el código `00590000–005C0000` (192 KiB) y se corrigen las constantes
normales a `042D8000–042DC000` (16 KiB). Se siguen hasta 64 entradas por tabla,
solo dentro de las secciones conocidas de la imagen y reutilizando bloques.
No se ejecutan esas entradas ni se exportan bloques completos de objetos del heap.
El máximo es 1916,5 KiB más manifiesto; el conjunto fijo ocupa 892 KiB.

Las pruebas usan memoria simulada para comprobar el origen de las tablas,
la separación respecto al dato del contexto, la reutilización de código, los
límites y los cambios de contexto. Las cuatro firmas se contrastaron con los
binarios de esta captura. Falta probar la corrección en el cliente real y analizar
el código que añade antes de habilitar ataques de mercenarios. Los turnos siguen
siendo manuales; no se modifica la caza ni sus tiempos.
