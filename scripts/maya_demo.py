"""Run the canonical synthetic Maya demonstration without credentials or network."""

from pathlib import Path
from tempfile import TemporaryDirectory

from serene.demo.maya import MayaDemo
from serene.demo.report import render_html, verify_report
from serene.domain.canonical import canonical_json, sha256_hex

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".demo" / "maya"


def main() -> None:
    with TemporaryDirectory(prefix="serene-synthetic-maya-") as temp:
        report = MayaDemo(Path(temp) / "memory").run()
    rows = verify_report(report)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = canonical_json(report)
    (OUTPUT / "report.json").write_bytes(data + b"\n")
    (OUTPUT / "report.html").write_text(render_html(report), encoding="utf-8", newline="\n")
    for row in rows:
        print(f"{row['beat']:02d}. PASS {row['title']} | ledger {row['sequences']}")
    print(f"Dream rejection: {report['dream_rejections']}")
    print(f"Domain report SHA-256: {sha256_hex(data)}")
    print(f"Judge evidence: {OUTPUT / 'report.html'}")


if __name__ == "__main__":
    main()
