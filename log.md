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

---

## Proximo paso

### Objetivo: Pulir flujo completo + review funcional

**Estado actual**: sync -> study -> generate -> test funcionan como MVP. UX pulida con display progresivo y seleccion interactiva.

```
sync (OK) -> PDFs + bibliography.json
study (OK) -> knowledge.json (display progresivo)
generate (OK) -> questions.json 5 opciones A-E (display progresivo)
test (OK) -> sessions.json + coverage.json (selector interactivo)
review (PENDIENTE) -> analisis de gaps via LLM
export (PENDIENTE) -> markdown/CSV
```

**Accion inmediata**: Verificar review y export. Testar flujo completo end-to-end con el proyecto real de nefrologia.

**Criterio de exito**: Un usuario puede completar todo el ciclo sync -> study -> generate -> test -> review desde la TUI, con feedback visual en cada paso.

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
