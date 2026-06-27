# e2egraph

[English](README.md) | **Español**

Convierte repositorios locales en un mapa navegable de **flujos funcionales end-to-end** — cómo una funcionalidad viaja desde el frontend, a través del gateway GraphQL / la capa de API, cruzando clientes gRPC o REST, hasta el microservicio destino, y baja a la tabla de base de datos o el servicio externo que toca.

Es una skill de [Claude Code](https://docs.claude.com/en/docs/claude-code) (`/e2egraph`). **No** usa ninguna API key de proveedor: el trabajo determinista es Python puro, y el trabajo semántico corre a través de subagentes de Claude Code en tu sesión actual.

> Pensado para ecosistemas de microservicios (NestJS / gateway GraphQL / gRPC / microservicios con Drizzle-o-SQL / frontends Next.js), pero el motor es genérico.

---

## Qué obtienes

Ejecutar la skill sobre una carpeta de repos produce un directorio de salida autocontenido (`e2egraph-out/`) con tres vistas complementarias:

| Vista | Archivo | Qué responde |
|---|---|---|
| **Dashboard** | `index.html` | "¿Qué funcionalidades existen y cuáles están trazadas?" — un catálogo buscable de cada operación por repo, agrupado por repo de entrada, cada una marcada como *trazada* o *pendiente*. |
| **Flujo** | `flows/<feature>.html` | "¿Cómo funciona *esta* funcionalidad de punta a punta?" — una cadena clicable (frontend → resolver → gRPC/REST → microservicio → tabla) con detalle rico por paso. |
| **Vista general** | `graph.html` | "¿Quién llama a quién?" — la arquitectura: repos como nodos, llamadas reales entre servicios como aristas. |

Además `GRAPH_REPORT.md` (reporte en lenguaje natural) y `graph.json` (datos crudos).

Todo es un único archivo HTML autocontenido (Cytoscape.js embebido inline) — se abre con doble clic, sin servidor, sin internet.

---

## El modelo de dos niveles (la idea clave)

Trazar cada funcionalidad en detalle sería costoso (cada trazado profundo lee código vía un subagente). Por eso e2egraph divide el trabajo en dos niveles:

1. **Catálogo — gratis, determinista, instantáneo.** Un escaneo en Python puro lista *todas* las operaciones de cada repo (operaciones GraphQL consumidas, resolvers/endpoints definidos) con `archivo:línea`. Esto llena el dashboard con cobertura completa a **cero costo de tokens**.
2. **Trazado profundo — bajo demanda, cacheado.** Eliges una funcionalidad del catálogo y la trazas de punta a punta con `/e2egraph flow "<feature>"`. Solo este paso usa tokens de la sesión (un subagente lee el código), y el resultado queda cacheado como `flows/<feature>.json` y se muestra en el dashboard.

> **Ves todo gratis; solo pagas por profundizar las funcionalidades que te importan.**

---

## Requisitos

- **Claude Code** (la skill corre dentro de él).
- **Python 3** (solo librería estándar — no requiere `pip install`).
- **universal-ctags** *(opcional)* — mejora la extracción de símbolos multi-lenguaje; si no está, usa un fallback por regex.
- Para trazados profundos: una sesión de Claude Code (los subagentes corren ahí). **Sin API key, nunca.**

---

## Instalación

Coloca la carpeta de la skill en `~/.claude/skills/e2egraph/` y registra el trigger en tu `~/.claude/CLAUDE.md`:

```markdown
# e2egraph
- **e2egraph** (`~/.claude/skills/e2egraph/SKILL.md`) - local repos to E2E flow knowledge graph. Trigger: `/e2egraph`
When the user types `/e2egraph`, invoke the Skill tool with `skill: "e2egraph"` before doing anything else.
```

O clona este repo en esa ruta:
```bash
git clone git@github.com:Fechm/e2egraph.git ~/.claude/skills/e2egraph
```

---

## Uso

```
/e2egraph                      # construye/refresca el dashboard sobre la raíz actual
/e2egraph --root C:\ruta\repos # define explícitamente la carpeta madre de tus repos
/e2egraph --update             # incremental: solo repos cambiados
/e2egraph flows                # el catálogo (gratis) — qué se puede trazar
/e2egraph flow "<feature>"     # traza UNA funcionalidad de punta a punta (usa tokens de sesión)
/e2egraph --depth structural   # omite la capa semántica (cero tokens)
/e2egraph query "<pregunta>"   # responde desde graph.json vía la sesión
```

**Flujo de trabajo típico**

1. `/e2egraph --root <tu carpeta de repos>` → abre `e2egraph-out/index.html`.
2. Busca/navega el catálogo; encuentra una funcionalidad pendiente (ej. `saveRequestTne`).
3. Clic en **"Trazar"** en su tarjeta → copia `/e2egraph flow "saveRequestTne"` a tu portapapeles.
4. Pégalo en Claude Code → la funcionalidad se traza en detalle.
5. Refresca el dashboard → la funcionalidad ahora aparece como trazada, con su badge de seguridad y un enlace a su flujo.

---

## Anatomía de un flujo trazado

Cada paso del HTML de un flujo es un **nodo clicable**. Al hacer clic muestra:

- **Archivo** (`archivo:línea`) y qué hace el paso.
- **Mecanismo** hacia el siguiente salto (mutation GraphQL, gRPC client-streaming, llamada REST, escritura SQL…).
- **Dónde se usa** — dónde se dispara la funcionalidad (ej. *"botón Guardar en la página de solicitud TNE"*).
- **Participantes** — los servicios/llamadas involucrados dentro de ese paso.
- **Contrato de datos** — los campos y tipos que viajan (input type de GraphQL, message proto, schema de validación, columnas de la tabla), cada uno marcado como obligatorio u opcional.
- **Seguridad** — una observación honesta por paso: 🟢 controles presentes / 🟡 revisar / 🔴 riesgo, cada una con evidencia `archivo:línea` y un disclaimer. **Nunca marca un paso como "seguro"** — reporta los controles encontrados y las banderas concretas, porque un verde falso es peor que ninguno.

---

## Cómo funciona

```
detect  →  symbols + relations  →  build (grafo por repo)  →  crossrepo (merge + resolución)  →  overview + dashboard
                                                                                                       │
                                                              catalog (determinista, gratis) ──────────┤
                                                                                                       │
                                          flow "<feature>"  →  subagente traza E2E  →  flow HTML + tarjeta en dashboard
```

- **Extracción estructural (determinista, gratis):** detección de repos/archivos, símbolos (ctags o fallback regex), imports, referencias a servicios por variable de entorno (`*_URL`/`*_HOST`/`*_ADDRESS`, `config.X`, `configService.get`), llamadas API, servicios `.proto`, tablas SQL / Drizzle.
- **Resolución cross-repo:** las env vars de servicio se emparejan con el repo destino **solo cuando la coincidencia es inequívoca** (coincidencia exacta o de token único) — nunca adivina por una palabra compartida; las tablas y los contratos proto compartidos enlazan productores y consumidores.
- **Capa semántica (selectiva, vía subagentes):** trazado profundo de flujos, descripciones en lenguaje natural, seguridad y contratos de datos por paso. Corre en tu sesión de Claude Code — sin API key.

---

## Garantías

- **No se lee ninguna API key** de proveedor en ninguna etapa. La capa semántica son subagentes de Claude Code (tu sesión).
- **Sin fuga de secretos.** Los *valores* de las env vars nunca se leen. Los *nombres* de variables que parecen secretos se enmascaran (ej. `STRIPE_••••_KEY`); solo se conservan los endpoints de servicio (`*_URL`/`*_HOST`/…). Nada sensible entra al grafo, al HTML ni al reporte.
- **Salida autocontenida.** Cada HTML embebe su librería inline — sin CDN, sin red, sin servidor.
- **Honesto por diseño.** Las aristas que no se pueden confirmar se marcan `AMBIGUOUS`; la seguridad se reporta como observaciones con evidencia, nunca como un veredicto binario.

---

## Arquitectura

Módulos Python de responsabilidad única bajo `lib/` (solo librería estándar):

| Módulo | Responsabilidad |
|---|---|
| `detect.py` | Descubrir repos y archivos fuente bajo una raíz |
| `symbols.py` | Símbolos vía universal-ctags, fallback regex |
| `relations.py` | Aristas: imports, env vars, API, proto, SQL/Drizzle, endpoints |
| `secrets_filter.py` | Clasificar/enmascarar nombres de env vars (sin fuga de secretos) |
| `build.py` | Ensamblar el grafo por capas de un repo |
| `crossrepo.py` | Fusionar repos + resolver conexiones cross-repo |
| `overview.py` | Reducir a la vista de arquitectura limpia (repos + flujos) |
| `catalog.py` | Catálogo de funcionalidades determinista |
| `semantic.py` | Fusionar resultados de subagentes (enlaces gql, descripciones) |
| `render_html.py` | Vista general interactiva con Cytoscape |
| `render_flow_html.py` | Cadena de flujo interactiva (detalle, seguridad, contrato de datos) |
| `dashboard.py` | Dashboard: catálogo, buscador, sidebar, botones de trazado |
| `report.py` | `GRAPH_REPORT.md` |
| `io_utils.py` | Lectura segura de archivos |

---

## Tests

```bash
cd ~/.claude/skills/e2egraph
python -m unittest discover -s tests -v
```

La suite es `unittest` puro (sin dependencias) y cubre cada módulo más un test de integración end-to-end sobre fixtures conocidos (incluida la garantía de no-fuga-de-secretos).

---

## Limitaciones conocidas

- **El emparejamiento cross-repo por nombre es conservador** — solo resuelve coincidencias inequívocas. Cuando un frontend apunta a un backend por una URL genérica/`localhost`, ese enlace se deja a la capa semántica en vez de adivinarlo.
- **El catálogo/cadena determinista es bueno, no perfecto** — el código que resuelve cosas en runtime (URLs dinámicas, condicionales) puede dejar huecos que solo un trazado profundo completa.
- **El trazado profundo cuesta tokens de sesión** (un subagente lee código). El catálogo, el dashboard, el buscador y la vista general son gratis.
- **Los grafos grandes** colapsan la vista general a repos/módulos por encima de ~5000 nodos.

---

## Licencia

Herramienta personal/interna. Úsala a tu criterio.
