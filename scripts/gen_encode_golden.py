"""Write the encoder golden the browser encoder is tested against.

    python scripts/gen_encode_golden.py [--out receipts/web-v1/encode_golden.json]

The file depends only on chesslab/encode.py, chesslab/webref.py and
python-chess, not on any model. tests/test_web_golden.py regenerates it in
memory and compares bytes; web/test/encode.test.ts checks the TypeScript
encoder against it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chesslab import webref  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "receipts" / "web-v1" / "encode_golden.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    golden = webref.build_golden()
    args.out.write_text(webref.golden_text(golden), encoding="utf-8", newline="\n")
    print(f"{args.out}: {len(golden['cases'])} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
