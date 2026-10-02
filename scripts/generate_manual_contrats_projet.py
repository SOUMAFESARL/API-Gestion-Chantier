"""Generate the practical manual with the API contract and implementation."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer


def main():
    root = Path(__file__).resolve().parents[1]
    styles = getSampleStyleSheet()
    styles["Code"].fontSize = 7
    styles["Code"].leading = 9
    story = []
    code = None
    for block in (root / "docs/api-projets-contrats.md").read_text(encoding="utf-8").splitlines():
        if block.startswith("```"):
            if code is None:
                code = []
            else:
                story.extend([Preformatted("\n".join(code), styles["Code"]), Spacer(1, 10)])
                code = None
        elif code is not None:
            code.append(block)
        elif block:
            style = "Title" if block.startswith("# ") else "BodyText"
            story.append(Paragraph(escape(block.removeprefix("# ")), styles[style]))
        else:
            story.append(Spacer(1, 8))
    for filename in (
        "apps/projets/models/contrat.py",
        "apps/projets/storage.py",
        "apps/projets/services/contrats.py",
        "apps/projets/serializers/swagger.py",
    ):
        story.extend(
            [
                PageBreak(),
                Paragraph(escape(filename), styles["Heading1"]),
                Preformatted((root / filename).read_text(encoding="utf-8"), styles["Code"]),
            ]
        )
    target = root / "Manuels_Apprentissage/MANUEL_SPRINT_3_TACHE_CONTRATS_PROJET.pdf"
    target.parent.mkdir(exist_ok=True)
    SimpleDocTemplate(str(target)).build(story)
    print(target)


if __name__ == "__main__":
    main()
