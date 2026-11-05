# Nombre automático del Main

Desde **0.21.0**, al pulsar **Conectar** el panel intenta leer el nombre del
personaje principal de la instancia elegida. Lo muestra en **Nombre del Main**,
en la cabecera, en el título de Windows y en la vista general.

Cuando el nombre se obtiene del juego, el campo indica **Nombre leído del
personaje principal del juego** y queda de solo lectura. Si el cliente aún está
cargando o la consulta falla, muestra el motivo y permite el nombre manual. La
consulta vuelve a intentarse cada dos segundos. Este dato de presentación no
bloquea la conexión ni detiene la ejecución del bot.

## Ruta localizada en las capturas

Las capturas de código de los PID anteriores contienen la misma ruta:

| Dirección | Instrucciones observadas |
| --- | --- |
| `004352DB` | Lee `actor+30`, suma 8 y salta a `00435046`. |
| `00435046` | Calcula `this+DC` y devuelve esa dirección. |
| `00436665` | Llama a `004352DB` y entrega el resultado al argumento `Name:[%s]` del registro `CharUnique`. |

Por tanto, el búfer devuelto está en `[actor+30]+E4`. El panel lee hasta 24
unidades UTF-16 y exige un terminador, texto imprimible y lecturas coincidentes.
Comprueba los bytes de las tres rutas antes de consultar el dato.

El actor procede de `[objeto_global+828]+2C`, con puesto local 1 y enlace de
regreso al mismo gestor. La identidad del actor, su información, la escena y la
fecha de creación del proceso se comprueban antes y después. Así se descartan
lecturas mezcladas al cambiar de personaje, cerrar un cliente o reutilizar un PID.

La implementación usa consultas de lectura. No llama al getter ni al auxiliar
`00906AF4` que aparece dentro de esa rutina, y no cambia memoria del juego.

La ruta se contrastó en tres capturas cuyo bloque `character-dispatch_00435000.bin`
tiene SHA-256 `80585548e9747a26632be460f4e60c41c69bf4a2cc486c0f566433035848ef85`.
Esas capturas contienen el código, no el búfer vivo del nombre. La primera
comprobación en el cliente real consiste en comparar el nombre mostrado con el Main.

Las pruebas cubren dos PID con nombres distintos, reutilización de PID, cambios
de personaje durante la consulta, escenas de carga, datos inválidos y código
incompatible. La comprobación gráfica valida que el nombre automático llegue a
la cabecera y a la vista general y que un fallo de nombre conserve la conexión.
