# Ruta del combate observado y revisión de las funciones BF

Se comprobaron los 27 bloques y SHA-256 de
`Atlantica-PID10192-combate-20261103-081115.zip`, panel 0.8.1, esquema 4 y 492 KiB.
La captura corresponde al mismo PID 10192 y creación `134381538653581584`.
Antes y después el personaje tiene contexto A (`actor+318`) = 0 y contexto B
(`actor+254`) = −1. Auto Battle y caza nativa están apagados. El bot registraba una
solicitud y un combate y estaba pausado para jugar los turnos.

## Diferencia entre las dos rutas

El código BF capturado contiene validaciones y construye solicitudes `0D80` con
cargas de 36 bytes. Se resolvió `00A55E94`: devuelve el campo `+14` del receptor.
También se encontró la tabla de selección de nueve unidades en el gestor BF.
Esto permite estudiar esa familia, pero no la vincula por sí solo a la batalla
observada por el usuario.

La ruta de selección BF `008BC836` consulta el personaje local a través de
`owner+828`, exige `actor+254 >= 0` y comprueba la fase del objeto relacionado con
`owner+16360`. La muestra del usuario tiene ese campo en −1. No se habilitó una
prueba de ataque con esas funciones: no está verificado que correspondan al
contexto actual.

La ruta que sí utiliza `actor+318` aparece en código ya capturado:

| Código | Acceso observado |
| --- | --- |
| `00431769` | Si `actor+318` es no negativo, lee `owner+091C`, obtiene `gestor+8+índice*4` y llama a `004FE29F`. |
| `00431A0E` | Obtiene el mismo contexto y llama a `004FE198`. |
| `00431FFE` / `00432A4B` | Consultan unidades de ese contexto mediante `004FE4FA`. |

Esas funciones `004FE…` no estaban en la captura 0.8.1. El archivo en disco sigue
mostrando código protegido en esas direcciones. La ruta se identificó por las
instrucciones del volcado; todavía falta contrastar su objeto vivo.

## Lectura de contexto y puestos en 0.8.2

El lector comprueba los 54 bytes de `00431769` y los 52 bytes de `004ED38B` contra
la captura y exige la ruta observada: A no negativo, B negativo. El índice está
limitado a 128 entradas para acotar el diagnóstico; no se presenta ese límite
como el tamaño real del gestor ni se permite ejecutar órdenes con él.

Para los miembros se sigue la disposición de `004ED38B`: registros de `488` bytes
desde `información_del_personaje+4108`. Se comprueba que la información pertenezca
al personaje local en la colección de `owner+830`, usando la misma base y el paso
`215B8` de `004ED36F`. Solo se leen nueve puestos y tres enteros por puesto:
tipo en `+08`, valor en `+4C` y valor en `+50`.

Los nombres que muestra el visor vienen del perfil del usuario. Los valores `4C`
y `50` no se etiquetan como maná o puntos de acción ni habilitan acciones. Si los
miembros no se pueden validar, se conserva el contexto con `members_status=unavailable`
y su error; no se devuelve una lista parcial como si estuviera completa.

La consulta comprueba instancia y escena antes y después, así como la dirección
del actor, su identidad, índice, gestor, contexto e información de miembros. Un
cambio en ese vínculo invalida la consulta. Detectar este contexto tampoco indica
de quién es el turno: `turn_state_verified` y `turn_execution_available` siguen en
`false`.

## Captura dirigida al contexto activo

0.8.2 añade `004F0000–00520000` (192 KiB de código) y `042DC000–042DE000` (8 KiB de
constantes). Incluye el informe estructurado anterior en `combat.normal_combat`.

La primera palabra del contexto solo se sigue como candidata a tabla de métodos
si apunta dentro de la sección conocida de solo lectura. Se leen 256 bytes y se
exigen tres entradas iniciales que apunten a código de la misma imagen. Se
capturan hasta 24 regiones de 8 KiB de esas entradas, reutilizando las ya presentes.
No se siguen direcciones de heap como si fueran código ni se llama a los destinos.
El informe declara el límite alcanzado y no afirma que la tabla esté identificada
semánticamente por esa prueba de direcciones.

El tamaño fijo pasa a 692 KiB y el máximo con métodos a 884,25 KiB, más el
manifiesto. La captura termina sin crear un ZIP válido si un método queda incompleto
o el vínculo de contexto cambia. Si la primera palabra no cumple los límites,
se registra que no se pudo resolver la tabla y se conservan los bloques fijos.

Las pruebas usan memoria simulada para verificar los vínculos, cambios de contexto,
lecturas incompletas, límites y reutilización de bloques. Las firmas se compararon
además con los binarios aportados. Falta probar el lector en el cliente real y
analizar los métodos de esta ruta antes de incorporar el ataque básico nativo.
No se modificaron la persecución, el delay ni el ejecutor de caza.
