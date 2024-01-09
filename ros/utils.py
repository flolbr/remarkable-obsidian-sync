import json
import os
import re
from pathlib import Path
from typing import Optional

from rmscene import read_tree
from rmscene.text import TextDocument

from vars import IMPORT_TAG


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
