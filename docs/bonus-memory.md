# Comparar los bonus mediante lecturas de memoria

En 0.15.0, **Caza y botín → Capturar bonus (memoria)** y el botón **Capturar bonus**
de la vista general abren una comparación vinculada al PID y la fecha de creación
del proceso conectado. El bot debe estar detenido y Auto Battle apagado. Mientras
está abierta, se bloquean el inicio y los cambios de cliente o perfil.

1. Cuando veas el bonus dentro del combate, selecciona **EXP**, **Armas /
   equipamiento** o **Libros de EXP** y pulsa **Capturar bonus visible**.
2. Vuelve al juego y pulsa **X una vez**, igual que al recogerlo manualmente.
3. Indica si viste la recogida y pulsa **Capturar después de X**. Puede ser
   dentro de la misma batalla o después de regresar al mapa.
4. Guarda el ZIP y adjúntalo al chat para analizar las diferencias. Si el bonus
   desapareció antes de completar el segundo paso, puedes guardar solo la captura
   inicial. **Nueva comparación** descarta la comparación del diálogo y permite otra.

**Sin bonus (control)** permite obtener una comparación equivalente en una batalla
sin bonus. El programa etiqueta el tipo según lo que el usuario ve; todavía no
lo deduce de la memoria ni confirma por sí mismo la recogida. El resultado visual
indicado por el usuario queda separado de las observaciones.

La captura lee los campos de combate conocidos y los objetos publicados en la
colección gráfica, incluidos los que el lector normal omite. Estos objetos se
guardan para diagnóstico y no se convierten en objetivos del recolector. Añade
los selectores de acción, identidades de participantes, efectos de búsqueda y
cinco objetos de claves de propiedades usados por las funciones conocidas, sin
seguir sus punteros internos. Lee seis regiones fijas de la imagen que contienen
las rutas conocidas de búsqueda y sus auxiliares. Registra bloques inaccesibles
sin sustituirlos por ceros. La exportación limita el JSON a 256 KiB y el código
a 512 KiB; no hace un volcado completo del proceso.

Las comprobaciones descartan cambios de instancia, escena o contexto durante la
lectura. No escribe memoria, no envía comandos, no pulsa X ni instala un debugger.
La siguiente mejora de recogida dependerá de contrastar capturas de los tipos
que fallan con la pulsación manual que sí funciona. El recolector actual usa una
búsqueda genérica sobre cuerpos; no contiene un filtro que elija solo bonus EXP.

## Velocidad durante el combate

No se ha identificado un comando nativo verificado de velocidad de animación en
los bloques analizados. Esta versión no incorpora un speedhack. Para estudiar
una opción de animación habría que localizarla y comprobar que respeta los turnos
del servidor, sin cambiar relojes globales ni la cadencia de solicitudes, y que
se restaura al salir del combate o parar. Acelerar la presentación no garantiza
reducir el tiempo que el servidor necesita para completar una acción.
