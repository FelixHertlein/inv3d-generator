import json
from dataclasses import dataclass
from pathlib import Path
from typing import *

import cv2
import numpy as np
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBoxHorizontal, LTChar, LTFigure
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

from .bbox import BoundingBox
from ..util import check_file


@dataclass
class Word:
    text: str
    bbox: BoundingBox

    def to_json(self, height: int, width: int):
        bbox = self.bbox.scale(factor_x=width, factor_y=height)
        return {
            "text": self.text,
            "top": int(bbox.top),
            "left": int(bbox.left),
            "height": int(bbox.height),
            "width": int(bbox.width),
        }

    def draw(self, image: np.ndarray, color: Tuple = (52, 174, 235)):
        height, width, _ = image.shape
        color = tuple(reversed(color))

        # draw background
        sub_img = self.bbox.take_patch(image)
        color_rect = np.ones(sub_img.shape, dtype=np.uint8) * np.array(color).astype("uint8")
        self.bbox.put_patch(image, cv2.addWeighted(sub_img, 0.5, color_rect, 0.5, 1.0))

        # draw border
        cv2.rectangle(image, (int(self.bbox.x0), int(self.bbox.y0)), (int(self.bbox.x1), int(self.bbox.y1)), color, 1)

    @staticmethod
    def from_json(data: Dict):
        return Word(text=data["text"],
                    bbox=BoundingBox(top=data["top"], left=data["left"], height=data["height"], width=data["width"]))


class WordLocator:
    def __init__(self, input_file: Path):
        check_file(input_file, suffix=".pdf")

        self.words = []

        self._find_words(input_file=input_file)

    def _find_words(self, input_file: Path):
        with input_file.open('rb') as fp:
            parser = PDFParser(fp)
            document = PDFDocument(parser)

            assert document.is_extractable

            resource_manager = PDFResourceManager()
            device = PDFPageAggregator(resource_manager, laparams=LAParams())
            interpreter = PDFPageInterpreter(resource_manager, device)

            for page in PDFPage.create_pages(document):
                interpreter.process_page(page)
                layout = device.get_result()

                self.page_width = layout.x1
                self.page_height = layout.y1

                self._parse_objs(lt_objs=[obj for obj in layout])
                return  # gather first page only

    def _parse_objs(self, lt_objs):

        for obj in lt_objs:
            if isinstance(obj, LTFigure):
                self._parse_objs(lt_objs=[child for child in obj])

            elif isinstance(obj, LTTextBoxHorizontal):
                self._parse_text_box(text_box=obj)

    def _parse_text_box(self, text_box: LTTextBoxHorizontal):

        for text_line in text_box:
            word_chars = []
            for item in text_line:
                if isinstance(item, LTChar) and not item.get_text().isspace():
                    word_chars.append(item)
                else:
                    self._build_word(word_chars)
                    word_chars = []

    def _build_word(self, data: List[LTChar]):
        text = ''.join(char.get_text() for char in data)

        if len(text) == 0:
            return

        char_boxes = [BoundingBox.from_corners(x0=char.x0, y0=self.page_height - char.y1,
                                               x1=char.x1, y1=self.page_height - char.y0) for char in data]

        word_bbox = BoundingBox.union_all(char_boxes)
        word_bbox = BoundingBox(top=word_bbox.top / self.page_height,
                                left=word_bbox.left / self.page_width,
                                height=word_bbox.height / self.page_height,
                                width=word_bbox.width / self.page_width)

        self.words.append(Word(text=text, bbox=word_bbox))

    @staticmethod
    def visualize(json_file: Path, background_file: Path, output_file: Path):
        check_file(json_file, ".json")
        check_file(background_file, ".png")
        check_file(output_file, ".png", exist=None)

        with json_file.open("r") as f:
            words = [Word.from_json(data) for data in json.load(f)]

        image = cv2.imread(str(background_file), cv2.IMREAD_COLOR)

        for word in words:
            word.draw(image, color=(209, 0, 0))

        cv2.imwrite(str(output_file), image)

    def export_json(self, output_file: Path, height: int, width: int):
        check_file(output_file, ".json", exist=None)

        output = [word.to_json(height=height, width=width) for word in self.words]

        with output_file.open("w") as f:
            json.dump(output, f, indent=4)
