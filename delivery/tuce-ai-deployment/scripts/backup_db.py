"""使用 SQLite 在线备份 API 生成一致快照；不打印线索或凭据。"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'data' / 'leads.db')
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
if not args.source.is_file():
    parser.error('源数据库不存在')
args.output_dir.mkdir(parents=True, exist_ok=True)
target = args.output_dir / ('leads-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
# 先用独占创建和仅拥有者可读写的权限创建文件。
import os
fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
with sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro', uri=True) as source:
    with sqlite3.connect(target) as dest:
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('备份完整性检查失败')
print('备份完成：', target)
