# OpenCode Go — factoría v3 (DeepSeek V4 Pro + Kimi K3, con control de cuota)

**Fecha:** 17 de octubre de 2026. **Estado:** paquete revisado y probado LOCALMENTE (validación estática y pruebas unitarias); **NO probado con la cuenta Go, el Jira y GitHub reales del usuario**. Es un **piloto manual de UNA issue**. No tiene cron ni paralelismo triple. No sustituye Claude ni Cursor.

## Qué cambia respecto al paquete anterior

La última ejecución de OpenCode agotó una ventana de cuota sin una sola edición: ~65 llamadas al LLM y ~118 lecturas en dos sesiones de builder, y el orquestador efectivo era el `build` genérico. Este paquete elimina el reintento desde cero y añade controles externos verificables. No pretende arreglar la cuota simplemente cambiando GLM por otro modelo.

| Rol | Modelo | Archivo | `steps` |
|---|---|---|---:|
| Orquestador | **Kimi K3** | `.opencode/agents/factory-orchestrator.md` | 40 |
| Builder | **DeepSeek V4 Pro** | `.opencode/agents/feature-builder.md` | sin límite (sin clave `steps`) |
| Reviewer | **Kimi K3** | `.opencode/agents/pr-reviewer.md` | 15 |

IDs exactos: `opencode-go/kimi-k3` y `opencode-go/deepseek-v4-pro`.

> **Cambio de Álvaro (17/10/2026):** orquestador y reviewer pasan de Kimi K2.7 Code a **Kimi K3** (`opencode-go/kimi-k3`); el builder sigue siendo DeepSeek V4 Pro. **Ojo con la cuota:** en OpenCode Go, Kimi K3 tiene bastante menos cupo que K2.7 Code (equivale a unos **15 $ al mes** de uso frente a **60 $** de K2.7 Code). Con K3 en dos roles, la ventana de 5 horas se agota antes: vigila la consola Go en el primer piloto y mantén **Use balance desactivado**.

> **Equivalencias del tablero KAN (obligatorias):** Ready = **Listo**, Done = **Finalizada** (In Progress = En curso). Es la misma regla que el contrato de Claude (`multiprovider/claude/01-jira-three-parallel-STRICT-ROUTING.md`, "Localized status names") y el de Cursor: cualquier otro nombre no es Ready/Done, y `JIRA_READY_STATUS`/`JIRA_DONE_STATUS` ya no amplían la lista. **No hace falta configurar nada:** sin variables nuevas, sin `issue_key` obligatorio y sin cambiar las stories de Jira (repo por defecto = el del workflow; se aceptan `Repository:`, `Repositorio:` y `Repositorio destino:`). Las ramas de feature se crean siempre desde un **fetch fresco de `origin/master`**.

**Nueva disciplina:** 1 issue, 1 builder inicial, 0 reinicios nuevos, máximo 1 corrección solamente si se puede retomar EXACTAMENTE el mismo builder y branch; sin reanudación verificable = `BLOCKED`. Antes se hablaba de 3 rondas: ese límite se ha reducido **deliberadamente en este piloto** por el incidente de cuota.

**Controles reales (no solo prompts):**

- `opencode.json` fija `default_agent: factory-orchestrator`; la CLI recibe también `--agent factory-orchestrator` explícito.
- `check_config.py` falla ANTES DE INFERENCIA si falta cualquiera de los tres agentes, no coincide su modelo o modo, no está el agente en `opencode agent list`, o no figuran los IDs en `opencode models opencode-go`.
- `jira_gate.py` verifica Jira mediante REST, **sin llamar a un modelo**: `Ready`, etiquetas exclusivas, `Repository: owner/repo` o campo definido, blockers actuales en `Done`, rama/PR no duplicadas. Si la issue no está exactamente en el estado Ready configurado, **falla**; nunca mueve estados por su cuenta ni recupera sesiones antiguas.
- Builder **sin límite de pasos** (no lleva clave `steps`; según la doc de OpenCode, si no se fija, el agente itera hasta que el modelo para o se interrumpe), orquestador `steps:40`, reviewer `steps:15`. Al builder lo acotan solo los topes externos: 20400 s totales (5 h 40 min), 900 s sin editar, 5.000.000 de tokens de entrada informados y 355 min de job (el máximo de GitHub-hosted es 360). Prioridad: que termine, no que vaya rápido. El requisito de editar antes de 10 pasos es **un contrato de prompt**, NO un límite de tokens garantizado.
- `guarded_run.py` es un watchdog externo: **900 segundos desde iniciar OpenCode sin ningún diff de source/tests ⇒ detener todo el grupo de procesos**; tiempo total máximo 20400 segundos (5 h 40 min); corte adicional al detectar 5.000.000 de tokens de entrada INFORMADOS por el stream JSON; timeout del job 355 min; respuesta 429 observable ⇒ parada sin retry. Si la salida JSON no incluye un evento de uso, no inventa cifras de tokens.
- `postflight.py` exige Draft PR verdadera, marcador de engine/issue, comentario de PASS con HEAD exacto y Jira realmente en Human Review. **Un marcador escrito por un agente no demuestra por sí solo que haya existido una review independiente:** hay que cotejar logs y diff de GitHub antes de dar el piloto por validado.
- Jira MCP recortado a cinco herramientas; NO implica aislamiento de permisos. La cuenta Jira debe tener privilegios mínimos.

## Instalación en este repo de contratos (factoria-contracts)

- Este directorio (`multiprovider/opencode/`) refleja la raíz de un repo de producto: `opencode.json`, `.opencode/agents/`, `.github/workflows/opencode-factory.yml`, `automation/opencode/` y `tests/` (ejecutables con `python -m pytest -q tests` o `python -m unittest discover -s tests` desde aquí).
- **`opencode-factory-PILOT.yml` queda SUPERADO por `opencode-factory.yml`** (v3). No se ha borrado por la regla de no borrar nada; Álvaro puede eliminarlo cuando quiera. No lo copies a un repo de producto junto al v3: habría dos workflows de implementación.
- `opencode-connectivity.yml` se mantiene solo para diagnósticos puntuales.
- `issue_key` es opcional, como en el piloto anterior: vacío = el runner selecciona **sin LLM** (REST/JQL, `Rank ASC`) la primera story elegible y procesa solo esa; si no hay ninguna, `NO_WORK` en verde sin gastar cuota.

## Árbol del paquete

```text
repo/                              # copiar/combinar en la raíz de UN repositorio de producto
  opencode.json                    # ejemplo completo, FUSIONAR con el actual si ya existe
  .opencode/agents/
    factory-orchestrator.md
    feature-builder.md
    pr-reviewer.md
  .github/workflows/
    opencode-factory.yml           # solo workflow_dispatch; NO cron
  automation/opencode/
    check_config.py               # cero tokens, valida agentes y modelos
    jira_gate.py                  # cero tokens, lectura REST Jira + GitHub
    guarded_run.py                # único opencode run; watchdog, sin reintentos
    postflight.py                 # evidencias PR + Jira finales
    pilot-prompt.md               # prompt de orquestación

tests/
  test_jira_gate.py
  test_guarded_run.py
MIGRACION.md
PRUEBAS-Y-ARRANQUE-LIMPIO.md
```

## Instalación — desde la configuración que ya tenías funcionando

1. **No cambies** tus repositorios Claude/Cursor, sus dos agentes ni las Routines/Automations. Este es exclusivamente el motor OpenCode.
2. Abre el ZIP y copia la carpeta `repo/.opencode/agents/` al repo de producto. **Sustituye los TRES agentes OpenCode anteriores**. Borra/reemplaza el YAML antiguo de OpenCode (`opencode-factory-PILOT.yml`/`opencode-factory.yml` según lo que tengas) para **evitar dos workflows de implementación**.
3. Copia `repo/automation/opencode/` y `.github/workflows/opencode-factory.yml` al repositorio.
4. En `opencode.json` actual, **FUSIONA** el nuevo `default_agent`, `model`, `provider` y el bloque `mcp.jira`. No borres configuraciones de tu proyecto ajenas. Verifica el JSON localmente: `python -m json.tool opencode.json >/dev/null`.
5. Conserva tus Secrets ya configurados: `OPENCODE_GO_API_KEY`, `JIRA_API_TOKEN`, `JIRA_USERNAME`, y la variable `JIRA_URL` que ya usaba la versión anterior. **No hay que crear ninguna variable nueva**: `JIRA_PROJECT_KEY` (por defecto `KAN`), `JIRA_HUMAN_REVIEW_STATUS` (por defecto `Human Review`) y `ENABLE_OPENCODE_FACTORY_PILOT` son opcionales; esta última solo bloquea build si vale literalmente `false`. `JIRA_READY_STATUS`/`JIRA_DONE_STATUS` ya no se usan (Ready=Listo, Done=Finalizada fijos, regla de Claude).
6. No hay que tocar las stories: sin `Repository:` se usa el repo del workflow; también se aceptan `Repositorio:` y `Repositorio destino:`. Una story que nombre otro repo se rechaza. `JIRA_REPOSITORY_FIELD_ID`/`JIRA_DEPENDENCIES_FIELD_ID` son opcionales, solo para campos propios (ver MIGRACION.md).
7. En la consola OpenCode Go comprueba que **Use balance esté desactivado**. Esto se gestiona en la consola, no por YAML, para que un 429 por cuota no consuma crédito Zen adicional.
8. `git add ...`, revisa el diff y haz commit/push. El workflow aparece en **GitHub → Actions → OpenCode Factory - bounded single issue**.

## Cómo probar SIN gastar cuota de Go

- Lanza `Run workflow` con **`mode=inspect`** y `issue_key` vacío (selección automática) o una clave concreta. Este modo valida configuración + elegibilidad sin invocar modelos ni editar Jira/archivos de producto.
- **KAN-9 ya fue movida manualmente en Jira por el usuario para comenzar de cero.** NO volver a cambiar su estado ni intentar recuperar trabajo previo. Ejecuta `inspect` para verificar `Ready`/`Listo`, `agent-ready`, `engine-opencode`, repo y blockers `Done`/`Finalizada`. Si falla el gate, corrige solo el dato que indique el error. El runner también rechaza PRs o ramas remotas antiguas.
- La clave debe pertenecer al proyecto (`JIRA_PROJECT_KEY`, por defecto `KAN`) y **todas las dependencias bloqueantes deben estar en `Done`/`Finalizada`**.
- Después lanza `mode=build` (es el valor por defecto; no hace falta ninguna variable). Es una única ejecución de una sola issue, jamás tres jobs; la issue la elige el runner de forma determinista, nunca el agente.

## Aseguramiento y límites

- **No hay PR merge, despliegue, trigger de comentario humano ni actualización automática de Jira Done**. Done lo gestionas tú después del merge humano.
- **No existe límite hard de tokens proporcionado por `steps`.** Son límites de iteraciones. El watchdog recorta tiempo/no-progreso, **pero un modelo aún puede consumir muchos tokens dentro de esos límites**. Revisa el uso de Go, especialmente en el primer piloto.
- Los permisos `edit`, `task`, `bash` son barreras del cliente y el prompt; **no son un sandbox fuerte**. El runner permite trabajar sobre código no confiable y dispone de credenciales. Usa proyecto de prueba, cuentas de servicio de mínimos permisos y branch protection.
- `ENABLED_TOOLS` es un filtro de exposición MCP, no una garantía de autorización. Reduce permisos en la propia cuenta de Jira.
- Un `GITHUB_TOKEN` creado por GitHub Actions puede no disparar otros workflows al crear una PR. No afirmar CI aprobado si no existen los checks reales. Considera una GitHub App con permisos mínimos más adelante.
- El OpenCode CLI se instala con `@latest` en este piloto, con validación de compatibilidad antes de ejecutar modelos; **fija la versión exacta tras el primer piloto exitoso** para reproducibilidad. Fijar commits SHA de las Actions es recomendable antes de operación sin supervisión.

## Documentación y verificación

- [OpenCode: Agents (`steps`, `mode`, `model`)](https://opencode.ai/docs/agents/)
- [OpenCode: CLI (`run --agent`, `agent list`, `models`)](https://opencode.ai/docs/cli/)
- [OpenCode: default_agent y precedencia](https://opencode.ai/docs/config/)
- [OpenCode Go: IDs, límites y Use balance](https://opencode.ai/docs/go/)
- [mcp-atlassian: configuración de herramientas](https://github.com/sooperset/mcp-atlassian/blob/main/docs/configuration.mdx)

**Importante:** el acceso a los modelos y las credenciales ya funcionó en tu prueba de conectividad, pero **este paquete no se ha ejecutado en tu entorno real**. Los tests que acompañan al ZIP son unitarios y de sintaxis/estructura; no garantizan creación de PR ni review real hasta que tú pases el nuevo piloto.
