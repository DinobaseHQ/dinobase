# dinobase website

Marketing site and documentation for [dinobase](https://github.com/DinobaseHQ/dinobase) — the SQL query layer for agent stacks. Dinobase connects 100+ business data sources behind a unified DuckDB interface, so agents write SQL and cross-connector `JOIN`s work natively. In benchmarks across 11 LLMs: **91% accuracy vs 35% for bare MCP tools, 3x faster, 16x cheaper per correct answer.**

Built with [Astro](https://astro.build) and [Starlight](https://starlight.astro.build).

## Project structure

```
.
├── public/                 static assets (og image, install.sh, logos)
├── src/
│   ├── assets/             images referenced from content
│   ├── components/         landing Astro components
│   ├── content/docs/       guides, reference, integrations, connectors
│   ├── pages/index.astro   landing page
│   └── styles/
├── astro.config.mjs        Starlight sidebar + site config
└── package.json
```

Docs live under `src/content/docs/` and are routed by file name. Sidebar order is configured in `astro.config.mjs`.

## Commands

All commands run from `ee/website/`:

| Command           | Action                                       |
| :---------------- | :------------------------------------------- |
| `npm install`     | Install dependencies                         |
| `npm run dev`     | Start local dev server at `localhost:4321`   |
| `npm run build`   | Build production site to `./dist/`           |
| `npm run preview` | Preview the production build locally         |

## Editing docs

When adding or changing a user-facing feature in dinobase, update the relevant page(s) under `src/content/docs/`. If no existing page covers the feature, create one in the appropriate subdirectory (`guides/`, `reference/`, `connectors/`, `integrations/`) and add it to the sidebar in `astro.config.mjs`.
