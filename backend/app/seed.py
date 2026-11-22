import json
from datetime import datetime, timezone

from app.db import 夹具目录, 连接

建表 = """
CREATE TABLE IF NOT EXISTS 错挂隔离名册 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  批号 TEXT NOT NULL,
  卫星类 TEXT NOT NULL DEFAULT '',
  卫星键 TEXT NOT NULL DEFAULT '',
  错误父哈希 TEXT NOT NULL DEFAULT '',
  期望父类 TEXT NOT NULL DEFAULT '',
  原因码 TEXT NOT NULL DEFAULT '',
  处置 TEXT NOT NULL DEFAULT '',
  时刻 TEXT NOT NULL DEFAULT '',
  解除时刻 TEXT NOT NULL DEFAULT '',
  解除说明 TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS 站规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  装载日 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 枢纽_号卡 (
  哈希键 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL UNIQUE,
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 枢纽_套餐 (
  哈希键 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL UNIQUE,
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 枢纽_客户 (
  哈希键 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL UNIQUE,
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 链接_号卡套餐 (
  哈希键 TEXT PRIMARY KEY,
  号卡哈希 TEXT NOT NULL REFERENCES 枢纽_号卡(哈希键),
  套餐哈希 TEXT NOT NULL REFERENCES 枢纽_套餐(哈希键),
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 链接_号卡客户 (
  哈希键 TEXT PRIMARY KEY,
  号卡哈希 TEXT NOT NULL REFERENCES 枢纽_号卡(哈希键),
  客户哈希 TEXT NOT NULL REFERENCES 枢纽_客户(哈希键),
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 卫星_号卡属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  号卡哈希 TEXT NOT NULL REFERENCES 枢纽_号卡(哈希键),
  卫星键 TEXT NOT NULL DEFAULT '',
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 卫星_套餐属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  套餐哈希 TEXT NOT NULL REFERENCES 枢纽_套餐(哈希键),
  卫星键 TEXT NOT NULL DEFAULT '',
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 卫星_客户属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  客户哈希 TEXT NOT NULL REFERENCES 枢纽_客户(哈希键),
  卫星键 TEXT NOT NULL DEFAULT '',
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 卫星_订购属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  链接哈希 TEXT NOT NULL REFERENCES 链接_号卡套餐(哈希键),
  卫星键 TEXT NOT NULL DEFAULT '',
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 隔离匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  原因 TEXT NOT NULL,
  载荷 TEXT NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 挂错父证据 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  批次编号 TEXT NOT NULL,
  装载日 TEXT NOT NULL,
  卫星类 TEXT NOT NULL,
  卫星键 TEXT NOT NULL DEFAULT '',
  父哈希 TEXT NOT NULL,
  期望父类 TEXT NOT NULL,
  实际父类 TEXT,
  原因 TEXT NOT NULL,
  原因码 TEXT NOT NULL DEFAULT '',
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 金库贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  枢纽数 INTEGER NOT NULL,
  链接数 INTEGER NOT NULL,
  卫星当前数 INTEGER NOT NULL,
  是否通过 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
"""

# 旧库补列（CREATE TABLE IF NOT EXISTS 不会给既有表加列）
补列表 = {
    "错挂隔离名册": (
        ("卫星类", "TEXT NOT NULL DEFAULT ''"),
        ("解除时刻", "TEXT NOT NULL DEFAULT ''"),
        ("解除说明", "TEXT NOT NULL DEFAULT ''"),
    ),
    "挂错父证据": (
        ("卫星键", "TEXT NOT NULL DEFAULT ''"),
        ("原因码", "TEXT NOT NULL DEFAULT ''"),
    ),
    "卫星_号卡属性": (("卫星键", "TEXT NOT NULL DEFAULT ''"),),
    "卫星_套餐属性": (("卫星键", "TEXT NOT NULL DEFAULT ''"),),
    "卫星_客户属性": (("卫星键", "TEXT NOT NULL DEFAULT ''"),),
    "卫星_订购属性": (("卫星键", "TEXT NOT NULL DEFAULT ''"),),
}

初始索引 = """
CREATE INDEX IF NOT EXISTS idx_名册_卫星 ON 错挂隔离名册(卫星类, 卫星键, 处置);
CREATE INDEX IF NOT EXISTS idx_名册_父 ON 错挂隔离名册(卫星类, 错误父哈希, 处置);
CREATE INDEX IF NOT EXISTS idx_证据_卫星 ON 挂错父证据(批次编号, 卫星类, 卫星键);
CREATE INDEX IF NOT EXISTS idx_卫星_号卡_键 ON 卫星_号卡属性(卫星键, 是否当前);
CREATE INDEX IF NOT EXISTS idx_卫星_套餐_键 ON 卫星_套餐属性(卫星键, 是否当前);
CREATE INDEX IF NOT EXISTS idx_卫星_客户_键 ON 卫星_客户属性(卫星键, 是否当前);
CREATE INDEX IF NOT EXISTS idx_卫星_订购_键 ON 卫星_订购属性(卫星键, 是否当前);
"""


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 哈希键(*parts: str) -> str:
    import hashlib

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def 载荷哈希(obj) -> str:
    import hashlib

    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _列集(conn, 表: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({表})")}


def _补列(conn) -> None:
    for 表, 列s in 补列表.items():
        try:
            已有 = _列集(conn, 表)
        except Exception:
            continue
        for 列, 定义 in 列s:
            if 列 not in 已有:
                conn.execute(f"ALTER TABLE {表} ADD COLUMN {列} {定义}")


def 初始化库() -> None:
    conn = 连接()
    try:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        conn.executescript(建表)
        _补列(conn)
        conn.executescript(初始索引)
        if conn.execute("SELECT COUNT(*) AS c FROM 站规").fetchone()["c"] == 0:
            for k, v in {"站名": "号枢", "默认装载日": "2026-11-21"}.items():
                conn.execute("INSERT INTO 站规(键, 值) VALUES (?, ?)", (k, v))
        conn.commit()
    finally:
        conn.close()
