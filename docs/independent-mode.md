# Caza independiente: contexto que falta analizar

Objetivo activo: iniciar desde el panel manteniendo Auto Battle apagado. El modo
nativo sigue necesitando ese indicador dentro del cliente; retirar únicamente el
bloqueo de nuestra interfaz no elimina esa dependencia.

La primera captura se recibió con Auto Battle apagado, B=28 y HUNT=0. Se verificó
su integridad y se analizaron los cuatro bloques: hay información de tabla/getters,
constructor de mensajes y un despachador indirecto. Falta identificar el destino
real y el contexto de ejecución del método de envío. No hay todavía una API de ataque
validada. El usuario también comunicó un cierre al probar el clic manual sin caza,
Auto Battle ni x32dbg; falta su registro. Véase
[el análisis del contexto](context-analysis-20261102.md).

La prioridad inmediata confirmada es seleccionar mobs e iniciar encuentros con
Auto Battle apagado. También se pidió jugar los turnos de los mercenarios, pero el
usuario indicó avanzar primero con los mobs. Los turnos quedan para después.

## Captura acotada desde el panel

La actualización incorpora **Exportar diagnóstico**. Funciona con Auto Battle apagado
y no requiere adjuntar un depurador. Después de **Conectar**, permite guardar un ZIP
con estas regiones fijas de la sección de código de la compilación comprobada:

| Región candidata | Dirección inicial | Tamaño |
| --- | --- | --- |
| Contexto del auxiliar `0040C4E9` | `0040C000` | 8 KiB |
| Getters del personaje y auxiliar `0043652D` | `00435000` | 8 KiB |
| Selección de objetivos y auxiliares `0044CF2D`/`0044D39F` | `0044C000` | 8 KiB |
| Auxiliares de vectores y distancia | `0043A000` | 4 KiB |
| Identidad y comprobación adicional del objetivo | `00433000` | 8 KiB |
| Índices activos de la colección | `00446000` | 4 KiB |

La versión 0.2 también resuelve por lectura el destino del método virtual del
despachador. Si la tabla y el método están en las regiones conocidas de la imagen,
incluye hasta 8 KiB de su código. De lo contrario, registra la limitación sin
exportar regiones arbitrarias fuera de esas secciones.

El manifiesto incluye el hash del cliente, PID de esa captura, direcciones, tamaños
y hashes de los bloques. No incluye la ruta personal de instalación ni vuelca objetos
del jugador. Solo resuelve punteros de métodos y un contexto numérico del cliente
para el manifiesto. Se comprueba la sesión antes y después de
leer, además del hash de compilación y una instrucción conocida del bloque anterior.
Las lecturas cortas o vacías se rechazan; no se sobrescriben archivos existentes.

Los nombres de los bloques describen candidatos para investigar, no funciones
confirmadas de combate. La captura no llama esas funciones ni cambia el marcador
de caza, el indicador Auto Battle o instrucciones del proceso.

Uso opcional desde el checkout en Windows:

```powershell
py -3 diagnosticar.py capture --output Atlantica-contexto.zip
```

## Siguiente validación

Con el ZIP recibido se estudiarán argumentos, rutas de control, estructura de la
colección de objetivos y efectos de los auxiliares. Después habrá que contrastar
los candidatos con el clic manual normal antes de incorporarlos al modo independiente.
La caza independiente todavía no se presenta como implementada.

## Lectura independiente de candidatos

**Ver objetivos** permite contrastar las lecturas ya identificadas sin invocar
funciones internas ni exigir Auto Battle. Se limita a los índices 1–449 admitidos
por el auxiliar capturado. Identifica al personaje local en el índice 1, lee la
rejilla con los getters analizados y ordena por `abs(dx)+abs(dy)`.

Se aplican los filtros conocidos de ID, estado, flags y mapa. Aún faltan la pertenencia
a índices activos y `00433A4A`; por ello los resultados son candidatos, no objetivos
completamente validados para atacar. Se contabilizan lecturas fallidas, cambios de
puntero y causas de rechazo. Si cambia la escena o el personaje durante la consulta,
se invalida el resultado. El resumen se copia al portapapeles solo a petición del usuario.
