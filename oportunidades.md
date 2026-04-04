# Oportunidades post-MVP

Ideas validadas para implementar una vez el MVP funcione end-to-end.

---

## 1. Red bayesiana completa

**Que:** Reemplazar multiplicacion simple de probabilidades por tablas de probabilidad condicional (CPTs) en cada nodo.

**Que aportaria:**
- P(FRA | deshidratacion AND AINE) no es P(FRA|deshidratacion) x P(FRA|AINE) — hay interaccion. Una red bayesiana captura esto.
- Permite inferencia: dado que el paciente tiene FRA, cual es la P(AINE fue la causa)? (razonamiento diagnostico inverso)
- Permite simular escenarios: si cambio un farmaco, como cambia la probabilidad del outcome?

**Como se haria:**
1. Cada nodo tiene una CPT: `P(nodo | padres)` donde padres = nodos con aristas entrantes
2. Usar `pgmpy` (Python) para representar la red y hacer inferencia exacta (variable elimination) o aproximada (MCMC)
3. El LLM estima las CPTs iniciales a partir del texto, y se refinan con datos de test del usuario (Bayesian updating)
4. Visualizar con `rich` las probabilidades condicionales y los caminos de inferencia

**Requisitos previos:**
- Grafo homogeneo funcionando (MVP)
- Suficientes nodos (>50) para que las CPTs tengan sentido
- Validacion de que las probabilidades del LLM son razonables

**Complejidad:** Alta. ~2 semanas de desarrollo.

---

## 2. Embeddings para deteccion de aliases

**Que:** Usar un modelo de embeddings (e.g., `all-MiniLM-L6-v2`) para detectar automaticamente que "FRA" y "Fracaso renal agudo" son el mismo concepto.

**Que aportaria:**
- Elimina la dependencia del LLM para fusion de sinonimos
- Funciona cross-source (detecta que dos PDFs hablan del mismo concepto con nombres distintos)
- Permite calcular "distancia semantica" real entre nodos

**Como se haria:**
1. Generar embedding para cada nodo.canonical + aliases
2. Clustering por cosine similarity > threshold
3. Fusionar clusters como aliases del mismo nodo

---

## 3. Transferencia entre dominios (Functores)

**Que:** Detectar analogias estructurales entre subgrafos de distintos dominios.

**Que aportaria:**
- "El sistema renina-angiotensina en nefrologia es analogo al eje HPA en endocrino" — ambos son feedback loops con estructura similar
- Permite transferencia de aprendizaje: si dominas un dominio, el analogo se aprende mas rapido

**Como se haria:**
1. Graph isomorphism detection (subgraph matching)
2. Mapear nodos de un subgrafo a otro por similitud de vecindarios
3. Calcular "distancia funcorial" entre dominios

---

## 4. Deteccion de interferencia (pares confusos)

**Que:** Identificar pares de nodos que son faciles de confundir.

**Que aportaria:**
- "Nefritis intersticial vs NTA" — vecindarios similares pero tratamientos diferentes
- Genera preguntas de tipo "diferencial_excluyente" automaticamente
- Prioriza repaso de pares confusos

**Como se haria:**
1. Calcular similitud de vecindarios (Jaccard index sobre vecinos)
2. Nodos con alta similitud pero aristas diferentes = par confuso
3. Generar preguntas que fuercen la distincion

---

## 5. Actualizacion automatica del knowledge base

**Que:** Cuando se añade un nuevo PDF, actualizar probabilidades y confianzas de aristas existentes.

**Que aportaria:**
- Bayesian updating: un meta-analisis sube la confianza mas que un case report
- Deteccion de contradicciones: si una nueva fuente contradice una arista, flag automatico
- Tracking de "frescura" del conocimiento

---

## 6. Spreading activation en SM-2

**Que:** Cuando testas un nodo, los nodos vecinos reciben activacion parcial.

**Que aportaria:**
- Mas realista neurocientemente: recordar "AINE" activa parcialmente "nefrotoxicidad"
- Reduce el numero de preguntas necesarias para cobertura completa
- El "olvido" tambien se propaga: si no repasas un subgrafo, todo el cluster decae

---

## 7. Web UI con grafo interactivo

**Que:** Visualizacion del knowledge graph en browser con D3.js/Cytoscape.js.

**Que aportaria:**
- Zoom, pan, click en nodos para ver detalles
- Filtros por status, evidencia, probabilidad
- Mucho mas rico que la visualizacion CLI
