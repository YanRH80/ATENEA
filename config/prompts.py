"""
config/prompts.py — LLM Prompt Templates

Each prompt has {placeholders} for runtime injection.
Double braces {{}} escape literal braces.
"""

LANGUAGE_INSTRUCTIONS = {
    "es": "Responde exclusivamente en español.",
    "en": "Respond exclusively in English.",
}

# ============================================================
# STUDY: Condense text → knowledge structure
# ============================================================

CONDENSE_PROMPT = """\
## Rol
Eres un experto en síntesis de conocimiento académico.

## Tarea
Dado el siguiente texto académico, extrae TODA la información relevante como:

1. **keywords**: Conceptos clave (variables, entidades, clasificaciones, fármacos, procedimientos)
2. **associations**: Relaciones entre conceptos (A causa B, A inhibe B, A se clasifica en B)
3. **sequences**: Cadenas de {min_elements}-{max_elements} conceptos conectados (secuencias causales, algoritmos diagnósticos, cascadas fisiopatológicas)
4. **sets**: Agrupaciones semánticas (ej: "causas de X", "criterios de Y")

## Reglas
- Cada keyword debe tener: term, definition (1 línea), page (número de página donde aparece), tags (categorías)
- Cada association debe tener: from_term, to_term, relation (verbo: causa, inhibe, clasifica, indica...), description (1 línea), justification (cita verbatim del texto), page
- Cada sequence debe tener: nodes (lista de {min_elements}-{max_elements} términos conectados), description (1 línea), pages (lista de páginas)
- Cada set debe tener: name, keyword_terms (lista de términos), description
- Las justificaciones deben ser citas VERBATIM del texto original
- Para cada cita, incluir la referencia: [[@{citekey}, p.X]]

## Texto fuente
{text}

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{
  "keywords": [
    {{"term": "...", "definition": "...", "page": 1, "tags": ["variable", "lab"]}}
  ],
  "associations": [
    {{"from_term": "...", "to_term": "...", "relation": "causa", "description": "...", "justification": "cita verbatim [[@{citekey}, p.X]]", "page": 1}}
  ],
  "sequences": [
    {{"nodes": ["term1", "term2", "term3", "term4", "term5"], "description": "...", "pages": [1, 2]}}
  ],
  "sets": [
    {{"name": "...", "keyword_terms": ["term1", "term2"], "description": "..."}}
  ]
}}

{language_instruction}"""

# ============================================================
# GENERATE: Knowledge → MIR questions
# ============================================================

GENERATE_QUESTION_PROMPT = """\
## Rol
Eres un profesor de medicina que redacta preguntas tipo MIR/ENARM.

## Tarea
Genera {n_questions} preguntas tipo test basándote en el siguiente conocimiento.
Usa el patrón de pregunta indicado.

## Patrón: {pattern_name}
{pattern_description}

## Conocimiento disponible
{knowledge_context}

## Texto fuente (para citas verbatim)
{source_text}

## Reglas
- Cada pregunta debe tener: contexto clínico/teórico, pregunta, 5 opciones (A-E), respuesta correcta, justificación
- La justificación DEBE incluir cita verbatim del texto con referencia [{citekey}, p.X]
- Los distractores deben ser plausibles (del mismo dominio)
- Variar la dificultad: algunas directas, otras requieren razonamiento

## Output
Devuelve SOLO un JSON array:
[{{
  "context": "Paciente de...",
  "question": "¿Cuál es...?",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
  "correct": "B",
  "justification": "\\"cita verbatim\\" [{citekey}, p.X]",
  "targets": ["keyword_term_1", "keyword_term_2"],
  "difficulty": 1
}}]

{language_instruction}"""

# ============================================================
# ADVISOR: Document summary
# ============================================================

SUMMARIZE_DOCUMENT_PROMPT = """\
## Rol
Eres un experto en lectura rapida de articulos medicos y cientificos.

## Tarea
Resume el siguiente documento academico en 2-3 oraciones.

## Datos del documento
- Titulo: {title}
- Nivel de evidencia: {evidence_level}
- Tipo: {document_type}

## Texto del documento
{text}

## Reglas
- Primera oracion: objetivo principal del estudio/documento
- Segunda oracion: metodologia o diseno (si aplica)
- Tercera oracion: hallazgos clave o conclusiones principales
- Usa terminologia clinica precisa
- NO repitas el titulo
- Si el texto es insuficiente, indica que la informacion disponible es limitada

{language_instruction}"""

# ============================================================
# ADVISOR: Collection analysis
# ============================================================

COLLECTION_ADVISOR_PROMPT = """\
## Rol
Eres un asesor academico experto en planificacion de estudio para examenes medicos (MIR/ENARM).

## Tarea
Analiza la siguiente coleccion de documentos y genera un plan de estudio estructurado.

## Documentos en la coleccion
{collection_summary}

## Reglas
- Identifica clusters tematicos (agrupa documentos relacionados)
- Sugiere un orden de lectura optimo (de lo basico a lo complejo, de alta a baja evidencia)
- Estima el alcance del estudio (horas aproximadas, nivel de complejidad)
- Identifica 3-5 insights clave sobre la coleccion

## Output
Devuelve SOLO un JSON:
{{
  "collection_profile": "Descripcion de 2-3 oraciones sobre la coleccion",
  "topic_clusters": [
    {{"topic": "nombre del tema", "documents": ["citekey1", "citekey2"], "description": "que cubre este cluster"}}
  ],
  "study_roadmap": [
    {{"order": 1, "citekey": "citekey", "title": "titulo", "rationale": "por que leer esto primero"}}
  ],
  "estimated_scope": {{
    "total_documents": 0,
    "estimated_hours": 0.0,
    "complexity": "basico|intermedio|avanzado"
  }},
  "key_insights": ["insight 1", "insight 2", "insight 3"]
}}

{language_instruction}"""

# ============================================================
# REVIEW: Analyze gaps
# ============================================================

ANALYZE_GAPS_PROMPT = """\
## Rol
Eres un tutor adaptativo que identifica lagunas de conocimiento.

## Tarea
Analiza los resultados del estudiante y sugiere mejoras.

## Resultados recientes
{session_results}

## Conocimiento actual
{knowledge_summary}

## Output
Devuelve SOLO un JSON:
{{
  "weak_areas": ["tema 1", "tema 2"],
  "missing_concepts": ["concepto que falta"],
  "suggested_focus": "área prioritaria para próxima sesión",
  "refinements": [
    {{"keyword": "término", "suggestion": "mejorar definición/añadir detalle"}}
  ]
}}

{language_instruction}"""
