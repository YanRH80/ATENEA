# Guía de desarrollo de ATENEA para Sonnet 4.6

## Principios fundamentales

### 1. UN ARCHIVO A LA VEZ
Nunca pidas al modelo que escriba o modifique más de un archivo por mensaje.
Un archivo, una responsabilidad, un test. Si necesitas cambiar 3 archivos,
son 3 mensajes separados.

### 2. LEER ANTES DE ESCRIBIR
Siempre pide al modelo que lea el archivo ACTUAL antes de editarlo.
Nunca digas "modifica X" sin que primero haya visto el estado actual.
El modelo no tiene memoria entre conversaciones.

### 3. CONTEXTO MÍNIMO, MÁXIMA PRECISIÓN
No pegues todo el codebase en el prompt. Pega SOLO:
- El archivo que vas a modificar
- Los 2-3 archivos que ese archivo importa (interfaces, no implementación)
- El problema específico que hay que resolver

### 4. TEST INMEDIATO
Después de cada cambio, corre un comando que verifique que funciona.
No acumules 5 cambios sin verificar. La cadena es:
cambio → verificación → siguiente cambio.

### 5. COMMIT ATÓMICO
Cada commit es un cambio funcional completo. Nunca commitas código roto.
Si un fix requiere tocar 3 archivos, los 3 van en el mismo commit,
pero el desarrollo se hace de uno en uno.

### 6. EL DATO ES EL PRODUCTO
Antes de añadir features, asegúrate de que knowledge.json y questions.json
tienen datos correctos. Si los datos son malos, todo lo demás es basura.

---

## Roadmap granular — Bloques de trabajo

Cada bloque es una unidad atómica de trabajo. Puedes hacer 1-2 bloques
por sesión de chat. El orden importa: cada bloque depende del anterior.

---

### BLOQUE 0: Verificación base

**Objetivo:** Confirmar que el pipeline funciona desde cero.

**Paso 0.1:** Lee pyproject.toml. Verifica que las dependencias son correctas.
```
Prompt: "Lee pyproject.toml y dime si las deps están bien para: pdfplumber, PyMuPDF, litellm, click, rich, langdetect, python-dotenv"
```

**Paso 0.2:** Corre `python3 -m atenea.cli doctor` y verifica output.

**Paso 0.3:** Corre el pipeline completo con un PDF real:
```bash
python3 -m atenea.cli add ~/Desktop/"44. 12 Octubre.pdf" -p nefrologia
python3 -m atenea.cli study nefrologia
python3 -m atenea.cli generate nefrologia -n 5
python3 -m atenea.cli show nefrologia keywords
```

**Verificación:** Si todo corre sin error, el bloque 0 está completo.
Si falla, el error te dice exactamente qué bloque posterior atacar primero.

---

### BLOQUE 1: Fijar el grafo desconectado (PRIORIDAD MÁXIMA)

**El problema:** `study.py` → `condense_to_knowledge()` envía texto al LLM y
el LLM genera keywords con un term (ej: "Fracaso renal agudo (FA)") pero en
associations usa terms diferentes (ej: "AINE", "EFNa elevada") que NO existen
en keywords. Resultado: 33 de 48 terms referenciados en associations son huérfanos.

**Archivo a modificar:** `atenea/study.py`

**Fix — Opción A (post-proceso):**
Después de recibir el JSON del LLM, crear un paso que:
1. Recopilar todos los terms de keywords
2. Para cada from_term/to_term en associations, buscar el keyword más parecido
3. Si no hay match, crear un keyword nuevo con el term huérfano

```python
def _link_orphan_terms(keywords, associations):
    """Ensure all terms in associations exist as keywords."""
    kw_terms = {kw["term"].lower(): kw["term"] for kw in keywords}

    for assoc in associations:
        for field in ["from_term", "to_term"]:
            term = assoc.get(field, "")
            if term.lower() not in kw_terms:
                # Create missing keyword
                keywords.append({
                    "id": generate_id("kw"),
                    "term": term,
                    "definition": f"(Auto-generado desde asociación: {assoc.get('description', '')})",
                    "page": assoc.get("page", 0),
                    "tags": ["auto"],
                    "source": assoc.get("source", ""),
                    "status": "unknown",
                })
                kw_terms[term.lower()] = term

    return keywords
```

**Fix — Opción B (mejorar prompt):**
Añadir al CONDENSE_PROMPT una instrucción explícita:
```
REGLA CRÍTICA: Cada from_term y to_term en associations DEBE ser exactamente
igual a un term en keywords. Si necesitas un concepto que no es keyword,
primero añádelo a keywords.
```

**Recomendación:** Hacer ambos. Opción B reduce el problema, Opción A lo elimina.

**Prompt para Sonnet:**
```
Lee archivo/codigo/atenea/study.py completo.
Lee archivo/codigo/config/prompts.py completo.

Problema: los terms en associations (from_term, to_term) no coinciden con
los terms en keywords. Hay 33 terms huérfanos de 48.

Quiero 2 cambios:
1. En prompts.py, añade una regla al CONDENSE_PROMPT que fuerce al LLM
   a reutilizar los mismos terms exactos en keywords y associations.
2. En study.py, añade una función _link_orphan_terms() que se ejecute
   después de recibir el JSON del LLM, creando keywords automáticos
   para cualquier term huérfano.

Modifica primero prompts.py, luego study.py.
```

**Verificación:**
```bash
# Borrar knowledge.json existente
rm ~/.atenea/data/nefrologia/knowledge.json
python3 -m atenea.cli study nefrologia
# Verificar
python3 -c "
import json
with open('$HOME/.atenea/data/nefrologia/knowledge.json') as f:
    k = json.load(f)
kw_terms = {kw['term'].lower() for kw in k['keywords']}
orphans = set()
for a in k['associations']:
    if a['from_term'].lower() not in kw_terms: orphans.add(a['from_term'])
    if a['to_term'].lower() not in kw_terms: orphans.add(a['to_term'])
print(f'Orphan terms: {len(orphans)} (target: 0)')
"
```

---

### BLOQUE 2: Diversidad de patrones de pregunta

**El problema:** `generate.py` usa random.shuffle para elegir patrones,
pero en 10 preguntas solo salieron 2 de 8 patrones.

**Archivo a modificar:** `atenea/generate.py`

**Fix:** En `run_generate()`, reemplazar el ciclo while+random por round-robin:

```python
# ANTES (malo):
patterns_cycle = PATTERNS.copy()
random.shuffle(patterns_cycle)

# DESPUÉS (bueno):
patterns_cycle = PATTERNS.copy()
random.shuffle(patterns_cycle)
# Repeat cycle to cover all n questions
patterns_for_batches = []
while len(patterns_for_batches) < (n // batch_size + 1):
    patterns_for_batches.extend(patterns_cycle)
```

**Verificación:**
```bash
rm ~/.atenea/data/nefrologia/questions.json
python3 -m atenea.cli generate nefrologia -n 25
python3 -c "
import json
from collections import Counter
with open('$HOME/.atenea/data/nefrologia/questions.json') as f:
    q = json.load(f)
patterns = Counter(q['pattern'] for q in q['questions'])
print(f'Patterns used: {len(patterns)}/8')
for p, c in patterns.most_common():
    print(f'  {p}: {c}')
"
```

---

### BLOQUE 3: Validación de schema post-LLM

**El problema:** Si el LLM devuelve un keyword sin "term" o "definition",
se guarda roto en knowledge.json. No hay validación.

**Archivo a modificar:** `atenea/study.py`

**Fix:** Añadir validación después de recibir el JSON:

```python
def _validate_keyword(kw):
    """Return True if keyword has required fields."""
    return bool(kw.get("term") and kw.get("definition"))

def _validate_association(assoc):
    return bool(assoc.get("from_term") and assoc.get("to_term") and assoc.get("relation"))

def _validate_sequence(seq):
    nodes = seq.get("nodes", [])
    return len(nodes) >= 3  # Allow some flexibility, warn if <5
```

Usar en condense_to_knowledge():
```python
keywords = [kw for kw in result.get("keywords", []) if _validate_keyword(kw)]
```

**Verificación:** Correr study y verificar que no hay items con campos vacíos.

---

### BLOQUE 4: Dedup de sequences

**El problema:** Si corres `study` dos veces sobre el mismo source,
sequences se duplican porque merge_knowledge() siempre append.

**Archivo a modificar:** `atenea/study.py`

**Fix:** En merge_knowledge(), deduplicar sequences por hash de nodes:

```python
existing_seq_hashes = {
    tuple(s.get("nodes", [])) for s in existing.get("sequences", [])
}
for seq in new_items.get("sequences", []):
    seq_hash = tuple(seq.get("nodes", []))
    if seq_hash not in existing_seq_hashes:
        existing["sequences"].append(seq)
        existing_seq_hashes.add(seq_hash)
```

**Verificación:**
```bash
python3 -m atenea.cli study nefrologia  # Run twice
python3 -m atenea.cli study nefrologia
# Count should NOT double
python3 -c "
import json
with open('$HOME/.atenea/data/nefrologia/knowledge.json') as f:
    k = json.load(f)
print(f'Sequences: {len(k[\"sequences\"])} (should be ~13, not ~26)')
"
```

---

### BLOQUE 5: Coverage por ID en vez de string term

**El problema:** coverage.json usa el string del term como key. Si el term
cambia de nombre, el coverage se pierde.

**Archivos a modificar:** `atenea/test_engine.py`, `atenea/review.py`

**Fix:** Cambiar para que coverage use el `id` del knowledge item.
El problema es que questions.json guarda targets como strings (terms),
no como IDs. Hay dos opciones:

**Opción A:** Cambiar generate.py para que targets sea lista de IDs.
Problema: requiere que generate.py conozca los IDs de knowledge.json.

**Opción B:** Mantener strings pero hacer lookup term→id al actualizar coverage.
Más simple y retrocompatible.

```python
# En test_engine.py, update_coverage():
def update_coverage(coverage, targets, is_correct, knowledge=None):
    items = coverage.setdefault("items", {})
    quality = 4 if is_correct else 1

    # Build term→id lookup if knowledge available
    term_to_id = {}
    if knowledge:
        for kw in knowledge.get("keywords", []):
            term_to_id[kw["term"]] = kw["id"]

    for target in targets:
        key = term_to_id.get(target, target)  # Use ID if found, else term
        # ... rest of SM-2 update
```

**Dejar para después:** Este es un refactor que se puede hacer cuando haya
suficientes sesiones de test para que el problema se manifieste.

---

### BLOQUE 6: Mover dotenv a entry point

**Archivo a modificar:** `atenea/ai.py` y `atenea/cli.py`

**Fix:**
```python
# En ai.py, QUITAR estas líneas:
# from dotenv import load_dotenv
# load_dotenv()

# En cli.py, AÑADIR al inicio:
from dotenv import load_dotenv
load_dotenv()
```

**Verificación:** `python3 -m atenea.cli doctor` sigue funcionando.

---

### BLOQUE 7: Comando reset

**Archivo a modificar:** `atenea/cli.py`

**Fix:** Añadir un comando que borre datos generados de un proyecto:

```python
@main.command()
@click.argument("project")
@click.option("--all", "reset_all", is_flag=True, help="Delete everything including sources")
@click.confirmation_option(prompt="Are you sure?")
def reset(project, reset_all):
    """Reset project data (knowledge, questions, sessions, coverage)."""
    import os
    from atenea.storage import get_project_path
    for f in ["knowledge.json", "questions.json", "sessions.json", "coverage.json"]:
        path = str(get_project_path(project, f))
        if os.path.exists(path):
            os.remove(path)
            console.print(f"[red]Deleted[/red] {f}")
    if reset_all:
        import shutil
        shutil.rmtree(str(get_project_path(project, ".")))
        console.print(f"[red]Deleted[/red] entire project {project}")
```

---

### BLOQUE 8: Tests unitarios básicos

**Archivos nuevos:** `tests/test_utils.py`, `tests/test_storage.py`

Solo funciones puras primero (no necesitan LLM ni PDFs):
- `test_generate_id`: verifica formato "prefix_8hexchars"
- `test_validate_element_count`: verifica 7+-2 rule
- `test_load_json_missing`: verifica que devuelve {} si no existe
- `test_save_load_roundtrip`: guardar y cargar JSON

```bash
pip install pytest
python3 -m pytest tests/ -v
```

---

### BLOQUE 9: Multi-source merge

**El problema:** Si añades un segundo PDF al proyecto, study fusiona correctamente
keywords por term, pero no detecta relaciones ENTRE fuentes.

**Archivo a modificar:** `atenea/study.py`

**Fix en merge_knowledge():**
- Cuando un keyword ya existe (por term match), enriquecer: si la nueva
  definición es más larga, actualizar. Si tiene tags nuevos, añadir.
- Log qué keywords son compartidos entre fuentes.

---

### BLOQUE 10: Tablas en knowledge

**El problema:** ingest.py extrae tablas a tables.json pero study.py
las ignora completamente. Las tablas médicas contienen información
estructurada de alta densidad (diagnósticos diferenciales, criterios, etc.)

**Archivos a modificar:** `atenea/study.py`, `config/prompts.py`

**Fix:** En run_study(), después de cargar text, también cargar tables.json
y formatearlas como texto legible para incluir en el prompt:

```python
tables_path = storage.get_source_path(project, source_id, "tables.json")
tables_data = storage.load_json(str(tables_path))
tables_text = ""
for table in tables_data.get("tables", []):
    tables_text += f"\n\nTabla (p.{table['page']}): {table.get('caption','')}\n"
    tables_text += " | ".join(table.get("headers", [])) + "\n"
    for row in table.get("rows", []):
        tables_text += " | ".join(row) + "\n"
```

---

## Orden recomendado de ejecución

```
Sesión 1: Bloque 0 (verificar) + Bloque 1 (grafo desconectado)
Sesión 2: Bloque 2 (patrones) + Bloque 3 (validación schema)
Sesión 3: Bloque 4 (dedup sequences) + Bloque 6 (dotenv)
Sesión 4: Bloque 7 (reset) + Bloque 8 (tests)
Sesión 5: Bloque 5 (coverage IDs) + Bloque 10 (tablas)
Sesión 6: Bloque 9 (multi-source) + verificación end-to-end
```

Cada sesión: ~2 bloques, ~30 min, ~2000-3000 tokens de código generado.

---

## Cómo pedir cosas a Sonnet 4.6

### Patrón correcto:
```
1. "Lee [archivo]. Dime qué hace la función [nombre]."
2. [Modelo lee y explica]
3. "Ahora modifica [función] para que [cambio específico].
    No cambies nada más en el archivo."
4. [Modelo modifica]
5. "Corre [comando de verificación]."
6. [Verificar resultado]
```

### Patrón INCORRECTO:
```
"Refactoriza todo el módulo study.py para mejorar la calidad"
```
Esto genera código impredecible, bugs ocultos, y tokens desperdiciados.

### Reglas de oro:
- **Nombra la función exacta** que quieres cambiar
- **Da el input y output esperado** del cambio
- **Incluye el comando de verificación** en el mismo mensaje
- **No pidas "mejorar" — pide "cambiar X a Y"**
- **Si el modelo genera >100 líneas, probablemente está haciendo demasiado**

---

## Anti-patterns a evitar

1. **"Reescribe todo el archivo"** → Bugs garantizados. Edita funciones.
2. **"Arregla todos los problemas"** → El modelo priorizará mal. Uno a la vez.
3. **"Hazlo más robusto"** → Vago. Di exactamente qué caso edge manejar.
4. **"Añade logging"** → Sin especificar dónde, inundará de logs.
5. **Copiar todo el CONTEXTO.md como prompt** → Demasiado contexto = confusión.
   Copia solo la sección relevante al bloque que estás trabajando.
6. **No verificar después de cada cambio** → El error se acumula.
   3 cambios sin verificar = 3x más difícil de debugear.
