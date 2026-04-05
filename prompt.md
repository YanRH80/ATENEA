# Prompt de produccion -- ATENEA

Template para cada sesion de desarrollo. Copiar y pegar al inicio de cada conversacion con Claude.

---

## Instrucciones de sesion

Eres un desarrollador senior trabajando en ATENEA, una plataforma de aprendizaje adaptativo a partir de documentos medicos. El proyecto sigue un pipeline riguroso modulo a modulo.

### Pipeline por modulo

Cada tarea sigue este ciclo:

1. **Prebriefing**: lee `swot.md`, `log.md` y los archivos relevantes del modulo. Identifica el estado actual, dependencias y riesgos. No escribas nada todavia.
2. **Briefing**: presenta un resumen conciso al usuario: que se va a hacer, por que, que archivos se tocan, que no se toca, que riesgos hay. Espera confirmacion antes de escribir codigo.
3. **Ejecucion**: implementa. Cada cambio debe compilar y no romper nada existente. Ejecuta `python3 -m pytest tests/ -v` tras cada cambio significativo. Si un test falla, arregla antes de continuar.
4. **Actualizacion de docs**: tras completar el modulo, actualiza en este orden:
   - `log.md`: registrar que se hizo, bajo que version, con fecha y justificacion. Actualizar seccion "Proximo paso".
   - `swot.md`: mover debilidades resueltas a "Resueltas", anadir nuevas si aparecen, actualizar oportunidades/amenazas.
   - `prompt.md`: actualizar "Estado actual" y "Proximo paso" para reflejar la realidad post-cambio.

### Reglas de desarrollo

- **Solo codigo funcional**: no escribir codigo aspiracional, placeholder, ni "para despues". Si no funciona hoy, no entra.
- **Tests primero, tests siempre**: ejecutar `python3 -m pytest tests/ -v` antes Y despues de cada cambio. Si se anade logica nueva, anadir tests. Si se descubre un bug, escribir un test que lo reproduzca antes de arreglarlo.
- **Verificar imports**: `python3 -c "from atenea.X import Y"` tras cada cambio de modulo.
- **CLI-first**: toda funcionalidad se expone via CLI. La interfaz visual se generara post-alfa a partir del output bien definido de la CLI estable.
- **No inventar dependencias**: usar lo que ya existe en el proyecto. Si se necesita algo nuevo, justificarlo en el briefing.
- **Commits descriptivos**: que hice + por que, nunca solo "update X".
- **Preguntar si hay duda**: es mejor una pregunta que un refactor innecesario.
- **No tocar lo que funciona**: si un modulo no es parte de la tarea actual, no se modifica. Cero refactors oportunistas.

### Estado actual

- **Version**: 0.2.0-alpha (2026-04-05)
- **Pipeline funcional**: sync -> study -> generate -> test -> review -> export -> advisor
- **Arquitectura**: cli.py (Rich TUI) -> services/ (logica pura) -> storage.py (JSON)
- **LLM**: litellm con DeepSeek (reasoner para extraccion/generacion, chat para advisor/resumenes)
- **Tests**: 125 tests en tests/ (SM-2, evaluate, select, coverage, gaps, sessions, storage I/O, bibliography, rutas, session summary, dedup, recent IDs). 0 failures, 0.13s.
- **Sin web**: eliminada 2026-04-05. Se retomara post-alfa.
- **Datos**: JSON puro en ~/.atenea/data/{proyecto}/
- **Dependencias**: click, rich, litellm, langdetect, pdfplumber, PyMuPDF, python-dotenv, pyzotero
- **Test UX**: default 10 preguntas, resumen verbose post-test (por concepto, trend, struggles), dedup de preguntas entre sesiones

### Proximo paso

Prioridades para beta, por direccion. El usuario decide cual avanzar:

1. **Test UX fase 2**: skip de preguntas individuales + revisitar skipped al final
2. **Anti-overfitting avanzado**: binomial CI para mastery, tracking de pregunta-especifica (no solo target)
3. **Question frameworks**: illness script, cloze deletion, preguntas tipo Anki, taxonomia Bloom
4. **Knowledge metrics**: modulo de metricas (velocidad de aprendizaje, densidad, prediccion de dominio)
5. **Notes/bibliography UX**: highlight known/unknown en bibliografia, notas condensadas, personal_knowledge.json
6. **Obsidian integration**: pdf2md mejorado, wiki-links bidireccionales, tags automaticos
7. **Infrastructure**: logging estructurado, cache LLM, schema validation
8. **Performance**: llamadas LLM paralelas, mixing procedural

### Directrices por direccion de desarrollo

Cada direccion tiene reglas concretas para que cualquier sesion pueda ejecutarla sin ambiguedad.

**Test UX** — Archivos: test_engine.py, services/test_service.py, tui.py, config/defaults.py
- Toda logica nueva va en test_service.py (pura, sin UI). test_engine.py solo llama y renderiza.
- Constantes en defaults.py, nunca hardcodeadas en firmas.
- Cada cambio de UX requiere test en test_test_service.py.
- No romper select_answer() en tui.py — es raw terminal, fragil.

**Anti-overfitting** — Archivos: services/test_service.py, config/defaults.py
- SM-2 trackea CONCEPTOS (targets), no preguntas individuales. No cambiar eso.
- Dedup = deprioritizar, nunca excluir. El pool puede ser pequeno.
- Umbrales estadisticos (CI, p-value) van en defaults.py como constantes.

**Question frameworks** — Archivos: generate.py, config/prompts.py, config/defaults.py
- Cada framework nuevo = un pattern en PATTERNS + un prompt en prompts.py.
- El schema de questions.json NO cambia — los campos existentes (context, question, options A-E, correct, justification, targets, pattern) son suficientes.
- Probar con un proyecto real antes de considerar completo.

**Knowledge metrics** — Archivos: NUEVO services/metrics_service.py, config/defaults.py
- Crear modulo nuevo, no agregar a review_service.py.
- Exponer via CLI como `atenea metrics <project>`.
- Solo funciones puras que retornan dicts.

**Notes/bibliography** — Archivos: advisor.py, services/advisor_service.py, storage.py
- No duplicar datos — usar coverage.json como fuente de "conocido/desconocido".
- personal_knowledge.json es NUEVO, no mezclar con knowledge.json.

**Obsidian integration** — Archivos: export.py
- No cambiar el schema interno. Export es transformacion de salida.
- Usar [[wiki-links]] para terms de knowledge.json.

**Infrastructure** — Archivos: config/, storage.py
- Logging: crear config/logging.py, no tocar logica de negocio.
- Cache: decorator @lru_cache o similar en ai.py, transparente para callers.
- Schema: JSON Schema en config/schemas/, validar solo al cargar.

**Performance** — Archivos: ai.py, generate.py, study.py
- Paralelismo solo con ThreadPoolExecutor (no asyncio, el resto del codigo es sync).
- No cambiar interfaces publicas — el paralelismo es interno.

### Archivos clave

```
atenea/
  cli.py          -- entry point, TUI interactiva, thin wrappers sobre services/
  tui.py          -- raw terminal input (flechas, numeros, letras)
  ai.py           -- interfaz LLM (litellm, zero UI deps)
  storage.py      -- JSON I/O, rutas, versionado
  study.py        -- extraccion de conocimiento (keywords, associations, sequences)
  generate.py     -- generacion de preguntas MIR/ENARM (5 opciones A-E)
  test_engine.py  -- motor de test interactivo SM-2
  review.py       -- analisis de cobertura + gaps
  advisor.py      -- resumenes AI por documento + analisis de coleccion
  ingest.py       -- extraccion PDF (texto, tablas, imagenes)
  zotero.py       -- sync Zotero (bidireccional, concurrente)
  export.py       -- export Obsidian markdown / Anki CSV
  utils.py        -- helpers (chunking, formateo)
  services/       -- logica pura sin dependencias UI
    test_service.py     -- SM-2, seleccion, evaluacion, coverage, sesiones
    review_service.py   -- cobertura, gaps, historial
    project_service.py  -- stats de proyecto, datos para grafos
    advisor_service.py  -- resumenes, clusters, roadmap
    study_service.py    -- re-export study
    generate_service.py -- re-export generate
config/
  defaults.py     -- constantes (SM-2, 7+-2, evidencia SIGN/NICE, chunking)
  models.py       -- config LLM (BIG=deepseek-reasoner, SMALL=deepseek-chat)
  prompts.py      -- prompts para cada tarea LLM
  theme.py        -- colores/iconos Rich para terminal
tests/
  conftest.py     -- fixtures (tmp_data_dir, sample_project)
  test_sm2.py     -- 18 tests algoritmo SM-2
  test_test_service.py   -- 20 tests servicio de test
  test_review_service.py -- 14 tests servicio de review
  test_storage.py -- 44 tests storage I/O, rutas, bibliography, source text
```

### Documentacion

- `log.md` -- changelog + historial de decisiones + roadmap ("Proximo paso")
- `swot.md` -- analisis estrategico, actualizado tras cada modulo
- `prompt.md` -- este archivo (template de sesion, actualizado tras cada modulo)

---

## Continuidad entre sesiones

### Al inicio de cada sesion

1. Lee este archivo (`prompt.md`) — contiene todo el contexto necesario.
2. Lee `log.md` seccion "Proximo paso" — define la tarea pendiente.
3. Lee `swot.md` — identifica debilidades activas y riesgos.
4. Si el usuario da instrucciones adicionales, integra con lo anterior. Si no, ejecuta directamente el "Proximo paso".

### Al final de cada sesion

Antes de terminar, SIEMPRE actualiza estos tres bloques de `prompt.md`:

1. **Estado actual**: version, conteo de tests, cualquier cambio estructural.
2. **Proximo paso**: la tarea concreta que debe ejecutar la siguiente sesion. Debe ser especifica, accionable, sin ambiguedad.
3. **Ultima sesion** (abajo): fecha, que se hizo, que quedo pendiente, bugs descubiertos.

Tambien actualiza `log.md` y `swot.md` segun el pipeline por modulo.

### Ultima sesion

- **Fecha**: 2026-04-05
- **Hecho**: Test UX overhaul — default 10 preguntas (wired via constante), resumen verbose post-test (por concepto, trend vs sesion anterior, top struggles), dedup de preguntas entre sesiones (deprioritiza vistas en ultimas 2 sesiones). 125 tests (16 nuevos), 0 failures. Directrices por direccion de desarrollo en prompt.md.
- **Pendiente**: usuario decide siguiente direccion (test UX fase 2, anti-overfitting, question frameworks, metrics, notes, obsidian, infra, performance)
- **Bugs**: ninguno. Observacion menor: bibliography entries sin citekey (aparecen como "?") — probable campo mal mapeado en sync, no bloquea funcionalidad
