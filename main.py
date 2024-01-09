import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rmscene import read_tree
from rmscene.scene_items import ParagraphStyle
from rmscene.text import TextDocument

load_dotenv()

IMPORT_TAG = 'Obsidian/Import'
REMARKABLE_DIRECTORY = os.getenv('REMARKABLE_DIRECTORY', 'app/remarkables')
VAULT_DIRECTORY = os.getenv('VAULT_DIRECTORY', 'app/vault')
INGEST_DIRECTORY = os.getenv('INGEST_DIRECTORY', '99 - Ingest')
TEMPLATE_DIRECTORY = os.getenv('TEMPLATE_DIRECTORY', '91 - Templates')

template_directory = Path(f"{VAULT_DIRECTORY}/{TEMPLATE_DIRECTORY}")
available_templates = set(x.stem for x in template_directory.glob('*.md'))


def get_uuids_to_process(directory: Path, filter_tag: Optional[str] = IMPORT_TAG) -> list:
    """
    Get a list of uuids to process from a directory.
    """
    # Get a list of directories
    directories = filter(lambda d: not d.name.endswith(".thumbnails"), [x for x in directory.iterdir() if x.is_dir()])
    uuids = [x.name for x in directories]
    # Filter out any possible invalid files / directories that are not a uuid
    uuids = list(filter(
        lambda d: re.search(r'^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$',
                            d), uuids))  # noqa: E501

    if filter_tag is None:
        return uuids

    output = []
    for uuid in uuids:
        content = RM_read_json(directory / f"{uuid}.content")
        try:
            tags = [tag['name'] for tag in content['tags']]
        except TypeError:
            tags = []
        try:
            page_tags = [tag['name'] for tag in content['pageTags']]
        except TypeError:
            page_tags = []
        # print(tags, page_tags)
        if filter_tag in tags + page_tags:
            output.append(uuid)

    return output


def RM_read_json(filepath: Path) -> Optional[dict]:
    if os.path.isfile(filepath):
        data = open(filepath, 'r', encoding='utf8').read().strip()
        return None if data == "Blank" else json.loads(data)
    return None


def extract_doc(path):
    with open(path, "rb") as f:
        tree = read_tree(f)
        assert tree.root_text
        doc = TextDocument.from_scene_item(tree.root_text)
        return doc


class RemarkablePage:
    def __init__(self, path: Path, parent: 'RemarkableDocument'):
        self.path = path
        self.uuid = path.stem
        self.parent = parent

        with open(self.path, "rb") as f:
            self._tree = read_tree(f)

        self.tags = set(tag['name'] for tag in self.parent.content['pageTags'] if tag['pageId'] == self.uuid)

        self.page_number = next(
            (i + 1 for i, page in enumerate(self.parent.content['cPages']['pages']) if page['id'] == self.uuid), 0)
        self.name = f"{self.parent.name} - Page {self.page_number}"

        self._text_document = TextDocument.from_scene_item(self._tree.root_text) if self._tree.root_text else None

        # Improve the name of the page if possible
        if self.has_text:
            try:
                if self._text_document.contents[0].style.value == ParagraphStyle.HEADING:
                    self.name = f"{self.parent.name} - {self._text_document.contents[0].contents[0].s}"
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


class RemarkableDocument:
    def _find_pages(self) -> list[Path]:
        # return list(self._root_directory.glob(f"{self._uuid}/*.rm"))
        return [self._path / f"{page['id']}.rm" for page in self.content['cPages']['pages'] if 'deleted' not in page]

    def _read_json(self, filename: str) -> dict:
        if os.path.isfile(self._root_directory / filename):
            data = open(self._root_directory / filename, 'r').read().strip()
            return {} if data == "Blank" else json.loads(data)
        return {}

    def __init__(self, uuid: str, root_directory: Path):
        self._root_directory = root_directory
        self._uuid = uuid
        self._path = self._root_directory / self._uuid

        self.content = self._read_json(f'{uuid}.content')  # TODO: convert to RemarkableContent
        self.metadata = self._read_json(f'{uuid}.metadata')  # TODO: convert to RemarkableMetadata

        self.tags = [tag['name'] for tag in self.content['tags']]

        self.name = self.metadata.get('visibleName', 'Untitled')
        self.background = "pdf" in self.content['fileType']

        self.pages = [RemarkablePage(p, self) for p in self._find_pages()]

        # TODO: add an array of parent directories

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
        if self.name == '.keep':
            return
        for tag in self.content['tags']:
            if tag['name'] == frm:
                tag['name'] = to
                self.save_content()
                return

    def save_content(self):
        with open(self._root_directory / f"{self._uuid}.content", "w", encoding='utf8') as f:
            json.dump(self.content, f, indent=4)

    def __str__(self):
        return f"RemarkableDocument(name={self.name}, uuid={self._uuid})"

    def __repr__(self):
        return f"RemarkableDocument(name={self.name}, uuid={self._uuid})"


def app(remarkables_directory: Path, vault_directory, overwrite: bool = True) -> bool:
    def save(name: str, content: str) -> None:
        directory = vault_directory / INGEST_DIRECTORY
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / f"{name}.md"
        if file_path.exists() and not overwrite:
            print(f"File {file_path} already exists, skipping")
            return False

        with open(file_path, "w", encoding='utf8') as f:
            f.write(content)

        return True

    uuids = get_uuids_to_process(remarkables_directory)

    print(uuids)

    rm_docs = [RemarkableDocument(uuid, remarkables_directory) for uuid in uuids]

    for rm_doc in rm_docs:
        choice = input(f'Do you want to process "{rm_doc.name}" ? ([y]/n)')
        # choice = True
        if choice == 'n':
            continue
        if IMPORT_TAG in rm_doc.tags:
            print(f"Processing {rm_doc.name}")
            obsidian = rm_doc.to_obsidian()
            print(obsidian)
            if save(rm_doc.name, obsidian):
                rm_doc.replace_tag(IMPORT_TAG, 'Obsidian/Imported')
        else:
            for page in rm_doc.pages:
                if IMPORT_TAG in page.tags:
                    print(f"Processing {page}")
                    template_tags = list(page.tags & available_templates)
                    if len(template_tags) == 1:
                        obsidian = page.to_obsidian(template_tags[0])
                    else:
                        if len(template_tags) > 1:
                            print(f"Multiple templates found for {page}, not using any template")
                        obsidian = page.to_obsidian()
                    print(obsidian)
                    if save(page.name, obsidian):
                        page.replace_tag(IMPORT_TAG, 'Obsidian/Imported')

    # TODO: update and save the tags

    exit(0)


if __name__ == "__main__":
    app(Path(REMARKABLE_DIRECTORY), Path(VAULT_DIRECTORY))
