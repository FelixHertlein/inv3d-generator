import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any

import bs4

from .fake_content import InvoiceContent
from .util import change_hue_randomly, xpath_soup, rgb_to_hex, color_range
from ..util import check_file


class Template:
    COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")
    FONT_SIZE_PATTERN = re.compile(r"font-size:\s*(?P<size>[0-9.]+)pt")
    ATTRIBUTE_PATTERN = re.compile(r"{{\s*(?P<attribute>[a-zA-Z0-9_.]+)\s*}}")

    class Container:
        def __init__(self, value: bs4.NavigableString):
            self.value = value
            self._xpath = xpath_soup(value)

        def __repr__(self):
            return f"Container({xpath_soup(self.value)})"

        def __eq__(self, other: Any):
            return hash(self) == hash(other)

        def __hash__(self) -> int:
            return hash(self._xpath)

    def __init__(self, template_file: Path, summary: Dict):
        template = template_file.read_text()
        template = Template._replace_colors_randomly(template=template, summary=summary)
        template = Template._replace_font_size_randomly(template=template, summary=summary)

        self.soup = bs4.BeautifulSoup(template, 'html.parser')

        self.container_map = self._create_container_map()
        self.attributes = [attribute
                           for insertion_list in self.container_map.values()
                           for insertion in insertion_list
                           for attribute in re.findall(self.ATTRIBUTE_PATTERN, str(insertion))]

        self.num_products = max([int(subtag)
                                 for attribute in self.attributes if attribute.startswith("products.")
                                 for subtag in attribute.split(".") if subtag.isdigit()]) + 1

        self.color_mapping = None
        self.template_file = template_file

    @property
    def shipment_tag(self) -> bool:
        return "summary.shipping.price" in self.attributes

    @property
    def discount_tag(self):
        return "summary.discount" in self.attributes

    @property
    def image_dir(self):
        return self.template_file.parent / (self.template_file.stem + "_files")

    @classmethod
    def _replace_colors_randomly(cls, template: str, summary: Dict) -> str:
        color_map = {}

        def replace(match):
            color = match.group(0)

            if color not in color_map:
                color_map[color] = change_hue_randomly(match.group(0))
            return color_map[color]

        result = re.sub(pattern=cls.COLOR_PATTERN, repl=replace, string=template)
        summary["color_map"] = color_map
        return result

    @classmethod
    def _replace_font_size_randomly(cls, template: str, summary: Dict) -> str:
        factor = random.uniform(0.8, 1.2)
        summary["font_scale"] = factor

        def replace(match):
            pt_size = float(match.groupdict()["size"])
            pt_size *= factor
            return f"font-size:{str(pt_size)}pt"

        return re.sub(pattern=cls.FONT_SIZE_PATTERN, repl=replace, string=template)

    def _create_container_map(self) -> Dict["Container", List[bs4.NavigableString]]:
        container_map = defaultdict(list)
        for insertion in self.soup.find_all(text=self.ATTRIBUTE_PATTERN):
            container = insertion.find_parent('td')
            if container is None:
                container = insertion.find_parent('p')  # fallback container
            if container is None:
                container = insertion.parent
                print(f"INFO: Insertion '{insertion}' outside of td or p element! Direct parent will be used!")

            container_map[self.Container(container)].append(insertion)
        return container_map

    def fill_content(self, content: InvoiceContent):
        assert self.color_mapping is None, "Template was already filled!"

        # prepare replacement
        all_colors = color_range(num_colors=len(self.attributes) + len(self.container_map))
        color_mapping = color_mapping = defaultdict(dict)

        # function to add colors to container elements
        def process_container(element):
            color = all_colors.pop()
            element["data-color"] = rgb_to_hex(color)
            element['class'] = element.get('class', []) + ['template_wrapper']
            return color

        # function to replace attribute placeholders and adds color information
        def process_insertion(element, parent_color):
            def replace(match):
                attribute = match.groupdict()["attribute"]
                if attribute not in content.all_attributes:
                    print(f"WARNING: No correspondence of attribute '{attribute}' in generated data!")
                value = content.all_attributes[attribute] if attribute in content.all_attributes else "&nbsp;"
                value = "&nbsp;" if value is None else value
                assert isinstance(value, str)
                value = value.replace("\n", "<br>")

                color = all_colors.pop()
                color_mapping[parent_color][color] = attribute
                return f"<span class='template_text' data-color='{rgb_to_hex(color)}'>{value}</span>"

            filled_element_str = re.sub(pattern=self.ATTRIBUTE_PATTERN, repl=replace, string=str(element))
            element.replaceWith(bs4.BeautifulSoup(filled_element_str, 'html.parser'))

        for container, insertions in self.container_map.items():
            container_color = process_container(container.value)
            for insertion in insertions:
                process_insertion(insertion, container_color)

        # add exclusion tag to spans
        for container in self.container_map:
            for span in container.value.find_all('span'):
                if span.text.strip() != '' and 'template_text' not in span.get('class', []):
                    span["data-color"] = '#000000'
                    span['class'] = span.get('class', []) + ['template_blocker']

        self.color_mapping = color_mapping

    def save(self, file: Path):
        check_file(file, suffix=".htm", exist=False)
        file.write_text(self.soup.prettify(formatter="html"))
