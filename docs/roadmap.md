# Próximas etapas acordadas

## Ataque individual confirmado

El usuario confirmó que la prueba 0.3 inició el ataque con Auto Battle apagado.
El resultado identificó PID 16244, hilo 18440, objetivo 8, solicitud encolada sin
excepciones y distancia dentro del umbral nativo. Solo había una ventana abierta.
La primera prueba con varias ventanas continúa pendiente; no se presenta como realizada.

Se recibieron tres capturas de contexto, verificadas y analizadas como datos. Se
identificaron la lista activa, los métodos de validación, construcción del mensaje,
transformación y cola. El puente x86 usa el hilo de la ventana elegida y comprueba
compilación, PID, fecha de creación, HWND, hilo e identidad del objetivo.

## Ciclo cercano 0.4 — objetivo activo

Se implementaron Iniciar bot/Parar bot, selección dentro del alcance 3D, espera de
escena de combate y reanudación tras volver al mismo mapa y estabilizarse. El ciclo
no cambia Auto Battle, el marcador de caza nativa, instrucciones o relojes del juego.
No juega turnos ni mueve al personaje hacia mobs lejanos.

La interfaz conserva respuesta mientras el auxiliar espera. La parada y el cierre
señalan una cancelación que el cliente comprueba antes del envío. Una solicitud ya
en curso/encolada puede completarse. Datos cambiantes se descartan; resultados
inciertos y ausencia de confirmación de combate detienen el ciclo sin repetirlos.
Los controles para cambiar cliente permanecen bloqueados hasta terminar el trabajador.

La lógica de fases, cancelación y aislamiento tiene pruebas. Quedan por validar el
ciclo completo y el detector de escena en el cliente real, y después varias ventanas.
Véase el comportamiento y sus límites en independent-hunt.md.

## Aislamiento y estabilidad

Cada ejecución queda ligada a PID, fecha de creación y ventana/hilo. Perder la sesión
detiene el trabajador; no se busca otro cliente automáticamente. Un mutex por PID
excluye ciclos o pruebas simultáneos del mismo cliente. Las otras instancias utilizan
su propia reserva y evento de cancelación.

La caza nativa anterior utiliza HuntingMode.txt, compartido si varios clientes
usan la misma carpeta. Sus cambios permanecen bloqueados en ese caso. El ciclo 0.4
no utiliza ese marcador para iniciar o parar.

El usuario comunicó anteriormente cierres al moverse con caza nativa/x32dbg, y también
con clic manual sin ambos. El registro se perdió y no hay causa confirmada. El ataque
individual nuevo funcionó, pero no se afirma que haya corregido esos otros cierres.

## Turnos por perfil 0.11

El usuario pidió también jugar los turnos de sus mercenarios, y confirmó avanzar
primero con el inicio de encuentros. Después confirmó el básico nativo de 0.9 y
la magia Q de 0.10. La versión 0.11 añade ejecución opcional en orden, solo con
miembros presentes/habilitados, magia en el primer turno propio y básicos después,
y estado de los nueve puestos en el panel. Deja de enviar órdenes sin enemigos
vivos. La primera prueba automática confirmó Q del miembro 1, derrota de todos los
enemigos y omisión de las órdenes restantes. Quedan la secuencia entre varios
miembros, los básicos posteriores y un equipo de dos miembros.

La versión 0.11.1 elimina la pausa entre selección y magia, relee inmediatamente
la barra y revisa la preparación del combate cada 100 ms. Busca dejar más tiempo al
NeoACA para recoger y terminar en el primer turno. El usuario confirmó esa recogida
y final en el primer turno en la prueba de 0.11.1; el botín con X sigue pendiente.

## Vista general 0.12

Se añade una ventana flotante con Main fijo en el puesto 1 y Mercenarios 2–9,
vida actual en batalla, presencia, habilitación, prioridad y acción. Usa los
controles y perfiles existentes. Durante los turnos automáticos muestra el estado
que ya publica el trabajador, sin seleccionar unidades ni añadir lecturas del juego.
Las columnas de maná, máximos y experiencia de la imagen de referencia requieren
identificar sus lecturas antes de incorporarlas.

## Velocidad — etapa posterior

Se solicitó estudiar una velocidad configurable durante batallas y restaurarla al
salir/parar. Esa función continúa sin implementar. Queda para después de validar
el ciclo, la estabilidad y el comportamiento de los turnos.
