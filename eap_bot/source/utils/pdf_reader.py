from abc import ABC, abstractmethod
from typing import BinaryIO, Union

from pypdf import PdfReader


class DocumentParser(ABC):

    @abstractmethod
    def extract_text(self, source: Union[str, BinaryIO]) -> str:
        """Return the full plain-text content of the document. Accepts a path or a binary file-like object."""

    @abstractmethod
    def extract_pages(self, source: Union[str, BinaryIO]) -> list[tuple[int, str]]:
        """Return a list of (page_number, text) tuples. page_number is 1-indexed."""

class PyMuPDFParser(DocumentParser):

    def _get_doc(self, source: Union[str, BinaryIO]):
        import fitz
        if isinstance(source, str):
            return fitz.open(source)
        else:
            return fitz.open(stream=source.read(), filetype="pdf")

    def extract_text(self, source: Union[str, BinaryIO]) -> str:
        doc = self._get_doc(source)
        pages = []
        for page in doc:
            content = page.get_text()
            if content:
                pages.append(content)
        doc.close()
        return "\n".join(pages)

    def extract_pages(self, source: Union[str, BinaryIO]) -> list[tuple[int, str]]:
        doc = self._get_doc(source)
        pages = []
        for i, page in enumerate(doc, start=1):
            content = page.get_text()
            if content:
                pages.append((i, content))
        doc.close()
        return pages


class PyPDFParser(DocumentParser):

    def extract_text(self, source: Union[str, BinaryIO]) -> str:
        reader = PdfReader(source)
        pages = []
        for page in reader.pages:
            content = page.extract_text()
            if content:
                pages.append(content)
        return "\n".join(pages)

    def extract_pages(self, source: Union[str, BinaryIO]) -> list[tuple[int, str]]:
        reader = PdfReader(source)
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            content = page.extract_text()
            if content:
                pages.append((i, content))
        return pages


class DocumentParserFactory:

    @staticmethod
    def create() -> DocumentParser:
        try:
            import fitz
            return PyMuPDFParser()
        except ImportError:
            return PyPDFParser()
