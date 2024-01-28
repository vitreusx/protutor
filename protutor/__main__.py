import argparse
from pathlib import Path
import asyncio
import logging
from .engine import Engine


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lang", help="Language to use.")
    p.add_argument("infile", type=Path, help=".tex file to annotate.")
    p.add_argument("outfile", type=Path, help="Output file path.")

    args = p.parse_args()

    with open(args.infile, "r") as f:
        tex_code = f.read()

    engine = Engine(lang=args.lang)
    transformed = asyncio.run(engine.transform_tex_file(tex_code))

    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    with open(args.outfile, "w") as f:
        f.write(transformed)


if __name__ == "__main__":
    main()
