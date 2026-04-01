"use client";

import Link from "next/link";
import { createClient } from "@/lib/supabase";
import { useRouter } from "next/navigation";

export function Nav({
  email,
  showAuth = true,
}: {
  email?: string;
  showAuth?: boolean;
}) {
  const router = useRouter();
  const supabase = createClient();

  async function handleLogout() {
    await supabase.auth.signOut();
    router.push("/");
  }

  return (
    <nav className="border-b border-zinc-800 px-6 py-3 flex items-center justify-between bg-zinc-950">
      <Link href="/" className="flex items-center gap-2">
        <img src="/logo.svg" alt="Dinobase" className="h-7 w-auto" />
        <span className="text-sm font-normal text-zinc-500">Cloud</span>
      </Link>
      {showAuth && (
        <div className="flex items-center gap-4">
          <a
            href="https://dinobase.ai/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="text-zinc-500 hover:text-zinc-300 text-sm"
          >
            Docs
          </a>
          {email ? (
            <>
              <span className="text-sm text-zinc-400">{email}</span>
              <button
                onClick={handleLogout}
                className="text-zinc-500 hover:text-zinc-300 text-sm"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="text-zinc-400 hover:text-white text-sm"
              >
                Log in
              </Link>
              <Link
                href="/login"
                className="bg-dino-green text-white px-4 py-2 rounded-lg text-sm font-medium hover:brightness-110"
              >
                Sign up free
              </Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
}
