"""
config/prompts.py — LLM Prompt Templates

Each prompt is a string with {placeholders} for runtime injection.
Double braces {{}} escape literal braces in f-string-style templates.
"""

# ============================================================
# LANGUAGE
# ============================================================

LANGUAGE_INSTRUCTIONS = {
    "es": "Responde exclusivamente en espanol.",
    "en": "Respond exclusively in English.",
}

# ============================================================
# EXTRACTION: Points (key concepts)
# ============================================================

EXTRACT_POINTS_PROMPT = """\
## Rol
Eres un experto en extraccion de conceptos clave de textos academicos.

## Tarea
Dado el siguiente texto y su lista de keywords candidatas, selecciona SOLO las keywords
que tienen relevancia especial para comprender el texto.

## Criterios de seleccion
- La keyword debe representar un concepto, entidad o proceso importante
- Debe ser mencionada en relaciones significativas (no solo de pasada)
- Preferir terminos tecnicos sobre terminos genericos
- Incluir acronimos con su forma expandida
- Excluir palabras comunes, conectores y terminos demasiado generales

## Input
### Keywords candidatas:
{keywords}

### Texto fuente (seccion: {section_title}):
{text}

## Output
Devuelve SOLO un JSON array de objetos, sin texto adicional:
[{{"term": "keyword seleccionada", "relevance_reason": "breve explicacion de por que es relevante"}}]

{language_instruction}"""

# ============================================================
# EXTRACTION: Paths (CSPOJ relationships)
# ============================================================

EXTRACT_PATHS_PROMPT = """\
## Rol
Eres un experto en analisis ontologico que descompone textos en pentadas CSPOJ
(Contexto-Sujeto-Predicado-Objeto-Justificacion).

## Tarea
Dado el texto y los puntos clave extraidos, genera pentadas ontologicas CSPOJ
que capturen las relaciones de conocimiento presentes en el texto.

## Estructura CSPOJ
- **Context (C)**: Dominio o contexto tematico de la afirmacion
- **Subject (S)**: Entidad principal sobre la que se afirma algo
- **Predicate (P)**: Funcion/relacion que conecta Sujeto con Objeto
  - Debe ser un verbo o frase verbal especifica (NO "esta relacionado con")
  - Ejemplos buenos: "produce", "inhibe", "se compone de", "regula", "requiere"
- **Object (O)**: Entidad o valor destino de la relacion
- **Justification (J)**: Cita VERBATIM del texto original que justifica esta relacion

## Reglas
- Cada camino DEBE referenciar entre {min_elements} y {max_elements} point_ids
- La Justificacion es OBLIGATORIAMENTE texto verbatim del original
- Generar caminos que cubran la mayor cantidad posible de puntos
- Priorizar relaciones causales, funcionales y jerarquicas

## Input
### Puntos clave disponibles:
{points}

### Texto fuente (seccion: {section_title}):
{text}

## Output
Devuelve SOLO un JSON array de objetos CSPOJ, sin texto adicional:
[{{
  "context": "dominio tematico",
  "subject": "entidad principal",
  "predicate": "relacion/funcion",
  "object": "entidad destino",
  "justification": "texto VERBATIM del original",
  "point_ids": ["pt_xxx", "pt_yyy", ...]
}}]

{language_instruction}"""

# ============================================================
# EXTRACTION: Sets (semantic groups)
# ============================================================

EXTRACT_SETS_PROMPT = """\
## Rol
Eres un experto en clasificacion semantica y organizacion del conocimiento.

## Tarea
Agrupa los siguientes puntos/keywords en conjuntos semanticos significativos.

## Reglas
- Cada conjunto debe tener un nombre descriptivo y conciso
- Un punto puede pertenecer a varios conjuntos
- Buscar agrupaciones por: tema, funcion, relacion causal, jerarquia, similitud

## Input
### Puntos a agrupar:
{points}

## Output
Devuelve SOLO un JSON array, sin texto adicional:
[{{
  "name": "nombre descriptivo del conjunto",
  "point_ids": ["pt_xxx", "pt_yyy", ...],
  "description": "breve explicacion del criterio de agrupacion"
}}]

{language_instruction}"""

# ============================================================
# EXTRACTION: Maps (meta-structures)
# ============================================================

EXTRACT_MAPS_PROMPT = """\
## Rol
Eres un experto en sintesis de conocimiento complejo y pensamiento sistemico.

## Tarea
Dado un conjunto de caminos CSPOJ, crea mapas agrupando caminos relacionados
en estructuras de conocimiento de nivel superior.

## Reglas
- Cada mapa agrupa entre {min_elements} y {max_elements} caminos
- El mapa debe representar una idea emergente, no solo una lista
- Priorizar: procesos multi-paso, causa-efecto complejas, sistemas con feedback

## Input
### Caminos CSPOJ disponibles:
{paths}

## Output
Devuelve SOLO un JSON array, sin texto adicional:
[{{
  "content": "descripcion textual del mapa como pentada CSPOJ de alto nivel",
  "path_ids": ["path_xxx", "path_yyy", ...],
  "description": "explicacion de como los caminos se interrelacionan"
}}]

{language_instruction}"""

# ============================================================
# QUESTION GENERATION: True/False
# ============================================================

GENERATE_TF_PROMPT = """\
## Rol
Eres un generador de preguntas de examen experto en crear distractores plausibles.

## Tarea
Genera una afirmacion FALSA pero plausible alterando el componente indicado
del siguiente CSPOJ.

## CSPOJ original
- Contexto: {context}
- Sujeto: {subject}
- Predicado: {predicate}
- Objeto: {object}
- Justificacion: {justification}

## Componente a alterar: {component}

## Reglas
- Debe ser plausible dentro del mismo dominio
- No debe ser absurda ni obviamente incorrecta
- La falsedad debe ser sutil

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{"statement": "la afirmacion falsa completa", "why_false": "explicacion breve de por que es falsa"}}

{language_instruction}"""

# ============================================================
# QUESTION GENERATION: Multiple Choice distractors
# ============================================================

GENERATE_MC_PROMPT = """\
## Rol
Eres un profesor universitario experto en preguntas tipo test.

## Tarea
Genera exactamente {n_distractors} opciones INCORRECTAS (distractores) para
la siguiente pregunta de opcion multiple.

## Pregunta
{question}

## Respuesta correcta
{correct_answer}

## Contexto (otros conceptos del tema)
{related_concepts}

## Reglas
- Cada distractor debe ser plausible dentro del dominio
- Variar el tipo de error entre los distractores
- Los distractores deben tener longitud similar a la respuesta correcta
- NO usar "Todas las anteriores" ni "Ninguna de las anteriores"

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{"distractors": ["distractor 1", "distractor 2", "distractor 3"]}}

{language_instruction}"""

# ============================================================
# QUESTION FORMULATION (natural language)
# ============================================================

FORMULATE_QUESTION_PROMPT = """\
## Rol
Eres un profesor universitario que formula preguntas de examen claras y precisas.

## Tarea
Reformula la siguiente pregunta para que suene natural, clara y profesional.

## Pregunta original:
{template_question}

## Contexto CSPOJ:
- Contexto: {context}
- Sujeto: {subject}
- Predicado: {predicate}
- Objeto: {object}

## Componente que se pregunta: {component}
## Respuesta esperada: {correct_answer}

## Output
Devuelve SOLO un JSON:
{{"question": "la pregunta reformulada", "stem": "contexto breve opcional"}}

{language_instruction}"""

# ============================================================
# ANSWER EVALUATION
# ============================================================

EVALUATE_ANSWER_PROMPT = """\
## Rol
Eres un evaluador academico justo y constructivo.

## Tarea
Evalua la respuesta del estudiante comparandola con la respuesta esperada.

## Pregunta
{question}

## Respuesta esperada
{expected}

## Justificacion original
{justification}

## Respuesta del estudiante
{user_answer}

## Criterios
- Evalua el SIGNIFICADO, no la redaccion exacta
- Sinonimos y parafrasis correctas son aceptables
- 0.0 = incorrecto, 0.5 = parcialmente correcto, 1.0 = correcto

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{"score": 0.0, "feedback": "explicacion constructiva", "correct": false}}

{language_instruction}"""
