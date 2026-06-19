# Cómo busco y respondo (algoritmo de recuperación)

## El algoritmo BM25

Para encontrar los pasajes relevantes uso BM25 (Best Match 25), el mismo algoritmo de ranking que usan motores de búsqueda como Elasticsearch y Lucene. BM25 puntúa cada pasaje según cuántas veces aparecen en él los términos de tu pregunta (frecuencia de término o TF), penalizando las palabras muy comunes que aparecen en casi todos los documentos (mediante la frecuencia inversa de documento o IDF) y ajustando por la longitud del pasaje (para que un texto largo no gane ventaja solo por tener más palabras). La fórmula combina estos factores con dos parámetros de calibración: k1 (controla la saturación de la frecuencia de término, en mi caso 1.5) y b (controla la normalización por longitud, en mi caso 0.75). Antes usaba TF-IDF con similitud coseno, pero migré a BM25 porque rankea mejor los términos raros y técnicos, que son justamente los que más importan en preguntas especializadas.

## El índice invertido

No comparo tu pregunta contra cada pasaje uno por uno (eso sería lentísimo). En su lugar construyo un índice invertido: una tabla que, para cada término, guarda la lista de pasajes donde aparece junto con su peso BM25 precalculado. Cuando preguntas algo, tokenizo tu consulta, busco cada término en el índice y sumo los pesos de los pasajes que coinciden. Así, buscar entre cientos de miles de pasajes toma milisegundos. El índice se guarda en disco (data/knowledge_index.json) y se reconstruye automáticamente solo cuando detecto que los archivos de knowledge/ han cambiado, comparando una firma de fecha y tamaño de cada archivo.

## Normalización, raíces y sinónimos

Para que "proteínas" encuentre documentos que dicen "proteína", aplico un proceso de stemming ligero: recorto sufijos de plural (-s, -es) y algunas terminaciones (-ción) para normalizar las palabras a una raíz común. Además tengo un diccionario de sinónimos y puentes entre español e inglés: si preguntas "what is DNA methylation" en inglés, expando la consulta para que también busque "metilación", "ADN", "epigenética" en español, y así encuentro el contenido aunque esté escrito en otro idioma. Esto me permite ser verdaderamente bilingüe sobre un mismo cuerpo de conocimiento.

## Cómo compongo la respuesta

Una vez tengo los pasajes ordenados por relevancia, no me limito a soltar el primero. Selecciono los mejores pasajes de fuentes y dominios distintos (evitando repetir contenido con más del 55% de solapamiento de palabras) y los combino en una respuesta de varias secciones, enlazándolas con frases de transición naturales como "Desde la perspectiva de la Física, se añade que…". El primer pasaje solo necesita superar un umbral bajo de relevancia; los siguientes deben ser claramente relevantes (umbral más alto) para no forzar conexiones irrelevantes. Cuántas secciones combino depende del perfil de recursos del equipo: en un PC potente compongo hasta 5 secciones (modo detallado); en uno modesto, 1 (modo breve). Al final añado una línea de conexiones que indica con qué otras materias se relaciona el tema.

## Niveles de confianza

A cada respuesta le asigno un nivel de confianza basado en la puntuación del mejor pasaje: alta, media o baja. Si la mejor coincidencia es muy débil (por debajo del umbral mínimo), reconozco honestamente que no tengo información suficiente, en lugar de inventar una respuesta. Esta confianza también gobierna mi capacidad de debatir: solo defiendo una postura si mi evidencia la sostiene.
