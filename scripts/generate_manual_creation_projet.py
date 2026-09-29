"""Génère le manuel de cette tâche depuis le contrat versionné."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / "Manuels_Apprentissage/MANUEL_SPRINT_3_TACHE_CREATION_PROJET_CONTEXTE.pdf"
    target.parent.mkdir(exist_ok=True)
    styles = getSampleStyleSheet()
    styles["Code"].fontSize = 7
    styles["Code"].leading = 9
    story = []
    paragraph = []
    code = None

    def flush():
        if paragraph:
            story.append(Paragraph(escape(" ".join(paragraph)), styles["BodyText"]))
            story.append(Spacer(1, 6))
            paragraph.clear()

    for line in (root / "docs/api-creation-projet.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            flush()
            if code is None:
                code = []
            else:
                story.append(Preformatted("\n".join(code), styles["Code"]))
                code = None
        elif code is not None:
            code.append(line)
        elif line.startswith("#"):
            flush()
            level = "Title" if line.startswith("# ") else "Heading2"
            story.append(Paragraph(escape(line.lstrip("# ")), styles[level]))
        elif not line:
            flush()
        else:
            paragraph.append(line)
    flush()
    SimpleDocTemplate(str(target), title="API création de projet et contexte connecté").build(story)
    print(target)


if __name__ == "__main__":
    main()
