import warnings
from pathlib import Path
from typing import Dict

from .fake_content import InvoiceContent
from .template import Template
from .web_renderer import WebRenderer
from .word_locator import WordLocator
from ..formats import load_image
from ..util import check_file, check_dir, print_if

warnings.filterwarnings("ignore")


def create_invoice(output_dir: Path, assets_dir: Path, template_file: Path, logo_file: Path, font_file: Path, dpi: int,
                   summary: Dict, verbose: bool = False):
    check_dir(output_dir)
    check_dir(assets_dir)
    check_file(template_file, suffix=".htm")
    check_file(logo_file, suffix=".png")
    check_file(font_file, suffix=".ttf")

    summary["template"] = template_file
    summary["logo"] = logo_file
    summary["font"] = font_file
    summary["dpi"] = dpi

    print_if(verbose, "Start invoice generation")

    template = Template(template_file=template_file, summary=summary)
    content = InvoiceContent(assets_dir=assets_dir, max_products=template.num_products,
                             shipping_tag=template.shipment_tag, discount_tag=template.discount_tag)
    template.fill_content(content=content)

    renderer = WebRenderer(output_dir=output_dir, template=template, logo_file=logo_file, font_file=font_file, dpi=dpi,
                           summary=summary)
    template_fields = renderer.render()

    content.export_ground_truth(output_dir=output_dir, template_fields=template_fields)

    height, width, _ = load_image(output_dir / "flat_document.png").shape
    locator = WordLocator(output_dir / "flat_document.pdf")
    locator.export_json(output_dir / "ground_truth_words.json", height=height, width=width)

    print_if(verbose, "Stop invoice generation")
