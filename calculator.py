#!/usr/bin/env python3
"""Simple command-line string concatenation program."""

from __future__ import annotations


def add_strings(first: str, second: str) -> str:
    """Return two strings concatenated together."""
    return first + second


def main() -> None:
    print("V.O.I.D.E. String Addition")
    print("Type 'exit' or 'quit' to close.\n")

    while True:
        try:
            first = input("First string: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if first.lower() in {"exit", "quit"}:
            break

        try:
            second = input("Second string: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if second.lower() in {"exit", "quit"}:
            break

        print(f"Result: {add_strings(first, second)}\n")


if __name__ == "__main__":
    main()
