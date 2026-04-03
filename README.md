# Atenea — Aprendizaje Adaptativo desde Documentos

Atenea es un sistema de aprendizaje adaptativo que transforma documentos PDF en sesiones de estudio personalizadas. Extrae conocimiento estructurado usando una ontología propia (CSPOJ), genera preguntas de distintos tipos y adapta la repetición usando algoritmos de memoria espaciada.

## Tabla de Contenidos

- [Concepto](#concepto)
- [Arquitectura del Pipeline](#arquitectura-del-pipeline)
- [Ontología CSPOJ](#ontología-cspoj)
- [Algoritmos de Aprendizaje](#algoritmos-de-aprendizaje)
- [Instalación](#instalación)
- [Uso](#uso)
- [Interfaz Web (UI)](#interfaz-web-ui)
- [Configuración](#configuración)
- [Docker](#docker)
- [Tests](#tests)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Referencia de Módulos](#referencia-de-módulos)

---

## Concepto

El problema: lees un PDF de 100 páginas, pero a la semana ya olvidaste el 80% (curva de olvido de Ebbinghaus). Atenea automatiza el ciclo completo:

1. **Convierte** el PDF a texto limpio
2. **Estructura** el texto en secciones, líneas y keywords
3. **Extrae** relaciones ontológicas (quién hace qué, por qué, en qué contexto)
4. **Genera** preguntas de verdadero/falso, opción múltiple y texto libre
5. **Evalúa** tus respuestas y adapta la dificultad
6. **Analiza** tu progreso y detecta puntos débiles

Todo sin base de datos — los datos son archivos JSON legibles que puedes inspeccionar y versionar con Git.

---

## Arquitectura del Pipeline

```
PDF
 │
 ▼
┌─────────────┐
│  1. convert  │──→ raw_output.md
└─────────────┘
       │
       ▼
┌─────────────┐
│  2. chunk    │──→ clean-md.json
└─────────────┘
       │
       ▼
┌─────────────┐
│  3. extract  │──→ data.json          ← usa LLM
└─────────────┘
       │
       ▼
┌──────────────┐
│  4. generate  │──→ preguntas.json
└──────────────┘
       │
       ▼
┌─────────────┐
│  5. test     │──→ sessions.json + history.json
└─────────────┘
       │
       ▼
┌──────────────┐
│  6. analyze   │──→ analisis.json
└──────────────┘
```

Cada paso produce un archivo JSON que sirve de entrada al siguiente. Esto permite:
- Ejecutar pasos individualmente
- Inspeccionar resultados intermedios
- Repetir un paso sin rehacer los anteriores

---

## Ontología CSPOJ

CSPOJ (Context-Subject-Predicate-Object-Justification) es una estructura de cinco componentes que representa una unidad de conocimiento:

| Componente | Pregunta que responde | Ejemplo |
|---|---|---|
| **Context** | ¿En qué campo/tema? | Biología celular |
| **Subject** | ¿Quién o qué? | La mitocondria |
| **Predicate** | ¿Qué hace/es? | produce |
| **Object** | ¿Qué resultado? | ATP (adenosín trifosfato) |
| **Justification** | ¿Por qué/cómo? | Mediante fosforilación oxidativa |

### Jerarquía de estructuras

```
Point (keyword relevante)
  └── referenciado por →  Path (péntada CSPOJ, 5-9 puntos)
                            └── agrupado en →  Map (5-9 paths temáticos)
                                                 └── cubierto por →  Set (agrupación semántica)
```

- **Point**: Un concepto clave extraído del texto (ej: "mitocondria", "ATP")
- **Path**: Una relación CSPOJ completa que conecta 5-9 puntos
- **Map**: Un mapa temático que agrupa 5-9 paths relacionados
- **Set**: Una agrupación semántica de puntos por tema

La **regla 7±2** (Miller, 1956) rige las cardinalidades: tanto paths como maps contienen entre 5 y 9 elementos, respetando los límites de la memoria de trabajo humana.

---

## Algoritmos de Aprendizaje

### SM-2 (Repetición Espaciada)

Basado en el algoritmo de Wozniak (1990), usado en SuperMemo y Anki:

- Cada pregunta tiene un **factor de facilidad** (EF) que empieza en 2.5
- Tras cada respuesta, el EF se ajusta: respuestas fáciles lo aumentan, difíciles lo reducen
- El **intervalo** entre repeticiones crece exponencialmente: 1 día → 6 días → 6×EF días → ...
- El EF nunca baja de 1.3 (las preguntas difíciles no se vuelven "imposibles")

### Curva de Olvido (Ebbinghaus)

La retención se modela como: `R(t) = e^(-t/S)`

Donde `t` es el tiempo desde la última revisión y `S` es la estabilidad de la memoria.

### Wilson Score (Dominio)

Para determinar si un estudiante "domina" un tema, se usa el intervalo de confianza de Wilson:

- No basta con acertar 3/3 — se necesita suficiente evidencia estadística
- Con 50/50 aciertos, el score Wilson es 0.93 (dominio confirmado)
- Con 3/3 aciertos, el score Wilson es solo 0.44 (muestra muy pequeña)

### Prioridad Adaptativa

La selección de preguntas combina:
- Urgencia SM-2 (¿está programada para hoy?)
- Retención estimada (¿cuánto ha olvidado?)
- Nivel de Bloom (preguntas más complejas primero si ya domina lo básico)
- Interleaving (mezclar temas para mejor retención)

---

## Instalación

### Requisitos

- Python 3.10 o superior
- Una API key de LLM (DeepSeek recomendado por costo/calidad)

### Instalación básica

```bash
# Clonar el repositorio
git clone <repo-url>
cd atenea

# Instalar (modo desarrollo)
pip install -e "."

# Con todas las dependencias opcionales
pip install -e ".[all]"
```

### Configurar API key

```bash
# Opción 1: Variable de entorno
export DEEPSEEK_API_KEY=sk-...

# Opción 2: Archivo .env (copiar template)
cp .env.example .env
# Editar .env con tu key
```

### Verificar instalación

```bash
atenea doctor
```

Esto comprueba: versión de Python, directorio de datos, paquetes instalados y API key configurada.

---

## Uso

### Pipeline completo (automático)

```bash
atenea pipeline mi-libro.pdf --project biologia
```

Ejecuta los 4 pasos de procesamiento: convert → chunk → extract → generate.

### Paso a paso (recomendado para control)

```bash
# 1. Convertir PDF a markdown
atenea convert mi-libro.pdf --project biologia

# 2. Estructurar en secciones, líneas y keywords
atenea chunk biologia

# 3. Extraer conocimiento CSPOJ (requiere LLM)
atenea extract biologia

# 4. Generar preguntas
atenea generate biologia              # Modo lite: solo texto libre, sin LLM
atenea generate biologia --no-lite    # Modo full: todos los tipos, con LLM
atenea generate biologia --mc-only    # Solo opción múltiple

# 5. Ejecutar test adaptativo
atenea test biologia

# 6. Ver analíticas de progreso
atenea analyze biologia
```

### Gestión de proyectos

```bash
# Listar proyectos
atenea projects

# Ver info detallada
atenea info biologia

# Inicializar directorio de datos
atenea init
atenea init --data-dir /ruta/custom
```

### AI Advisor

```bash
# Sesión interactiva del advisor
atenea advisor biologia

# Feedback rápido
atenea advisor biologia --feedback "las preguntas son demasiado fáciles"

# Solo sugerencias
atenea advisor biologia --suggest

# Evolucionar prompts del sistema
atenea advisor biologia --evolve-prompts
```

---

## Interfaz Web (UI)

Atenea incluye un dashboard web construido con NiceGUI:

```bash
pip install -e ".[ui]"
atenea ui                    # Puerto 8080 por defecto
atenea ui --port 3000        # Puerto custom
atenea ui --reload           # Auto-reload para desarrollo
```

### Funcionalidades del dashboard

- **Proyectos**: Tarjetas con estado del pipeline, conteo de PDFs y preguntas
- **Pipeline**: Ejecución paso a paso con:
  - Paneles expandibles por paso con logs en tiempo real
  - Barras de progreso con porcentaje, tiempo transcurrido y ETA
  - Selector de modo de generación (lite/MC/full)
- **Test**: Sesión de evaluación con preguntas MC renderizadas como botones
- **Inspector**: Explorador de datos CSPOJ con estadísticas de grafo
- **Analytics**: Visualización de progreso y áreas débiles

---

## Configuración

### Directorio de datos

Por defecto: `~/.atenea/data`. Override con:

```bash
export ATENEA_DATA_DIR=/ruta/a/mis/datos
```

### Archivos de configuración

| Archivo | Qué configura |
|---|---|
| `config/defaults.py` | Constantes globales: 7±2, SM-2, Bloom, umbrales |
| `config/models.py` | Modelos LLM por tarea, temperaturas, tokens máximos |
| `config/prompts.py` | Templates de prompts para el LLM (editables) |

### Modelos LLM

El modelo por defecto es `deepseek/deepseek-chat`. Se puede cambiar por tarea:

```python
# config/models.py
EXTRACTION_MODEL = "deepseek/deepseek-chat"     # Temp: 0.3
GENERATION_MODEL = "deepseek/deepseek-chat"      # Temp: 0.7
EVALUATION_MODEL = "deepseek/deepseek-chat"      # Temp: 0.1
```

Compatible con cualquier modelo soportado por litellm (OpenAI, Anthropic, local, etc.).

---

## Docker

### Con docker-compose

```bash
# Ejecutar doctor (verificación)
docker compose run atenea doctor

# Ejecutar pipeline completo
docker compose run atenea pipeline /data/libro.pdf --project bio

# Lanzar UI
docker compose up atenea-ui
# → http://localhost:8080
```

### Solo Docker

```bash
docker build -t atenea .
docker run -v atenea-data:/data -e DEEPSEEK_API_KEY=sk-... atenea doctor
```

---

## Tests

```bash
# Instalar dependencias de test
pip install -e ".[dev]"

# Ejecutar todos los tests
pytest tests/ -v

# Con cobertura
pytest tests/ -v --cov=atenea --cov-report=term-missing
```

### Suite de tests (139 tests)

| Archivo | Tests | Cobertura | Qué verifica |
|---|---|---|---|
| `test_scoring.py` | 53 | 92% | SM-2, retención, Wilson, prioridad, Bloom, Leitner |
| `test_generate.py` | 31 | 39% | Generación de preguntas, distractores, calidad |
| `test_utils.py` | 19 | 97% | IDs, validación 7±2, schemas JSON, CSPOJ |
| `test_storage.py` | 18 | 97% | I/O JSON/texto, directorios, fuentes |
| `test_chunk.py` | 10 | 71% | Secciones, líneas, keywords, n-gramas |

---

## Estructura del Proyecto

```
atenea/
├── atenea/                    # Paquete principal (~5,500 líneas)
│   ├── __init__.py
│   ├── cli.py                 # Entry point CLI (Click)
│   ├── convert.py             # Step 1: PDF → Markdown (Marker)
│   ├── chunk.py               # Step 2: Markdown → clean-md.json
│   ├── extract.py             # Step 3: Extracción CSPOJ (LLM)
│   ├── generate.py            # Step 4: Generación de preguntas
│   ├── test_engine.py         # Step 5: Motor de tests adaptativos
│   ├── analyze.py             # Step 6: Analíticas de aprendizaje
│   ├── advisor.py             # AI Advisor (meta-aprendizaje)
│   ├── scoring.py             # Algoritmos: SM-2, Wilson, Bloom, Leitner
│   ├── storage.py             # I/O de archivos JSON y gestión de proyectos
│   ├── ai.py                  # Interfaz unificada con LLM (litellm)
│   ├── utils.py               # Utilidades: IDs, validación, schemas
│   └── ui/
│       └── app.py             # Dashboard web (NiceGUI)
│
├── config/                    # Configuración (~550 líneas)
│   ├── __init__.py
│   ├── defaults.py            # Constantes globales con referencias científicas
│   ├── models.py              # Selección de modelos LLM por tarea
│   └── prompts.py             # Templates de prompts editables
│
├── tests/                     # Tests (~830 líneas, 139 tests)
│   ├── test_scoring.py
│   ├── test_generate.py
│   ├── test_utils.py
│   ├── test_storage.py
│   └── test_chunk.py
│
├── pyproject.toml             # Dependencias y metadata del paquete
├── Dockerfile                 # Imagen Docker (Python 3.12-slim)
├── docker-compose.yml         # Servicios: CLI + UI
├── .github/workflows/ci.yml   # CI: tests en Python 3.10/3.11/3.12
└── .env.example               # Template de variables de entorno
```

---

## Referencia de Módulos

### `atenea/convert.py` — Conversión PDF → Markdown

Usa la librería Marker para OCR y conversión. Incluye post-procesamiento para limpiar artefactos de OCR (mojibake, caracteres de control).

| Función | Descripción |
|---|---|
| `convert_pdf_to_markdown(pdf_path, project, use_llm)` | Convierte PDF, guarda `raw_output.md` y metadata |
| `postprocess_ocr(text)` | Limpia artefactos de OCR del texto |
| `validate_pdf(pdf_path)` | Valida existencia, extensión y magic number |
| `get_marker_config(use_llm)` | Construye configuración para Marker |

### `atenea/chunk.py` — Chunking de Markdown

Parsea el markdown en una estructura jerárquica. No usa IA — es procesamiento puramente algorítmico.

| Función | Descripción |
|---|---|
| `chunk_markdown(project, source_id)` | Orquesta el pipeline completo de chunking |
| `split_into_sections(md_text)` | Detecta headers y construye árbol jerárquico |
| `extract_lines(md_text, sections)` | Extrae líneas con números y asignación de sección |
| `extract_keywords(lines)` | Tokeniza, filtra stopwords (ES+EN), ordena por frecuencia |
| `build_clean_md(...)` | Ensambla el JSON final con stats |

### `atenea/extract.py` — Extracción de Conocimiento (IA)

El módulo más complejo (~1,170 líneas). Envía texto al LLM para extraer la ontología CSPOJ.

| Función | Descripción |
|---|---|
| `run_extraction(project, source_id, model, progress_callback)` | Pipeline completo de extracción |
| `extract_points(clean_md, model)` | Filtra keywords a puntos relevantes |
| `extract_paths(clean_md, points, model)` | Genera péntadas CSPOJ |
| `extract_sets(points, model)` | Agrupa puntos en sets semánticos |
| `extract_maps(paths, sets, model)` | Agrupa paths en mapas temáticos |
| `recover_orphan_points(...)` | Rescata puntos no referenciados |
| `expand_maps(...)` | Expande mapas para cumplir 7±2 |
| `enrich_graph(data)` | Conectividad bidireccional y estadísticas |
| `compute_extraction_stats(data, clean_md)` | Métricas de calidad de extracción |

### `atenea/generate.py` — Generación de Preguntas

Tres tipos de preguntas, cada una ocultando un componente CSPOJ diferente:

| Función | Descripción |
|---|---|
| `generate_questions(project, ..., progress_callback)` | Generación completa (T/F, MC, free-text) con LLM |
| `generate_questions_lite(project, ..., progress_callback)` | Solo free-text, sin llamadas LLM |
| `generate_true_false(path, model)` | Altera un componente CSPOJ para crear afirmación falsa |
| `generate_multiple_choice(path, model)` | Genera distractores plausibles con LLM |
| `generate_free_text(path, components)` | Oculta componente y pregunta por él |

### `atenea/test_engine.py` — Motor de Tests

Ejecuta sesiones de evaluación interactivas con selección adaptativa.

| Función | Descripción |
|---|---|
| `run_test(project, source_id, n_questions, model)` | Sesión completa de test |
| `select_questions(questions, history, n)` | Selección por prioridad SM-2 + interleaving |
| `evaluate_answer(question, user_answer, model)` | Evaluación (exacta para MC/T-F, LLM para texto) |

### `atenea/analyze.py` — Analíticas

Calcula métricas de progreso y detecta áreas débiles.

| Función | Descripción |
|---|---|
| `run_analytics(project)` | Pipeline completo de analíticas |
| `compute_analytics(project)` | Calcula mastery, componentes, tendencias, áreas débiles |
| `display_analytics(analytics)` | Muestra resultados con tablas Rich |

### `atenea/advisor.py` — AI Advisor

Módulo transversal de meta-aprendizaje que mejora el propio sistema.

| Función | Descripción |
|---|---|
| `run_advisor_session(project, ...)` | Sesión interactiva del advisor |
| `analyze_domain(clean_md, model)` | Detecta dominio académico del documento |
| `suggest_prompt_specialization(domain, model)` | Propone especialización de prompts |
| `process_user_feedback(feedback, project, model)` | Interpreta feedback en lenguaje natural |
| `suggest_priority_adjustment(project)` | Sugiere ajustes de pesos de prioridad |
| `evolve_prompt(prompt_name, project, model)` | Propone versión mejorada de un prompt |

### `atenea/scoring.py` — Algoritmos de Scoring

16 funciones puras sin efectos secundarios. Toda la lógica de repetición espaciada.

| Función | Descripción |
|---|---|
| `update_sm2(ef, interval, repetitions, quality)` | Actualiza parámetros SM-2 |
| `retention(t_days, stability)` | Retención estimada (Ebbinghaus) |
| `wilson_lower(successes, total, z)` | Intervalo de confianza Wilson |
| `is_mastered(successes, total)` | ¿Domina el tema? (Wilson ≥ 0.85) |
| `compute_priority(question, history)` | Prioridad adaptativa multi-factor |
| `should_escalate_bloom(history)` | ¿Subir nivel de Bloom? |
| `leitner_next_box(current_box, correct)` | Sistema de cajas Leitner |

### `atenea/storage.py` — Almacenamiento

Toda la I/O de archivos. Si algún día se migra a SQLite, solo se cambia este módulo.

| Función | Descripción |
|---|---|
| `save_json(path, data)` | Guarda JSON con UTF-8 e indentación |
| `load_json(path)` | Carga JSON, devuelve `None` si no existe |
| `save_text(path, text)` / `load_text(path)` | I/O de texto plano |
| `get_project_path(project, filename)` | Resuelve ruta dentro del proyecto |
| `get_source_path(project, source_id, filename)` | Ruta dentro de un source |
| `ensure_project_dirs(project)` | Crea directorios del proyecto |
| `list_projects()` / `list_sources(project)` | Lista proyectos/sources |

### `atenea/ai.py` — Interfaz LLM

Punto único de comunicación con modelos de lenguaje via litellm.

| Función | Descripción |
|---|---|
| `call_llm(prompt, model, temperature, max_tokens)` | Llamada LLM, devuelve texto |
| `call_llm_json(prompt, model, temperature, max_tokens)` | Llamada LLM, parsea JSON con retry |
| `detect_language(text)` | Detecta idioma del texto (langdetect) |

### `atenea/utils.py` — Utilidades

| Función | Descripción |
|---|---|
| `generate_id(prefix)` | Genera ID único con prefijo (ej: `pt-a1b2c3`) |
| `validate_element_count(elements, min, max)` | Valida cardinalidad 7±2 |
| `validate_json_schema(data, required_fields)` | Valida campos requeridos en dict |
| `validate_cspoj(path)` | Valida que un path tenga los 5 componentes CSPOJ |
| `truncate_text(text, max_len)` | Trunca texto con "..." |

---

## Organización de Datos por Proyecto

```
~/.atenea/data/                    # Raíz (configurable)
└── mi-proyecto/
    ├── project.json               # Metadata del proyecto
    ├── sources/
    │   └── src-001/
    │       ├── original.pdf       # PDF original
    │       ├── raw_output.md      # Markdown extraído
    │       ├── clean-md.json      # Texto estructurado
    │       └── source-meta.json   # Metadata del source
    ├── data.json                  # Conocimiento CSPOJ extraído
    ├── preguntas.json             # Preguntas generadas
    ├── sessions.json              # Historial de sesiones de test
    ├── history.json               # Historial por pregunta (SM-2)
    ├── analisis.json              # Analíticas de aprendizaje
    └── advisor-log.json           # Log del AI Advisor
```

---

## Principios de Diseño

1. **Solo funciones, no clases**: Todo el código es funcional. Sin OOP, sin herencia, sin estado mutable compartido.

2. **JSON como persistencia**: Archivos legibles, versionables, sin setup de base de datos.

3. **Pipeline desacoplado**: Cada paso lee un archivo y produce otro. Sin dependencias ocultas entre pasos.

4. **Configuración transparente**: Cada constante en `config/defaults.py` tiene la referencia científica de donde viene.

5. **LLM como servicio intercambiable**: Via litellm, se puede usar DeepSeek, OpenAI, Anthropic o modelos locales sin cambiar código.

6. **Progreso observable**: Callbacks de progreso en extract y generate para que la UI muestre avance en tiempo real.

---

## Licencia

MIT — Yan Rodriguez Hachimaru
