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
