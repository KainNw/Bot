# Configuración por personaje — 0.23.0

Al conectar, el panel lee el nombre del Main del juego y carga la configuración
guardada para ese personaje. El PID y la fecha de creación siguen identificando
la instancia que controla; no forman parte de la clave del guardado. Así, el
mismo personaje recupera su configuración después de cerrar y abrir el cliente.

El guardado incluye:

- Los tres perfiles y cuál fue el último seleccionado.
- Mercenarios habilitados, nombres, orden, básicos, magias, objetivos y magia de
  primer turno.
- Modo de ataque al mob, radio y espera antes del encuentro.
- Recogida de botín restante y espera del NeoACA.
- Modo de Speed y factores separados de General y Combate, y la opción
  **Ejecutar turnos del perfil**.
- Auto Life de MP: habilitación, umbral y tecla F1–F9.

Los campos de caza, botín, Speed y ejecutar turnos se guardan automáticamente
tras 600 ms sin cambios, mientras el bot está detenido. Un campo incompleto o
inválido deja un aviso y conserva la última configuración válida. **Guardar
opciones del perfil**, **Guardar perfil** en el editor de mercenarios e
**Iniciar bot** también guardan los ajustes válidos. Cambiar de perfil, desconectar
o cerrar el panel guarda los cambios válidos que estén pendientes.

**Conectar no inicia el bot ni aplica Speed al juego**. Carga los controles y
espera a **Iniciar bot** para caza y Auto Life. General se aplica al marcar su
casilla o pulsar **Aplicar**, aunque el bot esté detenido. Si ya hay una operación abierta, la carga de otra
configuración espera a que termine; no reemplaza un ciclo activo.

## Identificación y varias ventanas

La clave combina el nombre leído del juego y la carpeta de instalación del
cliente. Distingue personajes de una misma instalación y nombres iguales en
instalaciones distintas. No deduce la cuenta de inicio de sesión ni identifica
servidores diferentes seleccionados desde una misma carpeta. Cambiar de carpeta
o renombrar al personaje crea otra configuración.

Un alias escrito a mano solo cambia la presentación: no carga ni guarda ajustes
de otro personaje. Si el nombre todavía está cargando, el panel sigue conectado
y reintenta la lectura. El ciclo puede ejecutarse con los ajustes actuales sin
asignarlos a un nombre no verificado.

Cada panel usa la configuración del personaje conectado. Los procesos con nicks
diferentes no comparten cambios. Si dos paneles editan el mismo personaje y perfil,
se conserva el último guardado; los otros perfiles tienen archivos separados.

## Archivos y perfiles anteriores

Los archivos están en
`%LOCALAPPDATA%\AtlanticaPanel\profiles\characters\<clave>\`:

- `profile-1.json`, `profile-2.json` y `profile-3.json`, con los ajustes del perfil.
- `character.json`, con el nick, carpeta, último perfil y ejecutar turnos.

La clave de la carpeta es un SHA-256: los caracteres del nick no se interpretan
como rutas. Los archivos se reemplazan de forma atómica. Una configuración rota,
de otra identidad o con formato desconocido se conserva y se muestra el fallo;
no se sustituye automáticamente por valores vacíos ni desconecta el PID.

Los perfiles generales anteriores siguen disponibles sin conexión. Un perfil
todavía no guardado para un personaje usa su perfil general como punto de partida;
al editarlo, queda separado. No se sobrescriben los perfiles generales al guardar
un personaje. Los personajes nuevos comienzan con el perfil 1 y turnos manuales.

Las pruebas comprueban reconexión con otro PID, dos nicks, instalaciones distintas,
conservación de los perfiles anteriores, escritura atómica, entradas inválidas,
temporizadores de guardado y carga en los controles de la interfaz. Usan sesiones
simuladas y archivos temporales; la comprobación final con personajes reales
requiere conectar el cliente de Windows.
