# Log & Roadmap -- ATENEA

Registro de cambios + plan de proximos pasos. Se actualiza tras cada iteracion.

---

## Realizado

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

---

## Proximo paso

### Objetivo: Frontend web con NiceGUI (Fase 2 del plan)

**Estado actual**: Capa de servicios extraida. CLI y web comparten el mismo backend.

```
atenea/services/  <-- NUEVO: logica pura, sin UI
     |                    |
  cli.py (Rich)      web/ (NiceGUI, por construir)
```

**Accion inmediata**: Instalar NiceGUI, crear estructura web/, implementar homepage + test interactivo (primer milestone visible).

**Primer milestone**: Un medico abre localhost:8080, elige proyecto, hace test de 25 preguntas con botones clickables, ve justificacion y score.

**Criterio de exito**: `atenea-web` abre navegador con homepage funcional + grafo de conocimiento + test interactivo.

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
