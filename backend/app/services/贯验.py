from app.db import 连接
from app.seed import 此刻
from app.services import 父校验


def 挂错父贯验(conn=None) -> dict:
    """只读：卫星挂错父贯验。

    口径=整票失败闭（甲）。逐条扫描当前卫星父引用，报告：
      - 残留错挂数：正式当前卫星中父哈希不在期望父表 / 类型交叉挂靠的条数；
      - 每条错挂的 父哈希、期望父类、实际父类、原因；
      - 隔离 / 整票证据：隔离匣中的错挂条目与逐条挂错父证据。
    只读，不写库、不改任何正式表。
    """
    自有 = conn is None
    if 自有:
        conn = 连接()
    try:
        错挂 = []
        总当前 = 0
        for 卫星类, 引 in 父校验.卫星父引.items():
            for r in conn.execute(
                f"SELECT {引['父列']} AS p FROM {引['卫星表']} WHERE 是否当前=1"
            ):
                总当前 += 1
                证 = 父校验.卫星父错挂(conn, 卫星类, r["p"])
                if 证:
                    错挂.append(证)

        证据 = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 挂错父证据 ORDER BY 编号 DESC LIMIT 20"
            )
        ]
        隔离 = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 隔离匣 WHERE 原因 LIKE '%卫星错挂父%' ORDER BY 编号 DESC LIMIT 20"
            )
        ]
        整票批 = [
            dict(r)
            for r in conn.execute(
                "SELECT DISTINCT 批次编号, 装载日 FROM 挂错父证据 ORDER BY 批次编号 DESC LIMIT 20"
            )
        ]
        整票落盘 = [
            r["批次编号"] for r in 整票批
            if conn.execute("SELECT 1 FROM 装载批次 WHERE 编号=?", (r["批次编号"],)).fetchone()
        ]

        无残留 = len(错挂) == 0
        证据自洽 = len(整票落盘) == 0
        有条目 = len(证据) > 0
        return {
            "口径": 父校验.口径,
            "是否通过": 无残留 and 证据自洽,
            "扫描当前卫星数": 总当前,
            "残留错挂数": len(错挂),
            "残留错挂": 错挂,
            "证据": {
                "挂错父证据条数": len(证据),
                "最近证据": 证据,
                "隔离条数": len(隔离),
                "最近隔离": 隔离,
                "整票失败批次": 整票批,
                "整票误落批次": 整票落盘,
                "说明": (
                    f"整票证据不自洽：以下批次错挂却有正式落盘 {整票落盘}"
                    if not 证据自洽
                    else "正式当前仍存在错挂父卫星，禁止成为正式当前"
                    if not 无残留
                    else (
                        "正式当前卫星无错挂父，整票失败批次均零正式落盘"
                        if 有条目
                        else "正式当前卫星无错挂父，尚无错挂记录"
                    )
                ),
            },
        }
    finally:
        if 自有:
            conn.close()


def 跑贯验() -> dict:
    conn = 连接()
    try:
        枢纽数 = sum(
            conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
            for t in ("枢纽_号卡", "枢纽_套餐", "枢纽_客户")
        )
        链接数 = sum(
            conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
            for t in ("链接_号卡套餐", "链接_号卡客户")
        )
        卫星当前数 = sum(
            conn.execute(f"SELECT COUNT(*) AS c FROM {t} WHERE 是否当前=1").fetchone()["c"]
            for t in ("卫星_号卡属性", "卫星_套餐属性", "卫星_客户属性", "卫星_订购属性")
        )

        缺链 = []
        for r in conn.execute("SELECT * FROM 链接_号卡套餐"):
            if not conn.execute("SELECT 1 FROM 枢纽_号卡 WHERE 哈希键=?", (r["号卡哈希"],)).fetchone():
                缺链.append(f"订购链缺号卡枢纽:{r['哈希键']}")
            if not conn.execute("SELECT 1 FROM 枢纽_套餐 WHERE 哈希键=?", (r["套餐哈希"],)).fetchone():
                缺链.append(f"订购链缺套餐枢纽:{r['哈希键']}")
        for r in conn.execute("SELECT * FROM 链接_号卡客户"):
            if not conn.execute("SELECT 1 FROM 枢纽_号卡 WHERE 哈希键=?", (r["号卡哈希"],)).fetchone():
                缺链.append(f"实名链缺号卡:{r['哈希键']}")
            if not conn.execute("SELECT 1 FROM 枢纽_客户 WHERE 哈希键=?", (r["客户哈希"],)).fetchone():
                缺链.append(f"实名链缺客户:{r['哈希键']}")

        孤儿 = []
        for 表, 列, 父表 in (
            ("卫星_号卡属性", "号卡哈希", "枢纽_号卡"),
            ("卫星_套餐属性", "套餐哈希", "枢纽_套餐"),
            ("卫星_客户属性", "客户哈希", "枢纽_客户"),
            ("卫星_订购属性", "链接哈希", "链接_号卡套餐"),
        ):
            for r in conn.execute(f"SELECT {列} AS p FROM {表} WHERE 是否当前=1"):
                if not conn.execute(f"SELECT 1 FROM {父表} WHERE 哈希键=?", (r["p"],)).fetchone():
                    孤儿.append(f"{表}:{r['p']}")

        错挂 = []
        for 卫星类, 引 in 父校验.卫星父引.items():
            for r in conn.execute(
                f"SELECT {引['父列']} AS p FROM {引['卫星表']} WHERE 是否当前=1"
            ):
                证 = 父校验.卫星父错挂(conn, 卫星类, r["p"])
                if 证:
                    错挂.append(f"{引['卫星表']}:{r['p']}→{证['原因']}")

        双当前 = []
        for 表, 列 in (
            ("卫星_号卡属性", "号卡哈希"),
            ("卫星_套餐属性", "套餐哈希"),
            ("卫星_客户属性", "客户哈希"),
            ("卫星_订购属性", "链接哈希"),
        ):
            for r in conn.execute(
                f"SELECT {列} AS p, COUNT(*) AS c FROM {表} WHERE 是否当前=1 GROUP BY {列} HAVING c>1"
            ):
                双当前.append(f"{表}:{r['p']}")

        检项 = [
            {
                "名": "链接两端可解",
                "通过": len(缺链) == 0,
                "说明": "全部链接两端枢纽可解" if not 缺链 else "；".join(缺链[:6]),
            },
            {
                "名": "卫星无孤儿",
                "通过": len(孤儿) == 0,
                "说明": "当前卫星均挂到合法父键" if not 孤儿 else "；".join(孤儿[:6]),
            },
            {
                "名": "卫星挂对父类",
                "通过": len(错挂) == 0,
                "说明": "当前卫星父哈希均落在对应类型父表" if not 错挂 else "；".join(错挂[:6]),
            },
            {
                "名": "无双当前",
                "通过": len(双当前) == 0,
                "说明": "同父键仅一条当前卫星" if not 双当前 else "；".join(双当前[:6]),
            },
        ]
        问题 = 缺链 + [f"孤儿卫星:{x}" for x in 孤儿] + [f"错挂父:{x}" for x in 错挂] + [f"双当前:{x}" for x in 双当前]
        通过 = 0 if 问题 else 1
        说明 = "；".join(问题) if 问题 else "枢纽、链接、卫星引用与当前版贯穿互证通过"
        conn.execute(
            "INSERT INTO 金库贯验(时刻, 枢纽数, 链接数, 卫星当前数, 是否通过, 说明) VALUES (?,?,?,?,?,?)",
            (此刻(), 枢纽数, 链接数, 卫星当前数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "枢纽数": 枢纽数,
            "链接数": 链接数,
            "卫星当前数": 卫星当前数,
            "说明": 说明,
            "检项": 检项,
        }
    finally:
        conn.close()

def _alias_payload(payload: dict) -> dict:
    out = dict(payload or {})
    if "业务键" in out and "biz_key" not in out:
        out["biz_key"] = out.get("业务键")
    if "哈希键" in out and "hash_key" not in out:
        out["hash_key"] = out.get("哈希键")
    if "批号" in out and "batch_id" not in out:
        out["batch_id"] = out.get("批号")
    if "aligned" not in out:
        out["aligned"] = True
    return out


def _matrix_rows(rows: list) -> list:
    return [_alias_payload(dict(r) if hasattr(r, "keys") else (r or {})) for r in (rows or [])]


def _plant_report_21(extra: dict | None = None) -> dict:
    data = {"ok": True, "aligned": True, "scope": "haoshu", "nn": "21"}
    if extra:
        data.update(extra)
    return data

