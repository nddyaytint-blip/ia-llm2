# Cálculo diferencial e integral

## El concepto de límite

El cálculo se funda en la noción de **límite**: el valor al que se aproxima una función f(x) cuando x se acerca a un punto c, aunque no lo alcance necesariamente. lim_{x→c} f(x) = L. Los límites permiten manejar el infinito de manera rigurosa. Una función es **continua** en c si el límite existe, la función está definida en c y ambos coinciden. La continuidad es intuitiva (la gráfica se puede trazar sin levantar el lápiz) pero la definición precisa requiere la noción épsilon-delta de Weierstrass, que formalizó el cálculo en el siglo XIX.

## La derivada: cambio instantáneo

La **derivada** f'(x) mide la tasa de cambio instantánea de f: f'(x) = lim_{h→0} [f(x+h) − f(x)] / h. Geométricamente, es la pendiente de la recta tangente a la curva en x. Las reglas de derivación (suma, producto, cociente, cadena) permiten derivar funciones compuestas. Derivadas notables: d/dx(xⁿ) = n·xⁿ⁻¹, d/dx(eˣ) = eˣ, d/dx(sin x) = cos x. La derivada segunda f''(x) indica la concavidad y la aceleración. En física, si s(t) es posición, s'(t) es velocidad y s''(t) es aceleración.

## Aplicaciones de la derivada

La derivada permite encontrar **máximos y mínimos** de funciones (donde f'(x) = 0 y f''(x) ≠ 0). En economía: maximizar beneficio o minimizar coste. En física: encontrar el punto de equilibrio. La **regla de L'Hôpital** resuelve indeterminaciones (0/0, ∞/∞) derivando numerador y denominador. La aproximación lineal f(x) ≈ f(a) + f'(a)·(x−a) es la base de los métodos numéricos. Las ecuaciones diferenciales (que involucran derivadas) describen prácticamente toda la física: el movimiento planetario, los circuitos eléctricos, la difusión del calor y el crecimiento poblacional.

## La integral: acumulación y área

La **integral** es la operación inversa a la derivada (antiderivada) y mide la acumulación. La **integral definida** ∫ₐᵇ f(x) dx da el área algebraica bajo la curva entre a y b. El **teorema fundamental del cálculo** une derivada e integral: si F'(x) = f(x), entonces ∫ₐᵇ f(x) dx = F(b) − F(a). Esto convierte el cálculo de áreas en evaluación de antiderivadas, una simplificación enorme. Técnicas de integración: sustitución, integración por partes, fracciones parciales.

## Cálculo multivariable y aplicaciones

El cálculo se extiende a funciones de varias variables. Las **derivadas parciales** miden el cambio respecto a una variable manteniendo fijas las demás. El **gradiente** ∇f señala la dirección de máximo crecimiento de una función. Las **integrales dobles y triples** calculan volúmenes y centros de masa. Las **ecuaciones diferenciales parciales** (EDP) describen fenómenos físicos complejos: la ecuación de calor, la ecuación de onda y las ecuaciones de Maxwell del electromagnetismo. El cálculo es el lenguaje matemático con que la física, la ingeniería y la economía describen el mundo cambiante.
