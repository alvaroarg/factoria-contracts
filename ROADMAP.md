# Roadmap de la factoría

> **Estado de todas las iniciativas: Propuesto.** El diseño técnico lo decide Álvaro. Aquí solo se recogen objetivos, alcance inicial, piezas del repo afectadas, riesgos y preguntas abiertas. Nada de esto es una decisión cerrada.

## Regla de priorización

**Prioridad = Impacto (1–5) + Encaje (1–5) − Esfuerzo (1–5).** Si hay empate, va antes la que menos esfuerzo tiene. Álvaro puede reordenar o vetar cualquier iniciativa.

| # | Iniciativa | Impacto | Encaje | Esfuerzo | Prioridad | Estado |
|---|---|---|---|---|---|---|
| 1 | OpenAI como proveedor | por decidir | por decidir | por decidir | por decidir | Propuesto |
| 2 | Factoría multirrepo (Jira como fuente única) | por decidir | por decidir | por decidir | por decidir | Propuesto (dirección elegida) |
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

**Objetivo.** Que un solo Jira gestione n repositorios y que el pool de tareas se distribuya entre ellos. Así hay un único backlog priorizado para todo el producto, en lugar de un Jira o un filtro por repo, y la capacidad de la factoría se reparte según el Rank global. Hoy cada repo tiene su instalación. El repo sale del propio repo o de la línea `Repository:` de la story, y si la story apunta a otro repo, se rechaza.

**Dirección elegida por Álvaro:** usar Jira como fuente única.
- Hay **un solo proyecto o backlog** de Jira.
- **Cada story indica su repo destino.**
- **El pool de stories elegibles se reparte entre los repos.**

El diseño técnico de cómo se hace sigue abierto.

**Alcance inicial**
- Que el repo destino de la story deje de servir solo para rechazarla y pase a decidir en qué repo se trabaja, dentro de una lista de repos permitidos.
- Repartir el pool de stories elegibles (Listo + `agent-ready` + engine + blockers en Finalizada, por Rank) entre los repos, sin que dos runs cojan la misma story.
- Seguir con un Draft PR por story en su repo destino.
- Mantener las reglas actuales: rama desde la rama por defecto de cada repo, `AGENTS.md` propio de cada repo y routing exclusivo por `engine-*`.

**Piezas del repo afectadas**
- `jira_gate.py`: hoy toma `GITHUB_REPOSITORY` como referencia y rechaza la story si declara otro repo («A declaration that names ANOTHER repo fails»). También comprueba la rama remota y los PR abiertos en ese mismo repo. La JQL actual filtra por proyecto y etiquetas, no por repo.
- `guarded_run.py` y `pilot-prompt.md`: sustituyen `__GITHUB_REPOSITORY__` por el repo del workflow.
- `multiprovider/opencode/.github/workflows/opencode-factory.yml`: `concurrency: opencode-factory-${{ github.repository }}`, el `GITHUB_TOKEN` del propio repo y el job `select`, que hoy elige hasta 3 stories para ese repo.
- `PORTABLE-CONTRACT.md` y los contratos de Claude y Cursor: «work only in the EXACT selected `owner/repo`», «one non-overlapping run per engine/repo» y «at most 3 issues per batch».
- `multiprovider/jira/ROUTING.md`: la plantilla `Repository:` y la JQL por provider.

**Dependencias y riesgos**
- **Reparto y concurrencia:** el estado de Jira no es un lock atómico. Si varios runs leen el mismo pool, hace falta una regla de reparto que impida que dos runs cojan la misma story.
- **Dependencias entre repos:** una story de un repo puede depender de otra de otro repo. La puerta actual (blockers en Finalizada) ya funciona por key de Jira, pero hay que confirmar que se mantiene igual.
- **Credenciales:** el `GITHUB_TOKEN` de Actions solo sirve para su propio repo. Un orquestador central necesitaría un PAT o una GitHub App con un alcance mucho más amplio.
- **Errores de etiquetado:** una story sin repo destino, o con un repo que no está en la lista permitida, debe saltarse y no ir a un repo por defecto.
- **Contexto por repo:** cada repo tiene su `AGENTS.md`, sus tests y su entorno.

**Preguntas abiertas para Álvaro**
1. **¿Cómo se marca el repo en la story?** ¿Con la línea `Repository:` de la descripción (como ahora), con un campo propio de Jira (ya existe el hueco `JIRA_REPOSITORY_FIELD_ID`), con componentes o con etiquetas?
2. **¿Quién reparte?** ¿Cada repo mantiene su instalación y coge solo las stories cuyo repo destino es el suyo, o hay un orquestador central que lee el pool y reparte?
3. **¿El límite de 3 por run es por repo o global?** Y si es global, ¿cómo se reparte entre repos: solo por Rank, o con un cupo o turno por repo?
4. **Dependencias entre stories de repos distintos:** ¿basta con exigir el blocker en Finalizada, o hace falta algo más (orden de merge, versiones)?
5. **Credenciales:** si hay un orquestador central, ¿con qué identidad escribe en cada repo (GitHub App, PAT o la integración de cada provider)?
6. ¿Dónde vive la lista de repos permitidos: en este repo, en Jira o en otro sitio?
7. ¿Aplica a los tres providers a la vez o empezamos por uno?

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
