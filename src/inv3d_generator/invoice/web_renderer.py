import random
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Dict

from zipfile import BadZipfile
import numpy as np
from PIL import Image, UnidentifiedImageError
from pdf2image import convert_from_path

from .bbox import BoundingBox
from .rendering.pyhtml2pdf import convert
from .template import Template
from .util import map_colors
from ..util import check_file


class WebRenderer:
    WEB_DIR = Path(__file__).parent / "web"
    JQUERY_FILE = WEB_DIR / "jquery-3.6.0.min.js"

    def __init__(self, output_dir: Path, template: Template, logo_file: Path, font_file: Path, dpi: int, summary: Dict):
        self.output_dir = output_dir
        self.template = template
        self.logo_file = logo_file
        self.font_file = font_file
        self.dpi = dpi
        self.margin = random.randint(10, 20)
        summary["margin"] = self.margin

        with self.JQUERY_FILE.open("r") as jquery_js:
            self.jquery_script = jquery_js.read()

        assert self.template.color_mapping is not None

    def render(self) -> List[BoundingBox]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir = Path(tmp_dir)

            html_file = tmp_dir / "invoice.htm"
            self.template.save(html_file)

            self._prepare_image(html_file=html_file)

            document_image = self.output_dir / "flat_document.png"
            document_pdf = self.output_dir / "flat_document.pdf"
            self._render_a4_page(html_file, output_file=document_image, pdf_file=document_pdf)

            template_image = self.output_dir / "flat_template.png"
            self._render_a4_page(html_file, output_file=template_image,
                                 scripts=["$('.template_text').css('visibility', 'hidden');"])

            information_delta_image = self.output_dir / "flat_information_delta.png"
            self._render_a4_page(html_file, output_file=information_delta_image,
                                 scripts=["$('*').css('visibility', 'hidden');",
                                          "$('.template_text, .template_text *').css({'visibility': 'visible', 'color': 'black'});"])

            text_mask_image = self.output_dir / "flat_text_mask.png"
            self._render_a4_page(html_file, output_file=text_mask_image,
                                 scripts=[
                                     "$('*').css({'color': 'black', 'background-color': 'transparent', 'border-color': 'transparent', 'box-shadow': 'transparent'});",
                                     "$('img').css('visibility', 'hidden');"])

            # Note: replace images with blockers
            template_fields = self._extract_template_fields(html_file=html_file)

            return template_fields

    def _prepare_image(self, html_file: Path):
        if self.template.image_dir.is_dir():
            # copy supplementary data
            target_image_dir = html_file.parent / self.template.image_dir.name

            # copy supplementary files for web page rendering
            shutil.copytree(str(self.template.image_dir), str(target_image_dir))

            # check assumptions about the logo file
            [image_file] = list(self.template.image_dir.glob("image001.*"))

            logo = Image.open(str(self.logo_file))
            logo = logo.resize(Image.open(str(image_file)).size, Image.ANTIALIAS)
            logo.save(str(target_image_dir / image_file.name))

    def _render_a4_page(self, html_file: Path, output_file: Path, scripts: Optional[List[str]] = None,
                        pdf_file: Optional[Path] = None):
        def inner():
            nonlocal scripts
            nonlocal pdf_file

            if scripts is None:
                scripts = []

            if pdf_file is None:
                pdf_file = html_file.parent / output_file.with_suffix(".pdf").name

            check_file(html_file, suffix=[".htm", ".html"])
            check_file(output_file, suffix=".png", exist=False)
            check_file(pdf_file, suffix=".pdf", exist=False)

            base_scripts = [self.jquery_script,
                            "$('head').prepend(\"<style>@font-face {font-family: 'customFont';src: url('file:///" + str(
                                self.font_file.resolve()) + "');}</style>\");",
                            "$('*').css('font-family', 'customFont');"
                            "$('html').css('display', 'flex');",
                            "$('body').css({'margin': '0', 'width': '100%'});",
                            "$('table').css('width', '100%');",
                            "$('.template_text').css({'display': 'inline-block', 'vertical-align': 'top', 'white-space': 'nowrap'});"]

            script = ";".join(base_scripts + scripts)

            print_options = {
                "marginTop": self.margin / 25.4,
                "marginBottom": 5 / 25.4,  # set margin bottom to 5 mm -> keeps overflowing content on same page
                "marginLeft": self.margin / 25.4,
                "marginRight": self.margin / 25.4,
            }

            convert(f'file:///{html_file.resolve()}', str(pdf_file.resolve()), print_options=print_options, script=script)

            # convert pdf to image
            [image] = convert_from_path(str(pdf_file), last_page=1, dpi=self.dpi)
            image.save(str(output_file))

        for i in range(5):
            try:
                inner()
                return
            except (IndexError, BadZipfile):
                print("WARNING: Failed to render A4 page. Retrying!")
        raise ValueError("ERROR: Could not render A4 page")

    def _extract_template_fields(self, html_file: Path) -> List[BoundingBox]:
        # replaces images with blockers
        resource_folder = html_file.parent / self.template.image_dir.name
        for resource_file in resource_folder.rglob("*"):
            try:
                image = Image.open(str(resource_file))
                replacement = Image.new(image.mode, image.size, (0, 0, 0))
                replacement.save(str(resource_file))
            except UnidentifiedImageError:
                pass

        highlight_script = """
        var template_elements = document.querySelectorAll('.template_wrapper,.template_text,.template_blocker');

        for (var i = 0; i < template_elements.length; i++) {
            var color = template_elements[i].dataset.color;
            var element = template_elements[i];
    
            element.style.visibility = "visible";
            element.style.backgroundColor = color;
            element.style.borderColor = color;
            element.style.color = color;
        }
        
        var template_elements = document.querySelectorAll('.template_blocker');

        for (var i = 0; i < template_elements.length; i++) {
            var color = template_elements[i].dataset.color;
            var element = template_elements[i];
    
            element.style.visibility = "visible";
            element.style.backgroundColor = "rgba(0, 0, 0, 0)";
            element.style.borderColor = "rgba(0, 0, 0, 0)";
            element.style.color = color;
        }
        """

        # render image containing colored bounding boxes
        flat_template_structure_file = html_file.parent / "flat_template_structure.png"
        self._render_a4_page(html_file, output_file=flat_template_structure_file,
                             scripts=["$('*').css('visibility', 'hidden');",
                                      "$('img').css('visibility', 'visible');",
                                      highlight_script])

        # extract bounding boxes from image
        input_image = Image.open(str(flat_template_structure_file))
        forms_image = np.asanyarray(input_image)  # format: (height, width, rgb)

        color_mapping = self.template.color_mapping
        color_reduce_map = [(insertion_color, container_color)
                            for container_color, insertion_map in color_mapping.items()
                            for insertion_color in insertion_map.keys()]

        container_bboxes = BoundingBox.find_bounding_boxes(image=map_colors(forms_image, color_reduce_map),
                                                           valid_colors=list(color_mapping.keys()),
                                                           allow_disconnected=True)

        insertion_colors = [color for insertion_map in color_mapping.values() for color in insertion_map.keys()]
        insertion_names = [name for insertion_map in color_mapping.values() for name in insertion_map.values()]

        insertion_bboxes = BoundingBox.find_bounding_boxes(image=forms_image,
                                                           valid_colors=insertion_colors,
                                                           bbox_names=insertion_names)

        occlusion_mask = np.asanyarray(input_image.convert("HSV"))[:, :, -1] < 255

        final_bboxes = [bbox
                        for container_bbox in container_bboxes
                        for bbox in BoundingBox.expand_children(container_bbox, insertion_bboxes, occlusion_mask)]

        return final_bboxes
