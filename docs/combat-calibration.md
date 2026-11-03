# Calibración y perfiles

Desde 0.6, conectar con la compilación compatible prepara automáticamente el
detector local que se contrastó en mapa/combate/regreso y dos encuentros completos.
Lo vincula al PID y fecha de creación nuevos; las instrucciones siguientes describen
la calibración manual, que se conserva como diagnóstico opcional.

El usuario confirmó que 0.4 inició un combate sin Auto Battle, pero el panel se detuvo
con cero combates observados. El resultado fue `status=1`, sin excepción, distancia
al cuadrado 13.8651 y límite 20. Una captura posterior comunicada durante el combate
siguió mostrando `scene_code=2`. No basta con asumir que `owner+0xB98` pasará a 1.
El visor anterior tampoco incluía la hora de actualización, por lo que el informe
no permite descartar por sí solo una captura anterior a la transición.

En otra captura, el candidato más cercano (puesto 11, tipo 18310, mapa 127) tenía
distancia 3D al cuadrado 49.4430, mayor que el umbral nativo 20. La distancia de
rejilla 13 usa otra escala. Este caso requiere acercamiento; aumentar el filtro
del panel no amplía el alcance que comprueba el cliente.

## Capturar y comprobar el detector

Conecta con el cliente exacto y deja Auto Battle/caza nativa apagados.

1. Abre **Calibrar combate**, deja el personaje quieto fuera de combate y pulsa
   **Capturar mapa**. Toma tres observaciones separadas por 300 ms.
2. Inicia un combate. Puedes usar **Más controles → Probar un ataque** cerca de un
   mob. Sin cerrar la calibración, pulsa **Capturar combate** mientras esté activo.
3. Juega los turnos. Al terminar, deja el personaje quieto en el mismo mapa y pulsa
   **Capturar regreso**.
4. Usa **Copiar calibración**, también si no encuentra una señal. El texto incluye
   los tres grupos, sus horas de captura, PID, fecha de creación, señales y resultado.
5. Tras una prueba individual, pulsa **Conectar** al mismo PID para resolver la
   solicitud anterior antes de iniciar el ciclo. La calibración permanece en memoria
   para ese PID y fecha de creación. Un cliente reiniciado requiere otra calibración.

La herramienta solo consulta datos durante las capturas. No inicia ataques ni
modifica estados del juego al calibrar. Antes de activar el ciclo exige un regreso
comprobado al mismo mapa. Los datos sin una diferencia utilizable se conservan en
el informe y no habilitan un detector.

Solo considera dos señales delimitadas por el código que ya se analizó:

| Señal | Evidencia exigida | Clasificación posterior |
| --- | --- | --- |
| Cambio de contexto global | Mapa 2 → combate 1 → mapa 2 en los grupos etiquetados. | 1 combate, 2 con posición mapa; otros desconocidos. |
| Contexto del personaje local | Contexto global 2; ambos campos locales negativos antes/después; al menos uno no negativo durante las tres muestras de combate. | Dentro de contexto 2, usa ese predicado; ausencia de datos es desconocida. |

Los campos locales proceden del predicado nativo `00435D5A`: enteros con signo en
`actor+0x318` y `actor+0x254`. Antes se utilizaba para filtrar objetivos, no para
afirmar el estado del personaje local. Ahora su uso como detector requiere la
comparación etiquetada. También registra el estado local, flags y estado vinculado
para analizar diferencias; no les asigna un significado de combate sin evidencia.

El ciclo exige dos observaciones consecutivas de combate, pausa durante estados
desconocidos y estabiliza el regreso durante dos segundos. Tras una solicitud
encolada espera hasta treinta segundos y se detiene sin repetirla si no observa el
combate. Los tests verifican la lógica con datos simulados; en la captura 0.7 del
cliente real se confirmaron seis solicitudes y seis combates.

## Configurar el equipo

Elige perfil 1, 2 o 3 y abre **Configurar mercenarios**. Los nueve puestos son un
plan definido por el usuario; todavía no se han vinculado a objetos de mercenarios
del cliente. Puedes ponerles nombres, marcar los que participarán y moverlos con
**Subir / Bajar**. El primero tiene mayor prioridad. Desde 0.8, cada puesto permite
elegir **Ataque básico** o **Magia Q/W/E/R/T**. **Básico alternativo** guarda la
preferencia de atacar normal si la magia no está disponible; solo se puede cambiar
al elegir una magia. **Guardar perfil** conserva el plan aunque cierres el panel.

Los perfiles se guardan como JSON separados en
`%LOCALAPPDATA%/AtlanticaPanel/profiles/profile-N.json`. No contienen el PID ni se
asignan automáticamente al primer cliente abierto. El ciclo toma una copia inmutable
del perfil elegido al iniciar; el editor y selector quedan bloqueados durante la
ejecución. Guardar un perfil no modifica el juego ni las otras ventanas.

Los archivos nuevos usan `schema_version=3`, con `action` (`basic`, `Q`, `W`, `E`,
`R` o `T`), `fallback_basic` y `target` por puesto, y `magic_first_turn_only` en el
perfil. El objetivo puede ser `enemy`, `self` o `slot_1`–`slot_9`. Los perfiles de
esquema 1/2 conservan nombres, selección, prioridad y acciones; cargan enemigo y
magia inicial por defecto y solo actualizan el archivo al pulsar Guardar. Un perfil
inválido se conserva para revisión.

Desde 0.11, **Ejecutar turnos según el perfil (experimental)** permite aplicar el
plan a los miembros vivos presentes, en orden. La pestaña **Mercenarios** distingue
presencia en batalla de habilitación en el perfil. Si no activas la opción, los
turnos son manuales. El informe del perfil indica `turn_execution_available=true`;
`combat.enabled` muestra si activaste la ejecución. Consulta
[turnos de mercenarios](mercenary-turns.md) para configurar la magia inicial y los
objetivos, y para comprobar la primera prueba del ciclo automático.

## Alcance y observaciones

**Ver objetivos** añade una columna **En alcance**, la observación del personaje y
la hora de la actualización. La copia contiene esa consulta concreta: usa
**Actualizar** si el visor ya estaba abierto antes de entrar en combate.

**Copiar estado del bot** incluye contadores por contexto/clasificación, las últimas
24 observaciones, señal calibrada, perfil y distancia/límite del objetivo más cercano.
La espera pasa de 0.5 s a 0.25 s mientras hay una solicitud pendiente. El auxiliar
nativo puede bloquear hasta ocho segundos durante el envío; no se afirma que el
registro capture cada transición breve que ocurra durante esa llamada.

En 0.5 se comprobó el ciclo cercano en dos combates. La versión 0.7 sustituyó el
[acercamiento de 0.6](native-approach.md) por
[persecución y ataque nativos](native-attack.md), comprobados en seis combates.
Mantiene el umbral de ataque y su revalidación nativa. Los turnos automáticos de
mercenarios y una eventual velocidad de combate siguen sin implementarse.
