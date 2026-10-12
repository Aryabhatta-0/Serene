import { readDemoState } from "@/lib/demo/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const headers = { "Cache-Control": "no-store" };
  if (process.env.SERENE_DEMO_MODE !== "1") return new Response(null, { status: 404, headers });
  try {
    return Response.json(await readDemoState(), { headers });
  } catch {
    // Never expose subprocess diagnostics or local paths to the browser.
    return Response.json({ error: "Canonical Maya report unavailable or invalid. Run reset and the Maya demo, then reload." }, { status: 503, headers });
  }
}
