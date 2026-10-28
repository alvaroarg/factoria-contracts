# Roadmap de la factoría

> **Estado de todas las iniciativas: Propuesto.** El diseño técnico lo decide Álvaro. Aquí solo se recogen objetivos, alcance inicial, piezas del repo afectadas, riesgos y preguntas abiertas. Nada de esto es una decisión cerrada.

## Regla de priorización

**Prioridad = Impacto (1–5) + Encaje (1–5) − Esfuerzo (1–5).** Si hay empate, va antes la que menos esfuerzo tiene. Álvaro puede reordenar o vetar cualquier iniciativa.

| # | Iniciativa | Impacto | Encaje | Esfuerzo | Prioridad | Estado |
|---|---|---|---|---|---|---|
| 1 | OpenAI como proveedor | por decidir | por decidir | por decidir | por decidir | Propuesto |
| 2 | Factoría multirrepo | por decidir | por decidir | por decidir | por decidir | Propuesto |
| 3 | Propagación automática de contratos por PR | por decidir | por decidir | por decidir | por decidir | Propuesto |

---

## 1. Incorporar OpenAI como proveedor

**Objetivo.** Tener un cuarto proveedor junto a Claude, Cursor y OpenCode, con las mismas reglas comunes y el mismo [contrato portable](multiprovider/contracts/PORTABLE-CONTRACT.md). Así hay más capacidad y menos dependencia de un solo vendor, y se pueden comparar coste y calidad por story.

**Alcance inicial**
- Una carpeta `multiprovider/<openai>/` con el contrato del orquestador y los agentes builder y reviewer, sin perder la regla de reviewer independiente y en solo lectura.
- Una etiqueta de routing nueva y el valor correspondiente en `Factory Engine:`.
- Instrucciones de instalación en el README, siguiendo el mismo formato que los demás providers.

**Piezas del repo afectadas**
- `multiprovider/jira/ROUTING.md`: lista de etiquetas `engine-*` y JQL por provider.
- `multiprovider/contracts/PORTABLE-CONTRACT.md`: la lista de etiquetas válidas (`engine-claude`, `engine-cursor`, `engine-opencode`) y `Factory Engine: <claude|cursor|opencode>`.
- `multiprovider/opencode/automation/opencode/jira_gate.py`: la regla de una sola etiqueta engine se basa en una lista fija de tres etiquetas. Habría que ampliarla para que una story con dos etiquetas engine siga saltándose. También sus tests en `multiprovider/opencode/tests/`.
- Los contratos de Claude (`multiprovider/claude/…STRICT-ROUTING.md`) y Cursor (`multiprovider/cursor/01-scheduled-implement.md`), que también nombran las tres etiquetas.
- `README.md`: tabla de providers e instalación.

**Dependencias y riesgos**
- Si un provider no reconoce la etiqueta nueva, podría tratar como válida una story que tenga dos etiquetas engine. Hay que actualizar los tres a la vez.
- No sé si el runtime elegido permite subagentes aislados y un reviewer de verdad independiente. Si no lo permite, el contrato obliga a declararlo como hueco.
- Habrá secretos y costes nuevos por run.

**Preguntas abiertas para Álvaro**
1. ¿Qué runtime usamos: Codex (CLI o cloud), la Agents API/SDK u OpenAI como modelo dentro de OpenCode? Si es lo último, ¿hablamos de un proveedor nuevo o de un modelo más de OpenCode?
2. ¿Dónde se ejecuta: en GitHub Actions, como OpenCode, o en una plataforma gestionada?
3. ¿Qué nombre llevan la etiqueta y el marcador (`engine-openai` / `Factory Engine: openai`)?
4. ¿Cuántas stories por run y qué modelos usan el builder y el reviewer?

---

## 2. Factoría multirrepo

**Objetivo.** Que un solo run u orquestador trabaje stories de varios repos. Así hay que instalar y mantener una vez en lugar de una por repo, y el backlog de Jira se puede planificar de forma global. Hoy cada repo tiene su instalación. El repo sale del propio repo o de la línea `Repository:` de la story, y si la story apunta a otro repo, se rechaza.

**Alcance inicial**
- Que el valor de `Repository:` deje de servir solo para rechazar la story y pase a decidir dónde se trabaja, dentro de una lista de repos permitidos.
- Seguir con un Draft PR por story en el repo que corresponda.
- Mantener las reglas actuales sin cambios: rama desde la rama por defecto de cada repo, `AGENTS.md` propio de cada repo y blockers en Finalizada.

**Piezas del repo afectadas**
- `jira_gate.py`: hoy toma `GITHUB_REPOSITORY` como referencia y falla con «A declaration that names ANOTHER repo fails». También comprueba la rama remota y los PR abiertos en ese mismo repo.
- `guarded_run.py` y `pilot-prompt.md`: sustituyen `__GITHUB_REPOSITORY__` por el repo del workflow.
- `multiprovider/opencode/.github/workflows/opencode-factory.yml`: `concurrency: opencode-factory-${{ github.repository }}` y `GITHUB_TOKEN` del propio repo, con `contents: write` solo en ese repo.
- `PORTABLE-CONTRACT.md` y los contratos de Claude y Cursor, que dicen «work only in the EXACT selected `owner/repo`» y «one non-overlapping run per engine/repo».
- `multiprovider/jira/ROUTING.md`, en la parte de la plantilla `Repository:`.

**Dependencias y riesgos**
- **Permisos:** el `GITHUB_TOKEN` de Actions solo vale para su propio repo. Haría falta un PAT o una GitHub App, lo que amplía mucho el alcance de las credenciales.
- **Concurrencia:** hoy el bloqueo es por engine y repo, y el estado de Jira no sirve como lock atómico. Habría que volver a definir cómo se evita trabajar la misma story dos veces.
- **Contexto:** cada repo tiene su `AGENTS.md`, sus tests y su entorno, así que el builder necesita un checkout limpio por repo.
- Es más fácil que una story mal etiquetada acabe en el repo equivocado.

**Preguntas abiertas para Álvaro**
1. ¿Dónde vive el orquestador: en un repo central o en uno de los repos de producto?
2. ¿La lista de repos permitidos está en este repo, en Jira o en otro sitio?
3. ¿El límite de stories por run es global o por repo?
4. ¿Qué identidad usamos para escribir en los demás repos: GitHub App, PAT o la integración de cada provider?
5. ¿Aplica a los tres providers a la vez o empezamos por uno?

---

## 3. Propagación automática de contratos por PR

**Objetivo.** Que, cuando cambien los contratos de este repo, se abra automáticamente un PR en cada repo que tenga la factoría instalada. Así se evita que las instalaciones se queden desfasadas y se ahorra la copia manual. Hoy todo, salvo el README, se copia a mano a LicitacionesScrapping y se abre un PR contra su rama por defecto.

**Alcance inicial**
- Un registro de los repos instalados y de qué provider o providers tiene cada uno.
- Al hacer merge en `main` de este repo, abrir en cada repo instalado un **Draft PR** contra su rama por defecto, con los archivos del provider en sus mismas rutas.
- Seguir las reglas de instalación actuales: no copiar el README, no tocar el `AGENTS.md` del repo ni los agentes de otros providers, no copiar `opencode-factory-PILOT.yml` junto al v3 y no borrar nada.
- Ningún merge automático: el humano revisa cada PR.

**Piezas del repo afectadas**
- Todo lo que se copia hoy: `.claude/agents/`, `multiprovider/cursor/.cursor/agents/`, `multiprovider/contracts/`, y de `multiprovider/opencode/` los workflows, `.opencode/agents/`, `opencode.json`, `automation/opencode/` y `tests/`.
- `README.md`, en la sección «Guía de instalación», que es donde están hoy las reglas de qué se copia.
- Un workflow nuevo en este repo. Hoy este repo no tiene workflows propios en `.github/`, solo las plantillas de OpenCode bajo `multiprovider/`.

**Dependencias y riesgos**
- Necesita los mismos permisos entre repos que la iniciativa 2 (PAT o GitHub App), así que comparte decisión con ella.
- Si un repo ha adaptado algún archivo en local, un PR que lo sobrescriba borra esos cambios. Hace falta decidir cómo se detecta y cómo se resuelve.
- Copiar a la vez workflows y contratos puede activar la factoría con una versión a medias si el PR se mergea por partes.
- Los contratos de Claude y Cursor se pegan en la Routine o la Automation (en la UI), no en el repo. El PR no los actualiza, y ese paso seguiría siendo manual.

**Preguntas abiertas para Álvaro**
1. ¿El registro de repos instalados se mantiene a mano en este repo o se descubre solo, por ejemplo buscando repos que tengan `.opencode/agents/factory-orchestrator.md`?
2. ¿Se propaga cada merge o solo cuando se publica una versión o tag de contratos?
3. ¿Cómo tratamos las diferencias locales: se sobrescriben, se avisa o se salta el archivo?
4. ¿Cómo avisamos de lo que hay que actualizar a mano en la UI de Claude y Cursor?
5. ¿Va antes, después o a la vez que la iniciativa 2, ya que comparten credenciales?
