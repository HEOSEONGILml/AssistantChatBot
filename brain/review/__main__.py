"""검수 하네스 실행 (brain/에서):
  uv run python -m review run 이름 [이름...]   # scenarios/이름.json 실행
  uv run python -m review run --all            # 모든 시나리오(probe-* 포함)
  uv run python -m review coverage             # out/*.jsonl 전체로 커버리지만 다시 계산
  --fake: 가짜 Jev·Gemini (하네스 시험용, 판정에 쓰지 않는다)
결과: review/out/<이름>.jsonl, <이름>.analysis.md, coverage.md"""
import argparse
import asyncio
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

from .analysis import analyze, coverage
from .harness import run_scenario

HERE = Path(__file__).resolve().parent
SCENARIOS, OUT = HERE / "scenarios", HERE / "out"


def load_runs() -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(OUT.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            runs[f"{f.stem}/{r.pop('run')}"].append(r)
    return runs


def write_coverage() -> list[str]:
    table, missing = coverage(load_runs())
    (OUT / "coverage.md").write_text(table + "\n", encoding="utf-8")
    return missing


async def run(names: list[str], fake: bool) -> None:
    for name in names:
        sc = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))
        sc.setdefault("name", name)
        started = time.monotonic()
        runs = await run_scenario(sc, fake=fake, out_dir=OUT)
        (OUT / f"{name}.analysis.md").write_text(analyze(name, runs) + "\n", encoding="utf-8")
        calls = [next(r for r in recs if r["type"] == "end")["calls"] for recs in runs.values()]
        print(f"{name}: {time.monotonic() - started:.0f}초, 호출 {calls}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("names", nargs="*")
    r.add_argument("--all", action="store_true")
    r.add_argument("--fake", action="store_true")
    sub.add_parser("coverage")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    OUT.mkdir(exist_ok=True)
    if a.cmd == "run":
        names = sorted(p.stem for p in SCENARIOS.glob("*.json")) if a.all else a.names
        asyncio.run(run(names, a.fake))
    missing = write_coverage()
    print(f"커버리지 필수 빈 칸 {len(missing)}개" + (": " + ", ".join(missing) if missing else ""))


if __name__ == "__main__":
    main()
