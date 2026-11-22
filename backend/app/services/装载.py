import json
import uuid
from typing import Any

from app.db import 连接
from app.seed import 哈希键, 载荷哈希, 此刻
from app.modules import 错挂隔离名册 as 名册
from app.services import 父校验


_枢纽短名 = {"号卡": "枢纽_号卡", "套餐": "枢纽_套餐", "客户": "枢纽_客户"}
_链接短名 = {"号卡套餐": "链接_号卡套餐", "订购": "链接_号卡套餐", "号卡客户": "链接_号卡客户"}
_卫星序 = ("号卡", "套餐", "客户", "订购")


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


def _证(卫星类: str, 父哈希: str, 期望父类: str, 实际类, 原因: str) -> dict:
    return {
        "卫星类": 卫星类,
        "父哈希": 父哈希 or "",
        "期望父类": 期望父类,
        "实际类": 实际类,
        "原因": 原因,
        "原因码": 父校验.原因码(原因),
    }


def _卫星键(卫星类: str, 项: dict) -> str:
    """同键禁写所用键：解析成功与否都稳定同形，重灌才可能命中名册。

    订购卫星以 业务键 → 父业务键 → 「号卡业务键|套餐/客户业务键」派生；
    其余卫星以 业务键 → 父业务键 → 父哈希 派生。
    """
    直 = 项.get("卫星键") or 项.get("业务键")
    if 直:
        return str(直).strip()
    if 卫星类 == "订购":
        右 = 项.get("套餐业务键") or 项.get("客户业务键") or ""
        if 项.get("号卡业务键") or 右:
            return f"{str(项.get('号卡业务键') or '').strip()}|{str(右).strip()}"
    return str(项.get("父业务键") or 项.get("父哈希") or "").strip()


class _拒载(Exception):
    """卫星写闸整票拒绝：错挂父证据 / 名册禁写命中。"""

    def __init__(self, *, 错挂: list[dict], 名册命中: list[dict]):
        self.错挂 = 错挂
        self.名册命中 = 名册命中
        super().__init__("卫星错挂父 / 名册禁写")


def 装一批(体: dict[str, Any]) -> dict[str, Any]:
    """顺序：枢纽 → 链接 → 卫星。失败整批回滚。

    卫星父写闸（口径=甲·隔离名册禁写）：
      ① 先查错挂隔离名册：同卫星类下同卫星键或同错误父哈希仍生效禁写 -> 整票拒绝，
         即使现查父已可解（名册未解除不得写出）。
      ② 再查父引用：父哈希必须落在对应类型父表且可解；任一条错挂 -> 整票拒绝。
      ③ 任一拒绝：正式枢纽/链接/卫星零增量；挂错父证据与隔离名册行在同一事务内
         同成败写入 —— 处置成功而名册空不可能。
      ④ 兼容旧口径「现场父可解」：名册为空时行为不变；名册生效时以名册为准。
    """
    装载日 = str(体.get("装载日") or "").strip()
    枢纽 = 体.get("枢纽") or {}
    链接 = 体.get("链接") or {}
    卫星 = 体.get("卫星") or {}
    if not 装载日:
        return {"结果": "拒绝", "说明": "缺装载日", "口径": 父校验.口径, "写闸口径": 父校验.写闸口径}

    批号 = str(体.get("批次编号") or f"批-{uuid.uuid4().hex[:10]}")
    conn = 连接()
    报 = {"枢纽": 0, "链接": 0, "卫星": 0, "跳过": 0, "明细": []}
    try:
        # 显式写事务：装载 / 证据 / 登册同成败；并发装载按写锁串行，半截不可提交。
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM 装载批次 WHERE 编号=?", (批号,)).fetchone():
            conn.rollback()
            return {"结果": "拒绝", "说明": "批次编号已存在", "口径": 父校验.口径, "写闸口径": 父校验.写闸口径}

        conn.execute("SAVEPOINT 正式装载")
        try:
            _装正式(conn, 批号, 装载日, 枢纽, 链接, 卫星, 报)
        except _拒载 as 拒:
            # 正式写入整票回滚，再同事务登册 + 留证。
            conn.execute("ROLLBACK TO 正式装载")
            conn.execute("RELEASE 正式装载")
            时刻 = 此刻()
            try:
                conn.execute(
                    "INSERT INTO 隔离匣(原因, 载荷, 时刻) VALUES (?,?,?)",
                    (
                        f"卫星写闸整票拒绝（{父校验.写闸口径}）：{_拒摘要(拒)}",
                        json.dumps(体, ensure_ascii=False)[:2000],
                        时刻,
                    ),
                )
                登册 = _登册主体(conn, 批号, 装载日, 拒.错挂, 拒.名册命中, 时刻)
                conn.commit()
            except Exception as e:
                # 登册失败：整票回滚，绝不以“处置成功而名册空”返回。
                conn.rollback()
                return {
                    "结果": "失败", "批次编号": 批号, "装载日": 装载日,
                    "口径": 父校验.口径, "写闸口径": 父校验.写闸口径,
                    "说明": f"卫星写闸拒绝且隔离名册登册失败，整票回滚：{e}",
                    "名册登册失败": True,
                    "报告": {"枢纽": 0, "链接": 0, "卫星": 0, "跳过": 0, "明细": []},
                }
            return _失败报(批号, 装载日, 拒, 登册, 报)
        except Exception as e:
            conn.execute("ROLLBACK TO 正式装载")
            conn.execute("RELEASE 正式装载")
            时刻 = 此刻()
            conn.execute(
                "INSERT INTO 隔离匣(原因, 载荷, 时刻) VALUES (?,?,?)",
                (str(e), json.dumps(体, ensure_ascii=False)[:2000], 时刻),
            )
            conn.commit()
            return {"结果": "失败", "批号": 批号, "批次编号": 批号, "装载日": 装载日,
                    "口径": 父校验.口径, "写闸口径": 父校验.写闸口径, "说明": str(e)}

        conn.execute("RELEASE 正式装载")
        conn.commit()
        return {"结果": "成功", "批次编号": 批号, "装载日": 装载日,
                "口径": 父校验.口径, "写闸口径": 父校验.写闸口径, "报告": 报}
    finally:
        conn.close()


def _拒摘要(拒: _拒载) -> str:
    段 = []
    if 拒.名册命中:
        段.append("名册未解除 " + "；".join(
            f"{h['卫星类']}:{h.get('卫星键') or h.get('父哈希') or '(空)'}" for h in 拒.名册命中[:4]
        ))
    if 拒.错挂:
        段.append("错挂 " + "；".join(
            f"{d['卫星类']}父{d.get('父哈希') or '(空)'}→{d['原因']}" for d in 拒.错挂[:4]
        ))
    return " / ".join(段) or "写闸拒绝"


def _失败报(批号, 装载日, 拒: _拒载, 登册: dict, 报: dict) -> dict:
    名册行 = 登册.get("名册行") or []
    段 = []
    if 拒.名册命中:
        段.append("名册未解除，同键/同父装载一律拒绝（即使父现可解）")
    if 拒.错挂:
        段.append("存在卫星错挂父 / 父不可解")
    return {
        "结果": "失败",
        "批次编号": 批号,
        "装载日": 装载日,
        "口径": 父校验.口径,
        "写闸口径": 父校验.写闸口径,
        "说明": "；".join(段) + "。正式枢纽/链接/卫星零增量。",
        "错挂父": 拒.错挂,
        "名册禁写": 拒.名册命中,
        "已登册": 名册行,
        "已登册行数": len(名册行) if 拒.错挂 else 0,
        "报告": {"枢纽": 0, "链接": 0, "卫星": 0, "跳过": 0, "明细": []},
    }


def _装正式(conn, 批号: str, 装载日: str, 枢纽, 链接, 卫星, 报: dict) -> None:
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
                return None, f"卫星链接父端点不可解: {号}/{客}"
            lh = 哈希键("链实名", hk卡, hk客)
            if not conn.execute("SELECT 1 FROM 链接_号卡客户 WHERE 哈希键=?", (lh,)).fetchone():
                return None, f"卫星链接父不存在: {号}/{客}"
            return lh, ""
        套 = str(项.get("套餐业务键") or "").strip()
        hk卡 = 取枢纽哈希("枢纽_号卡", 号)
        hk套 = 取枢纽哈希("枢纽_套餐", 套)
        if not hk卡 or not hk套:
            return None, f"卫星链接父端点不可解: {号}/{套}"
        lh = 哈希键("链订购", hk卡, hk套)
        if not conn.execute("SELECT 1 FROM 链接_号卡套餐 WHERE 哈希键=?", (lh,)).fetchone():
            return None, f"卫星链接父不存在: {号}/{套}"
        return lh, ""

    def 解析卫星父(卫星类: str, 项: dict) -> tuple[str, str]:
        """解析卫星声明的父：返回（父哈希, 声明父类表名）。"""
        引 = 父校验.卫星父引[卫星类]

        if 项.get("父哈希"):
            return str(项["父哈希"]).strip(), (_规整父类(项.get("父类")) or 引["期望父类"])

        if 项.get("父业务键") or 项.get("父类"):
            父类 = _规整父类(项.get("父类")) or 引["期望父类"]
            键 = str(项.get("父业务键") or 项.get("业务键") or "").strip()
            if 父类 in ("枢纽_号卡", "枢纽_套餐", "枢纽_客户"):
                h = 取枢纽哈希(父类, 键)
                if not h:
                    raise 父校验.错挂父异常([_证(
                        卫星类, "", 引["期望父类"], 父类, f"父业务键不可解:{父类}/{键}",
                    )])
                return h, 父类
            if 父类 in ("链接_号卡套餐", "链接_号卡客户"):
                lh, 说明 = 取链接哈希(项, 父类)
                if not lh:
                    raise 父校验.错挂父异常([_证(
                        卫星类, "", 引["期望父类"], 父类, 说明,
                    )])
                return lh, 父类
            raise 父校验.错挂父异常([_证(
                卫星类, "", 引["期望父类"], 父类, f"未知父类:{父类}",
            )])

        if 卫星类 == "号卡":
            键 = str(项.get("业务键") or "").strip()
            h = 取枢纽哈希("枢纽_号卡", 键)
            if not h:
                raise 父校验.错挂父异常([_证(卫星类, "", 引["期望父类"], None, f"卫星枢纽父不存在: {键}")])
            return h, "枢纽_号卡"
        if 卫星类 == "套餐":
            键 = str(项.get("业务键") or "").strip()
            h = 取枢纽哈希("枢纽_套餐", 键)
            if not h:
                raise 父校验.错挂父异常([_证(卫星类, "", 引["期望父类"], None, f"卫星枢纽父不存在: {键}")])
            return h, "枢纽_套餐"
        if 卫星类 == "客户":
            键 = str(项.get("业务键") or "").strip()
            h = 取枢纽哈希("枢纽_客户", 键)
            if not h:
                raise 父校验.错挂父异常([_证(卫星类, "", 引["期望父类"], None, f"卫星枢纽父不存在: {键}")])
            return h, "枢纽_客户"
        lh, 说明 = 取链接哈希(项)
        if not lh:
            raise 父校验.错挂父异常([_证(卫星类, "", 引["期望父类"], None, 说明)])
        return lh, "链接_号卡套餐"

    已解析: list[tuple[str, str, dict, str]] = []
    错挂: list[dict] = []
    名册命中: list[dict] = []
    for 卫星类 in _卫星序:
        for 项 in 卫星.get(卫星类) or []:
            卫星键 = _卫星键(卫星类, 项)
            try:
                父哈希, 声明父类 = 解析卫星父(卫星类, 项)
            except 父校验.错挂父异常 as e:
                for d in e.明细:
                    d["卫星键"] = 卫星键
                错挂.extend(e.明细)
                continue

            # ① 名册写闸（甲）：先于父可解判断；父已可解也照拒。
            命中 = 名册.命中的禁写(conn, 卫星类, 卫星键, 父哈希)
            if 命中:
                for h in 命中:
                    名册命中.append({
                        "卫星类": 卫星类,
                        "卫星键": 卫星键 or h.get("卫星键") or "",
                        "父哈希": 父哈希,
                        "期望父类": 父校验.卫星父引[卫星类]["期望父类"],
                        "实际类": h.get("期望父类"),
                        "原因": f"名册未解除（名册编号 {h.get('编号')}，批号 {h.get('批号')}）",
                        "原因码": 父校验.原因码_名册禁写,
                        "名册编号": h.get("编号"),
                        "名册批号": h.get("批号"),
                        "父现可解": 父校验.现场父可解(conn, 卫星类, 父哈希, 声明父类),
                    })
                continue

            # ② 现场父校验。
            证 = 父校验.卫星父错挂(conn, 卫星类, 父哈希, 声明父类)
            if 证:
                证["卫星键"] = 卫星键
                错挂.append(证)
                continue
            已解析.append((卫星类, 父哈希, 项.get("属性") or {}, 卫星键))

        if 错挂 or 名册命中:
            break

    if 错挂 or 名册命中:
        raise _拒载(错挂=错挂, 名册命中=名册命中)

    def 开卫星(表, 父列, 父哈希, 卫星键, 属性: dict):
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
            f"INSERT INTO {表}({父列}, 卫星键, 装载日, 载荷哈希, 属性, 是否当前) VALUES (?,?,?,?,?,1)",
            (父哈希, 卫星键, 装载日, ph, json.dumps(属性, ensure_ascii=False)),
        )
        报["卫星"] += 1

    for 卫星类, 父哈希, 属性, 卫星键 in 已解析:
        引 = 父校验.卫星父引[卫星类]
        开卫星(引["卫星表"], 引["父列"], 父哈希, 卫星键, 属性)

    conn.execute(
        "INSERT INTO 装载批次(编号, 装载日, 时刻, 报告) VALUES (?,?,?,?)",
        (批号, 装载日, 此刻(), json.dumps(报, ensure_ascii=False)),
    )


def _登册主体(conn, 批号: str, 装载日: str, 错挂: list[dict], 名册命中: list[dict], 时刻: str) -> dict:
    """错挂处置同成败登册；原因码为空即整票失败（调用方回滚）。"""
    行 = []
    for d in 错挂:
        码 = str(d.get("原因码") or "").strip() or 父校验.原因码(d.get("原因"))
        # 父哈希缺失时尽量落确定性候选哈希，使「补齐父后可解」可被名册分叉核证。
        错父 = str(d.get("父哈希") or "").strip() or 父校验.候选父哈希(
            d["卫星类"], str(d.get("卫星键") or "").strip()
        )
        got = 名册.登册(
            conn,
            批号=批号,
            卫星类=d["卫星类"],
            卫星键=str(d.get("卫星键") or "").strip(),
            错误父哈希=错父,
            期望父类=d["期望父类"],
            原因码=码,
            处置="隔离",
            时刻=时刻,
        )
        conn.execute(
            "INSERT INTO 挂错父证据(批次编号, 装载日, 卫星类, 卫星键, 父哈希, 期望父类, 实际父类, 原因, 原因码, 时刻)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (批号, 装载日, d["卫星类"], str(d.get("卫星键") or ""), 错父, d["期望父类"],
             d.get("实际类"), d["原因"], 码, 时刻),
        )
        行.extend(got)
    for h in 名册命中:
        码 = str(h.get("原因码") or 父校验.原因码_名册禁写)
        conn.execute(
            "INSERT INTO 挂错父证据(批次编号, 装载日, 卫星类, 卫星键, 父哈希, 期望父类, 实际父类, 原因, 原因码, 时刻)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (批号, 装载日, h["卫星类"], h.get("卫星键") or "", h["父哈希"], h["期望父类"],
             h.get("实际类"), h["原因"], 码, 时刻),
        )
    return {"名册行": 行}
