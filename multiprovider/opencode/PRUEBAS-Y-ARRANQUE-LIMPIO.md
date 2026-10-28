# OpenCode Go — recuperación y matriz de pruebas

## Caso KAN-9: reinicio limpio solicitado por el usuario

**Decisión operativa:** el usuario ya ha movido KAN-9 manualmente en Jira y ha decidido implementarla **desde cero**. El paquete NO debe mover la issue de vuelta a Ready, ni intentar restaurar sesiones, worktrees o tareas de GLM-5.3.

1. Confirmar que la ejecución anterior fue cancelada y no sigue activa en GitHub Actions.
2. (Recomendado) Lanzar `mode=inspect` con `issue_key` vacío o `KAN-9`, **sin LLM y sin cambios en Jira**. No hace falta crear variables ni editar la story. El gate comprueba `Ready`/`Listo`, las etiquetas `agent-ready` + `engine-opencode`, el repo (por defecto el del workflow), los blockers en `Done`/`Finalizada` y la inexistencia de ramas/PR previas.
3. Si `inspect` devuelve `GATE_BLOCKED`, corregir únicamente la causa identificada. **No hacer otra transición de Jira si ya está Ready.**
4. Comprobar que hay cuota Go disponible y `Use balance` desactivado.
5. Ejecutar `mode=build` una única vez (no hace falta `ENABLE_OPENCODE_FACTORY_PILOT`; solo si existe con valor `false` bloquea). El builder será DeepSeek V4.1 Flash; no se reaprovecha contexto de GLM.

**La ejecución fallida solo se conserva como evidencia histórica para evitar repetir el incidente; no es fuente de estado operativo.**

## Matriz de pruebas

| Caso | Ejecución | Resultado correcto |
|---|---|---|
| Agente `factory-orchestrator` ausente | `inspect` | CONFIG_BLOCKED **sin llamar a Kimi K3.1 Pro** |
| Builder todavía GLM | `inspect` | CONFIG_BLOCKED por modelo incompatible |
| DeepSeek V4.1 Flash ausente en catálogo Go | `inspect` | CONFIG_BLOCKED sin sustituto automático; el error nombra todos los modelos que faltan, tras hasta 3 listados separados 60 s |
| Sin `OPENCODE_GO_API_KEY` | `inspect` | CONFIG_BLOCKED |
| Jira sin `engine-opencode` exclusivo | `inspect` | GATE_BLOCKED |
| Jira en `En curso` / In Progress | `inspect` | GATE_BLOCKED; nunca reabrir automáticamente |
| Jira en `Listo` (= Ready) y blockers en `Finalizada` (= Done) | `inspect` | Elegible (misma regla de estados que Claude/Cursor) |
| Estado con otro nombre (p. ej. `Selected for Development`) aunque haya variable | `inspect` | GATE_BLOCKED: "Any other name is not Ready/Done" |
| Sin ninguna variable de GitHub (salvo secrets y `JIRA_URL` ya existentes) | `inspect`/`build` | Funciona con los valores por defecto |
| `issue_key` vacío | `inspect`/`build` | Elige sin LLM hasta `max_issues` stories elegibles por Rank ASC (1–3, por defecto 3) y, en `build`, un job por story |
| `issue_key` con una clave | `inspect`/`build` | Solo esa story, aunque `max_issues` sea 3 |
| `issue_key` vacío y ninguna elegible | `inspect`/`build` | `NO_WORK`, run en verde, sin llamar al modelo |
| Story sin `Repository:` | `inspect` | Usa el repo del workflow |
| Story con `Repositorio destino:` de otro repo | `inspect` | GATE_BLOCKED |
| `ENABLE_OPENCODE_FACTORY_PILOT=false` | `build` | CONFIG_BLOCKED (interruptor opcional) |
| Blocker en Human Review/Resolved | `inspect` | GATE_BLOCKED |
| Issue blocks (no is blocked by) otra | `inspect` | No tratar esa issue saliente como prerequisite |
| PR o rama remota ya existente | `build` | GATE_BLOCKED antes de inferencia |
| Agente lee sin editar durante 900 s | `build` | BLOCKED_NO_PROGRESS_TIMEBOUND + kill group + sin retry |
| 429 del provider | `build` | BLOCKED_QUOTA_429 si observable + sin retry |
| Builder edita solo config protegida | `build` | No cuenta como progreso de source/tests; watchdog corta |
| PR no creada | `build` | POSTFLIGHT_BLOCKED, sin falsa Human Review |
| Reviewer no ve diff publicado | `build` | BLOCKED, no PASS |
| Review PASS en commit anterior | `build` | POSTFLIGHT_BLOCKED por SHA de HEAD |
| Todo correcto, checks reales | `build` | UNA Draft PR + comentario de review ligada a HEAD + estado Jira Human Review |

## Diagnóstico de eventos

El watchdog guarda JSON bruto (potencialmente sensible) sólo en `$RUNNER_TEMP` de ese job y NO lo sube como artifact. Publica un resumen sin specs/tokens. Los eventos `task` pueden no emitirse idénticamente para todas las versiones de OpenCode; su ausencia en el resumen NO demuestra que no haya subagentes. Verifica en la sesión OpenCode que se llamó a DeepSeek V4.1 Flash una única vez y a un nuevo Kimi K3.1 Pro para review. El flujo no merece considerarse validado hasta tener prueba externa de esas identidades.

## Limites para volver a producción

- Piloto manual de UNA issue primero.
- Consumo controlado: compara cuota antes/después en Console; no fiarse de estimaciones sólo por logs.
- Hard stop temporal/no-progreso y `steps` para todos, pero ningún límite duro de tokens garantizado.
- Revisar seguridad de GitHub Token, Jira API Token y CI que no se dispara tras PRs creadas por `GITHUB_TOKEN`.
- El `schedule` ya está definido: cron `0 23 * * *` (00:00 Europe/Madrid en invierno, CET; en verano, CEST, sería `0 22 * * *`). Cada run puede tomar hasta 3 stories en jobs distintos (`max-parallel: 3`, `fail-fast: false`). Cada rama sale de un fetch fresco de `origin/master` y conserva los mismos topes (355 min, 20400 s, 900 s sin editar, 5.000.000 de tokens).
