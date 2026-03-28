// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
	integrations: [
		starlight({
			title: '🦕 Dinobase',
			description: 'The agent-native database. Connect your business data. Let AI agents query across all of it.',
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/DinobaseHQ/dinobase' }],
			customCss: ['./src/styles/custom.css'],
			head: [
				{
					tag: 'meta',
					attrs: { property: 'og:image', content: '/og.png' },
				},
			],
			sidebar: [
				{
					label: 'Start Here',
					items: [
						{ label: 'Introduction', slug: 'index' },
						{ label: 'Getting Started', slug: 'getting-started' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ label: 'Connecting Sources', slug: 'guides/connecting-sources' },
						{ label: 'Querying Data', slug: 'guides/querying' },
						{ label: 'Syncing & Scheduling', slug: 'guides/syncing' },
						{ label: 'Schema Annotations', slug: 'guides/annotations' },
						{ label: 'Mutations', slug: 'guides/mutations' },
						{ label: 'Cloud Storage Backend', slug: 'guides/cloud-storage-backend' },
					],
        },
        {
          label: 'Integrations',
          items: [
            { label: 'MCP', slug: 'integrations/mcp' },
            { label: 'Claude Code', slug: 'integrations/claude-code' },
            { label: 'Claude Desktop', slug: 'integrations/claude-desktop' },
            { label: 'Cursor', slug: 'integrations/cursor' },
            { label: 'OpenClaw', slug: 'integrations/openclaw' },
            { label: 'Vercel AI SDK', slug: 'integrations/vercel-ai' },
						{ label: 'CrewAI', slug: 'integrations/crewai' },
						{ label: 'LangChain / LangGraph', slug: 'integrations/langchain' },
						{ label: 'Pydantic AI', slug: 'integrations/pydantic-ai' },
						{ label: 'LlamaIndex', slug: 'integrations/llamaindex' },
						{ label: 'Mastra', slug: 'integrations/mastra' },
          ],
				},
				{
					label: 'Sources',
					items: [
						{ label: 'Overview', slug: 'sources/overview' },
						{ label: 'SaaS APIs', slug: 'sources/saas' },
						{ label: 'Databases', slug: 'sources/databases' },
						{ label: 'File Sources', slug: 'sources/files' },
						{ label: 'Cloud Storage', slug: 'sources/cloud-storage' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'CLI', slug: 'reference/cli' },
						{ label: 'Configuration', slug: 'reference/configuration' },
						{ label: 'MCP Tools', slug: 'reference/mcp-tools' },
						{ label: 'Python API', slug: 'reference/python-api' },
						{ label: 'Environment Variables', slug: 'reference/environment-variables' },
					],
				},
				{
					label: 'Project',
					items: [
						{ label: 'Architecture', slug: 'project/architecture' },
						{ label: 'Development', slug: 'project/development' },
					],
				},
			],
		}),
	],
});
