# Prueba manual de escala de combate — 0.16.0

La investigación identificó el getter y el setter finales de la compilación
compatible. `00A46DEA` toma el puntero en `objeto+120`, carga su float `+50` y
retorna. `00A46DDA` toma ese mismo puntero y almacena el argumento float en `+50`.
Los bytes completos aparecen en las capturas del usuario y se contrastan antes
de ejecutar el setter. Véase [la investigación](battle-speed.md).

La prueba modifica temporalmente ese campo gráfico del contexto 1 y el campo
del gestor de combate `+265C`, de 1,40 a 1,45. El incremento nominal respecto a
1,40 es de aproximadamente 3,6 %; no significa «combate a 1,45x». El techo local
observado es 1,50. Ese techo no garantiza la sincronización con el servidor.
El efecto visible, la recogida y la duración real de las batallas todavía deben
comprobarse jugando. No hay velocidad automática por perfil en esta versión.

## Uso

1. Conecta con la ventana elegida, detén el bot y deja Auto Battle y caza nativa apagados.
2. Entra manualmente en una batalla. Abre **Caza y botín → Prueba de velocidad
   (experimental)** y pulsa **Leer estado** si hace falta.
3. Cuando la lectura sea válida, pulsa **Probar escala 1,45 (10 s)** y ejecuta
   una acción manual para observar su animación.
4. El panel intenta restaurar 1,40 al vencer el tiempo, salir del combate o cerrar
   la ventana. Puedes pulsar **Restaurar** antes. Si no se confirma, conserva el
   juego y la ventana de prueba abiertos y usa Restaurar; el panel mantiene los
   originales y la reserva del PID.
5. Pulsa **Copiar resultado** y pega el JSON, indicando aparte si notaste el efecto
   y si el combate y el botín terminaron normalmente.

Abrir la ventana solo lee. La prueba exige que ambos campos de combate estén
inicialmente en 1,40 y que los receptores gráficos finales de mapa y batalla sean
distintos. Si la lectura se bloquea, Copiar resultado incluye su motivo y la
instantánea disponible. No hace falta aplicar un cambio para obtener ese informe.
Los cambios de PID, perfil e inicio de bot quedan bloqueados mientras la ventana
está abierta. Una reserva por PID impide otra prueba o bot sobre la misma instancia.

## Comprobaciones y restauración

El puente vuelve a comprobar ejecutable, creación del proceso, HWND/hilo, código
cargado, cadena completa de los contextos gráficos 0 y 1, gestor, personaje,
identidad y turno. Aplicar exige fase de combate 3 y valores originales 1,40.
Solo admite el par fijo 1,40 → 1,45. No sustituye el selector gráfico activo.
Lee el campo del mapa antes/después y exige que conserve sus bits. No cambia los
relojes de Windows ni envía mensajes de ataque, movimiento o recogida.

La restauración conserva la identidad del receptor que recibió el cambio y busca
ese mismo objeto en los contextos actuales. Si pasó al contexto del mapa, revierte
solo el campo propio que lleva el valor aplicado y lo registra expresamente.
Solo sobrescribe campos que aún contengan el valor aplicado por esta prueba.
Un receptor sustituido o un valor cambiado de otra forma se registra como control
retirado, sin sobrescribir el estado nuevo ni llamarlo restauración confirmada.
Usa una cancelación nueva y puede ejecutarse con la ventana del juego minimizada
o bloqueada por un diálogo; los demás comandos conservan sus restricciones.

Una respuesta perdida puede corresponder a un cambio parcial. En ese caso se
intenta restaurar y se conservan los originales si sigue sin confirmarse. No
hay reintentos automáticos ilimitados. El panel intenta restaurar antes de cerrar
y mantiene la ventana si falla; terminar el panel a la fuerza puede impedir esa
limpieza. Si la instancia original termina o su PID se reutiliza, descarta el
control antiguo sin escribir en el proceso nuevo y no lo llama restauración.

El informe distingue `memory_change_confirmed`, `restoration_confirmed` y
`visual_speedup_confirmed`. Leer 1,45 después del envío confirma el campo, no un
combate más rápido. El IPC pasa a versión 10 y 476 bytes; operaciones 11 aplicar
y 12 restaurar. Las operaciones 0–10 conservan su comportamiento.

Las pruebas verifican aislamiento, valores previos, respuestas de otra instancia,
parada por tiempo/escena, limpieza tras incertidumbre y reutilización de PID.
El self-test nativo usa una ventana propia, sin cliente del juego: comprueba la
cancelación y restauración permitida con esa ventana minimizada/deshabilitada.
Windows valida también el parser sobre un proceso propio que se rechaza por
compilación, y el arranque de la interfaz empaquetada. No sustituyen la prueba
visual en el cliente del usuario.
