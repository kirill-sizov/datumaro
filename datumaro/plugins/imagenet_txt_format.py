# Copyright (C) 2020-2021 Intel Corporation
#
# SPDX-License-Identifier: MIT

import os
import os.path as osp

from datumaro.components.annotation import (
    AnnotationType, Label, LabelCategories,
)
from datumaro.components.cli_plugin import CliPlugin
from datumaro.components.converter import Converter
from datumaro.components.extractor import DatasetItem, Importer, SourceExtractor


class ImagenetTxtPath:
    LABELS_FILE = 'synsets.txt'
    IMAGE_DIR = 'images'

class ImagenetTxtExtractor(SourceExtractor):
    def __init__(self, path, labels=None, image_dir=None, subset=None):
        assert osp.isfile(path), path

        if not subset:
            subset = osp.splitext(osp.basename(path))[0]
        super().__init__(subset=subset)

        if not image_dir:
            image_dir = ImagenetTxtPath.IMAGE_DIR
        self.image_dir = osp.join(osp.dirname(path), image_dir)

        if labels is None or isinstance(labels, str):
            labels = self._parse_labels(
                osp.join(osp.dirname(path),
                    labels or ImagenetTxtPath.LABELS_FILE))
        else:
            assert all(isinstance(e, str) for e in labels)
        self._categories = self._load_categories(labels)

        self._items = list(self._load_items(path).values())

    @staticmethod
    def _parse_labels(path):
        with open(path, encoding='utf-8') as labels_file:
            return [s.strip() for s in labels_file]

    def _load_categories(self, labels):
        return { AnnotationType.label: LabelCategories().from_iterable(labels) }

    def _load_items(self, path):
        items = {}

        with open(path, encoding='utf-8') as f:
            for line in f:
                item = line.split('\"')
                if 1 < len(item):
                    if len(item) == 3:
                        item_id = item[1]
                        item = item[2].split()
                        image = item_id + item[0]
                        label_ids = [int(id) for id in item[1:]]
                    else:
                        raise Exception("Line %s: unexpected number "
                            "of quotes in filename" % line)
                else:
                    item = line.split()
                    item_id = osp.splitext(item[0])[0]
                    image = item[0]
                    label_ids = [int(id) for id in item[1:]]

                anno = []
                for label in label_ids:
                    assert 0 <= label and \
                        label < len(self._categories[AnnotationType.label]), \
                        "Image '%s': unknown label id '%s'" % (item_id, label)
                    anno.append(Label(label))

                items[item_id] = DatasetItem(id=item_id, subset=self._subset,
                    image=osp.join(self.image_dir, image), annotations=anno)

        return items


class ImagenetTxtImporter(Importer, CliPlugin):
    @classmethod
    def build_cmdline_parser(cls, **kwargs):
        parser = super().build_cmdline_parser(**kwargs)
        parser.add_argument('--labels-file', dest='labels',
            help="Path to the file with label descriptions (synsets.txt)")
        return parser

    @classmethod
    def find_sources_with_params(cls, path, **extra_params):
        labels = extra_params.get('labels')
        labels_file_name = osp.basename(labels) \
            if isinstance(labels, str) else ImagenetTxtPath.LABELS_FILE

        return cls._find_sources_recursive(path, '.txt', 'imagenet_txt',
            file_filter=lambda p: \
                osp.basename(p) != labels_file_name)


class ImagenetTxtConverter(Converter):
    DEFAULT_IMAGE_EXT = '.jpg'

    def apply(self):
        subset_dir = self._save_dir
        os.makedirs(subset_dir, exist_ok=True)

        extractor = self._extractor
        for subset_name, subset in self._extractor.subsets().items():
            annotation_file = osp.join(subset_dir, '%s.txt' % subset_name)

            labels = {}
            for item in subset:
                item_id = item.id
                if 1 < len(item_id.split()):
                    item_id = '\"' + item_id + '\"'
                item_id += self._find_image_ext(item)
                labels[item_id] = set(p.label for p in item.annotations
                    if p.type == AnnotationType.label)

                if self._save_images and item.has_image:
                    self._save_image(item, subdir=ImagenetTxtPath.IMAGE_DIR)

            annotation = ''
            for item_id, item_labels in labels.items():
                annotation += '%s %s\n' % (item_id,
                    ' '.join(str(l) for l in item_labels))

            with open(annotation_file, 'w', encoding='utf-8') as f:
                f.write(annotation)

        labels_file = osp.join(subset_dir, ImagenetTxtPath.LABELS_FILE)
        with open(labels_file, 'w', encoding='utf-8') as f:
            f.writelines(l.name + '\n'
                for l in extractor.categories().get(
                    AnnotationType.label, LabelCategories())
            )
