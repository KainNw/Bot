# Speed en el panel

Desde **0.19.0**, el panel controla los temporizadores del cliente seleccionado sin
tener que abrir Cheat Engine. Es una función experimental, desactivada por defecto.

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
Speed apagado al cargarlos.

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

El controlador solicita **1×** al parar, al cerrar el panel, al perder su proceso
propietario o ante una lectura inválida. Un cambio gráfico o de preparación del
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

Los relojes usan MinHook bajo su licencia BSD, incluida en
`THIRD-PARTY-NOTICES.txt`. El código y su revisión de origen están en
`native/third_party/minhook/`. El complemento CE sigue disponible como alternativa
separada en [su guía](ce-speed-trial.md).
