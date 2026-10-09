"""Génère le manuel à partir du contrat et du code livré, sans secret."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Manuels_Apprentissage/MANUEL_SPRINT_4_TACHE_CRUD_JOURNAL_CHANTIER.pdf"


def main():
    styles = getSampleStyleSheet()
    story = []
    for line in (ROOT / "docs/journal-chantier-api.md").read_text(encoding="utf-8").splitlines():
        if not line:
            story.append(Spacer(1, 6))
        else:
            style = (
                styles["Heading1"]
                if line.startswith("# ")
                else styles["Heading2"]
                if line.startswith("## ")
                else styles["BodyText"]
            )
            story.append(Paragraph(escape(line.lstrip("# ")), style))
    for relative in (
        "apps/chantier/models/journal.py",
        "apps/chantier/serializers/journal.py",
        "apps/chantier/services/journal.py",
        "apps/chantier/selectors/journal.py",
        "apps/chantier/views/journal.py",
        "apps/chantier/urls_journal.py",
        "apps/chantier/migrations/0005_alertejournal_journalchantier_and_more.py",
        "apps/chantier/tests/test_journal_api.py",
        "apps/chantier/tests/test_journal_validation.py",
    ):
        path = ROOT / relative
        if path.exists():
            story.extend([PageBreak(), Paragraph(escape(relative), styles["Heading2"])])
            for line in path.read_text(encoding="utf-8").splitlines():
                # Une ligne longue est coupée pour rester imprimable.
                chunks = [line[i : i + 100] for i in range(0, len(line), 100)] or [""]
                style = styles["Code"].clone("code-small", fontSize=8, leading=10)
                story.append(Preformatted("\n".join(chunks), style))
    OUTPUT.parent.mkdir(exist_ok=True)
    SimpleDocTemplate(
        str(OUTPUT),
        title="API journal de chantier - apprentissage pratique",
        rightMargin=36,
        leftMargin=36,
    ).build(story)
    print(OUTPUT)


if __name__ == "__main__":
    main()
