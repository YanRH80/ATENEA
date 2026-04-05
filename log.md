# Log & Roadmap -- ATENEA

Registro de cambios + plan de proximos pasos. Se actualiza tras cada iteracion.

---

## Realizado

### v0.2.0-alpha (2026-04-05) -- Alfa

**Version bump**
- Pipeline completo verificado E2E: sync -> study -> generate -> test -> review -> export -> advisor
- 109 tests automatizados (services + storage), 0 failures, <0.15s
- Codebase limpia: solo codigo funcional, web eliminada, zero codigo muerto
- Datos reales verificados: 6 docs, 134 conceptos, 25 preguntas, gaps detectados

**Cubierto**:
- CLI interactiva con TUI (flechas, numeros, letras, q/Q)
- Zotero sync bidireccional con dedup
- Extraccion PDF (texto, tablas, imagenes)
- Extraccion de conocimiento (keywords, associations, sequences) via LLM
- Generacion de preguntas MIR/ENARM (5 opciones A-E) via LLM
- Test interactivo con SM-2 (repeticion espaciada)
- Review (cobertura, gaps, historial de sesiones)
- Advisor (resumenes AI, clusters, roadmap)
- Export (Obsidian markdown, Anki CSV)
- Storage versionado (JSON, envelopes, bibliography)

**Pendiente para beta**:
- Logging estructurado
- Cache de llamadas LLM
- Mas cobertura de tests (CLI wrappers, ingest, export)
- Schema validation formal
- Interfaz visual (post-beta, generada desde CLI output)

### v0.1.0 (2026-04-04) -- Fundacion

**Infraestructura**
- Creado swot.md (reemplaza oportunidades.md) y log.md
- Version reset a 0.1.0 con fecha en --version
- Sincronizado __init__.py y pyproject.toml

**Modulo Advisor**
- atenea/advisor.py: resumenes AI por documento (SMALL_MODEL) + analisis de coleccion (clusters, roadmap, insights)
- Prompts SUMMARIZE_DOCUMENT y COLLECTION_ADVISOR en config/prompts.py
- ai_summary almacenado en bibliography entries, analisis en advisor.json

**TUI interactiva**
- atenea/tui.py: navegacion con flechas (tty/termios raw mode), logo ASCII, colores
- Homepage interactiva: logo + workflow + lista de proyectos con stats
- Project menu: banner ASCII + overview de progreso (checklist sync/study/generate/test)
- Fallback a input numerico para terminales no interactivas

**Data model blindado**
- bibliography.json envuelto en envelope versionado: {"version": 1, "entries": [...], "updated": "..."}
- storage.load_bibliography() / save_bibliography() manejan formato legacy y nuevo
- project.json con schema_version
- Nivel de evidencia "E" para docs con metadata insuficiente (en vez de "4" falso)
- Citacion fallback "[fecha] citekey" para docs sin autores/anio
- Campo short_title (truncado en word boundary, sin prefijo numerico)
- Deduplicacion de citekeys: sufijo a/b/c si colision (BBT override sigue preferido)
- Columna Titulo (short_title) en tabla de bibliografia

**Zotero**
- Fix pyzotero 1.11: filtro itemType local en vez de server-side (API 400 bug)
- Error handling robusto en sync

**UX**
- Borrar proyecto con doble confirmacion (confirm + escribir nombre)
- Homepage con show_welcome() (logo + workflow visual)
- Project overview panel con progreso y stats

**Bug fixes**
- Fix bib_path NameError en zotero.py y advisor.py tras refactor a load_bibliography()
- Fix flicker en 6 handlers interactivos: agregado console.input() para esperar Enter
- Fix modelo LLM incorrecto: study usaba "extraction_points" (inexistente), generate usaba "question_gen_mc" (inexistente) -- ambos caian silenciosamente a SMALL_MODEL

**UX overhaul**
- Display progresivo en study: keywords, asociaciones, secuencias aparecen en tiempo real via callback
- Display progresivo en generate: preguntas aparecen batch a batch con nombre de patron
- Silenciado logging litellm/httpx durante sesiones interactivas
- Test con 5 opciones (A-E) como MIR/ENARM real (antes 4: A-D)
- Selector interactivo de respuestas: flechas arriba/abajo, numeros 1-5, letras a-e, Enter
- Keybindings estandarizados: q=atras, Q=salir app, flechas=navegar (inspirado en vim/lazygit/ranger)
- Welcome screen con logo + workflow visual
- Project overview panel con checklist de progreso
- Regeneradas preguntas con 5 opciones

**Arquitectura: Capa de servicios**
- Creado atenea/services/ — capa de logica pura sin dependencias de UI
- test_service.py: SM-2, seleccion de preguntas, evaluacion, coverage, sesiones
- project_service.py: stats de proyecto, builder de datos para grafo de conocimiento
- review_service.py: calculo de cobertura, deteccion de gaps, historial de sesiones
- advisor_service.py: resumen de documentos, analisis de coleccion, pipeline advisor
- study_service.py, generate_service.py: re-exports (ya estaban limpios)
- test_engine.py, review.py, advisor.py refactorizados como thin CLI wrappers
- ai.py: eliminado import Rich (zero dependencias UI)
- cli.py: _homepage() y _project_menu() usan project_service
- Backward compatibility mantenida en todos los modulos

**Frontend web NiceGUI (Fase 2) -- REVERTIDO 2026-04-05**
- Se desarrollo frontend NiceGUI (dashboard, test, analysis) durante 2 sesiones
- Bugs persistentes sin posibilidad de verificacion visual (radio buttons, grafo, port binding)
- Decision: eliminar web, conservar solo codigo funcional. La CLI cubre 100% del workflow
- Borrado: atenea/web/ (10 .py), nicegui/qrcode de dependencies, entry point atenea-web
- La web se generara post-alfa a partir del output bien definido de la CLI estable

**Limpieza post-web (2026-04-05)**
- Eliminado _start_web_bg(), _show_web_banner(), _wait_for_server(), import socket de cli.py
- Borrado atenea/web/ completo (10 .py, 1669 LOC), nicegui/qrcode de dependencies
- Creado prompt.md: template de sesion con pipeline de produccion (prebriefing/briefing/ejecucion/docs)

**Suite pytest (2026-04-05)**
- Creado tests/ con conftest.py (fixtures: tmp_data_dir, sample_project con JSON de ejemplo)
- test_sm2.py: 18 tests — EF adjustment, interval progression, status transitions, counters, edge cases
- test_test_service.py: 20 tests — evaluate_answer, select_questions, update_coverage, prepare_test, finish_test
- test_review_service.py: 14 tests — compute_coverage, detect_gaps, get_session_history
- pyproject.toml: configuracion pytest (testpaths, pythonpath)
- 65 tests, 0 failures, 0.08s. Todos los servicios criticos cubiertos.
- test_storage.py: 44 tests — JSON I/O, text I/O, rutas, directorios, list/next_source_id, bibliography envelope, project lifecycle, load_source_text
- Total: 109 tests, 0 failures, 0.13s

**Verificacion E2E (2026-04-05)**
- Pipeline completo verificado con proyecto "atenea" (6 docs reales)
- Datos: 6 sources (text+pdf), 60 keywords, 47 associations, 27 sequences, 25 questions, 43 coverage items, 3 sessions, advisor.json completo
- Servicios: get_project_overview, compute_coverage, detect_gaps, get_session_history, prepare_test — todos OK contra datos reales
- CLI: projects, review, show coverage/keywords/graph, export csv/md — todos exit 0
- 5 gaps detectados correctamente (Cinacalcet 0%, Hipercalcemia 0%, etc.)
- Observacion: 0 items "known" (todos "testing") — score bajo en sesiones (20%, 50%, 0%). Pipeline funciona, usuario necesita mas practica.

---

## Proximo paso

### Objetivo: Hacia beta

**Estado actual**: v0.2.0-alpha declarada. Pipeline E2E funcional, 109 tests, codebase limpia.

**Prioridades para beta**:
1. Logging estructurado (reemplazar basicConfig por modulo propio)
2. Cache de llamadas LLM (evitar repetir extracciones/generaciones costosas)
3. Mas cobertura de tests (CLI wrappers, ingest, export, advisor)
4. Schema validation (JSON Schema para knowledge.json, questions.json)
5. Lo que el usuario priorice

---

## Historial de decisiones

| Fecha | Decision | Justificacion |
|-------|----------|---------------|
| 2026-04-04 | Version reset a 0.1.0 | Comenzar conteo limpio; version anterior (0.3.0/0.4.0) era de prototipos |
| 2026-04-04 | BBT + dedup propia para citekeys | BBT no siempre disponible; dedup cubre caso comun en medicina (2+ Garcia2024) |
| 2026-04-04 | Nivel "E" para metadata insuficiente | "4" (opinion experta) es falso para docs sin metadata; honestidad > asuncion |
| 2026-04-04 | Envelope versionado para bibliography | Sin version, migraciones futuras son imposibles; coste minimo ahora |
| 2026-04-04 | Debilidades diferidas (tests, logging, cache) | Pipeline incompleto; testar interfaces inestables es contraproducente |
| 2026-04-04 | Rendering issue es de VSCode terminal | Usuario testa en Ghostty; no gastar esfuerzo en workaround para VSCode |
| 2026-04-04 | q=atras, Q=salir app | vim/lazygit/ranger/htop usan q; Q diferencia salir un nivel vs salir de todo |
| 2026-04-04 | 5 opciones (A-E) en test | MIR/ENARM real usa 5 opciones; 4 no es representativo |
| 2026-04-04 | Display progresivo via callbacks | Patron on_batch_complete en study/generate; CLI se suscribe sin acoplar backend a UI |
| 2026-04-04 | Capa de servicios para dual frontend | services/ retornan datos puros; CLI y web llaman los mismos servicios |
| 2026-04-04 | NiceGUI como framework web | Pure Python, ECharts integrado, async nativo, localhost-only, empaquetable |
| 2026-04-05 | Eliminar web, CLI-only para v1 | Bugs no verificables sin feedback visual; CLI cubre 100% del workflow; web post-alfa |
| 2026-04-05 | Crear prompt.md | Template de sesion para pipeline riguroso (prebriefing/briefing/ejecucion/docs) |
| 2026-04-05 | pytest sobre services/ y storage | 109 tests cubren SM-2, seleccion, evaluacion, coverage, gaps, JSON I/O, rutas, bibliography |
| 2026-04-05 | Verificacion E2E con datos reales | Pipeline completo funcional: 6 docs, 134 conceptos, 25 preguntas, todos CLI commands OK |
| 2026-04-05 | Version alfa 0.2.0-alpha | Pipeline E2E verificado, 109 tests, codebase limpia — criterios alfa cumplidos |
