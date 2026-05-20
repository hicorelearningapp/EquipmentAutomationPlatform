from abc import ABC, abstractmethod
from typing import BinaryIO, Union

from pypdf import PdfReader


class DocumentParser(ABC):

    @abstractmethod
    def extract_text(self, source: Union[str, BinaryIO]) -> str:
        """Return the full plain-text content of the document. Accepts a path or a binary file-like object."""


class PyPDFParser(DocumentParser):

    def extract_text(self, source: Union[str, BinaryIO]) -> str:
        reader = PdfReader(source)
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
