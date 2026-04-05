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
- **Tests**: 109 tests en tests/ (SM-2, evaluate, select, coverage, gaps, sessions, storage I/O, bibliography, rutas). 0 failures, 0.13s.
- **Sin web**: eliminada 2026-04-05. Se retomara post-alfa.
- **Datos**: JSON puro en ~/.atenea/data/{proyecto}/
- **Dependencias**: click, rich, litellm, langdetect, pdfplumber, PyMuPDF, python-dotenv, pyzotero

### Proximo paso

Version alfa declarada. Prioridades para beta (el usuario decide orden):
1. Logging estructurado
2. Cache de llamadas LLM
3. Mas cobertura de tests (CLI, ingest, export, advisor)
4. Schema validation (JSON Schema formal)
5. Nueva funcionalidad que el usuario pida

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
- **Hecho**: eliminada web (1669 LOC), creado prompt.md con pipeline + continuidad, 109 tests, verificacion E2E, bump a v0.2.0-alpha, actualizados log.md/swot.md/prompt.md
- **Pendiente**: usuario decide prioridad para avanzar hacia beta
- **Bugs**: ninguno. Observacion menor: bibliography entries sin citekey (aparecen como "?") — probable campo mal mapeado en sync, no bloquea funcionalidad
