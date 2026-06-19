# Estadística y probabilidad

## Probabilidad: el azar bajo reglas

La **probabilidad** mide la frecuencia relativa esperada de un evento en experimentos repetidos; varía entre 0 (imposible) y 1 (seguro). El **espacio muestral** Ω es el conjunto de todos los resultados posibles. La **regla de la adición** P(A ∪ B) = P(A) + P(B) − P(A ∩ B) y la **regla del producto** P(A ∩ B) = P(A) · P(B|A), donde P(B|A) es la probabilidad condicional. Dos eventos son **independientes** si P(A ∩ B) = P(A)·P(B). El **teorema de Bayes** P(A|B) = P(B|A)·P(A)/P(B) actualiza probabilidades a la luz de nueva evidencia; es la base del razonamiento probabilístico y del aprendizaje automático bayesiano.

## Variables aleatorias y distribuciones

Una **variable aleatoria** asigna un número a cada resultado del espacio muestral. Su **esperanza** (valor esperado) E[X] = Σ x·P(X=x) es el promedio a largo plazo. La **varianza** Var(X) = E[(X−μ)²] mide la dispersión. Distribuciones discretas importantes: Binomial (n ensayos, probabilidad p de éxito), Poisson (eventos raros en un intervalo). Distribuciones continuas: **Normal** (campana de Gauss), la más importante en estadística por el teorema central del límite; Exponencial (tiempos de espera). La distribución normal con media μ y desviación estándar σ se denota N(μ, σ²).

## El teorema central del límite

El **teorema central del límite** es uno de los resultados más poderosos de la probabilidad: la suma (o media) de un número grande de variables aleatorias independientes e idénticamente distribuidas tiende a una distribución normal, independientemente de la distribución original. Esto explica por qué tantas medidas reales siguen distribuciones aproximadamente normales (alturas, errores de medición, rendimientos de activos), y justifica el uso de la distribución normal como modelo universal en estadística.

## Estadística descriptiva e inferencial

La **estadística descriptiva** resume datos con medidas de tendencia central (media, mediana, moda) y de dispersión (rango, varianza, desviación estándar, cuartiles). La **estadística inferencial** extrae conclusiones sobre una población a partir de una muestra. Un **intervalo de confianza** da un rango plausible para el parámetro poblacional con una probabilidad dada (ej. 95%). El **test de hipótesis** evalúa si los datos son compatibles con una hipótesis nula: el **valor p** mide la probabilidad de obtener resultados tan extremos como los observados si la hipótesis nula fuera cierta; si p < 0,05 (umbral convencional) se rechaza. La regresión lineal modela la relación entre variables y permite predicciones.

## Probabilidad y ciencia

La estadística es la herramienta epistemológica de las ciencias empíricas. Sin ella no hay ensayos clínicos, genética de poblaciones, física de partículas (donde se distingue señal de ruido), ni inteligencia artificial. La **crisis de replicabilidad** en psicología y medicina revela el mal uso del valor p como criterio único de significación, generando debate sobre prácticas estadísticas. El **aprendizaje automático** es estadística computacional a gran escala: los modelos aprenden distribuciones de datos para hacer predicciones. La probabilidad conecta las matemáticas con la filosofía (interpretaciones frecuentista y bayesiana del azar) y con la física cuántica (donde la probabilidad no es ignorancia sino ontológica).
