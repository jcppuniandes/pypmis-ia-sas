
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({
    "version": 1,
    "engine": "fake-ifc-converter",
    "products": [{
        "express_id": 20,
        "global_id": "0ZRuQHuvw8SOaxTest001",
        "ifc_class": "IfcBuildingElementProxy",
        "name": "Concrete Column",
        "mesh": {
            "vertices": [0, 0, 0, 1, 0, 0, 0, 1, 0],
            "indices": [0, 1, 2]
        }
    }]
}))
