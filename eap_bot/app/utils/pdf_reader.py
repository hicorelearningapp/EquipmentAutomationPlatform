from abc import ABC, abstractmethod

from pypdf import PdfReader


class DocumentParser(ABC):

    @abstractmethod
    def extract_text(self, path: str) -> str:
        """Return the full plain-text content of the document at *path*."""


class PyPDFParser(DocumentParser):

    def extract_text(self, path: str) -> str:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            content = page.extract_text()
            if content:
                pages.append(content)
        return "\n".join(pages)


class DocumentParserFactory:

    @staticmethod
    def create() -> DocumentParser:
        return PyPDFParser()
