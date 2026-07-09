import math


def add_numbers(x, y):
    """Add two numbers and return the result."""
    return x + y


def factorial(n):
    """Return n factorial."""
    result = 1
    for i in range(1, n + 1):
        result = result * i
    return result


DEFAULT_PI = math.pi
