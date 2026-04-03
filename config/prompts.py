"""
config/prompts.py — LLM Prompt Templates for Atenea

CONVENTIONS:
- Each prompt is a string with {placeholders} for runtime injection
- Structured in ## sections with bulletpoints for easy manual/automatic editing
- {language_instruction} is injected dynamically based on detected language
- Double braces {{}} escape literal braces in f-string-style templates

EDITING TIPS:
- Change the ## Rol section to specialize for a domain
- Add/remove bullets in ## Reglas to change extraction behavior
- The ## Output section defines the expected JSON schema — change with care
- The advisor module can propose evolved versions of these prompts
"""


# ============================================================
# LANGUAGE INSTRUCTIONS
# Injected into all prompts based on detected document language.
# ============================================================

LANGUAGE_INSTRUCTIONS = {
    "es": "Responde exclusivamente en español.",
    "en": "Respond exclusively in English.",
}


# ============================================================
# STEP 3: KNOWLEDGE EXTRACTION PROMPTS
# ============================================================

EXTRACT_POINTS_PROMPT = """\
## Rol
Eres un experto en extracción de conceptos clave de textos académicos.

## Tarea
Dado el siguiente texto y su lista de keywords candidatas, selecciona SOLO las keywords
que tienen relevancia especial para comprender el texto.

## Criterios de selección
- La keyword debe representar un concepto, entidad o proceso importante
- Debe ser mencionada en relaciones significativas (no solo de pasada)
- Preferir términos técnicos sobre términos genéricos
- Incluir acrónimos con su forma expandida
- Excluir palabras comunes, conectores y términos demasiado generales

## Input
### Keywords candidatas:
{keywords}

### Texto fuente (sección: {section_title}):
{text}

## Output
Devuelve SOLO un JSON array de objetos, sin texto adicional:
[{{"term": "keyword seleccionada", "relevance_reason": "breve explicación de por qué es relevante"}}]

{language_instruction}"""

EXTRACT_PATHS_PROMPT = """\
## Rol
Eres un experto en análisis ontológico que descompone textos en péntadas CSPOJ
(Contexto-Sujeto-Predicado-Objeto-Justificación).

## Tarea
Dado el texto y los puntos clave extraídos, genera péntadas ontológicas CSPOJ
que capturen las relaciones de conocimiento presentes en el texto.

## Estructura CSPOJ
- **Context (C)**: Dominio o contexto temático de la afirmación
- **Subject (S)**: Entidad principal sobre la que se afirma algo
- **Predicate (P)**: Función/relación que conecta Sujeto con Objeto
  - Debe ser un verbo o frase verbal específica (NO "está relacionado con")
  - Ejemplos buenos: "produce", "inhibe", "se compone de", "regula", "requiere"
- **Object (O)**: Entidad o valor destino de la relación
- **Justification (J)**: Cita VERBATIM del texto original que justifica esta relación
  - DEBE ser copiada literalmente, palabra por palabra
  - Puede ser una o varias frases consecutivas del texto

## Reglas CRÍTICAS
- **OBLIGATORIO**: Cada camino DEBE referenciar entre {min_elements} y {max_elements} point_ids de la lista de puntos disponibles
- Si un camino no puede referenciar al menos {min_elements} puntos, NO lo incluyas
- Para cumplir este requisito, crea caminos que cubran relaciones amplias que involucren múltiples conceptos
- La Justificación es OBLIGATORIAMENTE texto verbatim del original — NO parafrasear
- Generar caminos que cubran la mayor cantidad posible de puntos
- Cada camino debe expresar una relación significativa, no trivial
- Priorizar relaciones causales, funcionales y jerárquicas

## Ejemplo de output correcto
Si los puntos disponibles son: pt_001 (mitocondria), pt_002 (ATP), pt_003 (fosforilación oxidativa),
pt_004 (membrana interna), pt_005 (cadena de transporte de electrones), pt_006 (gradiente de protones),
pt_007 (energía celular):

[{{
  "context": "Biología celular - metabolismo energético",
  "subject": "mitocondria",
  "predicate": "produce ATP mediante",
  "object": "fosforilación oxidativa en la membrana interna",
  "justification": "La mitocondria produce ATP mediante fosforilación oxidativa, un proceso que ocurre en la membrana interna mitocondrial a través de la cadena de transporte de electrones y el gradiente de protones.",
  "point_ids": ["pt_001", "pt_002", "pt_003", "pt_004", "pt_005", "pt_006", "pt_007"]
}}]

Nota: el ejemplo tiene 7 point_ids (dentro del rango {min_elements}-{max_elements}). TODOS tus caminos deben tener este nivel de cobertura de puntos.

## Input
### Puntos clave disponibles:
{points}

### Texto fuente (sección: {section_title}):
{text}

## Output
Devuelve SOLO un JSON array de objetos CSPOJ, sin texto adicional:
[{{
  "context": "dominio temático",
  "subject": "entidad principal",
  "predicate": "relación/función",
  "object": "entidad destino",
  "justification": "texto VERBATIM del original",
  "point_ids": ["pt_xxx", "pt_yyy", ...]
}}]

RECUERDA: Cada camino DEBE tener entre {min_elements} y {max_elements} point_ids. Caminos con menos de {min_elements} point_ids serán DESCARTADOS.

{language_instruction}"""

EXTRACT_SETS_PROMPT = """\
## Rol
Eres un experto en clasificación semántica y organización del conocimiento.

## Tarea
Agrupa los siguientes puntos/keywords en conjuntos semánticos significativos.

## Reglas
- Cada conjunto debe tener un nombre descriptivo y conciso
- Un punto puede pertenecer a varios conjuntos
- Los conjuntos NO tienen restricción de tamaño
- Buscar agrupaciones por:
  - Tema o subdisciplina
  - Función o rol
  - Relación causal
  - Jerarquía (general → específico)
  - Similitud conceptual

## Input
### Puntos a agrupar:
{points}

## Output
Devuelve SOLO un JSON array, sin texto adicional:
[{{
  "name": "nombre descriptivo del conjunto",
  "point_ids": ["pt_xxx", "pt_yyy", ...],
  "description": "breve explicación del criterio de agrupación"
}}]

{language_instruction}"""

EXTRACT_MAPS_PROMPT = """\
## Rol
Eres un experto en síntesis de conocimiento complejo y pensamiento sistémico.

## Tarea
Dado un conjunto de caminos CSPOJ, crea mapas de mayor complejidad agrupando
caminos relacionados en estructuras de conocimiento de nivel superior.

## Definición de Mapa
Un mapa es un "camino de caminos": una estructura donde algún elemento CSPOJ
(C, S, P, O, o J) de la péntada del mapa es en sí mismo otro camino completo.
Representa una idea más compleja que surge de la interrelación de múltiples caminos.

## Reglas
- Cada mapa agrupa entre {min_elements} y {max_elements} caminos
- El mapa debe representar una idea emergente, no solo una lista de caminos
- La descripción debe explicar cómo los caminos se interrelacionan
- Priorizar mapas que revelen:
  - Procesos multi-paso
  - Relaciones causa-efecto complejas
  - Sistemas con feedback loops
  - Jerarquías conceptuales

## Input
### Caminos CSPOJ disponibles:
{paths}

## Output
Devuelve SOLO un JSON array, sin texto adicional:
[{{
  "content": "descripción textual del mapa como péntada CSPOJ de alto nivel",
  "path_ids": ["path_xxx", "path_yyy", ...],
  "description": "explicación de cómo los caminos se interrelacionan para formar esta idea"
}}]

{language_instruction}"""

RECOVER_ORPHAN_PATHS_PROMPT = """\
## Rol
Eres un experto en análisis ontológico que crea relaciones CSPOJ para conectar
conceptos aislados con el resto del grafo de conocimiento.

## Tarea
Los siguientes puntos (conceptos) están POBREMENTE CONECTADOS en el grafo de conocimiento:
tienen 0 o 1 referencias desde los caminos CSPOJ existentes. Tu tarea es crear
NUEVOS caminos CSPOJ que integren estos puntos aislados con los puntos mejor conectados.

## Puntos aislados (a integrar):
{orphan_points}

## Puntos bien conectados (usar como anclas):
{hub_points}

## Texto fuente relevante:
{text}

## Reglas CRÍTICAS
- Cada nuevo camino DEBE incluir al menos 2 puntos aislados Y al menos 3 puntos conectados
- Cada camino DEBE tener entre {min_elements} y {max_elements} point_ids en total
- La Justificación DEBE ser texto verbatim del texto fuente
- Los caminos deben expresar relaciones reales presentes en el texto, NO inventadas
- Priorizar relaciones que revelen por qué estos conceptos son relevantes

## Output
JSON array de objetos CSPOJ:
[{{
  "context": "dominio temático",
  "subject": "entidad principal",
  "predicate": "relación/función",
  "object": "entidad destino",
  "justification": "texto VERBATIM del original",
  "point_ids": ["pt_xxx", "pt_yyy", ...]
}}]

{language_instruction}"""

EXPAND_MAPS_PROMPT = """\
## Rol
Eres un experto en síntesis de conocimiento que identifica macro-estructuras
emergentes en redes de relaciones ontológicas.

## Tarea
Los siguientes caminos CSPOJ NO pertenecen a ningún mapa (estructura de nivel superior).
Agrúpalos en mapas coherentes junto con los caminos ya mapeados si es necesario.

## Caminos sin mapa (a integrar):
{unmapped_paths}

## Mapas existentes (para contexto):
{existing_maps}

## Reglas
- Cada mapa agrupa entre {min_elements} y {max_elements} caminos
- Puedes crear mapas NUEVOS o EXPANDIR los existentes (añadiendo path_ids)
- Si expandes un mapa existente, incluye su map_id en el campo "extends"
- La descripción debe explicar la macro-relación emergente
- Priorizar agrupaciones por: proceso causal, subsistema funcional, secuencia temporal

## Output
JSON array:
[{{
  "content": "descripción de la macro-estructura",
  "path_ids": ["path_xxx", ...],
  "description": "cómo los caminos se interrelacionan",
  "extends": null
}}]

{language_instruction}"""


# ============================================================
# STEP 4: QUESTION GENERATION PROMPTS
# ============================================================

GENERATE_TF_PROMPT = """\
## Rol
Eres un generador de preguntas de examen experto en crear distractores plausibles.

## Tarea
Genera una afirmación FALSA pero plausible alterando el componente indicado
del siguiente CSPOJ. La afirmación debe ser difícil de distinguir de la verdadera
para alguien que no domine completamente el tema.

## CSPOJ original
- Contexto: {context}
- Sujeto: {subject}
- Predicado: {predicate}
- Objeto: {object}
- Justificación: {justification}

## Componente a alterar: {component}

## Reglas para generar la afirmación falsa
- Debe ser plausible dentro del mismo dominio
- No debe ser absurda ni obviamente incorrecta
- Idealmente, usar conceptos reales del mismo campo pero en relación incorrecta
- La falsedad debe ser sutil

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{"statement": "la afirmación falsa completa", "why_false": "explicación breve de por qué es falsa"}}

{language_instruction}"""

GENERATE_MC_PROMPT = """\
## Rol
Eres un profesor universitario experto en diseñar preguntas de examen tipo test.

## Tarea
Genera exactamente {n_distractors} opciones INCORRECTAS (distractores) para la
siguiente pregunta de opción múltiple.

## Pregunta
{question}

## Respuesta correcta
{correct_answer}

## Contexto (otros conceptos del tema)
{related_concepts}

## Reglas para generar distractores
- Cada distractor debe ser plausible dentro del dominio (no absurdo)
- Usar conceptos reales pero en contextos o relaciones incorrectas
- Variar el tipo de error entre los distractores:
  * Confusión de términos similares (ej: arteria renal vs vena renal)
  * Inversión de relaciones (ej: "aumenta" en vez de "disminuye")
  * Atribución incorrecta (concepto correcto, sujeto incorrecto)
  * Generalización o particularización excesiva
- Los distractores deben tener longitud similar a la respuesta correcta
- NO usar "Todas las anteriores" ni "Ninguna de las anteriores"
- Cada distractor debe ser claramente diferente de los demás

## Ejemplo de output correcto
Si la respuesta correcta es "creatinina sérica" y se piden 3 distractores:
{{"distractors": ["urea plasmática", "ácido úrico en sangre", "cistatina C urinaria"]}}

## Output
Devuelve SOLO un JSON objeto con el campo "distractors", sin texto adicional:
{{"distractors": ["distractor 1", "distractor 2", "distractor 3"]}}

{language_instruction}"""


# ============================================================
# STEP 5: ANSWER EVALUATION PROMPTS
FORMULATE_QUESTION_PROMPT = """\
## Rol
Eres un profesor universitario que formula preguntas de examen claras y precisas.

## Tarea
Reformula la siguiente pregunta de examen para que suene natural, clara y profesional.
La pregunta debe ser autosuficiente (comprensible sin contexto adicional).

## Pregunta original (generada por template):
{template_question}

## Contexto CSPOJ completo:
- Contexto: {context}
- Sujeto: {subject}
- Predicado: {predicate}
- Objeto: {object}

## Componente que se pregunta: {component}
## Respuesta esperada: {correct_answer}

## Reglas
- La pregunta debe sonar como una pregunta real de examen universitario
- Debe ser clara y sin ambigüedades
- No debe revelar la respuesta ni dar pistas obvias
- Mantener el nivel de dificultad adecuado al componente preguntado
- Si es multiple choice, la pregunta debe terminar en ":" o "?"
- Máximo 2 frases

## Output
Devuelve SOLO un JSON objeto:
{{"question": "la pregunta reformulada", "stem": "contexto breve opcional que precede a la pregunta"}}

{language_instruction}"""

# ============================================================

EVALUATE_ANSWER_PROMPT = """\
## Rol
Eres un evaluador académico justo y constructivo.

## Tarea
Evalúa la respuesta del estudiante comparándola con la respuesta esperada
y la justificación original del texto fuente.

## Pregunta formulada
{question}

## Respuesta esperada
{expected}

## Justificación original (texto verbatim de la fuente)
{justification}

## Respuesta del estudiante
{user_answer}

## Criterios de evaluación
- Evalúa el SIGNIFICADO, no la redacción exacta
- Sinónimos y paráfrasis correctas son aceptables
- Crédito parcial si captura la idea principal pero omite detalles importantes
- 0.0 = completamente incorrecto o irrelevante
- 0.5 = parcialmente correcto (idea principal pero faltan elementos clave)
- 1.0 = correcto (captura el significado completo)
- El feedback debe ser constructivo y educativo

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{"score": 0.0, "feedback": "explicación constructiva", "correct": false}}

{language_instruction}"""


# ============================================================
# ADVISOR PROMPTS
# ============================================================

DETECT_DOMAIN_PROMPT = """\
## Rol
Eres un clasificador de dominio académico y nivel educativo.

## Tarea
Dado las keywords y secciones del siguiente documento, identifica:
- El dominio principal (medicina, derecho, ingeniería, matemáticas, etc.)
- El subdominio específico
- El nivel académico estimado

## Input
### Keywords representativas:
{keywords}

### Títulos de secciones:
{section_titles}

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{
  "domain": "nombre del dominio principal",
  "subdomain": "nombre del subdominio específico",
  "level": "undergraduate|graduate|professional",
  "confidence": 0.0,
  "key_terminology": ["término especializado 1", "término especializado 2"]
}}

{language_instruction}"""

PROCESS_FEEDBACK_PROMPT = """\
## Rol
Eres un tutor adaptativo que interpreta el feedback del estudiante para
mejorar el sistema de aprendizaje.

## Contexto actual del estudiante
### Resumen de analytics:
{analytics_summary}

### Performance por componente CSPOJ:
{cspoj_performance}

### Historial de sesiones recientes:
{session_history}

## Feedback del estudiante
{user_feedback}

## Tarea
1. Interpreta qué quiere comunicar el estudiante
2. Identifica acciones concretas que mejorarían su experiencia
3. Para cada acción, indica qué variable de configuración cambiar y cómo

## Tipos de acciones posibles
- adjust_priority: Cambiar pesos de prioridad (W_URGENCY, etc.)
- change_question_mix: Alterar proporción de tipos de pregunta
- specialize_prompt: Adaptar un prompt a las necesidades del estudiante
- adjust_difficulty: Cambiar umbrales de dificultad/Bloom
- other: Cualquier otro ajuste no categorizado

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{
  "interpretation": "Lo que entiendo del feedback del estudiante...",
  "proposed_actions": [
    {{
      "action_type": "tipo de acción",
      "description": "Descripción legible de qué se propone hacer",
      "config_changes": [
        {{"variable": "nombre_variable", "current": "valor actual", "proposed": "valor propuesto"}}
      ],
      "expected_impact": "Qué debería mejorar con este cambio"
    }}
  ],
  "follow_up_question": "Pregunta para clarificar (null si no hace falta)"
}}

{language_instruction}"""

EVOLVE_PROMPT_PROMPT = """\
## Rol
Eres un prompt engineer experto que optimiza prompts basándose en
datos de performance reales.

## Prompt actual ({prompt_name}):
{current_prompt}

## Datos de performance con este prompt
### Métricas:
{performance_metrics}

### Errores comunes detectados:
{common_errors}

### Dominio del contenido:
{domain_info}

## Tarea
1. Analiza por qué el prompt actual produce los errores observados
2. Propón una versión mejorada que:
   - Mantenga la estructura (secciones ##, bulletpoints)
   - Corrija los errores detectados
   - Se especialice al dominio si es relevante
   - Conserve TODOS los placeholders {{...}} existentes
   - Sea compatible con el schema de output esperado

## Output
Devuelve SOLO un JSON, sin texto adicional:
{{
  "analysis": "Por qué el prompt actual falla en ciertos casos...",
  "evolved_prompt": "El prompt mejorado COMPLETO (no solo los cambios)...",
  "changes_summary": ["Cambio 1: ...", "Cambio 2: ..."],
  "expected_improvement": "Qué métricas deberían mejorar y por qué"
}}"""
