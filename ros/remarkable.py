import json
import re
import sys
from functools import cached_property
from pathlib import Path
from typing import Optional

from rmscene import read_tree
from rmscene.scene_items import ParagraphStyle
from rmscene.text import TextDocument

from ros.utils import read_json
from vars import template_directory


class RemarkablePage:
    def __init__(self, path: Path, parent: 'RemarkableDocument'):
        self.path = path
        self.uuid = path.stem
        self.parent: RemarkableDocument = parent

        with open(self.path, "rb") as f:
            self._tree = read_tree(f)

        self.tags = [tag['name'] for tag in self.parent.content['pageTags'] if tag['pageId'] == self.uuid]

        self.page_number = next(
            (i + 1 for i, page in enumerate(self.parent.content['cPages']['pages']) if page['id'] == self.uuid), 0)
        self.name = f"{self.parent.name} - Page {self.page_number}"

        self._text_document = TextDocument.from_scene_item(self._tree.root_text) if self._tree.root_text else None

        # Improve the name of the page if possible
        if self.has_text:
            try:
                if self._text_document.contents[0].style.value == ParagraphStyle.HEADING:
                    self.name = (f"{self.parent.name} - {self._text_document.contents[0].contents[0].s}"
                                 .replace('/', ' - ').strip())
            except IndexError:
                pass

    @property
    def has_text(self) -> bool:
        return self._text_document is not None

    def to_obsidian(self, template: Optional[str] = None) -> Optional[str]:
        text = ""
        if not self.has_text:
            print(f"Page {self} is empty", file=sys.stderr)
            # TODO: Use Excalidraw to generate a diagram instead ?
            return None

        if len(self._text_document.contents) == 0:
            return None

        old_style = ParagraphStyle.PLAIN
        for paragraph in self._text_document.contents:
            # Insert a line break if the paragraph is the beginning of a list
            if old_style == ParagraphStyle.PLAIN and \
                    ParagraphStyle.BULLET <= paragraph.style.value <= ParagraphStyle.CB_CHECKED:
                text += '\n'

            # Insert the correct markdown for the paragraph style
            match paragraph.style.value:
                case ParagraphStyle.HEADING:
                    text += '\n## '
                case ParagraphStyle.PLAIN:
                    pass
                case ParagraphStyle.BOLD:
                    text += "\n### "
                case ParagraphStyle.BULLET:
                    text += "- "
                case ParagraphStyle.BULLET2:
                    text += "    - "
                case ParagraphStyle.CB_EMPTY:
                    text += "- [ ] "
                case ParagraphStyle.CB_CHECKED:
                    text += "- [x] "
                # case ParagraphStyle.BASIC: # Never seen in RM documents, could be useful at some point ?
                #     pass
                case _:
                    raise NotImplementedError(f"Paragraph style {paragraph.style} not implemented")

            # Insert the text, wrap with styling
            for content in paragraph.contents:
                before = ('**' * (content.properties['font-weight'] == 'bold') +
                          '_' * (content.properties['font-style'] == 'italic'))
                after = ('_' * (content.properties['font-style'] == 'italic') +
                         '**' * (content.properties['font-weight'] == 'bold'))
                text += before + content.s + after

            # End of line breaks
            text += '\n'
            if paragraph.style.value in [ParagraphStyle.HEADING, ParagraphStyle.BOLD]:
                text += '\n'

            old_style = paragraph.style.value

        # Clean up the text
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'^(\s*-\s)\s+', '\\1', text, flags=re.MULTILINE)
        text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)

        if template:
            template_text = open(template_directory / f"{template}.md", 'r', encoding='utf8').read()
            text = template_text.replace('<% tp.file.selection() %>', text)

        return text.strip()

    def replace_tag(self, frm, to):
        for tag in self.parent.content['pageTags']:
            if tag['pageId'] == self.uuid and tag['name'] == frm:
                tag['name'] = to
                self.parent.save_content()
                return

    def __str__(self):
        return f"RemarkablePage(uuid={self.uuid})"

    def __repr__(self):
        return f"RemarkablePage(uuid={self.uuid})"


class RemarkableType:
    def __init__(self, uuid: str, root_directory: Path):
        self._root_directory = root_directory
        self._uuid = uuid
        self._path = self._root_directory / self._uuid

        self.content = self._read_json(f'{uuid}.content')  # TODO: convert to RemarkableContent
        self.metadata = self._read_json(f'{uuid}.metadata')  # TODO: convert to RemarkableMetadata

        self.name = self.metadata.get('visibleName', 'Untitled')
        self.tags = [tag['name'] for tag in self.content['tags']]

        if self.metadata['parent'] == '':
            self.parent = None
        else:
            self.parent = RemarkableCollection.create(self.metadata['parent'], self._root_directory, self)

    @cached_property
    def parents(self) -> list[str]:
        if self.parent is None:
            return []
        return self.parent.parents + [self.parent.name]

    def get_parent(self, level: int = 0) -> Optional['RemarkableCollection']:
        if level < 0:
            raise ValueError("Level must be positive")
        if level > 0:
            return self.parent.get_parent(level - 1)
        return self.parent

    def _read_json(self, filename: str) -> dict:
        data = read_json(self._root_directory / filename)
        if data:
            return data
        return {}

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name}, uuid={self._uuid})"


class RemarkableCollection(RemarkableType):

    collections: dict[str, 'RemarkableCollection'] = {}

    def __init__(self, root_directory: Path, uuid: str):
        super().__init__(uuid, root_directory)

        self.children: dict[str, RemarkableType] = {}

    @classmethod
    def create(cls, uuid: str, _root_directory: Path, child: RemarkableType):
        if uuid in cls.collections:
            if child._uuid not in cls.collections[uuid].children:
                cls.collections[uuid].children[child._uuid] = child
            return cls.collections[uuid]
        else:
            collection = cls(_root_directory, uuid)
            cls.collections[uuid] = collection
            collection.children[child._uuid] = child
            return collection


class RemarkableDocument(RemarkableType):
    def _find_pages(self) -> list[Path]:
        # return list(self._root_directory.glob(f"{self._uuid}/*.rm"))
        return [self._path / f"{page['id']}.rm" for page in self.content['cPages']['pages'] if 'deleted' not in page]

    def __init__(self, uuid: str, root_directory: Path):
        super().__init__(uuid, root_directory)

        self.background = "pdf" in self.content['fileType']

        self.pages = [RemarkablePage(p, self) for p in self._find_pages()]

    def page_by_id(self, uuid: str) -> RemarkablePage:
        return next(filter(lambda p: p.uuid == uuid, self.pages))

    def to_obsidian(self, template: str = None) -> str:
        text = f"# {self.name}\n\n"
        for page in self.pages:
            if page.has_text:
                text += page.to_obsidian() + '\n'

        if template:
            template_text = open(template_directory / f"{template}.md", 'r', encoding='utf8').read()
            text = template_text.replace('<% tp.file.selection() %>', text)

        return text

    def replace_tag(self, frm, to):
        if self.name == '.keep' or '.keep' in self.tags:
            return
        for tag in self.content['tags']:
            if tag['name'] == frm:
                tag['name'] = to
                self.save_content()
                return

    def save_content(self):
        with open(self._root_directory / f"{self._uuid}.content", "w", encoding='utf8') as f:
            json.dump(self.content, f, indent=4)
