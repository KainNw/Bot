# Análisis del primer ZIP de contexto

Entrada: `Atlantica-contexto-20261102-180139.zip`, 19 539 bytes. El manifiesto declara
el cliente con SHA-256 `BC87A0CC5826AA7FB5E4FF10B6B7C1A349962BD8B146AD28EC3FFA9453FE04E6`,
PID de captura 16244, Auto Battle apagado, B=28 y HUNT=0. Los tamaños y hashes de los
cuatro bloques se verificaron. No se ejecutó código de esos archivos.

## Constructor y despachador

`0040C4E9` usa ECX como objeto y cuatro argumentos de pila, retorna el objeto en EAX
y termina en `ret 0x10`. En el flujo capturado:

- Escribe el primer argumento como word en `objeto+3`.
- Calcula `tamaño+9` y lo escribe como word en `objeto+0`.
- Pone a cero un dword en `objeto+5`.
- Copia el contenido del tercer argumento a `objeto+9` si hay datos y tamaño.
- Cuando el cuarto argumento es 1, rechaza tamaños de al menos 30000 mediante una
  ruta de registro. El significado del byte `objeto+2` no se deduce de este constructor.

Esto respalda que sea un constructor de mensaje; no identifica el formato final de
red ni demuestra que baste con fabricar un buffer para enviarlo.

`0043652D` primero llama a `004355EC`. Ese auxiliar comprueba un puntero en
`personaje+0x14` y que un campo en `puntero+0x380` sea 2. Si permite continuar,
el despachador carga el objeto global de `04A9290C` y salta al método virtual
`[vtable+0x64]`. Si no, retorna descartando un argumento de pila.

La implementación del método virtual no está en los bloques recibidos. No se ha
comprobado su hilo de ejecución, validación, propiedad del buffer o sincronización.
La siguiente captura lo resuelve en el proceso actual sin llamar al método.

## Datos y selección de personajes

- `0043529B` devuelve un short con signo desde `[personaje+0x30]+0xCA`.
- `0043523B` y `0043524B` devuelven shorts desde los desplazamientos `0xCC` y `0xCE`
  del mismo objeto de datos. La ausencia de ese puntero devuelve cero en esos getters.
- En el selector `0044D39F`, el primero se compara entre personaje y candidato;
  los otros dos se usan para sumar diferencias absolutas. Son coherentes con mapa,
  rejilla X e Y; requieren contraste con el HUD del usuario.
- La colección se obtiene de `objeto_global+0x828`. Sus punteros se acceden como
  `colección+0x28+índice*4`.
- `0044D367` acepta índices 1–449. `0044CFF5` comprueba pertenencia, puntero e índice
  menor que 450. Existen getters más amplios; 450 no se presenta como capacidad total
  de todas las colecciones del cliente, solo como límite de esta inspección.
- El selector exige el ID observado en `personaje+0x204` entre 3500 y 21999, excluye
  estados 0x22/0x23, un bit en `+0x388`, campos no negativos en `+0x318`/`+0x254`
  y mapas diferentes. También llama a `00433A4A`, que no está capturada.
- Recorre índices activos mediante auxiliares en `0044611C`/`0044613D`, tampoco
  incluidos en el primer ZIP. Esto impide tratar un barrido parcial del array como
  validación completa de que se puede atacar.

`0043ADD7` calcula `x²+y²+z²`; no toma raíz cuadrada. Corrige la hipótesis previa
de que devolvía distancia euclídea directa. La ordenación de `0044D39F` utiliza
distancia Manhattan sobre los dos shorts de rejilla, no ese auxiliar de 3D.

## Resultado y límites

Hay suficiente información para implementar una vista independiente, de solo lectura,
de candidatos y contrastar rejilla/índices con el juego. No hay todavía una ruta de
ataque independiente validada. Las llamadas no se deben ejecutar desde un hilo
arbitrario ni presentar como una API pública del cliente a partir de estos datos.

Quedan por capturar el método virtual real, los auxiliares de índice/identidad y
la comprobación adicional del objetivo. El cliente también cerró durante una prueba
manual sin caza, según el usuario; ese fallo sigue sin excepción o registro suficiente.
