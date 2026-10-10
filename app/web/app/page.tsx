// Serene web shell (bootstrap). The five primary surfaces are placeholders;
// they are implemented by the M3 issues (#34-#39). Nothing here fakes data.

const SURFACES = [
  { name: "Today", issue: "#35" },
  { name: "Memory", issue: "#36" },
  { name: "Investigations", issue: "#35" },
  { name: "Experiments", issue: "#37" },
  { name: "Causal Twin", issue: "#38" },
];

export default function Home() {
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Serene</h1>
      <p>
        A self-correcting family intelligence agent. Bootstrap shell only &mdash;
        no feature is implemented yet.
      </p>
      <p>
        <em>what happened != what Serene remembers != what Serene believes</em>
      </p>
      <ul>
        {SURFACES.map((s) => (
          <li key={s.name}>
            {s.name} <small>({s.issue})</small>
          </li>
        ))}
      </ul>
    </main>
  );
}
