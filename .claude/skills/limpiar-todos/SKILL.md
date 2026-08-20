---
name: limpiar-todos
description: Elimina los TODOs terminales (estado:hecho o estado:descartado) que superaron el umbral de antigüedad (default 7 días). Mantiene la carpeta todos/ sin acumulación indefinida. El board todos.base ya separa Abiertos/Hechos/Descartados, así que la limpieza es solo de orden. Correr manualmente o desde /compactar semanal. Los archivos eliminados son recuperables vía git.
---

# limpiar-todos — limpieza de TODOs completados

Borra los archivos `todos/*.md` con estado **terminal** (`hecho` o `descartado`) que tengan más de
N días desde `created:`. El `todos.base` ya filtra los terminales a sus propias vistas — este skill
es higiene de carpeta, no de board. Un `descartado` (tombstone) viejo ya no bloquea recreación: su
`origen` salió de la ventana de captura de `/todos`, así que es seguro borrarlo.

## Uso

```
/limpiar-todos          # umbral default: 7 días
/limpiar-todos 14       # umbral custom: 14 días
/limpiar-todos --dry    # solo reporta qué se borraría, sin borrar
```

## Pasos

1. Calculá la fecha límite: `CUTOFF = hoy - N días` (N = argumento o 7 por default).

2. Listá todos los `todos/*.md` con estado terminal (`hecho` o `descartado`):
   ```bash
   grep -lE "^estado: (hecho|descartado)" todos/*.md
   ```

3. Para cada archivo, leé el campo `created:` del frontmatter:
   ```bash
   grep "^created:" todos/<archivo>.md
   ```
   Parseá la fecha. Si `created < CUTOFF` → candidato a borrar.
   Si no tiene campo `created:` → conservar (no asumir antigüedad).

4. **Sin `--dry`**: eliminá los candidatos con `rm`. Reportá nombre + fecha de cada uno.
   **Con `--dry`**: solo listá los candidatos sin tocar nada.

5. Reportá el resultado:
   ```
   Limpieza de TODOs completados (umbral: N días, cutoff: YYYY-MM-DD)
   Eliminados (M):
     - <nombre> (creado YYYY-MM-DD, proyecto: X)
     - ...
   Conservados con estado:hecho (K) — más recientes que el umbral:
     - <nombre> (creado YYYY-MM-DD)
   ```
   Si no hay nada para limpiar, decirlo en una línea.

## Notas

- Los archivos eliminados son **recuperables vía `git checkout`** mientras no se haya hecho
  un `git gc` (el vault hace backup diario, así que la historia está preservada).
- No tocar los TODOs con `estado: pendiente` o `estado: en-progreso` bajo ninguna circunstancia.
- No modificar `todos.base` — el board se adapta solo al desaparecer los archivos.
- Integración sugerida: llamar desde `/compactar semanal` al final, con umbral 14 días.
