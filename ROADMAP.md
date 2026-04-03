# ATENEA — Roadmap de Desarrollo

> **Momento 0**: 3 abril 2026. Reset completo. Solo queda la infraestructura probada.
> **Principio rector**: El aprendizaje debe parecerse a la adquisición del lenguaje
> materno por un bebé, no al estudio memorístico de un adulto.

---

## Filosofía: Adquisición vs. Estudio

Un bebé no memoriza reglas gramaticales. **Absorbe patrones** por exposición
repetida, construye asociaciones implícitas, y solo después las formaliza.

Atenea debe funcionar igual:

1. **Exposición**: Presentar hechos simples del texto (reconocimiento)
2. **Asociación**: Conectar hechos entre sí (relaciones)
3. **Patrón**: Detectar regularidades implícitas (estructura)
4. **Producción**: El estudiante genera conocimiento, no solo lo reconoce

Cada fase se construye sobre la anterior. Las preguntas de fases previas
**siguen apareciendo** (repetición espaciada), pero se añaden preguntas
más profundas conforme el estudiante demuestra dominio.

### Regla de oro

> Si el LLM genera mejor output que el código hard-coded, se usa el LLM.
> Solo se codifica proceduralmente lo que se puede mejorar de forma demostrable.

---

## Lo que ya funciona (infraestructura)

| Módulo | Líneas | Función |
|--------|--------|---------|
| `atenea/convert.py` | 282 | PDF → Markdown (Marker + OCR cleanup) |
| `atenea/chunk.py` | 391 | Markdown → secciones + keywords (determinístico) |
| `atenea/ai.py` | 199 | Interfaz LLM unificada (litellm, JSON retry) |
| `atenea/storage.py` | 298 | I/O JSON + gestión de proyectos |
| `atenea/utils.py` | 111 | IDs, validación, truncado |
| `atenea/cli.py` | ~150 | CLI (convert, chunk, pipeline, projects, info) |
| `config/prompts.py` | ~400 | Prompts de extracción y generación |
| `config/defaults.py` | ~100 | Constantes esenciales (SM-2, 7±2) |
| `config/models.py` | 152 | Modelo por tarea, temperaturas |

---

## Fase 1 — Preguntas directas del texto (Exposición)

**Objetivo**: Dado un PDF, generar preguntas que verifiquen si el estudiante
**ha leído y recuerda** el contenido explícito.

**Sin grafo de conocimiento**. Solo texto → LLM → preguntas.

### 1.1 — Prompt: generación de preguntas de reconocimiento
```
Input:  Sección de texto (de clean-md.json)
Output: Lista de preguntas factuales simples
```
- `atenea/generate.py` → función `generate_recognition_questions(section_text, section_title)`
- Un solo prompt al LLM por sección
- Tipos: verdadero/falso, completar, opción múltiple
- Dificultad 1: preguntas que se responden leyendo el texto
- **Validar**: ejecutar manualmente, revisar calidad antes de seguir

### 1.2 — CLI: comando `atenea generate <project>`
- Itera sobre secciones de clean-md.json
- Llama `generate_recognition_questions()` por sección
- Guarda en `preguntas.json`
- Output en terminal: muestra 3-5 preguntas de ejemplo

### 1.3 — Test interactivo básico en terminal
- `atenea/test_engine.py` → función `run_test(project_name)`
- Presenta preguntas una a una en terminal
- Evalúa: T/F y MC por coincidencia exacta, texto libre por LLM
- Registra respuestas en `history.json`
- Output: score final + preguntas falladas con explicación

### 1.4 — Repetición espaciada mínima
- `atenea/scoring.py` → solo `update_sm2()` y `needs_review()`
- En la siguiente sesión, las preguntas falladas aparecen primero
- Las preguntas acertadas aparecen con intervalo creciente
- **Nada más**: no Wilson, no Bloom, no prioridad compleja

### Criterio de avance
- [ ] Generar preguntas para un PDF real y que >80% sean útiles
- [ ] Completar una sesión de test de 25 preguntas en terminal
- [ ] En la segunda sesión, las falladas de la primera reaparecen

---

## Fase 2 — Extracción de nodos (Asociación)

**Objetivo**: Identificar los **conceptos clave** del texto y generar preguntas
que prueben la comprensión de cada concepto individual.

### 2.1 — Extracción de conceptos (points)
- `atenea/extract.py` → función `extract_concepts(clean_md)`
- Un prompt por sección: "¿Cuáles son los conceptos clave?"
- Output: lista de `{term, definition, importance}`
- Guardar en `data.json` campo `concepts`

### 2.2 — Preguntas de definición y comprensión
- Ampliar `generate.py` → `generate_concept_questions(concepts, section_text)`
- "¿Qué es X?", "Define X", "¿Cuál es la función de X?"
- Más profundas que Fase 1: requieren comprensión, no solo recuerdo
- Mezclar con preguntas de Fase 1 en las sesiones

### 2.3 — Feedback: qué conceptos domina el estudiante
- Tracking por concepto: % acierto por concept_id
- Mostrar al final de cada sesión: "Conceptos dominados / por repasar"
- Sin fórmulas complejas: simplemente `correctas / intentadas`

### Criterio de avance
- [ ] Los conceptos extraídos cubren >90% del contenido relevante
- [ ] Las preguntas de definición son claras y no ambiguas
- [ ] El tracking por concepto funciona y es informativo

---

## Fase 3 — Extracción de relaciones (Patrón)

**Objetivo**: Extraer **cómo se conectan** los conceptos (relaciones, causas,
secuencias) y generar preguntas que prueben esas conexiones.

### 3.1 — Extracción de relaciones (paths CSPOJ simplificado)
- Ampliar `extract.py` → `extract_relationships(concepts, section_text)`
- Output: `{subject, predicate, object, justification}`
- Sin forzar 7±2 artificialmente — solo relaciones reales
- La justificación es cita verbatim del texto

### 3.2 — Preguntas de relación
- Ampliar `generate.py` → `generate_relationship_questions(relationships)`
- "¿Qué causa X?", "¿Cómo se relaciona X con Y?", "¿Por qué X produce Y?"
- Ocultar diferentes componentes para variar dificultad
- Mezclar con preguntas de Fases 1 y 2

### 3.3 — Grafo de conocimiento visual (terminal)
- `atenea info <project> --graph` muestra nodos + conexiones en ASCII
- Nodos coloreados por dominio (verde=dominado, rojo=débil)
- Permite al estudiante ver qué sabe y qué no

### Criterio de avance
- [ ] Las relaciones extraídas son correctas y no triviales
- [ ] Las preguntas de relación son significativamente más difíciles que las de Fase 1-2
- [ ] El estudiante puede ver su progreso en el grafo

---

## Fase 4 — Conocimiento implícito (Producción)

**Objetivo**: Generar preguntas que prueben conocimiento **no explícito** en el
texto: inferencias, analogías, aplicaciones, contraejemplos.

### 4.1 — Preguntas de inferencia
- `generate.py` → `generate_inference_questions(relationships, concepts)`
- "Si X cambia, ¿qué pasa con Y?"
- "¿Qué pasaría si no existiera X?"
- Requiere que el LLM razone sobre el grafo, no solo lo lea

### 4.2 — Preguntas de síntesis multi-fuente
- Cuando hay >1 PDF en el proyecto, cruzar conocimiento
- "¿Qué tienen en común X (fuente A) e Y (fuente B)?"
- "¿Cómo se complementan las perspectivas de fuente A y fuente B sobre Z?"

### 4.3 — Preguntas de aplicación
- "Dado este caso clínico/problema/escenario, ¿qué harías?"
- Requiere integrar múltiples conceptos y relaciones
- Bloom niveles 3-5: aplicar, analizar, evaluar

### 4.4 — Evolución adaptativa de prompts
- Si un tipo de pregunta tiene baja calidad, mejorar el prompt automáticamente
- Guardar versiones de prompts con métricas de performance
- El LLM propone mejoras a sus propios prompts basándose en errores detectados

### Criterio de avance
- [ ] Las preguntas de inferencia revelan comprensión real, no memorización
- [ ] El cruce multi-fuente produce insights no evidentes en cada fuente individual
- [ ] El estudiante reporta que las preguntas le ayudan a entender, no solo a recordar

---

## Fase 5 — UI y distribución

**Solo cuando Fases 1-4 funcionen bien en CLI.**

### 5.1 — Dashboard web (NiceGUI o similar)
### 5.2 — Docker + deploy
### 5.3 — Multi-usuario
### 5.4 — Analytics avanzados

---

## Reglas de desarrollo

1. **Una función a la vez**. No avanzar a la siguiente hasta que la actual
   produzca output verificablemente útil.

2. **LLM-first**. Si el LLM puede hacer algo bien con un buen prompt,
   no escribir código para hacerlo. Solo codificar cuando:
   - El LLM es inconsistente (necesita validación)
   - El LLM es demasiado lento (necesita caché)
   - El LLM es demasiado caro (necesita heurística local)

3. **Test real antes de test automatizado**. Ejecutar con un PDF real,
   revisar output manualmente, LUEGO escribir tests.

4. **No over-engineer**. Sin abstracciones prematuras, sin features
   especulativos, sin optimización sin datos.

5. **El criterio de avance es funcional**, no técnico. "¿Las preguntas
   generadas sirven para aprender?" es la única pregunta que importa.
