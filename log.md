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

---

## Proximo paso

### Objetivo: Flujo end-to-end sync -> study -> generate -> test

**Por que este orden**: El valor de ATENEA esta en generar y ejecutar tests adaptativos. Sin completar este flujo, el producto no es usable. Cada paso depende del anterior:

```
sync (HECHO) -> PDFs + bibliography.json
  |
  v
study -> text extraction + LLM knowledge extraction -> knowledge.json
  |       (keywords, asociaciones, secuencias, sets)
  v
generate -> LLM question generation -> questions.json
  |          (preguntas tipo MIR/ENARM con justificaciones)
  v
test -> sesion interactiva con SM-2 -> sessions.json + coverage.json
  |      (repeticion espaciada, calificacion, estadisticas)
  v
review -> analisis de cobertura y gaps
```

**Accion inmediata**: Ejecutar `atenea study` con un proyecto real (coleccion Zotero ya sincronizada). Verificar que knowledge.json se genera correctamente. Iterar si falla.

**Criterio de exito**: Un usuario puede sincronizar una coleccion Zotero, estudiar los documentos, generar preguntas, y hacer un test interactivo -- todo desde la TUI sin tocar la terminal.

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
