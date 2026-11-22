import json
import uuid
from typing import Any

from app.db import 连接
from app.seed import 哈希键, 载荷哈希, 此刻
from app.services import 父校验


class 错挂父异常(ValueError):
    """本批存在卫星错挂父 / 父不可解。整票失败闭。"""

    def __init__(self, 明细: list[dict]):
        self.明细 = 明细
        super().__init__("；".join(
            f"{d['卫星类']}卫星父{d['父哈希'] or '(空)'}→{d['原因']}" for d in 明细[:6]
        ))


_枢纽短名 = {"号卡": "枢纽_号卡", "套餐": "枢纽_套餐", "客户": "枢纽_客户"}
_链接短名 = {"号卡套餐": "链接_号卡套餐", "订购": "链接_号卡套餐", "号卡客户": "链接_号卡客户"}


def _规整父类(raw: Any) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if s in _枢纽短名:
        return _枢纽短名[s]
    if s in _链接短名:
        return _链接短名[s]
    if s in 父校验.父表类:
        return s
    return s


def 装一批(体: dict[str, Any]) -> dict[str, Any]:
    """顺序：枢纽 → 链接 → 卫星。失败整批回滚。

    卫星父写闸（口径=整票失败闭）：卫星父哈希必须落在对应类型父表且可解；
    任一条错挂 / 不可解则本批正式枢纽、链接、卫星零增量，错挂证据另路留存。
    """
    装载日 = str(体.get("装载日") or "").strip()
    枢纽 = 体.get("枢纽") or {}
    链接 = 体.get("链接") or {}
    卫星 = 体.get("卫星") or {}
    if not 装载日:
        return {"结果": "拒绝", "说明": "缺装载日", "口径": 父校验.口径}

    批号 = str(体.get("批次编号") or f"批-{uuid.uuid4().hex[:10]}")
    conn = 连接()
    报 = {"枢纽": 0, "链接": 0, "卫星": 0, "跳过": 0, "明细": []}
    try:
        if conn.execute("SELECT 1 FROM 装载批次 WHERE 编号=?", (批号,)).fetchone():
            return {"结果": "拒绝", "说明": "批次编号已存在", "口径": 父校验.口径}

        for 类, 表, 前缀 in (
            ("号卡", "枢纽_号卡", "号卡"),
            ("套餐", "枢纽_套餐", "套餐"),
            ("客户", "枢纽_客户", "客户"),
        ):
            for 项 in 枢纽.get(类) or []:
                业务键 = str(项.get("业务键") or "").strip()
                if not 业务键:
                    报["跳过"] += 1
                    continue
                h = 哈希键(前缀, 业务键)
                旧 = conn.execute(f"SELECT 1 FROM {表} WHERE 业务键=?", (业务键,)).fetchone()
                if 旧:
                    报["跳过"] += 1
                    报["明细"].append({"类": f"枢纽-{类}", "业务键": 业务键, "结果": "已存在"})
                    continue
                conn.execute(
                    f"INSERT INTO {表}(哈希键, 业务键, 装载日) VALUES (?,?,?)",
                    (h, 业务键, 装载日),
                )
                报["枢纽"] += 1
                报["明细"].append({"类": f"枢纽-{类}", "业务键": 业务键, "哈希键": h, "结果": "新开"})

        def 取枢纽哈希(表, 业务键):
            r = conn.execute(f"SELECT 哈希键 FROM {表} WHERE 业务键=?", (业务键,)).fetchone()
            return r["哈希键"] if r else None

        for 项 in 链接.get("号卡套餐") or []:
            号 = str(项.get("号卡业务键") or "").strip()
            套 = str(项.get("套餐业务键") or "").strip()
            hk卡 = 取枢纽哈希("枢纽_号卡", 号)
            hk套 = 取枢纽哈希("枢纽_套餐", 套)
            if not hk卡 or not hk套:
                raise ValueError(f"链接号卡套餐缺枢纽: {号}/{套}")
            lh = 哈希键("链订购", hk卡, hk套)
            if conn.execute("SELECT 1 FROM 链接_号卡套餐 WHERE 哈希键=?", (lh,)).fetchone():
                报["跳过"] += 1
                continue
            conn.execute(
                "INSERT INTO 链接_号卡套餐(哈希键, 号卡哈希, 套餐哈希, 装载日) VALUES (?,?,?,?)",
                (lh, hk卡, hk套, 装载日),
            )
            报["链接"] += 1

        for 项 in 链接.get("号卡客户") or []:
            号 = str(项.get("号卡业务键") or "").strip()
            客 = str(项.get("客户业务键") or "").strip()
            hk卡 = 取枢纽哈希("枢纽_号卡", 号)
            hk客 = 取枢纽哈希("枢纽_客户", 客)
            if not hk卡 or not hk客:
                raise ValueError(f"链接号卡客户缺枢纽: {号}/{客}")
            lh = 哈希键("链实名", hk卡, hk客)
            if conn.execute("SELECT 1 FROM 链接_号卡客户 WHERE 哈希键=?", (lh,)).fetchone():
                报["跳过"] += 1
                continue
            conn.execute(
                "INSERT INTO 链接_号卡客户(哈希键, 号卡哈希, 客户哈希, 装载日) VALUES (?,?,?,?)",
                (lh, hk卡, hk客, 装载日),
            )
            报["链接"] += 1

        def 取链接哈希(项, 父类: str = "链接_号卡套餐") -> tuple[str | None, str]:
            """返回（链接哈希, 解析说明）。"""
            号 = str(项.get("号卡业务键") or "").strip()
            if 父类 == "链接_号卡客户":
                客 = str(项.get("客户业务键") or "").strip()
                hk卡 = 取枢纽哈希("枢纽_号卡", 号)
                hk客 = 取枢纽哈希("枢纽_客户", 客)
                if not hk卡 or not hk客:
                    return None, f"卫星订购无链接端: {号}/{客}"
                lh = 哈希键("链实名", hk卡, hk客)
                if not conn.execute("SELECT 1 FROM 链接_号卡客户 WHERE 哈希键=?", (lh,)).fetchone():
                    return None, f"卫星订购无实名链接: {号}/{客}"
                return lh, ""
            套 = str(项.get("套餐业务键") or "").strip()
            hk卡 = 取枢纽哈希("枢纽_号卡", 号)
            hk套 = 取枢纽哈希("枢纽_套餐", 套)
            if not hk卡 or not hk套:
                return None, f"卫星订购无链接端: {号}/{套}"
            lh = 哈希键("链订购", hk卡, hk套)
            if not conn.execute("SELECT 1 FROM 链接_号卡套餐 WHERE 哈希键=?", (lh,)).fetchone():
                return None, f"卫星订购无链接: {号}/{套}"
            return lh, ""

        def 解析卫星父(卫星类: str, 项: dict) -> tuple[str, str]:
            """解析卫星声明的父：返回（父哈希, 声明父类表名）。不给父则抛缺父。"""
            引 = 父校验.卫星父引[卫星类]

            if 项.get("父哈希"):
                return str(项["父哈希"]).strip(), (_规整父类(项.get("父类")) or 引["期望父类"])

            if 项.get("父业务键") or 项.get("父类"):
                父类 = _规整父类(项.get("父类")) or 引["期望父类"]
                键 = str(项.get("父业务键") or 项.get("业务键") or "").strip()
                if 父类 in ("枢纽_号卡", "枢纽_套餐", "枢纽_客户"):
                    h = 取枢纽哈希(父类, 键)
                    if not h:
                        raise 错挂父异常([{
                            "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                            "实际类": 父类, "原因": f"父业务键不可解:{父类}/{键}",
                        }])
                    return h, 父类
                if 父类 in ("链接_号卡套餐", "链接_号卡客户"):
                    lh, 说明 = 取链接哈希(项, 父类)
                    if not lh:
                        raise 错挂父异常([{
                            "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                            "实际类": 父类, "原因": 说明,
                        }])
                    return lh, 父类
                raise 错挂父异常([{
                    "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                    "实际类": 父类, "原因": f"未知父类:{父类}",
                }])

            if 卫星类 == "号卡":
                键 = str(项.get("业务键") or "").strip()
                h = 取枢纽哈希("枢纽_号卡", 键)
                if not h:
                    raise 错挂父异常([{
                        "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                        "实际类": None, "原因": f"卫星号卡无枢纽: {键}",
                    }])
                return h, "枢纽_号卡"
            if 卫星类 == "套餐":
                键 = str(项.get("业务键") or "").strip()
                h = 取枢纽哈希("枢纽_套餐", 键)
                if not h:
                    raise 错挂父异常([{
                        "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                        "实际类": None, "原因": f"卫星套餐无枢纽: {键}",
                    }])
                return h, "枢纽_套餐"
            if 卫星类 == "客户":
                键 = str(项.get("业务键") or "").strip()
                h = 取枢纽哈希("枢纽_客户", 键)
                if not h:
                    raise 错挂父异常([{
                        "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                        "实际类": None, "原因": f"卫星客户无枢纽: {键}",
                    }])
                return h, "枢纽_客户"
            lh, 说明 = 取链接哈希(项)
            if not lh:
                raise 错挂父异常([{
                    "卫星类": 卫星类, "父哈希": "", "期望父类": 引["期望父类"],
                    "实际类": None, "原因": 说明,
                }])
            return lh, "链接_号卡套餐"

        已解析: list[tuple[str, str, dict]] = []
        错挂: list[dict] = []
        for 卫星类 in ("号卡", "套餐", "客户", "订购"):
            for 项 in 卫星.get(卫星类) or []:
                try:
                    父哈希, 声明父类 = 解析卫星父(卫星类, 项)
                except 错挂父异常 as e:
                    错挂.extend(e.明细)
                    continue
                证 = 父校验.卫星父错挂(conn, 卫星类, 父哈希, 声明父类)
                if 证:
                    错挂.append(证)
                    continue
                已解析.append((卫星类, 父哈希, 项.get("属性") or {}))
        if 错挂:
            raise 错挂父异常(错挂)

        def 开卫星(表, 父列, 父哈希, 属性: dict):
            ph = 载荷哈希(属性)
            当前 = conn.execute(
                f"SELECT 编号, 载荷哈希 FROM {表} WHERE {父列}=? AND 是否当前=1",
                (父哈希,),
            ).fetchone()
            if 当前 and 当前["载荷哈希"] == ph:
                报["跳过"] += 1
                return
            if 当前:
                conn.execute(f"UPDATE {表} SET 是否当前=0 WHERE 编号=?", (当前["编号"],))
            conn.execute(
                f"INSERT INTO {表}({父列}, 装载日, 载荷哈希, 属性, 是否当前) VALUES (?,?,?,?,1)",
                (父哈希, 装载日, ph, json.dumps(属性, ensure_ascii=False)),
            )
            报["卫星"] += 1

        for 卫星类, 父哈希, 属性 in 已解析:
            引 = 父校验.卫星父引[卫星类]
            开卫星(引["卫星表"], 引["父列"], 父哈希, 属性)

        conn.execute(
            "INSERT INTO 装载批次(编号, 装载日, 时刻, 报告) VALUES (?,?,?,?)",
            (批号, 装载日, 此刻(), json.dumps(报, ensure_ascii=False)),
        )
        conn.commit()
        return {"结果": "成功", "批次编号": 批号, "装载日": 装载日, "口径": 父校验.口径, "报告": 报}
    except 错挂父异常 as e:
        conn.rollback()
        时刻 = 此刻()
        conn.execute(
            "INSERT INTO 隔离匣(原因, 载荷, 时刻) VALUES (?,?,?)",
            (f"卫星错挂父（整票失败闭）：{e}", json.dumps(体, ensure_ascii=False)[:2000], 时刻),
        )
        for d in e.明细:
            conn.execute(
                "INSERT INTO 挂错父证据(批次编号, 装载日, 卫星类, 父哈希, 期望父类, 实际父类, 原因, 时刻)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (批号, 装载日, d["卫星类"], d["父哈希"], d["期望父类"], d.get("实际类"), d["原因"], 时刻),
            )
        conn.commit()
        return {
            "结果": "失败",
            "批次编号": 批号,
            "装载日": 装载日,
            "口径": 父校验.口径,
            "说明": f"卫星错挂父，整票失败闭：正式枢纽/链接/卫星零增量；{e}",
            "错挂父": e.明细,
            "报告": {"枢纽": 0, "链接": 0, "卫星": 0, "跳过": 0, "明细": []},
        }
    except Exception as e:
        conn.rollback()
        conn.execute(
            "INSERT INTO 隔离匣(原因, 载荷, 时刻) VALUES (?,?,?)",
            (str(e), json.dumps(体, ensure_ascii=False)[:2000], 此刻()),
        )
        conn.commit()
        return {"结果": "失败", "口径": 父校验.口径, "说明": str(e)}
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

