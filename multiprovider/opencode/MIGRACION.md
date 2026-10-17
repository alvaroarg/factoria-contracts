# Migración sin arrastrar el fallo anterior

## 0. Congelar el sistema viejo

- Desactiva cualquier schedule o Automation antigua de OpenCode. No toques las de Claude/Cursor.
- Elimina/sustituye la Action anterior `anomalyco/opencode/github@latest` para este flujo. Aquí ejecutamos el **CLI** con `--agent factory-orchestrator` y preflight obligatorio; si el agente falta, el job falla y **no recurre a build**.
- Mantén el workflow `opencode-connectivity.yml` sólo para diagnósticos puntuales si lo quieres, **nunca como trigger de implementación**.

## 1. Nuevos agentes

Sustituye los tres archivos `.opencode/agents/*.md` por los del ZIP. No se trata de poner solo DeepSeek en el builder anterior: el problema fue también el orquestador, la reanudación y el consumo sin progreso.

## 2. Fusión de `opencode.json`

A partir del archivo ya funcional de Jira, incorpora:

- `"default_agent": "factory-orchestrator"`.
- `"model": "opencode-go/kimi-k3"` (orquestador y reviewer en Kimi K3; menos cupo en Go que K2.7 Code: ~15 $/mes frente a ~60 $).
- `"provider". "opencode-go". "options". "apiKey": "{env:OPENCODE_GO_API_KEY}"`.
- `mcp.jira.environment` con los cinco `ENABLED_TOOLS`, `JIRA_PROJECTS_FILTER` y sin `READ_ONLY_MODE=true` para el piloto de transiciones.

**Si tu MCP actual ya se conecta con éxito, mantenlo salvo las restricciones de herramientas: no sustituyas rutas, auth o un comando `uvx` que ya hayas probado solo por estética.**

## 3. Archivos en el repo

```text
opencode.json
.opencode/agents/factory-orchestrator.md
.opencode/agents/feature-builder.md
.opencode/agents/pr-reviewer.md
.github/workflows/opencode-factory.yml
automation/opencode/check_config.py
automation/opencode/jira_gate.py
automation/opencode/guarded_run.py
automation/opencode/postflight.py
automation/opencode/pilot-prompt.md
```

No reemplaces `AGENTS.md`, `.claude/agents/` ni `.cursor/agents/`.

## 4. Jira

- La issue debe ser `Ready` (o `JIRA_READY_STATUS` exacto), tener `agent-ready` y **solo** `engine-opencode` entre las tres etiquetas de motores.
- La descripción incluye `Repository: OWNER/REPO` en línea propia o tienes variable `JIRA_REPOSITORY_FIELD_ID` con nombre de campo exacto (por ejemplo `customfield_10024`). El runner necesita `JIRA_REPOSITORY_FIELD_ID: ${{ vars.JIRA_REPOSITORY_FIELD_ID }}` en `env:` si usas un campo específico.
- Si las dependencias están también en un campo adicional, añade `JIRA_DEPENDENCIES_FIELD_ID: ${{ vars.JIRA_DEPENDENCIES_FIELD_ID }}`. El parser del gate recoge los enlaces estructurados y ciertas referencias explícitas textuales; **la lectura de dependencias ambigua todavía bloquea según el contrato del orquestador**.
- Para tableros españoles: Ready = Listo y Done = Finalizada son equivalentes y el gate los acepta siempre. Otros nombres hay que añadirlos literalmente en `JIRA_READY_STATUS`/`JIRA_DONE_STATUS`; no se traduce cualquier categoría de Jira a Done.
- Las ramas de feature se crean desde un fetch fresco de `origin/master` (el workflow hace `git fetch origin master` justo antes de crear `agent/<clave>`).
- Si no hay transición disponible a In Progress, AI Review o Human Review, el piloto debe parar sin simularla.

## 5. En GitHub

Conserva Secrets existentes:

| Secret | Necesario |
|---|---|
| `OPENCODE_GO_API_KEY` | Sí |
| `JIRA_USERNAME` | Sí |
| `JIRA_API_TOKEN` | Sí |

Variables:

| Variable | Valor |
|---|---|
| `JIRA_URL` | HTTPS del Jira Cloud |
| `JIRA_PROJECT_KEY` | p.ej., `KAN` |
| `ENABLE_OPENCODE_FACTORY_PILOT` | `false` para inspección; `true` antes de build |
| `JIRA_READY_STATUS` | por defecto `Ready`; el gate acepta siempre `Ready` y `Listo` como equivalentes (admite varios valores separados por comas) |
| `JIRA_DONE_STATUS` | por defecto `Done`; el gate acepta siempre `Done` y `Finalizada` como equivalentes (admite varios valores separados por comas) |
| `JIRA_HUMAN_REVIEW_STATUS` | por defecto `Human Review` |

No escribas secrets en `opencode.json` ni en commits. **Use balance OFF** en OpenCode Go Console.

## 6. Ensayo

Primero: Actions → workflow → Run workflow → `mode=inspect`, `issue_key=KAN-9`. La issue ya fue reposicionada manualmente en Jira. No realices ninguna transición adicional por inercia: `inspect` confirma si su estado actual, labels, repo y blockers son elegibles. Ante `GATE_BLOCKED`, corrige solo el problema indicado, no repitas el batch a ciegas. Inspect no gasta tokens de OpenCode Go, pero sí hace llamadas normales a APIs Jira/GitHub.

Sólo cuando inspect sea verde: Variable piloto `true`, `mode=build`, y **una sola issue**. Observa los logs; no habilites Schedule ni tres builders.

## 7. Sobre el watchdog

- `steps:30` NO obliga al modelo a editar en diez pasos. Ese es un mandato del prompt.
- `guarded_run.py` sí mata los procesos si pasan 360 s desde el lanzamiento sin cambios fuente/test detectables. Es un límite temporal **externo real**. 35 minutos capan todo el job. Cambiar umbrales requiere editar el workflow; registra esos cambios.
- El watchdog añade un corte en 800.000 tokens de entrada únicamente SI vienen informados en eventos JSON, sin contar el coste exacto, el cache pricing o la cuota. El watchdog NO controla gasto exacto en Go: una cuota podría consumirse en menos tiempo. Usar `Use balance=false` y hacer pruebas cortas sigue siendo imprescindible.
- No se reintenta una sesión fallida. No se crea otro builder desde cero.
