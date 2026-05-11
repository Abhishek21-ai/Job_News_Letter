import fitz
from pathlib import Path


RESUME_PATH = Path("resumes/latest_resume.pdf")


class ResumeParser:
    def __init__(self, pdf_path: str = str(RESUME_PATH)):
        self.pdf_path = pdf_path

    def extract_text(self) -> str:
        doc = fitz.open(self.pdf_path)

        pages = []

        for page in doc:
            pages.append(page.get_text())

        doc.close()

        text = "\n".join(pages)

        return self._clean_text(text)

    def _clean_text(self, text: str) -> str:
        return " ".join(text.split())


if __name__ == "__main__":
    parser = ResumeParser()
    text = parser.extract_text()

    print(text[:2000])