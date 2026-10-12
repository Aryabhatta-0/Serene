// The five primary Serene surfaces (Issue #34). This list is the only source
// of truth for navigation; adding a sixth surface is a product decision, not a
// routing detail. Copy here describes what a surface is for, never its data.

type Surface = {
  href: string;
  label: string;
  /** The one question the surface answers, in a parent's words. */
  question: string;
  summary: string;
};

export const SURFACES: readonly Surface[] = [
  {
    href: "/today",
    question: "What matters now?",
    label: "Today",
    summary: "What Serene is working on and what it would do next.",
  },
  {
    href: "/memory",
    question: "What has Serene learned and kept?",
    label: "Memory",
    summary: "What Serene remembers, and where each memory came from.",
  },
  {
    href: "/investigations",
    question: "What might be happening, and what evidence is needed?",
    label: "Investigations",
    summary: "Competing explanations and the evidence still missing.",
  },
  {
    href: "/experiments",
    question: "What could we safely try?",
    label: "Experiments",
    summary: "Small, reversible changes you choose whether to try.",
  },
  {
    href: "/causal-twin",
    question: "Why does Serene believe what it believes?",
    label: "Causal Twin",
    summary: "A map of what may influence what, drawn by how well it is known.",
  },
];

export function surfaceFor(href: string): Surface {
  return SURFACES.find((s) => s.href === href)!;
}

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
