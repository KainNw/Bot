# Acercamiento opcional 0.6.1

El usuario confirmó dos encuentros con 0.5: entró en combate sin Auto Battle,
reconoció la batalla por `local_context` y volvió a buscar. El límite restante era
el alcance: solo atacaba los mobs cercanos. La versión 0.6 añade una ruta normal
del cliente hacia objetivos lejanos; su efecto en el juego sigue pendiente de prueba.

## Uso

1. Conecta con la ventana elegida. Tras verificar la compilación compatible, prepara
   el detector local ya contrastado; no hace falta repetir la calibración anterior.
2. Deja Auto Battle apagado y el personaje quieto. Marca **Acercamiento automático
   (experimental)** y ajusta **Radio de búsqueda**, inicialmente 60 casillas.
3. Pulsa **Iniciar bot**. El punto de inicio fija el centro del área de esa ejecución.
   El radio usa distancia de rejilla (|ΔX| + |ΔY|), entre 5 y 120; no representa metros.
4. El bot prefiere un objetivo ya en alcance. Si no hay uno disponible, solicita
   acercarse al más próximo dentro del área. Al alcanzar el margen de ataque,
   solicita parar, espera dos segundos de posición estable y vuelve a consultar.
5. **Parar bot** cancela nuevas acciones y solicita detener una ruta propia conocida.
   Espera el estado detenido antes de moverlo manualmente o cambiar de ventana.
6. **Copiar estado del bot** incluye `approach`: punto de inicio, configuración,
   solicitudes, llegadas, fallos, motivo de parada, ruta y respuestas nativas.

La casilla abre desmarcada para conservar el comportamiento cercano ya comprobado.
Los controles de radio y movimiento quedan bloqueados durante la ejecución. Los
perfiles de mercenarios siguen guardando solo el plan de turnos, que aún son manuales.

## Funciones y validación

La ruta usa la misma sesión, PID, creación, HWND e hilo de ventana que el ataque.
El puente verifica el hash y el código cargado; el hook valida el personaje local,
contextos locales negativos, identidad/lista activa del objetivo, mapa y radio.
Respeta el bloqueo de movimiento `player+0x338` y el estado vinculado de mapa.
No amplía la distancia de ataque ni activa Auto Battle o archivos compartidos.
El detector por defecto usa la comparación local validada y se vincula de nuevo al
PID y fecha de creación de cada conexión. La calibración manual sigue disponible.

## Corrección de la lectura inicial en 0.6.1

El informe de 0.6.0 del PID 10192 se detuvo con cero observaciones, consultas y
acciones: «El estado de desplazamiento del cliente no es válido». El lector exigía
que ambos bytes de navegación fuesen 0/1 y descartaba toda la observación si no
lo eran. El informe no incluía sus valores originales, por lo que no permite
identificar cuál de los dos provocó el rechazo.

La revisión conserva `active_raw` y `moving_raw`, incluso cuando tienen otro valor.
`active` sigue la comparación exacta con 1 encontrada en el consumidor de ruta
`0043E35F`. Para `moving`, un byte diferente de 0/1 se representa como `null`
(desconocido), nunca como prueba de inactividad. La primera observación se conserva
además de las últimas 24. **Ver objetivos → Copiar resultados** permite obtener
estos valores mediante una consulta sin iniciar movimientos.

El inicio de acercamiento no depende de tratar `+0xB78` como booleano: mantiene
posición estable, contexto, radio, identidad y ausencia de ruta activa. La orden
lleva el objeto y tick leídos; el hook exige que sigan coincidiendo justo antes de
llamar al método normal. Una revisión diferente rechaza la acción y no se reintenta
automáticamente. La parada mantiene su comparación de propiedad completa y solo
confirma flags desactivados cuando ambos bytes son exactamente cero. Un valor
desconocido no autoriza detener una ruta ajena ni se considera una ruta terminada.

| Operación | Función del cliente | Comprobación |
| --- | --- | --- |
| Solicitar ruta | `0043C9D3`, this=jugador, args mapa/X/Y, ret 12. | Envuelve `0043B145`, conserva la navegación normal del cliente. |
| Interrumpir ruta | `0043B211`, this=jugador, sin args. | Usa `0043B1E7`, `00443382` y `0043B145(-1,0,0)` y desactiva flags de ruta. |

Las funciones y su convención de llamada proceden del bloque de código aportado
por el usuario. Se comprueban sus bytes completos y los de los setters relacionados
antes de llamarlas. No se ejecuta el cliente en la nube. Las llamadas nativas
del puente se hacen en el hilo de la ventana seleccionada, sin clics ni teclas.

El descriptor de ruta incluye el objeto local, el tick de solicitud en `+0x1014`
y el destino en `+0x1018/+0x101A/+0x101C`. Antes de detener una ruta viva compara
esos valores; si cambiaron, no llama al método de parada. Si el cliente ya está
inactivo, lo registra sin enviar otra acción. La observación de movimiento usa
los flags `+0x1012` y `+0xB78` y admite progreso de posición durante las lecturas;
mantiene las comprobaciones de instancia, mapa, contexto e índices activos.

La solicitud de ruta aceptada (15) solo demuestra que el cliente publicó la ruta.
La parada (16) verifica flags inactivos y exige después posición estable; no se
presenta por sí sola como prueba de llegada física o aceptación del servidor.
El código nuevo necesita confirmar en el juego movimiento, llegada y Parar bot.

## Límites del ciclo

Durante el acercamiento solo consulta la ruta y el objetivo; no envía ataques.
Solicita parar cuando el objetivo entra en el 80 % del umbral de distancia al
cuadrado, para dejar margen. Después usa el filtro normal y la revalidación nativa
antes de pedir un ataque. Una identidad desaparecida, cambio importante del destino,
cinco segundos sin progreso o veinte segundos de duración terminan el acercamiento.
Los acercamientos no completados tienen una espera por objetivo; tras tres fallos
se detiene. Al superar el área se detiene también. El centro no se desplaza tras
cada combate.

Un cambio de personaje, escena, mapa, modo nativo o ruta ajena no permite sustituir
ese movimiento. La ruta propia conocida se intenta detener antes de soltar el
mutex del PID, con un canal de cancelación distinto al que acaba de cancelar la
ejecución. Una llamada de resultado incierto no se repite. Si no se recibió un
descriptor válido, no se inventa la propiedad de una ruta: se informa resultado
desconocido y se exige comprobar el juego/reconectar. Parar no deshace un ataque
ya encolado ni cancela un combate iniciado.

El protocolo es versión 4, con mensajes de 300 bytes y operaciones distintas para
consulta, ataque, acercamiento y parada. La respuesta debe coincidir en PID, hilo,
operación y objetivo. Las pruebas cubren el ciclo de estados, límites, cancelación
durante la aceptación, limpieza antes de liberar el PID, falta de progreso,
identidad/ruta cambiada y ausencia de reintentos ante una parada incierta. El self-test
de Windows comprueba cancelación y aislamiento sobre una ventana propia; no ejecuta
las funciones del juego.
