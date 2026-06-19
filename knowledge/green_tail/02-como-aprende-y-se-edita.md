# Cómo aprendo y edito mis propios archivos

## Aprendizaje de conocimiento nuevo

Puedo aprender contenido nuevo sin que nadie tenga que editar archivos a mano. Cuando me das un texto para aprender (mediante el botón "Enseñar" de la interfaz, o el endpoint /learn), hago lo siguiente: primero clasifico automáticamente a qué materia pertenece, luego formateo el texto como markdown estructurado con secciones, lo guardo en el archivo correcto dentro de knowledge/, y reconstruyo mi índice de búsqueda al instante para que el nuevo conocimiento quede disponible de inmediato. No necesito reiniciarme.

## Clasificación automática de dominio

Para decidir en qué materia guardar un texto nuevo, uso el mismo índice BM25 que uso para buscar. Tomo el texto entrante, lo puntúo contra el vocabulario de cada dominio existente y veo cuál tiene mayor densidad de coincidencia. Si el texto comparte mucho vocabulario con, por ejemplo, la economía (términos como mercado, precio, oferta, demanda), lo clasifico ahí con una confianza alta. Si el texto no encaja bien en ninguna materia existente —su densidad de coincidencia es baja—, reconozco que es un tema nuevo y propongo crear un dominio propio para él. Siempre explico mi razonamiento: digo qué dominio detecté, con qué confianza, cuáles son las alternativas cercanas y por qué tomé esa decisión. El usuario puede confirmar mi sugerencia o cambiarla.

## Discernir entre crear carpeta nueva o usar una existente

Mi criterio para discernir es la densidad de coincidencia léxica: qué proporción de los términos del texto nuevo ya existen en el vocabulario indexado de algún dominio. Si supera un umbral, asigno el texto a la materia existente más afín (sin pedirte que elijas carpeta). Si no lo supera, concluyo que el contenido trata de algo que aún no cubro y creo una carpeta y un tema nuevos, nombrados a partir del título. Así puedo crecer orgánicamente: empiezo con un conjunto de materias y voy añadiendo dominios completamente nuevos (astronomía, derecho, arte, lo que sea) a medida que me enseñan, distinguiendo solo cuándo algo es realmente nuevo y cuándo es una extensión de lo que ya sé.

## Enriquecer archivos existentes

Además de crear contenido nuevo, puedo enriquecer archivos que ya tengo para hacerlos más completos. Si me das información adicional sobre un tema que ya cubro, busco el archivo más relevante, le añado una nueva sección con el contenido extra, y reconstruyo el índice. De este modo un mismo documento crece y se vuelve más rico con el tiempo, en vez de fragmentarse en muchos archivos sueltos sobre lo mismo.

## Recarga automática

Tengo un hilo de vigilancia que revisa periódicamente (cada 30 segundos) si los archivos de knowledge/ han cambiado. Si detecta que se añadió, modificó o borró un archivo —ya sea por mí misma al aprender, o porque el usuario copió documentos directamente en la carpeta—, reconstruyo el índice automáticamente. Esto significa que cualquier cosa que se ponga en knowledge/ se vuelve parte de mi conocimiento sin intervención manual.
