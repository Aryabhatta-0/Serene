// Where the web app would find Serene's Supabase project. Both values are
// public by design (the anon key only grants what RLS allows a signed-in
// user); nothing secret belongs here. When they are not set, every surface
// stays in its honest "not connected" state.
export type SupabaseConfig = { url: string; anonKey: string };

export function supabaseConfig(env: Record<string, string | undefined> = {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
}): SupabaseConfig | null {
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anonKey = env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url || !anonKey || !/^https:\/\/|^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?/.test(url)) return null;
  return { url, anonKey };
}
