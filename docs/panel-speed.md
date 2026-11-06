# Speed en el panel

Desde **0.19.0**, el panel controla los temporizadores del cliente seleccionado sin
tener que abrir Cheat Engine. Es una función experimental, desactivada por defecto.

Desde **0.28.0** hay tres controles con factores guardados por separado:
**Speed en combate**, vinculado al bot; **Speed en combate independiente**, que
se arma con su propia casilla; y **General**, activo también en el mapa.
Cargar un perfil o conectar un personaje no activa relojes.

## Speed en combate independiente

1. Conecta con el PID y abre **Caza y botín → Speed en combate independiente**.
2. Elige **1,25×, 1,5×, 2×, 3× o 4×** y marca **Activar sin iniciar bot**.
   Si la casilla ya viene marcada de un perfil cargado, pulsa **Aplicar**.
3. En el mapa mantiene **1×**. Al entrar en un combate normal listo acelera y,
   al volver al mapa, restaura **1×** y queda esperando la siguiente batalla.
4. **Parar bot** conserva este control independiente. Desmarca su casilla para
   restaurar **1×** y desarmarlo. Cerrar el panel o perder el proceso propietario
   también solicita la restauración.

Reutiliza exactamente `NativeClock`, incluida su comprobación de estado y el
límite de 60 segundos reales por batalla. No inicia búsquedas, ataques, recogida
ni turnos. Su reserva por PID y cancelación son independientes del trabajador
de caza. El código del controlador nativo y del Speed del bot no cambia.

La casilla nueva conserva la habilitación y el factor del Speed original del bot.
Solo puede haber un controlador activo por PID. Para usar **Iniciar bot** con su
Speed en combate, desactiva antes el independiente y espera a que confirme 1×.
General y el independiente tampoco se superponen. Desmarcar, esperar 1× y cambiar
de factor permite rearmarlo con otra velocidad.

Se guarda por personaje. Los perfiles de esquemas 1–11 lo cargan desactivado y
mantienen sus ajustes anteriores; guardar el nuevo campo no arma el controlador.
**Copiar estado PID…** añade `independent_battle_speed` con el estado, factor
actual, PID y creación de la instancia, incluso cuando el bot está detenido.

## Speedhack general

1. Conecta con el personaje y entra en **Caza y botín → Speedhack general**.
2. Desde **0.26.0**, elige **1,25×, 1,5×, 2×, 3× o 4×** y marca
   **Activar Speed general**. Se aplica inmediatamente, sin pulsar Iniciar bot.
   Si la casilla viene marcada de un perfil cargado, pulsa **Aplicar**.
3. **Parar bot** conserva General. Desmarca la casilla para volver a **1×**.
   Para cambiar de factor, desmarca, espera la confirmación, cambia y vuelve a marcar.
   Cerrar el panel o perder su proceso propietario también solicita **1×**.

General no vuelve a 1× solo por salir del combate y no usa el límite por batalla.
Su controlador mantiene la comprobación del personaje y del proceso propietario.
Si temporalmente no puede leer el cliente, pasa a 1× y espera datos válidos para
reanudar mientras General siga activado. Un cambio de personaje o la cancelación
retiran el control. No afecta a otros PID ni inicia un segundo controlador.

El factor general es independiente del de combate. Por ejemplo, puedes conservar
Combate en 3× y General en 1,5× y elegir el modo antes de iniciar. La casilla y su
factor se guardan por personaje. Los perfiles de esquemas 1–8 cargan General
desactivado y conservan su configuración de combate anterior.

## Speed en combate: funcionamiento existente

1. Si usaste CE con ese cliente, cierra CE y reinicia el juego una vez. Restaurar
   1× en CE deja su DLL cargada: el panel rechaza combinar ambos sistemas.
2. Abre `AtlanticaPanel.exe`, actualiza la lista y conecta el PID del juego.
3. En **Caza y botín**, dentro de **Speed en combate**, marca **Activar Speed** y elige
   **1,25×, 1,5×, 2×, 3× o 4×**. Puedes comenzar con 1,25×.
4. Pulsa **Iniciar bot**. Al reconocer un combate normal listo, el controlador
   aplica el factor elegido. Al volver al mapa, restaura **1×** y queda esperando
   el siguiente combate. **Parar bot** cancela también el Speed.

La opción y el factor se guardan en el perfil. Para cambiarlos, para el bot,
edita las opciones e inícialo otra vez. Los perfiles anteriores mantienen el
modo General apagado; la configuración de combate que ya tuviesen se conserva.

El estado de Speed muestra el factor que mantiene el controlador nativo y su
motivo: esperando combate, en combate, regreso al mapa o detenido. **Copiar
estado PID…** incluye estos datos y los contadores de aplicaciones y
restauraciones. El factor informado no mide la rapidez real de la animación.

El control se limita a la instancia conectada y comprueba la creación del proceso
para evitar reutilizar un PID. Cada panel reserva el control de velocidad de su
PID. No actives CE sobre una instancia que ya haya usado el Speed nativo: para
cambiar de sistema hay que reiniciar ese cliente.

Puedes cerrar y abrir la misma compilación del panel sin cambiar la ruta de sus
componentes nativos. Si actualizas a una compilación diferente mientras ese
cliente conserva los relojes de la anterior, el panel pide reiniciar ese juego
antes de activar el Speed nuevo.

Ambos modos solicitan **1×** al desactivar su propio control, al cerrar el panel
o al perder su proceso propietario. Parar bot retira el modo de combate, mientras
que General tiene una cancelación independiente. En el modo de combate, una lectura inválida retira el control.
Un cambio gráfico o de preparación del
combate devuelve 1× y espera el mapa antes de volver a acelerar. También tiene
un límite de **60 segundos reales por combate**; no reaplica el factor durante
ese mismo encuentro. Si falta la confirmación de una parada, el panel conserva
la reserva y consulta el estado sin reenviar comandos de parada automáticamente.

El usuario confirmó con 0.19.0 la aceleración durante el combate y la vuelta a
velocidad normal al terminar. Esa validación corresponde a la prueba realizada.

Este sistema cambia relojes del proceso, incluidos temporizadores que puede usar
la red. No acelera el servidor ni garantiza que este acepte el ritmo. Las pruebas
anteriores de CE confirmaron aceleración y vuelta a 1× en combates concretos;
el resultado no demuestra estabilidad prolongada con todos los combates.

## Verificación del controlador

La compilación de Windows ejecuta pruebas en procesos propios: las cuatro APIs
de reloj, la continuidad al volver a 1×, el vencimiento sin lecturas intermedias,
la entrada y salida de combates simulados, la cancelación y la salida del panel
propietario. El puente comprueba además que un proceso ajeno al juego se rechaza
antes de acceder a direcciones del cliente. Estas pruebas no ejecutan el juego.

La prueba adicional del modo General recorre mapa, combate, preparación y cambios
gráficos en un proceso propio minimizado. Verifica la pausa y recuperación ante
lecturas incompletas, la vuelta a 1× al cancelar o salir el propietario y el cambio
posterior al modo de combate con sus reglas originales. El inicio General usa
una operación distinta; la reserva por PID y la restauración son comunes. Se renueva
una caducidad breve con tiempo real para evitar acumular un tramo acelerado sin
comprobaciones si el proceso se queda bloqueado. El comportamiento real de General
en Atlantica todavía necesita la prueba visual en el cliente de Windows.

La comprobación de interfaz del control independiente verifica la activación con
el bot detenido, el regreso a 1×, la permanencia al pulsar Parar bot y el guardado
del factor original. Reutiliza las pruebas nativas existentes de entrada/salida,
cancelación, límite por batalla y salida del propietario. Su uso real desde la
casilla nueva queda pendiente de una prueba visual en el cliente.

Los relojes usan MinHook bajo su licencia BSD, incluida en
`THIRD-PARTY-NOTICES.txt`. El código y su revisión de origen están en
`native/third_party/minhook/`. El complemento CE sigue disponible como alternativa
separada en [su guía](ce-speed-trial.md).
