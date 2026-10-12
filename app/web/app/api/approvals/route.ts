import { relayApproval } from "@/lib/experiments/relay";

// POST /api/approvals (Issue #84): the same-origin relay from the browser to
// the kernel's authenticated `POST /web/approvals`. Server-side only:
// SERENE_KERNEL_URL never reaches the browser.
export const dynamic = "force-dynamic";

export function POST(request: Request): Promise<Response> {
  return relayApproval(request, process.env, (...args) => fetch(...args));
}
