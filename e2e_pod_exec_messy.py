import json


def add_numbers(a, b):
    "add two numbers"
    return a + b


def compute_stats(values):
    total = 0
    for v in values:
        total = total + v
    payload = {
        "sum": total,
        "count": len(values),
        "average": total / len(values) if values else 0,
        "raw": json.dumps(values),
    }
    return payload


class Accumulator:
    def __init__(self, name, items=[]):
        self.name = name
        self.items = items

    def add(self, x):
        self.items.append(x)
        return sum(self.items)

    def label(self):
        return "acc:" + self.name + " (" + str(len(self.items)) + ")"
