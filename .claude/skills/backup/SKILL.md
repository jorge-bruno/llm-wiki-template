---
name: backup
description: Commitea y pushea el vault al repo privado de GitHub. Usar para "backupeá", "guardá los cambios", "pusheá el vault", o como paso final del pipeline diario. Es el respaldo que preserva los transcripts de Granola (que Granola free borra a los 7 días).
---

# backup — commit + push del vault

Versiona el estado del vault y lo sube al repo privado. Es lo que hace que las capturas (sobre todo
Granola) sobrevivan al borrado de 7 días de Granola free.

## Pasos
1. Mirá qué cambió: `git -C <vault> status --short`.
2. Si no hay cambios, informá "nada para backupear" y terminá.
3. Stage + commit con un mensaje que resuma el día:
   ```bash
   git add -A
   git commit -q -m "backup <FECHA>: <resumen corto de qué se capturó/compactó>

   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
   ```
   Ejemplo de resumen: "3 meetings Granola, bitácora, 2 TODOs nuevos".
4. Push: `git push` (si no hay upstream configurado, `git push -u origin main`).
5. Si el push falla por auth/red, informá el error textual y dejá el commit local hecho (no se pierde).

## Nota
- Recordá que `raw/` contiene data confidencial (transcripts de meetings, Slack, etc.) y el repo es privado. No agregues remotes
  públicos ni cambies la visibilidad.
