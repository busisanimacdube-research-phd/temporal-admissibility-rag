import glob, gzip, json, os


def load_nodes(folder):
    nodes = {}
    for p in sorted(glob.glob(os.path.join(folder, "*.json.gz"))):
        nodes.update(json.load(gzip.open(p))["nodes"])
    return nodes
