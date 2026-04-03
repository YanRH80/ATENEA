# Arquitectura de Atenea — Guía Técnica Detallada

Este documento explica en profundidad cómo funciona cada parte de Atenea: el flujo de datos, las decisiones de diseño, los algoritmos implementados y cómo modificar o extender el sistema.

## Índice

1. [Visión General](#1-visión-general)
2. [Flujo de Datos Detallado](#2-flujo-de-datos-detallado)
3. [Módulo por Módulo](#3-módulo-por-módulo)
4. [Sistema de Configuración](#4-sistema-de-configuración)
5. [Integración con LLM](#5-integración-con-llm)
6. [Sistema de Scoring](#6-sistema-de-scoring)
7. [Interfaz Web (UI)](#7-interfaz-web-ui)
8. [Testing](#8-testing)
9. [Guía de Extensión](#9-guía-de-extensión)

---

## 1. Visión General

Atenea sigue una arquitectura de **pipeline lineal** donde cada módulo lee un artefacto y produce otro:

```
PDF → raw_output.md → clean-md.json → data.json → preguntas.json → sessions/history → analisis.json
```

### Principios arquitectónicos

- **Sin clases**: Todo es funciones puras + I/O en los bordes. No hay herencia, no hay estado mutable compartido. Esto simplifica el testing y el razonamiento sobre el código.

- **Acoplamiento por archivos**: Los módulos no se importan entre sí (excepto `storage`, `ai`, `utils` y `config`). Se comunican a través de archivos JSON. Esto significa que puedes reemplazar cualquier paso sin tocar los demás.

- **Configuración centralizada**: Todas las constantes viven en `config/`. Cada valor tiene su referencia científica. No hay magic numbers dispersos por el código.

- **LLM como caja negra**: `ai.py` es el único módulo que habla con el LLM. Todos los demás pasan un prompt string y reciben texto o JSON de vuelta.

### Mapa de dependencias

```
cli.py
  ├── convert.py    → storage, config
  ├── chunk.py      → storage, config
  ├── extract.py    → storage, ai, utils, config
  ├── generate.py   → storage, ai, utils, config
  ├── test_engine.py → storage, ai, scoring, config
  ├── analyze.py    → storage, scoring, config
  ├── advisor.py    → storage, ai, config
  └── ui/app.py     → (importa los módulos de pipeline bajo demanda)

Módulos transversales:
  storage.py   → config.defaults (para DEFAULT_DATA_DIR)
  ai.py        → config.models, config.prompts
  scoring.py   → config.defaults (constantes SM-2, Wilson, Bloom)
  utils.py     → config.defaults (MIN_ELEMENTS, MAX_ELEMENTS)
```

---

## 2. Flujo de Datos Detallado

### Step 1: PDF → Markdown (`convert.py`)

**Input**: Archivo PDF en disco
**Output**: `sources/src-NNN/raw_output.md` + `source-meta.json`

1. Valida el PDF (existencia, extensión `.pdf`, magic number `%PDF`)
2. Configura Marker con opciones de OCR (opcionalmente con asistencia LLM)
3. Ejecuta la conversión con `marker.PdfConverter`
4. Post-procesa el texto: limpia mojibake, caracteres de control, artefactos de OCR
5. Guarda el markdown crudo y metadata (fecha, nombre original, hash)
6. Actualiza `project.json` con la nueva fuente

**Decisión de diseño**: Se usa Marker en vez de PyPDF2/pdfminer porque Marker maneja mejor las tablas, imágenes y layouts complejos. El flag `--use-llm` activa un modo donde Marker usa un LLM para interpretar layouts ambiguos.

### Step 2: Markdown → clean-md.json (`chunk.py`)

**Input**: `raw_output.md`
**Output**: `clean-md.json`

1. Lee el markdown crudo del source
2. `split_into_sections()`: Detecta headers (`#`, `##`, `###`...) y construye un árbol jerárquico con parent-child. Cada sección tiene: id, título, nivel, rango de líneas, parent_id
3. `extract_lines()`: Recorre el texto línea por línea, asigna cada línea a su sección, ignora líneas vacías y headers puros
4. `extract_keywords()`: Tokeniza todas las líneas, filtra stopwords en español e inglés, cuenta frecuencias, extrae n-gramas (2 y 3 palabras), ordena por frecuencia descendente
5. `build_clean_md()`: Ensambla el JSON final con stats (total de secciones, líneas, keywords)

**Decisión de diseño**: Este paso es 100% algorítmico — no usa LLM. Esto lo hace rápido, determinista y testeable. Los keywords en esta etapa son "candidatos brutos"; el paso 3 (extract) los filtra con IA.

**Estructura de `clean-md.json`**:
```json
{
  "source_name": "biologia-celular",
  "source_id": "src-001",
  "sections": [
    {
      "id": "sec-001",
      "title": "La célula",
      "level": 1,
      "line_start": 1,
      "line_end": 45,
      "parent_id": null,
      "children": ["sec-002", "sec-003"]
    }
  ],
  "lines": [
    {
      "line_number": 5,
      "text": "La célula es la unidad básica de la vida.",
      "section_id": "sec-001"
    }
  ],
  "keywords": ["célula", "mitocondria", "ATP", "membrana celular", ...],
  "stats": {
    "total_sections": 12,
    "total_lines": 340,
    "total_keywords": 156
  }
}
```

### Step 3: clean-md.json → data.json (`extract.py`)

**Input**: `clean-md.json`
**Output**: `data.json`

Este es el módulo más complejo (~1,170 líneas). Ejecuta 6 sub-pasos:

#### 3a. Extraer Points
- Para cada sección, envía el texto + keywords candidatas al LLM
- El LLM filtra solo los keywords con relevancia especial
- Cada point tiene: id, term, relevance_reason, source_section

#### 3b. Extraer Paths
- Para cada sección, envía el texto + points disponibles al LLM
- El LLM genera péntadas CSPOJ (Context, Subject, Predicate, Object, Justification)
- Cada path referencia 5-9 points (regla 7±2)
- Validación: paths que no cumplen 7±2 se ajustan (se piden más points o se truncan)

#### 3c. Extraer Sets
- Envía todos los points al LLM
- El LLM los agrupa en sets semánticos (sin restricción de tamaño)
- Cada set tiene: id, name, description, point_ids

#### 3d. Extraer Maps
- Envía paths + sets al LLM
- El LLM agrupa 5-9 paths en mapas temáticos
- Cada map referencia los sets que cubre

#### 3e. Recuperar Points Huérfanos
- Detecta points que no aparecen en ningún path
- Genera paths adicionales para incluirlos
- Esto maximiza la cobertura del conocimiento extraído

#### 3f. Expandir Maps
- Detecta maps con menos de 5 paths
- Genera paths adicionales o redistribuye para cumplir 7±2
- Asegura 100% de cobertura set↔map

#### Enrichment final
- `enrich_graph()`: Añade enlaces bidireccionales (point→paths, path→maps, set→points, map→sets)
- Calcula `graph_stats`: connectivity, coverage, density
- Valida la integridad del grafo completo

**Estructura de `data.json`**:
```json
{
  "points": [
    {
      "id": "pt-a1b2c3",
      "term": "mitocondria",
      "relevance_reason": "Organelo central en el metabolismo energético",
      "source_section": "sec-003",
      "paths": ["pa-x1y2z3"]
    }
  ],
  "paths": [
    {
      "id": "pa-x1y2z3",
      "context": "Biología celular",
      "subject": "La mitocondria",
      "predicate": "produce",
      "object": "ATP mediante fosforilación oxidativa",
      "justification": "La cadena de transporte de electrones...",
      "point_ids": ["pt-a1b2c3", "pt-d4e5f6", ...],
      "map_id": "mp-m1n2o3"
    }
  ],
  "sets": [
    {
      "id": "st-s1t2u3",
      "name": "Organelos celulares",
      "description": "Estructuras internas de la célula",
      "point_ids": ["pt-a1b2c3", ...]
    }
  ],
  "maps": [
    {
      "id": "mp-m1n2o3",
      "name": "Metabolismo energético",
      "description": "Procesos de producción y uso de energía",
      "path_ids": ["pa-x1y2z3", ...],
      "set_ids": ["st-s1t2u3"]
    }
  ],
  "graph_stats": {
    "total_points": 45,
    "total_paths": 18,
    "total_sets": 6,
    "total_maps": 3,
    "orphan_points": 0,
    "avg_points_per_path": 6.8,
    "avg_paths_per_map": 6.0,
    "connectivity": 0.88,
    "seven_plus_minus_two_compliance": 0.88
  }
}
```

### Step 4: data.json → preguntas.json (`generate.py`)

**Input**: `data.json`
**Output**: `preguntas.json`

Genera tres tipos de preguntas a partir de cada path CSPOJ:

#### Tipo 1: Free Text (texto libre)
- Oculta un componente CSPOJ del path
- Formula la pregunta: "En [context], [subject] [predicate] ___. ¿Qué [component]?"
- No requiere LLM — es puramente template-based
- La dificultad depende del componente oculto (Object=fácil, Context=difícil)

#### Tipo 2: True/False (verdadero/falso)
- Toma un path CSPOJ completo
- El LLM altera un componente para crear una afirmación falsa plausible
- El estudiante debe detectar si es verdadero o falso
- Requiere LLM para generar alteraciones convincentes

#### Tipo 3: Multiple Choice (opción múltiple)
- Genera la pregunta como free-text
- El LLM genera 3 distractores plausibles
- Los distractores se validan: no deben ser sinónimos de la respuesta correcta
- Se calcula un quality score basado en la plausibilidad de los distractores

#### Modos de generación
- **Lite** (`--lite`, default): Solo free-text, sin LLM. Rápido y gratuito.
- **MC** (`--mc-only`): Solo opción múltiple. Requiere LLM.
- **Full** (`--no-lite`): Todos los tipos. Requiere LLM.

**Estructura de `preguntas.json`**:
```json
{
  "questions": [
    {
      "id": "q-abc123",
      "type": "free_text",
      "path_id": "pa-x1y2z3",
      "hidden_component": "object",
      "question_text": "En Biología celular, la mitocondria produce ___.",
      "correct_answer": "ATP mediante fosforilación oxidativa",
      "difficulty": 0.3,
      "bloom_level": "remember",
      "point_ids": ["pt-a1b2c3", ...]
    },
    {
      "id": "q-def456",
      "type": "multiple_choice",
      "path_id": "pa-x1y2z3",
      "question_text": "¿Qué produce la mitocondria?",
      "correct_answer": "ATP",
      "options": ["ATP", "ADN", "ARN mensajero", "Glucosa"],
      "quality_score": 0.85
    }
  ],
  "stats": {
    "total": 145,
    "by_type": {
      "free_text": 90,
      "multiple_choice": 45,
      "true_false": 10
    }
  }
}
```

### Step 5: Test Adaptativo (`test_engine.py`)

**Input**: `preguntas.json` + `history.json`
**Output**: `sessions.json` + `history.json` (actualizado)

1. `select_questions()`: Selecciona las N preguntas con mayor prioridad
   - Prioridad = f(urgencia_SM2, retención_estimada, nivel_Bloom, interleaving)
   - Las preguntas nunca vistas tienen prioridad máxima
   - Las preguntas que necesitan revisión (según SM-2) tienen prioridad alta
   - El interleaving bonus evita que se agrupen preguntas del mismo map

2. Para cada pregunta:
   - Muestra la pregunta al usuario
   - Recoge la respuesta
   - `evaluate_answer()`: Evalúa la respuesta
     - T/F y MC: comparación exacta
     - Free text: el LLM evalúa similitud semántica (score 0-5)
   - Actualiza SM-2: EF, intervalo, repeticiones
   - Actualiza Leitner box
   - Guarda en history

3. Guarda la sesión completa con timestamp y resumen

### Step 6: Analytics (`analyze.py`)

**Input**: `history.json` + `data.json`
**Output**: `analisis.json`

Calcula:
- **Mastery global**: Wilson score sobre todos los intentos
- **Por componente CSPOJ**: ¿Qué componente domina peor? (context, subject, predicate, object, justification)
- **Por path**: Score acumulado de cada path
- **Tendencia temporal**: ¿Mejora sesión a sesión?
- **Áreas débiles**: Paths/maps con peor rendimiento → sugerencia de repaso
- **Estado de revisión**: ¿Cuántas preguntas están al día vs. pendientes?

---

## 3. Módulo por Módulo

### `atenea/ai.py` (199 líneas)

Punto único de comunicación con LLMs. Usa litellm como abstracción.

```python
call_llm(prompt, model=None, temperature=None, max_tokens=None) → str
```
- Si no se especifica model, usa `config.models.DEFAULT_MODEL`
- Si no se especifica temperature, usa la del task en `config.models`
- Maneja timeouts y errores de API

```python
call_llm_json(prompt, model=None, temperature=None, max_tokens=None) → dict
```
- Llama a `call_llm()` y parsea el resultado como JSON
- Si falla el parseo, envía un prompt de corrección al LLM pidiendo que arregle el JSON
- Máximo 2 intentos de corrección

```python
detect_language(text) → str
```
- Usa `langdetect` para detectar el idioma del texto
- Se usa para inyectar `{language_instruction}` en los prompts

### `atenea/scoring.py` (477 líneas)

16 funciones puras. No hacen I/O, no tienen estado, no importan otros módulos de atenea. Son las más fáciles de testear.

**SM-2** (Wozniak, 1990):
```python
update_sm2(ef, interval, repetitions, quality) → (new_ef, new_interval, new_repetitions)
```
- `quality`: 0-5 (0=blackout total, 5=perfecto)
- Si quality ≥ 3: sube el intervalo exponencialmente
- Si quality < 3: reset a 1 día, mantiene EF
- EF mínimo: 1.3

**Retención** (Ebbinghaus):
```python
retention(t_days, stability) → float  # 0.0 a 1.0
```
- `R(t) = e^(-t/S)` donde S es la estabilidad (crece con repeticiones exitosas)

**Wilson Score** (intervalo de confianza):
```python
wilson_lower(successes, total, z=1.96) → float
```
- Límite inferior del intervalo de confianza al 95%
- Más conservador que `successes/total`: necesitas muestra grande para score alto

**Prioridad**:
```python
compute_priority(question, history) → float
```
- Combina: urgencia SM-2, retención inversa, bonus por nivel Bloom, bonus por interleaving
- Los pesos están en `config/defaults.py`

**Bloom**:
```python
should_escalate_bloom(history) → bool
bloom_label(level) → str  # "remember", "understand", "apply", ...
```
- Sube de nivel cuando el estudiante demuestra dominio en el nivel actual

**Leitner**:
```python
leitner_next_box(current_box, correct) → int
leitner_interval(box) → float  # días
```
- Sistema de cajas: correcta → sube, incorrecta → vuelve a caja 1
- Intervalos: caja 1=1d, caja 2=3d, caja 3=7d, caja 4=14d, caja 5=30d

### `atenea/storage.py` (298 líneas)

Todo el acceso a disco. Si se migra a SQLite, solo cambia este módulo.

**Convención**: Todas las funciones que escriben archivos crean directorios intermedios automáticamente (`os.makedirs(exist_ok=True)`).

**Estructura de directorios**:
```
DEFAULT_DATA_DIR/
└── {project_name}/
    ├── project.json
    ├── sources/
    │   └── src-{NNN}/
    │       ├── original.pdf
    │       ├── raw_output.md
    │       ├── clean-md.json
    │       └── source-meta.json
    ├── data.json
    ├── preguntas.json
    ├── sessions.json
    ├── history.json
    ├── analisis.json
    └── advisor-log.json
```

`next_source_id(project)`: Lee sources existentes, encuentra el mayor número, devuelve `src-{N+1}` con padding a 3 dígitos.

### `atenea/utils.py` (111 líneas)

Funciones de utilidad sin dependencias externas (solo `config.defaults`).

- `generate_id(prefix)`: UUID4 truncado a 8 chars con prefijo. Ej: `pt-a1b2c3d4`
- `validate_element_count(elements, min, max)`: Verifica que un path/map tenga 5-9 elementos
- `validate_json_schema(data, required_fields)`: Verifica que un dict tenga los campos requeridos
- `validate_cspoj(path)`: Verifica los 5 componentes CSPOJ en un path
- `truncate_text(text, max_len)`: Trunca con "..." para displays y logs

### `atenea/convert.py` (283 líneas)

**OCR Post-processing**: El método `postprocess_ocr()` limpia:
- Mojibake (ej: `Ã©` → `é`, secuencias UTF-8 mal decodificadas)
- Caracteres de control (U+0000-U+001F excepto newline/tab)
- Espacios múltiples y líneas en blanco excesivas
- Headers markdown rotos (ej: `# # Título` → `# Título`)

**Validación de PDF**: Verifica magic number `%PDF` en los primeros 4 bytes del archivo. Esto evita errores crípticos de Marker si se pasa un archivo que no es PDF.

### `atenea/chunk.py` (392 líneas)

**Detección de secciones**: Usa regex para detectar headers markdown (`^#{1,6}\s+`). Construye un árbol jerárquico: un `## Subsección` es hijo del `# Sección` que lo precede.

**Extracción de keywords**:
1. Tokeniza: split por espacios y puntuación
2. Normaliza: lowercase, strip
3. Filtra stopwords (listas hardcoded para español e inglés, ~200 palabras cada una)
4. Cuenta frecuencias de unigrams
5. Genera n-gramas (bigrams y trigrams) para capturar términos compuestos ("membrana celular", "ácido desoxirribonucleico")
6. Ordena por frecuencia descendente

### `atenea/test_engine.py` (515 líneas)

**Selección adaptativa**: El algoritmo de selección combina múltiples señales:

```
prioridad = w_urgency * urgencia_sm2
           + w_retention * (1 - retención_estimada)
           + w_bloom * bloom_bonus
           + w_interleave * interleave_bonus
```

Donde:
- `urgencia_sm2`: 1.0 si la pregunta está vencida (interval transcurrido), 0.0 si está al día
- `retención_estimada`: Curva de Ebbinghaus. Baja retención = más urgente
- `bloom_bonus`: Bonus para preguntas de nivel superior si domina el actual
- `interleave_bonus`: Bonus si la pregunta es de un map diferente al de la pregunta anterior

**Evaluación de respuestas libres**: El LLM recibe la pregunta, respuesta correcta y respuesta del usuario. Devuelve un score 0-5 y feedback explicativo.

### `atenea/advisor.py` (520 líneas)

Módulo de meta-aprendizaje. No es parte del pipeline principal sino una herramienta transversal.

- **Detección de dominio**: Analiza clean-md.json para determinar campo académico. Esto permite especializar prompts (ej: usar terminología médica si el documento es de medicina).

- **Feedback en lenguaje natural**: El usuario puede decir "las preguntas son demasiado fáciles" y el advisor lo interpreta como acciones concretas (subir dificultad, generar más preguntas de tipo context/justification).

- **Evolución de prompts**: Analiza el rendimiento del sistema y propone versiones mejoradas de los prompts en `config/prompts.py`.

---

## 4. Sistema de Configuración

### `config/defaults.py` (~330 líneas)

Cada constante tiene:
1. El valor
2. La referencia científica (autor, año, paper)
3. Explicación de por qué ese valor

Categorías:
- **Estructura**: MIN/MAX_ELEMENTS (7±2), DEFAULT_DATA_DIR
- **SM-2**: EF inicial (2.5), EF mínimo (1.3), intervalos (1d, 6d)
- **Wilson Score**: z=1.96 (95% confianza), MASTERY_THRESHOLD=0.85
- **Bloom**: Niveles (remember→create), umbrales de escalación
- **Prioridad**: Pesos de cada factor (urgencia, retención, bloom, interleave)
- **CSPOJ**: Dificultad por componente (object=0.2, context=0.9)
- **Leitner**: Intervalos por caja (1d, 3d, 7d, 14d, 30d)
- **Consistencia**: Ventana de evaluación, umbrales

### `config/models.py` (~152 líneas)

Selección de modelo LLM por tarea:
- `DEFAULT_MODEL`: `deepseek/deepseek-chat`
- Cada tarea puede tener un modelo diferente
- Temperaturas por tarea: extracción=0.3 (precisa), generación=0.7 (creativa), evaluación=0.1 (determinista)
- Max tokens por tarea
- Función `get_model(task)` resuelve el modelo para una tarea

### `config/prompts.py` (~330 líneas)

Templates de prompts con placeholders `{variable}`:
- `EXTRACT_POINTS_PROMPT`: Filtrado de keywords
- `EXTRACT_PATHS_PROMPT`: Generación de péntadas CSPOJ
- `EXTRACT_SETS_PROMPT`: Agrupación de points
- `EXTRACT_MAPS_PROMPT`: Agrupación de paths
- `GENERATE_MC_DISTRACTORS_PROMPT`: Generación de distractores MC
- `GENERATE_TF_ALTERATION_PROMPT`: Alteración para T/F
- `EVALUATE_FREE_TEXT_PROMPT`: Evaluación de respuestas
- `REFORMULATE_NATURAL_PROMPT`: Reformulación en lenguaje natural

Cada prompt sigue el formato:
```
## Rol
## Tarea
## Reglas / Criterios
## Input
## Output (schema JSON esperado)
{language_instruction}
```

---

## 5. Integración con LLM

### Flujo de una llamada LLM

```
Módulo (ej: extract.py)
  → Construye prompt con template de config/prompts.py
  → Inyecta variables (texto, keywords, idioma)
  → ai.call_llm_json(prompt, model, temperature)
    → litellm.completion(model, messages, temperature, max_tokens)
    → Parsea respuesta como JSON
    → Si falla: envía prompt de corrección, reintenta
  ← Devuelve dict
```

### Manejo de errores LLM

1. **Timeout**: litellm maneja timeouts internamente
2. **JSON inválido**: Se envía un prompt de corrección con el output original y el error de parseo
3. **Respuesta vacía**: Se reintenta una vez
4. **Rate limiting**: litellm tiene backoff automático

### Costo estimado

Con DeepSeek (~$0.14/1M tokens input, $0.28/1M output):
- Extracción completa de un PDF de 50 páginas: ~74,500 tokens → ~$0.02
- Generación MC de 50 preguntas: ~25,000 tokens → ~$0.01
- Evaluación de 20 respuestas libres: ~10,000 tokens → ~$0.005

---

## 6. Sistema de Scoring

### Ciclo de vida de una pregunta

```
Pregunta nueva
  │ (prioridad = MAX, nunca vista)
  ▼
Primera respuesta
  │ quality = infer_quality(score)
  │ ef, interval, reps = update_sm2(2.5, 0, 0, quality)
  │ box = leitner_next_box(0, correct)
  ▼
Seleccionada de nuevo (cuando interval vence)
  │ prioridad = compute_priority(q, history)
  │ retention = retention(days_since_last, stability)
  ▼
Segunda respuesta
  │ ef, interval, reps = update_sm2(ef, interval, reps, quality)
  │ ... (ciclo continúa)
```

### Interacción SM-2 ↔ Leitner

Ambos sistemas coexisten. SM-2 determina **cuándo** revisar; Leitner determina en qué **caja** está la pregunta (útil para visualización). Si hay conflicto, SM-2 tiene prioridad.

### Consistencia

```python
compute_consistency(history_entries, window=5) → float
```
- Mide estabilidad de rendimiento en las últimas N respuestas
- 1.0 = todas iguales (consistente), 0.0 = alternando acierto/fallo
- Se usa para: bonus de interleaving, decisión de escalar Bloom

---

## 7. Interfaz Web (UI)

### Stack

- **NiceGUI 3.9**: Framework Python para UIs web. Genera HTML/JS automáticamente.
- Puerto default: 8080
- Sin frontend separado — todo se define en Python

### Estructura de `ui/app.py` (~1,390 líneas)

```python
start_ui(port=8080, reload=False)
```

Páginas:
1. **/** — Proyectos: Tarjetas con estado del pipeline
2. **/pipeline/{project}** — Pipeline: 4 pasos con paneles expandibles
3. **/test/{project}** — Test: Sesión interactiva
4. **/inspect/{project}** — Inspector: Datos CSPOJ crudos + estadísticas
5. **/analytics/{project}** — Analytics: Gráficos de progreso

### Patrón de progreso

Cada paso del pipeline usa un callback pattern:

```python
def progress_callback(current, total, msg):
    progress_bar.value = current / total
    pct_label.text = f"{current/total:.0%}"
    log_area.push(msg)
    # Calcula ETA basado en tiempo transcurrido
```

### Paneles por paso

Cada paso tiene su propio `ui.expansion` panel con:
- Barra de progreso
- Labels: porcentaje, tiempo transcurrido, ETA
- Log de mensajes
- Label de estadísticas (post-ejecución)
- Border color: gris (idle) → amarillo (running) → verde (done) / rojo (error)

---

## 8. Testing

### Filosofía

- Solo se testean funciones puras (sin I/O, sin LLM)
- Las funciones que llaman al LLM se testean indirectamente via integration tests manuales
- `tmp_path` + `monkeypatch` para aislar tests de storage del filesystem real

### Fixture compartida

```python
@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    import config.defaults as defaults_mod
    monkeypatch.setattr(defaults_mod, "DEFAULT_DATA_DIR", str(tmp_path))
    return tmp_path
```

Esto redirige TODO el storage a un directorio temporal por test.

### Ejecutar tests

```bash
# Todos
pytest tests/ -v

# Solo scoring
pytest tests/test_scoring.py -v

# Con cobertura
pytest tests/ --cov=atenea --cov-report=term-missing

# Solo un test específico
pytest tests/test_scoring.py::test_update_sm2_perfect_answer -v
```

---

## 9. Guía de Extensión

### Agregar un nuevo tipo de pregunta

1. En `generate.py`: Crear función `generate_new_type(path, model)` que devuelva un dict con el formato de pregunta
2. En `generate.py`: Agregar constante `Q_NEW_TYPE = "new_type"`
3. En `generate_questions()`: Incluir el nuevo tipo en el loop de generación
4. En `test_engine.py` → `evaluate_answer()`: Agregar lógica de evaluación para el nuevo tipo
5. En `config/prompts.py`: Agregar el prompt template si usa LLM

### Agregar un nuevo paso al pipeline

1. Crear `atenea/new_step.py` con la función principal
2. En `cli.py`: Agregar comando Click
3. En `ui/app.py`: Agregar panel en la página de pipeline
4. Los datos de entrada/salida deben ser JSON files en el proyecto

### Cambiar el modelo LLM

Opción 1: Variable de entorno
```bash
export ATENEA_LLM_MODEL=gpt-4o
```

Opción 2: En `config/models.py`
```python
DEFAULT_MODEL = "openai/gpt-4o"
```

Opción 3: Por comando
```bash
atenea extract biologia --model anthropic/claude-sonnet-4-20250514
```

### Agregar un nuevo idioma de stopwords

En `chunk.py`, agregar la lista de stopwords al diccionario `STOPWORDS`:
```python
STOPWORDS["fr"] = {"le", "la", "les", "de", "du", ...}
```
El idioma se detecta automáticamente via `ai.detect_language()`.

### Cambiar la persistencia (JSON → SQLite)

Solo necesitas cambiar `storage.py`. La API pública (`save_json`, `load_json`, `list_projects`, etc.) se mantiene igual, pero internamente usa SQLite. Ningún otro módulo toca el filesystem directamente.
