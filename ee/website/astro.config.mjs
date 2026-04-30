// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  integrations: [
    starlight({
      components: {
        Head: "./src/components/Head.astro",
        Footer: "./src/components/SiteFooter.astro",
      },
      title: "dinobase",
      logo: { src: "./src/assets/logo.svg", alt: "" },
      description:
        "The agent-first database. Connect your business data. Let AI agents query across all of it.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/DinobaseHQ/dinobase",
        },
      ],
      customCss: ["./src/styles/custom.css"],
      head: [
        {
          tag: "meta",
          attrs: { property: "og:image", content: "/og.png" },
        },
      ],
      sidebar: [
        {
          label: "Start Here",
          items: [
            { label: "Introduction", slug: "docs" },
            { label: "Getting Started", slug: "docs/getting-started" },
          ],
        },
        {
          label: "Guides",
          items: [
            { label: "Setup GUI", slug: "docs/guides/setup-ui" },
            { label: "Connectors", slug: "docs/guides/connecting-sources" },
            { label: "Querying Data", slug: "docs/guides/querying" },
            { label: "Syncing & Scheduling", slug: "docs/guides/syncing" },
            { label: "Schema Annotations", slug: "docs/guides/annotations" },
            { label: "Mutations", slug: "docs/guides/mutations" },
            { label: "Python Execution", slug: "docs/guides/exec-code" },
            {
              label: "Cloud Storage Backend",
              slug: "docs/guides/cloud-storage-backend",
            },
          ],
        },
        {
          label: "Integrations",
          items: [
            { label: "MCP", slug: "docs/integrations/mcp" },
            { label: "Claude Code", slug: "docs/integrations/claude-code" },
            {
              label: "Claude Desktop",
              slug: "docs/integrations/claude-desktop",
            },
            { label: "Cursor", slug: "docs/integrations/cursor" },
            { label: "Codex", slug: "docs/integrations/codex" },
            { label: "OpenClaw", slug: "docs/integrations/openclaw" },
            { label: "Vercel AI SDK", slug: "docs/integrations/vercel-ai" },
            { label: "CrewAI", slug: "docs/integrations/crewai" },
            {
              label: "LangChain / LangGraph",
              slug: "docs/integrations/langchain",
            },
            { label: "Pydantic AI", slug: "docs/integrations/pydantic-ai" },
            { label: "LlamaIndex", slug: "docs/integrations/llamaindex" },
            { label: "Mastra", slug: "docs/integrations/mastra" },
          ],
        },
        {
          label: "Connectors",
          items: [
            { label: "Overview", slug: "docs/connectors/overview" },
            { label: "SaaS APIs", slug: "docs/connectors/saas" },
            { label: "Databases", slug: "docs/connectors/databases" },
            { label: "Files", slug: "docs/connectors/files" },
            { label: "Cloud Storage", slug: "docs/connectors/cloud-storage" },
            { label: "Custom REST", slug: "docs/connectors/custom-rest" },
            { label: "MCP Servers", slug: "docs/connectors/mcp" },
            { label: "Customizing a sync", slug: "docs/connectors/customizing" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "CLI", slug: "docs/reference/cli" },
            { label: "Configuration", slug: "docs/reference/configuration" },
            { label: "MCP Tools", slug: "docs/reference/mcp-tools" },
            { label: "Python API", slug: "docs/reference/python-api" },
            {
              label: "Environment Variables",
              slug: "docs/reference/environment-variables",
            },
          ],
        },
        {
          label: "Project",
          items: [
            { label: "Architecture", slug: "docs/project/architecture" },
            { label: "Development", slug: "docs/project/development" },
            { label: "Benchmark", slug: "docs/project/benchmarks" },
          ],
        },
      ],
    }),
  ],
});
