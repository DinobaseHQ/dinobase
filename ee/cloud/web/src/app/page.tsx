import Link from "next/link";
import { redirect } from "next/navigation";
import { Nav } from "@/components/Nav";
import { createServerSupabaseClient } from "@/lib/supabase-server";

export default async function LandingPage() {
  const supabase = await createServerSupabaseClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (user) {
    redirect("/dashboard");
  }

  return (
    <>
      <Nav showAuth />
      <main className="max-w-5xl mx-auto px-6">
        {/* Hero */}
        <section className="text-center py-24">
          <h1 className="text-6xl font-bold tracking-tight mb-6">
            The agent-native
            <br />
            <span className="text-dino-green">database</span>
          </h1>
          <p className="text-xl text-zinc-400 mb-10 max-w-2xl mx-auto">
            Connect Stripe, HubSpot, Salesforce, and 100+ more in seconds.
            Query across all sources with SQL. Let AI agents set it up for you.
          </p>
          <div className="flex gap-4 justify-center">
            <Link
              href="/login"
              className="bg-dino-green text-white px-8 py-3 rounded-lg text-lg font-medium hover:brightness-110"
            >
              Get started free
            </Link>
            <a
              href="https://github.com/dinobase/dinobase"
              className="border border-zinc-700 text-zinc-300 px-8 py-3 rounded-lg text-lg font-medium hover:border-zinc-500"
            >
              View on GitHub
            </a>
          </div>
          <p className="text-zinc-600 text-sm mt-4">
            No credit card required
          </p>
        </section>

        {/* Features */}
        <section className="grid grid-cols-3 gap-6 mb-24">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <div className="text-3xl mb-4">&#x1F517;</div>
            <h3 className="font-semibold text-lg mb-2">Connect in clicks</h3>
            <p className="text-zinc-400 text-sm">
              OAuth for 30+ sources. Click, authorize, done. No API keys to
              hunt down.
            </p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <div className="text-3xl mb-4">&#x1F50D;</div>
            <h3 className="font-semibold text-lg mb-2">Query with SQL</h3>
            <p className="text-zinc-400 text-sm">
              Cross-source JOINs across Stripe, HubSpot, Zendesk, and more.
              Standard DuckDB SQL.
            </p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <div className="text-3xl mb-4">&#x1F916;</div>
            <h3 className="font-semibold text-lg mb-2">Agent-native</h3>
            <p className="text-zinc-400 text-sm">
              Built for AI agents. JSON output, MCP server, OpenClaw skill.
              Agents set up and query autonomously.
            </p>
          </div>
        </section>

        {/* CLI snippet */}
        <section className="mb-24">
          <h2 className="text-2xl font-bold mb-6 text-center">
            Or set up from the CLI
          </h2>
          <pre className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-sm overflow-x-auto">
            <code className="text-dino-green">
              {`pip install dinobase
dinobase login
dinobase auth hubspot
dinobase auth stripe
dinobase sync
dinobase query "SELECT * FROM stripe.customers JOIN hubspot.contacts USING (email)"`}
            </code>
          </pre>
        </section>
      </main>
    </>
  );
}
