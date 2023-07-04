from collections.abc import Iterable as IterableClass
from itertools import groupby
from pathlib import Path
from typing import List, Tuple, Iterable, Union

import cv2
import numpy as np
from bounding_box import bounding_box as bb


class BoundingBox:

    def __init__(self, top: Union[int, float], left: Union[int, float], height: Union[int, float],
                 width: Union[int, float], name: str = None, color: Tuple = None):
        assert width >= 0
        assert height >= 0

        self.top = top
        self.left = left
        self.height = height
        self.width = width
        self.name = name
        self.color = color

    def __repr__(self):
        opt1 = "" if self.name is None else f"name={self.name}, "
        opt2 = "" if self.color is None else f"id={self.color}, "
        return f"BoundingBox({opt1}{opt2}top={self.top}, left={self.left}, height={self.height}, width={self.width})"

    @property
    def y0(self):
        return self.top

    @property
    def x0(self):
        return self.left

    @property
    def y1(self):
        return self.top + self.height

    @property
    def x1(self):
        return self.left + self.width

    def corners(self):
        return (self.y0, self.x0), (self.y1, self.x1)

    def contains_point(self, point: Tuple):
        return self.y0 <= point[0] <= self.y1 and self.x0 <= point[1] <= self.x1

    def contains(self, other: "BoundingBox"):
        return all(self.contains_point(point) for point in other.corners())

    def shrink(self, shrink_y: int, shrink_x: int):
        return BoundingBox(top=self.top + shrink_y,
                           left=self.left + shrink_x,
                           height=self.height - 2 * shrink_y,
                           width=self.width - 2 * shrink_x,
                           name=self.name,
                           color=self.color)

    def scale(self, factor_x: float, factor_y: float):
        return BoundingBox(top=self.top * factor_y,
                           left=self.left * factor_x,
                           height=self.height * factor_y,
                           width=self.width * factor_x,
                           name=self.name,
                           color=self.color)

    def inplace_expand(self, delta_top, delta_right, delta_bottom, delta_left):
        self.top -= delta_top
        self.left -= delta_left
        self.height += delta_top + delta_bottom
        self.width += delta_left + delta_right

    def constrain(self, parent: "BoundingBox"):
        new_bbox = BoundingBox.intersect(self, parent)
        new_bbox.name = self.name
        new_bbox.color = self.color
        return new_bbox

    def intersects(self, other: "BoundingBox"):
        def intersects1D(min1, max1, min2, max2):
            return max1 > min2 and max2 > min1

        return intersects1D(self.x0, self.x1, other.x0, other.x1) and intersects1D(self.y0, self.y1, other.y0, other.y1)

    def take_patch(self, image: np.ndarray):
        return image[int(self.y0):int(self.y1), int(self.x0):int(self.x1), ...]

    def put_patch(self, image: np.ndarray, patch: np.ndarray):
        image[int(self.y0):int(self.y1), int(self.x0):int(self.x1), ...] = patch

    @staticmethod
    def from_corners(y0: int, x0: int, y1: int, x1: int, name: str = None, color: Tuple = None):
        return BoundingBox(top=y0, left=x0, height=y1 - y0, width=x1 - x0, name=name, color=color)

    @staticmethod
    def from_points(points: Iterable[Union[Tuple, np.ndarray]], name: str = None, color: Tuple = None):
        # points: list of points. each point: (y, x)

        y_coordinates, x_coordinates = zip(*points)

        return BoundingBox.from_corners(y0=min(y_coordinates), x0=min(x_coordinates),
                                        y1=max(y_coordinates), x1=max(x_coordinates),
                                        name=name, color=color)

    @staticmethod
    def intersect(bbox1: "BoundingBox", bbox2: "BoundingBox"):
        return BoundingBox.from_corners(y0=max(bbox1.y0, bbox2.y0),
                                        x0=max(bbox1.x0, bbox2.x0),
                                        y1=min(bbox1.y1, bbox2.y1),
                                        x1=min(bbox1.x1, bbox2.x1),
                                        name=bbox1.name,
                                        color=bbox1.color)

    @staticmethod
    def union(bbox1: "BoundingBox", bbox2: "BoundingBox"):
        return BoundingBox.from_corners(y0=min(bbox1.y0, bbox2.y0),
                                        x0=min(bbox1.x0, bbox2.x0),
                                        y1=max(bbox1.y1, bbox2.y1),
                                        x1=max(bbox1.x1, bbox2.x1),
                                        name=bbox1.name,
                                        color=bbox1.color)

    @staticmethod
    def union_all(bboxes: List["BoundingBox"]):
        assert len(bboxes) > 0

        res = bboxes[0]
        for bbox in bboxes[1:]:
            res = BoundingBox.union(res, bbox)

        return res

    @staticmethod
    def visualize(bboxes: Iterable["BoundingBox"], input_file: Path, output_file: Path):
        assert input_file.is_file()
        assert input_file.suffix == ".png"
        assert output_file.parent.is_dir()
        assert output_file.suffix == ".png"

        image = cv2.imread(str(input_file), cv2.IMREAD_COLOR)

        for bbox in bboxes:
            if bbox.name is None:
                bb.add(image, bbox.x0, bbox.y0, bbox.x1, bbox.y1)
            else:
                bb.add(image, bbox.x0, bbox.y0, bbox.x1, bbox.y1, bbox.name)

        cv2.imwrite(str(output_file), image)

    @staticmethod
    def find_bounding_boxes(image: np.ndarray, valid_colors: List, bbox_names: List = None, allow_disconnected: bool = False):
        # image format: (height, width, rgb)
        assert len(image.shape) == 3

        def format_color(c):
            return tuple(c) if isinstance(c, IterableClass) else tuple([c])

        # prepare name map
        if bbox_names is None:
            name_map = {format_color(color): None for color in valid_colors}
        else:
            assert len(valid_colors) == len(bbox_names)
            name_map = {format_color(color): name for color, name in zip(valid_colors, bbox_names)}

        horizontal_lines = ~np.all(image[:-1, :-1] == image[1:, :-1], axis=-1)  # compare shifted images
        vertical_lines = ~np.all(image[:-1, :-1] == image[:-1, 1:], axis=-1)  # compare shifted images

        edges_bottom_right = horizontal_lines & vertical_lines
        edges_top_left = np.roll(horizontal_lines, 1, 0) & np.roll(vertical_lines, 1,
                                                                   1)  # lines are too short -> roll to create intersections

        edge_coords = np.where(edges_bottom_right | edges_top_left)  # gather all edge coordinates

        def color_at(coords):
            return tuple(image[coords[0], coords[1]])

        bboxes = list()
        for color, corner_points in groupby(sorted(zip(*edge_coords), key=color_at), key=color_at):
            if color not in name_map:
                continue

            corner_points = list(corner_points)

            if len(corner_points) < 2:
                continue

            if len(corner_points) == 2 or allow_disconnected:
                bboxes.append(BoundingBox.from_points(corner_points, name=name_map[color], color=color))
                continue

            # handle special case with more than two edge points

            # find connected components with target color
            mask = np.all(image == color, axis=-1)
            num_labels, labels_im = cv2.connectedComponents(mask.astype("uint8"))

            # calculate the area per connected component and select biggest
            areas = [(np.count_nonzero(labels_im == label), label) for label in range(1, num_labels)]
            areas = sorted(areas, reverse=True)

            # create a cleaned image containing only the largest component
            cleaned_image = labels_im == areas[0][1]

            # filter corner points to match largest component only
            corner_points = [corner_point
                             for corner_point in corner_points
                             if cleaned_image[corner_point[0]][corner_point[1]]]

            # create and add bounding box
            bboxes.append(BoundingBox.from_points(corner_points, name=name_map[color], color=color))

        return bboxes

    @staticmethod
    def expand_children(parent_bbox: "BoundingBox", child_bboxes: List["BoundingBox"], occlusion_mask: np.ndarray):
        assert len(occlusion_mask.shape) == 2
        assert str(occlusion_mask.dtype) == "bool"

        # filter bboxes for relevance
        child_bboxes = [bbox.constrain(parent_bbox) for bbox in child_bboxes if parent_bbox.intersects(bbox)]

        if len(child_bboxes) == 0:
            return []

        if len(child_bboxes) == 1 and not parent_bbox.take_patch(occlusion_mask).any():
            return [BoundingBox(top=parent_bbox.top, left=parent_bbox.left, height=parent_bbox.height,
                                width=parent_bbox.width, name=child_bboxes[0].name)]

        shrink_y = max(min(child_bbox.height for child_bbox in child_bboxes) // 2 - 1, 0)
        shrink_x = max(min(child_bbox.width for child_bbox in child_bboxes) // 2 - 1, 0)
        grow_bboxes = [child_bbox.shrink(shrink_y, shrink_x) for child_bbox in child_bboxes]

        def is_valid(bbox):
            if not parent_bbox.contains(bbox):
                return False

            if any([bbox.intersects(other) for other in grow_bboxes if grow_bbox != other]):
                return False

            return not bbox.take_patch(occlusion_mask).any()

        def expand_and_check(bbox, delta_top, delta_right, delta_bottom, delta_left):
            bbox.inplace_expand(delta_top, delta_right, delta_bottom, delta_left)
            if is_valid(bbox):
                return True
            bbox.inplace_expand(-delta_top, -delta_right, -delta_bottom, -delta_left)

        changed = True
        while changed:
            changed = False
            for grow_bbox in grow_bboxes:
                changed = expand_and_check(grow_bbox, 0, 0, 0, 1) or changed
                changed = expand_and_check(grow_bbox, 0, 1, 0, 0) or changed

        changed = True
        while changed:
            changed = False
            for grow_bbox in grow_bboxes:
                changed = expand_and_check(grow_bbox, 1, 0, 0, 0) or changed
                changed = expand_and_check(grow_bbox, 0, 0, 1, 0) or changed

        final_bboxes = [BoundingBox.union(child_bbox, grow_bbox)
                        for child_bbox, grow_bbox in zip(child_bboxes, grow_bboxes)]

        return final_bboxes
