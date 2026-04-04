# SWOT -- ATENEA v0.1.0 (2026-04-04)

Analisis estrategico del proyecto. Se actualiza iterativamente tras cada modulo desarrollado.

---

## Fortalezas (S)

- **Pipeline modular completo**: sync -> study -> generate -> test -> review -> export
- **Fundamento cientifico solido**: SM-2 (Wozniak 1990), regla 7+-2 (Miller 1956), niveles de evidencia SIGN/NICE
- **Interfaz LLM unificada**: litellm permite cambiar proveedor sin modificar codigo
- **Datos portables**: JSON puro, sin base de datos, git-friendly
- **Integracion Zotero robusta**: sync bidireccional con diff, descarga concurrente, metadata CSL-JSON
- **Extraccion PDF completa**: texto (pdfplumber), tablas con caption, imagenes (PyMuPDF)
- **Configuracion centralizada**: modelos, prompts, constantes y tema en config/
- **Bilingue**: deteccion automatica espanol/ingles con prompts adaptados
- **TUI interactiva**: navegacion con flechas, logo ASCII, menus contextuales, sin memorizar comandos
- **Advisor pre-estudio**: resumenes AI por documento + analisis de coleccion + roadmap de estudio
- **Data model versionado**: bibliography.json con envelope {"version": N, "entries": [...]}, schema_version en project.json
- **Citekeys robustos**: BetterBibTeX como override preferido + dedup propia (sufijo a/b/c) como safety net
- **Metadata honesta**: nivel de evidencia "E" para docs sin metadata suficiente, citacion fallback informativa
- **Borrado seguro**: doble confirmacion para eliminar proyectos
- **Homepage informativa**: logo + workflow + overview de progreso por proyecto

## Debilidades (W)

### Activas (se abordan durante el MVP)
- **Sin tests automatizados (pytest)**: no existe suite pytest. Se escribe cuando sync->study->test->review este estable (testar interfaces que van a cambiar es contraproducente).
- **Sin logging estructurado**: solo basicConfig() en study.py. Solo hay un usuario (desarrollo). Logging es critico en produccion, no en MVP iterativo.
- **Sin cache de llamadas LLM**: cada ejecucion repite llamadas identicas. El coste por llamada es bajo (DeepSeek). Cache agrega complejidad (invalidacion, storage). Se implementa cuando el volumen de llamadas justifique el overhead.
- **Batch size hardcodeado**: PAGES_PER_BATCH=5 sin ajuste dinamico. Funciona para docs medicos tipicos (10-30 pags). Ajuste dinamico es optimizacion prematura.
- **Text extraction desacoplada de sync**: advisor.py lo hace lazy (correcto). Acoplar sync+extract fuerza re-extraccion en cada sync (lento).
- **Schema validation ausente**: sin JSON Schema formal. La version en el envelope permite migracion futura sin validacion formal. Overkill para un solo desarrollador.

### Resueltas
- ~~**CLI basada en comandos**: requiere memorizar sintaxis~~ -> RESUELTO: TUI interactiva
- ~~**Sin resumenes AI de documentos**~~ -> RESUELTO: advisor.py
- ~~**Sin vision global de coleccion**~~ -> RESUELTO: advisor.py con clusters + roadmap
- ~~**bibliography.json sin versionar**~~ -> RESUELTO: envelope con version + updated
- ~~**Colision de citekeys**~~ -> RESUELTO: dedup propia + BBT override
- ~~**Evidencia falsa para docs sin metadata**~~ -> RESUELTO: nivel "E"
- ~~**Citacion "Unknown. titulo. s.f."**~~ -> RESUELTO: fallback "[fecha] citekey"
- ~~**Sin short_title**~~ -> RESUELTO: campo + columna en tabla
- ~~**Sin feedback visual en study/generate**~~ -> RESUELTO: display progresivo via callbacks
- ~~**Test con 4 opciones**~~ -> RESUELTO: 5 opciones (A-E) como MIR/ENARM real
- ~~**Solo input por letras en test**~~ -> RESUELTO: flechas + numeros 1-5 + letras a-e
- ~~**Sin keybindings estandarizados**~~ -> RESUELTO: q=atras, Q=salir, flechas=navegar
- ~~**cli.py god class (1100 LOC)**~~ -> RESUELTO: services/ capa de logica pura, cli.py como thin wrapper
- ~~**Display logic en modulos de negocio**~~ -> RESUELTO: advisor, review, test extraidos a services

## Oportunidades (O)

### Corto plazo (MVP en progreso)
- **Flujo end-to-end**: completar sync -> study -> generate -> test -> review con proyecto real
- **Integracion text extraction en flujo**: extraer texto automaticamente post-sync (parcialmente resuelto: advisor lo hace lazy)

### Medio plazo (post-MVP)
1. **Red bayesiana completa** -- CPTs, inferencia inversa, simulacion de escenarios (pgmpy)
2. **Embeddings para aliases** -- deteccion cross-source de sinonimos (all-MiniLM-L6-v2)
3. **Deteccion de interferencia** -- pares confusos con vecindarios similares -> preguntas diferenciales
4. **Actualizacion incremental** -- Bayesian updating al anadir nuevas fuentes

### Largo plazo
5. **Transferencia functorial** -- analogias estructurales entre dominios (graph isomorphism)
6. **Spreading activation en SM-2** -- activacion/decay propagado a vecinos
7. **Web UI interactiva** -- D3.js/Cytoscape.js para visualizacion de grafo

## Amenazas (T)

- **Dependencia de API DeepSeek**: si el servicio cae o cambia precios, el pipeline se detiene
- **Calidad de extraccion PDF**: PDFs escaneados o con formato complejo producen texto basura
- **Escalabilidad JSON**: proyectos con >1000 keywords pueden volverse lentos sin indexacion
- **Estimacion de evidencia estatica**: mapeo tipo_documento -> nivel_evidencia es simplista (un case report en NEJM != uno en revista local)
- **Token limits**: documentos largos requieren chunking que puede perder contexto
