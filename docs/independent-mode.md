# Caza independiente: contexto que falta analizar

Objetivo activo: iniciar desde el panel manteniendo Auto Battle apagado. El modo
nativo sigue necesitando ese indicador dentro del cliente; retirar únicamente el
bloqueo de nuestra interfaz no elimina esa dependencia.

Ya se analizó la función que contiene los textos `Attack Monster`. Falta el código
de sus auxiliares: el ejecutable original está empaquetado y no contiene esas zonas
en la forma observada durante la ejecución. No se ha identificado una API de ataque
normal ni su contexto de llamada. El usuario también comunicó un cierre al probar
el clic manual con la caza y Auto Battle apagados y sin x32dbg; falta su registro.

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

El manifiesto incluye el hash del cliente, PID de esa captura, direcciones, tamaños
y hashes de los bloques. No incluye la ruta personal de instalación ni lee memoria
de objetos del jugador para exportarla. Se comprueba la sesión antes y después de
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
