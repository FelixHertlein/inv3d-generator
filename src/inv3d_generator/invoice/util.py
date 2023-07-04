import colorsys
import random
from typing import Tuple, List

import bs4
import numpy as np
from PIL import ImageColor


def color_range(num_colors: int):
    hsv_tuples = [(x / num_colors, 1, 1) for x in range(num_colors)]
    rgb_tuples = [colorsys.hsv_to_rgb(*x) for x in hsv_tuples]
    colors = [tuple(int(v * 255) for v in x) for x in rgb_tuples]
    assert len(set(colors)) == len(colors)
    return colors


def rgb_to_hex(rgb_color: Tuple):
    return '#{:02x}{:02x}{:02x}'.format(*rgb_color)


def change_hue_randomly(hex_rgb_color: str):
    color = ImageColor.getcolor(hex_rgb_color, "RGB")
    color = tuple(v / 255 for v in color)
    color = colorsys.rgb_to_hsv(*color)
    color = (random.random(), color[1], color[2])
    color = colorsys.hsv_to_rgb(*color)
    color = tuple(int(v * 255) for v in color)
    return rgb_to_hex(color)


def xpath_soup(element):
    """
    Generate xpath from BeautifulSoup4 element.
    :param element: BeautifulSoup4 element.
    :type element: bs4.element.Tag or bs4.element.NavigableString
    :return: xpath as string
    :rtype: str
    """
    components = []
    child = element if element.name else element.parent
    for parent in child.parents:  # type: bs4.element.Tag
        siblings = parent.find_all(child.name, recursive=False)
        components.append(
            child.name if 1 == len(siblings) else '%s[%d]' % (
                child.name,
                next(i for i, s in enumerate(siblings, 1) if s is child)
            )
        )
        child = parent
    components.reverse()
    return '/%s' % '/'.join(components)


def map_colors(image: np.ndarray, color_map: List[Tuple]):
    # image format: (height, width, rgb)
    # color_map: [rgb] -> [rgb]

    image = image.copy()

    # ensure correct type
    color_map = [(np.array(source, dtype=image.dtype), np.array(destination, dtype=image.dtype))
                 for source, destination in color_map]

    # only replace not equal colors
    color_map = [(source, destination)
                 for source, destination in color_map
                 if not np.array_equal(source, destination)]

    for source, destination in color_map:
        mask = np.all(image == source, axis=-1)
        image[mask, :] = destination

    return image
