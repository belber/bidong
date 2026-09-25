"""把存量「视频出处」CSV 初始化进数据库。

幂等：按 bvid 覆盖更新、空值不覆盖，所以可以反复执行。

用法（在 server/ 目录下）：
    .venv/bin/python -m scripts.import_sources            # 默认读 data/sources_seed.csv
    .venv/bin/python -m scripts.import_sources 某个.csv
"""

import sys
from pathlib import Path

from app.db import SessionLocal
from app.services import repost_source

DEFAULT_SEED = Path(__file__).resolve().parent.parent / "data" / "sources_seed.csv"


def import_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    db = SessionLocal()
    try:
        items = repost_source.parse_csv(text)
        return repost_source.upsert_items(db, items)
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT_SEED
    if not path.exists():
        print(f"找不到文件：{path}")
        return 1

    result = import_file(path)
    print(
        f"{path.name}：新增 {result['created']} / 更新 {result['updated']}"
        f" / 拒收 {len(result['rejected'])}"
    )
    for bad in result["rejected"][:10]:
        print(f"  拒收 {bad['bvid'] or '(空)'}：{bad['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
