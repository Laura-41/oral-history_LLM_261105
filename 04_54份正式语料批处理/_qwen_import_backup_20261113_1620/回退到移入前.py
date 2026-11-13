"""把 BATCH02-DOC09 / BATCH04-DOC09 恢复成「Qwen 结果移入前」的状态。

零删除：所有被替换下来的文件都移到本备份目录的 after_import/<文档>/ 下，
原始响应与 stage 响应（raw/ 子目录）保持不动。回退后重跑主链即可按原本
整篇 entity_time 方式继续。

用法（在工程任意位置执行均可）：
    python3 '04_54份正式语料批处理/_qwen_import_backup_20261113_1620/回退到移入前.py'
"""

from pathlib import Path
import shutil

BACKUP = Path(__file__).resolve().parent
ROOT = BACKUP.parents[1]
LAYER = ROOT / "04_54份正式语料批处理" / "document_consolidation" / "graph_layers" / "cuc_deepseek"
DOCS = ["BATCH02-DOC09", "BATCH04-DOC09"]

for doc in DOCS:
    dst = LAYER / doc
    before = BACKUP / doc
    after = BACKUP / "after_import" / doc
    after.mkdir(parents=True, exist_ok=True)

    if not dst.is_dir() or not before.is_dir():
        print(f"跳过 {doc}：目标或备份目录不存在")
        continue

    moved = []

    # 1. 移走搬入的 Qwen 响应（raw/ 目录里的其它文件一律保留）
    for f in sorted((dst / "raw").glob("*_FROM_QWEN.json")):
        shutil.move(str(f), str(after / f.name))
        moved.append(f"raw/{f.name}")

    # 2. 移走移入后产生的全部顶层文件（18 张 CSV + 4 份报告）
    for f in sorted(dst.iterdir()):
        if f.is_file():
            target = after / f.name
            if target.exists():
                target = after / f"dup_{f.name}"
            shutil.move(str(f), str(target))
            moved.append(f.name)

    # 3. 恢复原来的 10 张底座 CSV
    restored = []
    for f in sorted(before.glob("*.csv")):
        shutil.copy2(f, dst / f.name)
        restored.append(f.name)

    print(f"{doc}: 移走 {len(moved)} 个文件到 {after.relative_to(ROOT)}；恢复 {len(restored)} 张底座 CSV")

print("\n回退完成，零删除。原 24 张 import 表仍是移入后导出的，重跑一次主链会重新统一导出。")
print("继续跑真 DeepSeek：")
print("  cd '" + str(ROOT) + "'")
print("  caffeinate -i env TIMEOUT=1800 MODEL=cuc/deepseek SKIP_AFTER=2 bash scripts/graph_run_all_in_terminal.sh")
