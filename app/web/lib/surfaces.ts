// The five primary Serene surfaces (Issue #34). This list is the only source
// of truth for navigation; adding a sixth surface is a product decision, not a
// routing detail. Copy here describes what a surface is for, never its data.

export type Surface = {
  href: string;
  label: string;
  summary: string;
};

export const SURFACES = [
  {
    href: "/today",
    label: "Today",
    summary: "What Serene is working on and what it would do next.",
  },
  {
    href: "/memory",
    label: "Memory",
    summary: "What Serene remembers, and where each memory came from.",
  },
  {
    href: "/investigations",
    label: "Investigations",
    summary: "Competing explanations and the evidence still missing.",
  },
  {
    href: "/experiments",
    label: "Experiments",
    summary: "Small, reversible changes you choose whether to try.",
  },
  {
    href: "/causal-twin",
    label: "Causal Twin",
    summary: "A map of what may influence what, drawn by how well it is known.",
  },
] as const satisfies readonly Surface[];

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
