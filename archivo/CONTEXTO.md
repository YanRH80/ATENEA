# ATENEA — Contexto completo para desarrollo

## Qué es

CLI que transforma PDFs académicos en una estructura de datos de conocimiento
(keywords, asociaciones, secuencias, sets) y genera preguntas tipo MIR/ENARM
con repetición espaciada (SM-2). El producto es la data structure. Todo lo
demás (Obsidian, Anki, SNOMED) son transformaciones modulares sobre ella.

## Estado actual: v0.3.0

Pipeline funcional end-to-end verificado con PDF real de nefrología (13 páginas):

```
atenea add <pdf> -p <proyecto>     → text.json + tables.json + images/
atenea study <proyecto>            → knowledge.json (43 kw, 27 assoc, 13 seq, 17 sets)
atenea generate <proyecto> -n 10   → questions.json (10 preguntas MIR con citas)
atenea test <proyecto> -n 10       → sesión interactiva + coverage.json + sessions.json
atenea review <proyecto>           → tabla de cobertura + lagunas
atenea show <proyecto> keywords    → lista con status icons
atenea show <proyecto> graph       → secuencias visuales con flechas
atenea show <proyecto> coverage    → tabla cobertura por tipo y fuente
atenea export md <proyecto>        → .md con [[wikilinks]] para Obsidian
atenea export csv <proyecto>       → .csv tab-separated para Anki
```

## Codebase: 17 archivos, 2,846 líneas

```
atenea/
  __init__.py       3    Versión
  ai.py           199    LLM: call_llm(), call_llm_json(), detect_language()
  cli.py          356    11 comandos Click
  export.py       204    export_md(), export_csv()
  generate.py     345    8 patrones MIR, select_targets(), retrieve_context(), RAG
  ingest.py       295    pdfplumber texto/tablas, PyMuPDF imágenes
  review.py       262    compute_coverage(), detect_gaps(), display
  storage.py      272    JSON I/O, rutas proyecto/source
  study.py        234    condense_to_knowledge(), merge, batching 5pp
  test_engine.py  349    SM-2, presentación Rich, sesiones
  utils.py         54    generate_id(), validate_element_count()
config/
  defaults.py      38    DATA_DIR, 7+-2, SM-2 constants
  models.py        41    deepseek/deepseek-chat, timeouts, temps
  prompts.py      128    CONDENSE_PROMPT, GENERATE_QUESTION_PROMPT, ANALYZE_GAPS
pyproject.toml     31    v0.3.0, deps
.gitignore         34    .env, __pycache__, data/, .claude/
```

---

# SWOT — Análisis honesto

## S — Fortalezas

1. **Pipeline funcional end-to-end.** Desde PDF hasta preguntas con citas
   verbatim y página. Verificado con datos reales.
2. **RAG sin embeddings.** El knowledge graph (source+page) ES el índice
   de retrieval. Simple, trazable, sin dependencias pesadas.
3. **Arquitectura modular limpia.** Cada módulo tiene una responsabilidad
   clara. storage.py es el único que toca disco. ai.py es el único que
   toca el LLM. Cambiar uno no rompe los demás.
4. **Data structure como producto.** No está acoplada a ningún output.
   Se puede transformar a .md, .csv, o lo que sea.
5. **Batching robusto.** study.py procesa en lotes de 5 páginas (~1 min/lote).
   No hay timeouts.
6. **10/10 preguntas estructuralmente perfectas.** Context, question,
   4 options, correct, justification con cita, targets.
7. **SM-2 implementado.** Status transitions unknown→testing→known
   con easiness factor, intervals, y sesión tracking.

## W — Debilidades (bugs y problemas reales)

1. **CRÍTICO: Grafo desconectado.** 12 from_terms y 21 to_terms en
   associations NO existen como keywords. Ej: la asociación dice
   "AINE --causa--> EFNa elevada" pero "AINE" y "EFNa elevada" no
   son keywords. El LLM usa términos diferentes en keywords vs
   associations. **Fix necesario:** post-proceso que normalice términos
   o que fuerce al LLM a usar solo términos ya extraídos.

2. **Solo 2 de 8 patrones usados.** En 10 preguntas solo salieron
   "asociacion_causal" (5) y "clasificacion_criterios" (5). El shuffle
   aleatorio no garantiza diversidad. **Fix:** round-robin forzado.

3. **Dedup de sequences es inexistente.** merge_knowledge() siempre
   appends sequences. Si corres study dos veces, se duplican todas.

4. **coverage.json busca por term (string) no por id.** Si un keyword
   cambia de nombre entre runs, el coverage se pierde. Frágil.

5. **No hay validación de JSON del LLM.** Si DeepSeek devuelve un
   keyword sin "term" o sin "definition", se guarda roto. No hay
   schema validation post-LLM.

6. **export md no escapa caracteres.** Si un term tiene | o [ se rompe
   el markdown.

7. **No hay comando para borrar/resetear datos.** Si knowledge.json
   se corrompe, hay que borrar a mano.

8. **ai.py carga dotenv al importar.** Side effect en import. Si .env
   no existe, funciona pero es dirty.

## O — Oportunidades

1. **Multi-source study.** Añadir 2-3 PDFs al mismo proyecto y que el
   knowledge graph se enriquezca, detectando conexiones entre fuentes.
2. **SNOMED/ontología lookup.** Cada keyword podría tener sinónimos y
   antónimos validados de ontologías médicas.
3. **Test adaptativo real.** Ahora selecciona preguntas random con
   prioridad. Podría ser un sistema de recomendación que detecte
   patrones de fallo y genere preguntas específicas para esas lagunas.
4. **Zotero integration.** Auto-poblar bibliografía desde citekey.
5. **Multi-idioma real.** El prompt está en español hardcoded pero
   detect_language() detecta el idioma. Podría ser 100% dinámico.
6. **Imágenes y tablas en preguntas.** Ahora solo se usa el texto.
   Las tablas extraídas y las imágenes podrían alimentar preguntas.
7. **Diff entre runs de study.** Mostrar qué se añadió nuevo vs
   qué ya existía.

## T — Amenazas

1. **Dependencia total de DeepSeek.** Si cambia pricing, rate limits,
   o calidad del modelo, todo el sistema se degrada. litellm permite
   cambiar a otro provider pero los prompts están optimizados para DS.
2. **Calidad del PDF.** pdfplumber falla con PDFs escaneados (sin OCR).
   Los CID codes del 12-Octubre causaron pérdida de caracteres ("FA"
   en lugar de "FRA"). Cada PDF nuevo puede traer problemas nuevos.
3. **Prompts frágiles.** CONDENSE_PROMPT genera output diferente cada
   vez. Los terms en keywords vs associations no coinciden. Si se
   cambia el prompt, puede romper el post-proceso.
4. **Escalabilidad JSON.** Con 10+ sources y 500+ keywords,
   knowledge.json puede volverse lento de merge/dedup.

---

# Arquitectura de retrieval: por qué NO embeddings (aún)

## El problema de cita

El sistema actual cita a nivel de PÁGINA. Un keyword dice `page: 3`, generate.py
carga toda la página 3 (~2000 chars), la mete en el prompt, y el LLM busca la
frase dentro de esos 2000 chars. A veces cita verbatim, a veces no. Inverificable.

## Por qué embeddings no resuelven esto mejor que chunking directo

Embeddings sirven para buscar por SIGNIFICADO sin saber dónde está la info.
Pero nosotros ya SABEMOS dónde está: cada keyword tiene source + page.
No necesitamos buscar "todo lo relacionado con insuficiencia renal" — necesitamos
el párrafo exacto de donde salió el keyword "Fracaso renal agudo".

Lo que falta es GRANULARIDAD, no SEMÁNTICA. La solución es más simple que
embeddings: partir el texto en chunks de ~400 chars (párrafos) con IDs,
y que los keywords/associations referencien chunk_id en vez de page.

## Cuándo SÍ valdrá la pena añadir embeddings

1. Cuando haya 10+ fuentes y buscar manualmente por chunk_id sea lento
2. Cuando se quiera cruzar información entre proyectos diferentes
3. Cuando se implemente SNOMED lookup (buscar por sinónimos semánticos)
4. Cuando se generen preguntas que integren conceptos de fuentes diferentes
   sin que el knowledge graph tenga la conexión explícita

En ese momento, se añade un embedder (sentence-transformers local, sin API)
que indexe los chunks existentes. El cambio es aditivo: chunks.json ya existe,
solo se añade un vector store encima.

## Plan: Bloque 9 de GUIA_DESARROLLO.md

ingest.py genera `chunks.json` junto a `text.json`:
```json
{"chunks": [
    {"id": "c_0001", "page": 1, "sub": null, "text": "La creatinina sérica..."},
    {"id": "c_0002", "page": 1, "sub": "1/2", "text": "Los criterios KDIGO definen..."},
    {"id": "c_0003", "page": 1, "sub": "2/2", "text": "...diuresis menor de 0.5 ml/kg/h..."}
]}
```
Párrafos > 400 chars se dividen en subpárrafos etiquetados "1/2", "2/2".
study.py referencia chunk_id. generate.py recupera chunks exactos (200 chars)
en vez de páginas (2000 chars) = prompts más baratos, citas verificables.

---

# Data structures — Esquemas reales

## knowledge.json
```json
{
  "updated": "2026-04-03T...",
  "sources": ["src-001"],
  "keywords": [
    {
      "id": "kw_a1b2c3d4",
      "term": "Fracaso renal agudo (FA)",
      "definition": "Síndrome de caída brusca del FG...",
      "page": 1,
      "tags": ["síndrome", "diagnóstico"],
      "source": "src-001",
      "status": "unknown"
    }
  ],
  "associations": [
    {
      "id": "as_e5f6g7h8",
      "from_term": "Criterios KDIGO",
      "to_term": "Fracaso renal agudo (FA)",
      "relation": "diagnostica",
      "description": "El cumplimiento de los criterios KDIGO establece el dx de FA.",
      "justification": "\"de acuerdo con las guías KDIGO...\" [[@12-octubre, p.1]]",
      "page": 1,
      "source": "src-001",
      "status": "unknown"
    }
  ],
  "sequences": [
    {
      "id": "sq_i9j0k1l2",
      "nodes": ["Hipoperfusión renal", "FA prerrenal", "Osm >400", "Nau ≤20", "EFNa <1%", "EFUrea <35%"],
      "description": "Cascada fisiopatológica del FA prerrenal",
      "pages": [2, 4],
      "source": "src-001",
      "status": "unknown"
    }
  ],
  "sets": [
    {
      "id": "st_m3n4o5p6",
      "name": "Criterios diagnósticos KDIGO para FA",
      "keyword_terms": ["Cr ≥0.3 mg/dl en 48h", "Cr ≥1.5x basal en 7d", "Diuresis <0.5 ml/kg/h 6h"],
      "description": "...",
      "source": "src-001"
    }
  ],
  "maps": []
}
```

## questions.json
```json
{
  "updated": "2026-04-03T...",
  "questions": [
    {
      "id": "q_x1y2z3w4",
      "pattern": "asociacion_causal",
      "context": "Paciente de 72 años...",
      "question": "¿Qué patrón temporal de la Cr se espera en nefrotoxicidad por contraste?",
      "options": {
        "A": "Incremento inmediato...",
        "B": "Incremento a las 24-48h, pico 3-5d, normalización 1 sem",
        "C": "Incremento progresivo 2 sem...",
        "D": "Incremento brusco a la semana..."
      },
      "correct": "B",
      "justification": "\"Se presenta como un incremento de la Cr a las 24-48h...\" [[@12-octubre, p.10]]",
      "targets": ["Contrastes yodados", "Nefrotoxicidad", "Creatinina"],
      "difficulty": 1
    }
  ]
}
```

## coverage.json
```json
{
  "updated": "...",
  "items": {
    "Fracaso renal agudo (FA)": {
      "ef": 2.5,
      "interval": 1.0,
      "reviews": 3,
      "correct": 2,
      "status": "testing",
      "last": "2026-04-03T..."
    }
  }
}
```

## sessions.json
```json
{
  "sessions": [
    {
      "date": "...",
      "total": 10,
      "correct": 7,
      "score": 70.0,
      "results": [
        {"question_id": "q_x1y2z3w4", "answer": "B", "correct": true, "targets": [...]}
      ]
    }
  ]
}
```

---

# Dependencias entre módulos

```
cli.py ──→ ingest.py ──→ storage.py
       ──→ study.py  ──→ ai.py, storage.py, config/prompts.py
       ──→ generate.py ──→ ai.py, storage.py, config/prompts.py
       ──→ test_engine.py ──→ storage.py, config/defaults.py
       ──→ review.py ──→ ai.py (opcional), storage.py
       ──→ export.py ──→ storage.py
```

Regla: **storage.py** es el único que toca disco. **ai.py** es el único
que toca el LLM. config/ son constantes puras. utils.py son funciones puras.

---

# Problemas conocidos que resolver

| # | Problema | Severidad | Módulo | Fix |
|---|----------|-----------|--------|-----|
| 1 | Grafo desconectado: terms de associations no coinciden con keywords | ALTA | study.py | Normalizar terms post-LLM o forzar al LLM a reusar terms exactos |
| 2 | Solo 2/8 patrones de pregunta usados | MEDIA | generate.py | Round-robin forzado en vez de random |
| 3 | Sequences se duplican al re-run study | MEDIA | study.py | Dedup por description o hash de nodes |
| 4 | Coverage usa string term como key, no id | MEDIA | test_engine.py | Migrar a IDs |
| 5 | Sin validación de schema post-LLM | MEDIA | study.py, generate.py | Validar campos requeridos |
| 6 | Characters no escapados en export md | BAJA | export.py | Escapar pipes y brackets |
| 7 | No hay reset/clean command | BAJA | cli.py | Añadir `atenea reset <project>` |
| 8 | dotenv import side-effect | BAJA | ai.py | Mover a cli.py entry point |

---

# Cómo correr

```bash
cd /ruta/a/ATENEA
export DEEPSEEK_API_KEY=sk-...

# Pipeline completo
python3 -m atenea.cli add ~/ruta/al.pdf -p nefrologia
python3 -m atenea.cli study nefrologia
python3 -m atenea.cli generate nefrologia -n 10
python3 -m atenea.cli test nefrologia -n 5
python3 -m atenea.cli review nefrologia
python3 -m atenea.cli show nefrologia keywords
python3 -m atenea.cli export md nefrologia
python3 -m atenea.cli export csv nefrologia
```
