---
name: ingest
description: Convierte cualquier archivo o URL a markdown para ingestarlo al second brain o razonar sobre él. Usá esta skill cuando el usuario pase un PDF, Word/docx, PowerPoint/pptx, Excel/xlsx, imagen, audio, un link de YouTube, o un link de Google Docs / Sheets / Slides / Drive y quiera convertirlo, resumirlo, extraer accionables, o guardarlo en raw/docs/. Los archivos de Google Suite se bajan con el CLI `gog` (Docs→md, Sheets→csv, Slides→pptx, Drive→nativo) y de ahí se normalizan; el resto con markitdown. Para artículos web planos preferí la skill defuddle.
---

# ingest — adapter de fuentes arbitrarias (markitdown)

Normaliza fuentes heterogéneas al *lingua franca* del vault (markdown) usando el CLI `markitdown`
(instalado vía `uv tool`). Soporta: PDF, docx, pptx, xlsx/xls, imágenes (EXIF + OCR), audio
(transcripción — requiere `ffmpeg`), HTML, CSV/JSON/XML, ZIP, EPub y URLs de YouTube.

> Para **páginas web planas** (artículos, blogs, docs online) preferí la skill `defuddle`.
> markitdown brilla con **documentos, ofimática, media y YouTube**.

## Dos modos

Decidí el modo según lo que pida el usuario:

### Modo ingesta (persistir) — default cuando piden "ingestar/guardar/sumar al vault"
1. Calculá fecha y slug: `FECHA=$(date +%F)`; slug = kebab-case del título/nombre de la fuente.
2. **Delegá la extracción + limpieza al subagente `extraer-limpiar`** (uno por fuente; para batches de
   varios links, **fan-out en paralelo** — varios en un mismo mensaje). Pasale: la fuente (URL/ruta),
   el slug, la fecha y el destino `raw/docs/<FECHA>-<slug>.md`. El subagente convierte con markitdown,
   **limpia el clutter** (nav, related posts, ads, footers) y escribe el markdown limpio en `raw/docs/`,
   devolviendo `titulo`, `tipo`, `tema`, `resumen`, `takeaways`, `relacionado`. Si devuelve
   `no-extraible` (típico x.com/LinkedIn), no hay archivo crudo — seguí al paso 3 solo con el link.
3. Si la fuente es un **recurso de conocimiento** (artículo/video/paper/repo/curso/tip), escribí la
   nota curada en `wiki/biblioteca/<slug>.md` con el formato del `CLAUDE.md`:
   frontmatter `tags: [recurso]`, `tipo`, `tema` (del vocabulario controlado de `wiki/_taxonomia.md`),
   `url`, `fuente`, `estado: por-leer`, `agregado: <FECHA>`; cuerpo = **Resumen** + **Takeaways** +
   `[[wikilinks]]` a sistemas/conceptos relacionados. Usá el retorno del subagente.
   Si fue `no-extraible`, igual creá la nota con el link y una nota mínima (queda como puntero).
4. **No** edites `raw/` después de escribirlo (es inmutable). Actualizá `wiki/index.md` (sección
   Biblioteca) y confirmá qué se guardó.

### Modo efímero (razonar sin persistir) — cuando piden "resumime / extraé / compará / qué dice"
1. Convertí a un scratch temporal fuera del vault:
   ```bash
   markitdown "<fuente>" -o /tmp/ingest-scratch.md
   ```
2. Leé `/tmp/ingest-scratch.md` y razoná sobre el contenido (resumen, accionables, comparación
   contra un RFC o página existente, respuesta a la pregunta del usuario).
3. **No** dejes artefacto en `raw/`. Si la síntesis resultante es valiosa, ofrecé archivarla en
   `wiki/` o agregarla a la bitácora del día — pero eso es output curado, no la fuente cruda.
4. Limpiá el scratch: `rm -f /tmp/ingest-scratch.md`.

## Fuentes de Google Suite (vía `gog`)

markitdown no puede bajar un Google Doc/Sheet/Slide desde su URL (están detrás de auth de Google y la
URL no es un archivo). Para esas fuentes, **`gog` hace la adquisición** (exporta/baja a un archivo
local) y de ahí seguís el flujo normal de los dos modos. `gog` ya está instalado y la cuenta
`tu-usuario@ejemplo.com` es la default, con scopes de Drive/Docs/Sheets/Slides.

Lo más simple es delegar la detección + exportación al helper (saca el `<ID>` de la URL, elige el
comando `gog` por tipo y exporta):
```bash
.claude/skills/ingest/scripts/gog_fetch.sh "<google_url>" /tmp/ingest-gog   # imprime: "<ruta> <ya_markdown:0|1>"
```

| Fuente | URL | Export `gog` | Después |
|---|---|---|---|
| Doc | `…/document/d/<ID>` | `gog docs export <ID> --format md --out <dest>.md` | **ya es markdown** — saltá markitdown |
| Sheet | `…/spreadsheets/d/<ID>` | `gog download <ID> --format csv --out <dest>.csv` | markitdown/`extraer-limpiar` el `.csv` |
| Slides | `…/presentation/d/<ID>` | `gog slides export <ID> --format pptx --out <dest>.pptx` | markitdown el `.pptx` (Slides no exporta md) |
| Drive | `…/file/d/<ID>` o `open?id=<ID>` | `gog download <ID> --out <dest>` | markitdown el archivo bajado |

Encaje con los **dos modos**:
- **Ingesta**: para un Doc, el `.md` exportado va directo (o por `extraer-limpiar` si querés limpiarlo) a
  `raw/docs/<FECHA>-<slug>.md`. Para Sheet/Slides/Drive, pasá la **ruta local** (no la URL) a
  `extraer-limpiar`, que corre markitdown y limpia. Después, nota curada en `wiki/biblioteca/` si es recurso.
- **Efímero**: exportá a `/tmp/ingest-gog.*`, leé/razoná, y borralo al final.

Notas `gog`:
- Auth: si falla por token/scope, `gog auth list` muestra las cuentas; reautorizá con `gog login <email>`.
- Multi-cuenta: default `tu-usuario@ejemplo.com`; si el archivo vive en otra cuenta, agregá `-a <email>`.

## Notas
- Si la fuente es audio/video y `markitdown` avisa que falta `ffmpeg`, decile al usuario que
  instale `ffmpeg` (`brew install ffmpeg`) para habilitar transcripción.
- Para imágenes, markitdown extrae EXIF + OCR; para descripción semántica de imágenes hace falta un
  LLM client (no configurado por defecto) — alcanza con el OCR para la mayoría de los casos.
- Idempotencia: si `raw/docs/<fecha>-<slug>.md` ya existe, preguntá si sobrescribir o versionar el slug.
