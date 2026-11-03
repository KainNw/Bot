# Control de caza para Atlantica Online

Controla la lógica AutoHunting que ya incluye el cliente analizado del servidor
privado en Windows 10/11. El inicio y la parada usan `HuntingMode.txt`; el panel
consulta el estado del proceso para distinguir una solicitud de la confirmación del cliente.

La versión 0.3 añade selección de ventanas/PID y una **prueba experimental de un
ataque sin Auto Battle**, dirigida al cliente conectado. Esa prueba requiere
validación en el juego real; no es todavía un ciclo autónomo de caza.

**Comprobado por el usuario:** tras activar Auto Battle y crear el marcador, el cliente
mostró HUNT=1 y el personaje atacó mobs. También se comunicó un cierre al moverlo
manualmente con x32dbg adjunto. La causa sigue pendiente y el registro de esa sesión
se perdió. No se presenta ese cierre como corregido.
El usuario también comunicó un cierre al probar el clic manual con Auto Battle
apagado, marcador desactivado y sin x32dbg. No hay todavía registro de ese segundo
cierre que permita identificar su causa.

**Panel:** implementado con Iniciar, Parar y estado actualizado. La lógica tiene
pruebas automatizadas; el workflow de Windows también comprueba las APIs sobre su
propio proceso y el arranque del ejecutable gráfico. La conexión real con el cliente
requiere validación en tu PC. La próxima prueba debe hacerse con el juego abierto
normalmente, sin adjuntar x32dbg, para separar esa variable del comportamiento del cliente.
El usuario pudo conectar el panel y exportar contexto con Auto Battle apagado en
una sesión posterior con otro PID. La nueva vista de objetivos todavía requiere
contrastar sus resultados con el juego.

Solo se admite la compilación cuyo SHA-256 es
`BC87A0CC5826AA7FB5E4FF10B6B7C1A349962BD8B146AD28EC3FFA9453FE04E6`.

## Mejoras solicitadas y límites actuales

La prioridad más reciente es entregar el panel de inicio, parada y estado para poder
mejorarlo por etapas. Ese panel ya se publicó y se compiló para Windows. La siguiente
etapa solicitada es la caza independiente. El primer modo disponible sigue siendo el
control de la caza nativa.

El usuario ha pedido que Iniciar bot funcione manteniendo Auto Battle apagado.
**La caza autónoma independiente todavía no está completada.** Se ha implementado
una primera prueba de una solicitud de ataque usando los métodos nativos analizados,
con Auto Battle y caza nativa apagados. Quedan su prueba en el cliente real y, después,
el ciclo de caza, movimiento y confirmación de entrada en combate.

Como mejora posterior se solicitó estudiar una velocidad configurable solo durante
batallas, restaurando la velocidad normal al salir del combate o parar. No está
implementada ni se ha comprobado qué aceleración admitiría el cliente o el servidor.
Se priorizan los controles, la estabilidad y la caza independiente antes de esa función.

## Panel de inicio, parada y estado

Si abres varios clientes, selecciona su ventana en la lista antes de **Conectar**.
**Elegir ventana** permite activarla con Alt+Tab durante tres segundos. El panel
muestra el PID y vincula la conexión también a la fecha de creación de ese proceso.
No cambia automáticamente a otro cliente cuando se cierra el elegido.

Si varios clientes comparten carpeta, **Iniciar/Parar nativos se bloquean** porque
`HuntingMode.txt` es compartido. Las consultas de objetivos siguen siendo por PID.
Detalles: [varias ventanas](docs/multiple-clients.md).

Requiere Python 3.11 o posterior de 64 bits, con Tkinter (incluido en el instalador
normal de Python para Windows). En la carpeta de este proyecto:

```powershell
py -3 panel_caza.py
```

1. Abre el juego y pulsa **Conectar**. El panel identifica el proceso y su carpeta de
   trabajo; verifica el ejecutable antes de habilitar controles. Deja el PID opcional
   vacío para que se detecte automáticamente. Ese campo permite elegir un cliente
   concreto si hay varios abiertos.
2. Activa **Auto Battle** mediante el control normal del juego.
3. Pulsa **Iniciar**. El panel crea o restaura el marcador y espera la lectura del cliente.
4. Para mover el personaje manualmente, pulsa **Parar**, espera la confirmación y
   desactiva Auto Battle desde el juego. Es una forma de controlar la prueba; no es
   una corrección demostrada del cierre comunicado.

El estado distingue **Inicio solicitado**, **Caza habilitada**, **Parada solicitada**,
**Parada confirmada**, **Auto Battle apagado** y ausencia de lectura actual. La presencia
del archivo no demuestra por sí sola que el personaje esté atacando. Con Auto Battle
apagado puede quedar un indicador almacenado sin actualizar.

Si el juego se cierra, el panel deshabilita Iniciar y muestra que perdió la lectura.
Al abrirlo de nuevo, pulsa **Conectar**: el PID se busca de nuevo y el puntero del estado
se consulta en cada lectura. No se conserva el PID como identificador permanente.

Con el juego cerrado también puedes elegir **Seleccionar carpeta** y pulsar **Parar**
para dejar el marcador desactivado antes del siguiente arranque. Cerrar el panel no
desactiva automáticamente la función del cliente; si puede seguir activa, aparece
una confirmación antes de cerrar la ventana.

## Contexto para la siguiente etapa

En 0.3, **Probar un ataque (experimental)** comprueba el candidato más cercano y
envía como máximo una solicitud desde el hilo de la ventana elegida. Acércate antes
al mob y deja Auto Battle y caza nativa apagados. No mueve al personaje ni repite
ataques. **Copiar prueba** guarda el resultado en el portapapeles para contrastarlo
con lo ocurrido en el juego. Tras encolar o recibir un resultado incierto, comprueba
el cliente y reconecta antes de otra prueba. No se confirma batalla por el mero envío.

El ejecutable incluye un auxiliar y DLL x86 propios para esa solicitud. Solo se
cargan en el cliente al pulsar el botón de prueba. La conexión normal y Ver objetivos
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
Auto Battle apagado. La captura ampliada guarda hasta 76 KiB de código más un
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

La ruta encontrada permite aprovechar la caza nativa y consultar candidatos desde
el panel. La llamada independiente experimental requiere validación en el juego. Las
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
