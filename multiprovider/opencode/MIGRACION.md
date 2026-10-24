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
- `"model": "opencode-go/kimi-k3.1-pro"` (modelo por defecto: orquestador y reviewer en Kimi K3.1 Pro; el builder es `opencode-go/deepseek-v4.1-flash` en su agente).
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

## 4. Jira — no hay que cambiar ninguna story

Funciona igual que el piloto anterior (Licitaciones PR #16 / contracts PR #5): las stories se quedan como están.

- La issue debe estar en `Ready`/`Listo`, tener `agent-ready` y **solo** `engine-opencode` entre las tres etiquetas de motores.
- **Repositorio:** si la story no declara repositorio, se usa el repo donde corre el workflow (`GITHUB_REPOSITORY`). Se aceptan `Repository: owner/repo`, `Repositorio: owner/repo` y `Repositorio destino: owner/repo` (con negrita/código Markdown o URL de GitHub). Si la story nombra **otro** repo, el gate falla. `JIRA_REPOSITORY_FIELD_ID` es opcional, solo si algún día usas un campo propio.
- Dependencias: enlaces estructurados de Jira y referencias textuales explícitas (incluida la línea `Dependencias (is blocked by): KAN-8, …` de las stories KAN). `JIRA_DEPENDENCIES_FIELD_ID` es opcional. **La lectura de dependencias ambigua todavía bloquea según el contrato del orquestador**.
- **Equivalencia de estados (misma regla que Claude y Cursor, copiada de `multiprovider/claude/01-jira-three-parallel-STRICT-ROUTING.md`):** `Ready` = `Listo` y `Done` = `Finalizada` en todas las comprobaciones (selección, gate de dependencias y re-checks). Cualquier otro nombre no es Ready/Done; solo se normalizan mayúsculas y espacios. Por eso `JIRA_READY_STATUS`/`JIRA_DONE_STATUS` ya no se usan: no hay nada que configurar y los tres providers se comportan igual.
- **Sin `issue_key`:** el runner elige sin LLM (REST/JQL `project = KAN AND labels = agent-ready AND labels = engine-opencode … ORDER BY Rank ASC`) la **primera** story elegible: `Ready`/`Listo`, solo `engine-opencode`, repo correcto, todos los blockers en `Done`/`Finalizada` y sin rama `agent/<clave>` ni PR abierta. Una sola issue por run. Si no hay ninguna, `NO_WORK` y el run acaba en verde sin llamar al modelo.
- Las ramas de feature se crean desde un fetch fresco de `origin/master` (el workflow hace `git fetch origin master` justo antes de crear `agent/<clave>`).
- Si no hay transición disponible a In Progress, AI Review o Human Review, el piloto debe parar sin simularla.

## 5. En GitHub

**No hay que crear ninguna variable nueva.** Basta con lo que ya usaba la versión anterior.

Conserva Secrets existentes:

| Secret | Necesario |
|---|---|
| `OPENCODE_GO_API_KEY` | Sí |
| `JIRA_USERNAME` | Sí |
| `JIRA_API_TOKEN` | Sí |

Variables (ya existentes o con valor por defecto; ninguna nueva es obligatoria):

| Variable | Valor |
|---|---|
| `JIRA_URL` | HTTPS del Jira Cloud (la misma que ya usaban el piloto anterior y `opencode-connectivity.yml`) |
| `JIRA_PROJECT_KEY` | opcional; por defecto `KAN` |
| `ENABLE_OPENCODE_FACTORY_PILOT` | **opcional**. Sin la variable, build se ejecuta. Solo el valor literal `false` sirve de interruptor de apagado |
| `JIRA_HUMAN_REVIEW_STATUS` | opcional; por defecto `Human Review` |
| `JIRA_READY_STATUS` / `JIRA_DONE_STATUS` | **ya no se usan**: Ready=Listo y Done=Finalizada son fijos (regla del contrato de Claude) |

No escribas secrets en `opencode.json` ni en commits. **Use balance OFF** en OpenCode Go Console.

## 6. Ensayo

Como antes: Actions → workflow → Run workflow, y ya. `issue_key` vacío = selección automática de la primera story elegible; `mode` por defecto `build` (una ejecución vigilada).

Recomendado la primera vez: `mode=inspect` (con o sin `issue_key`) para ver qué story elegiría, sin gastar tokens de OpenCode Go (solo llamadas normales a Jira/GitHub). Ante `GATE_BLOCKED`, corrige solo el problema indicado; no repitas a ciegas. Después `mode=build`: **una sola issue** por run. Observa los logs; no añadas un segundo Schedule ni tres builders. El workflow ya incluye el cron diario `0 23 * * *` (00:00 Europe/Madrid en invierno, CET; en verano, CEST, sería `0 22 * * *`).

## 7. Sobre el watchdog

- El builder ya no tiene `steps` (sin límite de pasos) y eso NO obliga al modelo a editar en diez pasos. Ese es un mandato del prompt.
- `guarded_run.py` sí mata los procesos si pasan 900 s desde el lanzamiento sin cambios fuente/test detectables. Es un límite temporal **externo real**. El tiempo total del guarded run es 20400 s (5 h 40 min) y 355 minutos capan todo el job (máximo GitHub-hosted: 360). Cambiar umbrales requiere editar el workflow; registra esos cambios.
- El watchdog añade un corte en 5.000.000 de tokens de entrada únicamente SI vienen informados en eventos JSON, sin contar el coste exacto, el cache pricing o la cuota. El watchdog NO controla gasto exacto en Go: una cuota podría consumirse en menos tiempo. Usar `Use balance=false` y hacer pruebas cortas sigue siendo imprescindible.
- No se reintenta una sesión fallida. No se crea otro builder desde cero.
