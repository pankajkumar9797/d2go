#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

import copy
import json
import os
import unittest

import d2go.data.extended_coco as extended_coco
from d2go.data.keypoint_metadata_registry import (
    KEYPOINT_METADATA_REGISTRY,
    KeypointMetadata,
    get_keypoint_metadata,
)
from d2go.data.utils import (
    maybe_subsample_n_images,
    AdhocDatasetManager,
    COCOWithClassesToUse,
)
from d2go.runner import Detectron2GoRunner
from d2go.utils.testing.data_loader_helper import (
    LocalImageGenerator,
    create_toy_dataset,
)
from d2go.utils.testing.helper import tempdir
from detectron2.data import DatasetCatalog, MetadataCatalog
from mobile_cv.common.misc.file_utils import make_temp_directory


def create_test_images_and_dataset_json(data_dir, num_images=10, num_classes=-1):
    # create image and json
    image_dir = os.path.join(data_dir, "images")
    os.makedirs(image_dir)
    json_dataset, meta_data = create_toy_dataset(
        LocalImageGenerator(image_dir, width=80, height=60),
        num_images=num_images,
        num_classes=num_classes,
    )
    json_file = os.path.join(data_dir, "{}.json".format("inj_ds1"))
    with open(json_file, "w") as f:
        json.dump(json_dataset, f)

    return image_dir, json_file


class TestD2GoDatasets(unittest.TestCase):
    def test_coco_conversions(self):
        test_data_0 = {
            "info": {},
            "imgs": {
                "img_1": {
                    "file_name": "0.jpg",
                    "width": 600,
                    "height": 600,
                    "id": "img_1",
                }
            },
            "anns": {0: {"id": 0, "image_id": "img_1", "bbox": [30, 30, 60, 20]}},
            "imgToAnns": {"img_1": [0]},
            "cats": {},
        }
        test_data_1 = copy.deepcopy(test_data_0)
        test_data_1["imgs"][123] = test_data_1["imgs"].pop("img_1")
        test_data_1["imgs"][123]["id"] = 123
        test_data_1["anns"][0]["image_id"] = 123
        test_data_1["imgToAnns"][123] = test_data_1["imgToAnns"].pop("img_1")

        for test_data, exp_output in [(test_data_0, [0, 0]), (test_data_1, [123, 123])]:
            with make_temp_directory("detectron2go_tmp_dataset") as tmp_dir:
                src_json = os.path.join(tmp_dir, "source.json")
                out_json = os.path.join(tmp_dir, "output.json")

                with open(src_json, "w") as h_in:
                    json.dump(test_data, h_in)

                out_json = extended_coco.convert_coco_text_to_coco_detection_json(
                    src_json, out_json
                )

                self.assertEqual(out_json["images"][0]["id"], exp_output[0])
                self.assertEqual(out_json["annotations"][0]["image_id"], exp_output[1])

    def test_annotation_rejection(self):
        img_list = [
            {"id": 0, "width": 50, "height": 50, "file_name": "a.png"},
            {"id": 1, "width": 50, "height": 50, "file_name": "b.png"},
        ]
        ann_list = [
            [
                {
                    "id": 0,
                    "image_id": 0,
                    "category_id": 0,
                    "segmentation": [[0, 0, 10, 0, 10, 10, 0, 10]],
                    "area": 100,
                    "bbox": [0, 0, 10, 10],
                },
                {
                    "id": 1,
                    "image_id": 0,
                    "category_id": 0,
                    "segmentation": [[0, 0, 10, 0, 10, 10, 0, 10]],
                    "area": 100,
                    "bbox": [45, 45, 10, 10],
                },
                {
                    "id": 2,
                    "image_id": 0,
                    "category_id": 0,
                    "segmentation": [[0, 0, 10, 0, 10, 10, 0, 10]],
                    "area": 100,
                    "bbox": [-5, -5, 10, 10],
                },
                {
                    "id": 3,
                    "image_id": 0,
                    "category_id": 0,
                    "segmentation": [[0, 0, 10, 0, 10, 10, 0, 10]],
                    "area": 0,
                    "bbox": [5, 5, 0, 0],
                },
                {
                    "id": 4,
                    "image_id": 0,
                    "category_id": 0,
                    "segmentation": [[]],
                    "area": 25,
                    "bbox": [5, 5, 5, 5],
                },
            ],
            [
                {
                    "id": 5,
                    "image_id": 1,
                    "category_id": 0,
                    "segmentation": [[]],
                    "area": 100,
                    "bbox": [0, 0, 0, 0],
                },
            ],
        ]

        out_dict_list = extended_coco.convert_to_dict_list(
            "",
            [0],
            img_list,
            ann_list,
        )
        self.assertEqual(len(out_dict_list), 1)

    @tempdir
    def test_coco_injection(self, tmp_dir):
        image_dir, json_file = create_test_images_and_dataset_json(tmp_dir)

        runner = Detectron2GoRunner()
        cfg = runner.get_default_cfg()
        cfg.merge_from_list(
            [
                str(x)
                for x in [
                    "D2GO_DATA.DATASETS.COCO_INJECTION.NAMES",
                    ["inj_ds1", "inj_ds2"],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.IM_DIRS",
                    [image_dir, "/mnt/fair"],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.JSON_FILES",
                    [json_file, "inj_ds2"],
                ]
            ]
        )

        runner.register(cfg)
        inj_ds1 = DatasetCatalog.get("inj_ds1")
        self.assertEqual(len(inj_ds1), 10)
        for dic in inj_ds1:
            self.assertEqual(dic["width"], 80)
            self.assertEqual(dic["height"], 60)

    @tempdir
    def test_sub_dataset(self, tmp_dir):
        image_dir, json_file = create_test_images_and_dataset_json(tmp_dir)

        runner = Detectron2GoRunner()
        cfg = runner.get_default_cfg()
        cfg.merge_from_list(
            [
                str(x)
                for x in [
                    "D2GO_DATA.DATASETS.COCO_INJECTION.NAMES",
                    ["inj_ds3"],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.IM_DIRS",
                    [image_dir],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.JSON_FILES",
                    [json_file],
                    "DATASETS.TEST",
                    ("inj_ds3",),
                    "D2GO_DATA.TEST.MAX_IMAGES",
                    1,
                ]
            ]
        )

        runner.register(cfg)
        with maybe_subsample_n_images(cfg) as new_cfg:
            test_loader = runner.build_detection_test_loader(
                new_cfg, new_cfg.DATASETS.TEST[0]
            )
            self.assertEqual(len(test_loader), 1)

    def test_coco_metadata_registry(self):
        @KEYPOINT_METADATA_REGISTRY.register()
        def TriangleMetadata():
            return KeypointMetadata(
                names=("A", "B", "C"),
                flip_map=(
                    ("A", "B"),
                    ("B", "C"),
                ),
                connection_rules=[
                    ("A", "B", (102, 204, 255)),
                    ("B", "C", (51, 153, 255)),
                ],
            )

        tri_md = get_keypoint_metadata("TriangleMetadata")
        self.assertEqual(tri_md["keypoint_names"][0], "A")
        self.assertEqual(tri_md["keypoint_flip_map"][0][0], "A")
        self.assertEqual(tri_md["keypoint_connection_rules"][0][0], "A")

    @tempdir
    def test_coco_metadata_register(self, tmp_dir):
        @KEYPOINT_METADATA_REGISTRY.register()
        def LineMetadata():
            return KeypointMetadata(
                names=("A", "B"),
                flip_map=(("A", "B"),),
                connection_rules=[
                    ("A", "B", (102, 204, 255)),
                ],
            )

        image_dir, json_file = create_test_images_and_dataset_json(tmp_dir)

        runner = Detectron2GoRunner()
        cfg = runner.get_default_cfg()
        cfg.merge_from_list(
            [
                str(x)
                for x in [
                    "D2GO_DATA.DATASETS.COCO_INJECTION.NAMES",
                    ["inj_ds"],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.IM_DIRS",
                    [image_dir],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.JSON_FILES",
                    [json_file],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.KEYPOINT_METADATA",
                    ["LineMetadata"],
                ]
            ]
        )
        runner.register(cfg)
        inj_md = MetadataCatalog.get("inj_ds")
        self.assertEqual(inj_md.keypoint_names[0], "A")
        self.assertEqual(inj_md.keypoint_flip_map[0][0], "A")
        self.assertEqual(inj_md.keypoint_connection_rules[0][0], "A")

    @tempdir
    def test_coco_create_adhoc_class_to_use_dataset(self, tmp_dir):

        image_dir, json_file = create_test_images_and_dataset_json(
            tmp_dir, num_classes=2
        )

        runner = Detectron2GoRunner()
        cfg = runner.get_default_cfg()
        cfg.merge_from_list(
            [
                str(x)
                for x in [
                    "D2GO_DATA.DATASETS.COCO_INJECTION.NAMES",
                    ["test_adhoc_ds", "test_adhoc_ds2"],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.IM_DIRS",
                    [image_dir, image_dir],
                    "D2GO_DATA.DATASETS.COCO_INJECTION.JSON_FILES",
                    [json_file, json_file],
                ]
            ]
        )
        runner.register(cfg)

        # Test adhoc classes to use
        AdhocDatasetManager.add(COCOWithClassesToUse("test_adhoc_ds", ["class_0"]))
        ds_list = DatasetCatalog.get("test_adhoc_ds@1classes")
        self.assertEqual(len(ds_list), 5)

        # Test adhoc classes to use with suffix removal
        AdhocDatasetManager.add(COCOWithClassesToUse("test_adhoc_ds2@1classes", ["class_0"]))
        ds_list = DatasetCatalog.get("test_adhoc_ds2@1classes")
        self.assertEqual(len(ds_list), 5)
