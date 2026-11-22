import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import importlib

TMP = tempfile.mkdtemp(prefix="haoshu-test-")
os.environ["数据目录"] = TMP
os.environ["夹具目录"] = str(Path(__file__).resolve().parent.parent / "fixtures")

from app import seed
from app.db import 连接
from app.services import 装载, 贯验, 父校验
from app.modules import 错挂隔离名册 as 名册

seed.初始化库()

FAILS = []


def check(名, 条, 细则=""):
    if 条:
        print(f"  PASS {名}")
    else:
        print(f"  FAIL {名} {细则}")
        FAILS.append((名, 细则))


def 清库():
    conn = 连接()
    for t in (
        "错挂隔离名册", "挂错父证据", "隔离匣", "装载批次", "金库贯验",
        "卫星_号卡属性", "卫星_套餐属性", "卫星_客户属性", "卫星_订购属性",
        "链接_号卡套餐", "链接_号卡客户", "枢纽_号卡", "枢纽_套餐", "枢纽_客户",
    ):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()


def 桩卡(批号, 装载日="2026-11-22", 卫星=None, 枢纽=None, 链接=None):
    return {
        "装载日": 装载日,
        "批次编号": 批号,
        "枢纽": 枢纽 or {"号卡": [], "套餐": [], "客户": []},
        "链接": 链接 or {"号卡套餐": [], "号卡客户": []},
        "卫星": 卫星 or {"号卡": [], "套餐": [], "客户": [], "订购": []},
    }


def 计数():
    conn = 连接()
    try:
        d = {
            "名册": conn.execute("SELECT COUNT(*) c FROM 错挂隔离名册").fetchone()["c"],
            "证据": conn.execute("SELECT COUNT(*) c FROM 挂错父证据").fetchone()["c"],
            "批次": conn.execute("SELECT COUNT(*) c FROM 装载批次").fetchone()["c"],
            "枢纽": conn.execute("SELECT COUNT(*) c FROM 枢纽_客户").fetchone()["c"],
            "套餐卫星": conn.execute("SELECT COUNT(*) c FROM 卫星_套餐属性").fetchone()["c"],
            "客户卫星": conn.execute("SELECT COUNT(*) c FROM 卫星_客户属性").fetchone()["c"],
        }
        return d
    finally:
        conn.close()


def 名册行():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 错挂隔离名册 ORDER BY 编号")]
    finally:
        conn.close()


def 可用父():
    """先建齐一位客户与一张号卡，作为后续可解父。"""
    r = 装载.装一批(桩卡("基础", 枢纽={
        "号卡": [{"业务键": "卡-1"}],
        "套餐": [{"业务键": "套-1"}],
        "客户": [{"业务键": "客-1"}],
    }))
    assert r["结果"] == "成功", r


print("\n== 场景1：错挂登册（处置同成败写名册，原因码非空）==")
清库(); 可用父()
错挂批 = 桩卡("错挂-1", 卫星={"客户": [
    {"业务键": "客-幽灵", "属性": {"x": 1}},
]})
r = 装载.装一批(错挂批)
check("错挂批失败", r["结果"] == "失败", r)
check("名册有行", 计数()["名册"] == 1, 计数())
rows = 名册行()
check("名册原因码非空", rows and rows[0]["原因码"] not in ("", None), rows)
check("名册处置=隔离", rows and rows[0]["处置"] == "隔离", rows)
check("证据原因码非空", all(x["原因码"] for x in [dict(y) for y in 连接().execute("SELECT * FROM 挂错父证据")]), "")
check("正式零增量", 计数()["客户卫星"] == 0, 计数())
check("无装载批次", 计数()["批次"] == 1, 计数())

print("\n== 场景2（甲）：名册未解除，补父后同键重灌仍整票拒绝 ==")
清库(); 可用父()
id_bad = 桩卡("错挂-2", 卫星={"客户": [
    {"业务键": "客-后补", "属性": {"x": 1}},
]})
r = 装载.装一批(id_bad)
check("先错挂拒绝", r["结果"] == "失败", r)
check("名册命中", 计数()["名册"] == 1, 计数())
# 补齐父：先把「客-后补」建成枢纽
补 = 装载.装一批(桩卡("补父-1", 枢纽={"号卡": [], "套餐": [], "客户": [{"业务键": "客-后补"}]}))
check("补父成功", 补["结果"] == "成功", 补)
# 现查父已可解
conn = 连接()
check("现查父可解", 父校验.现场父可解(conn, "客户", seed.哈希键("客户", "客-后补")), "")
conn.close()
r2 = 装载.装一批(桩卡("重灌-甲", 卫星={"客户": [
    {"业务键": "客-后补", "属性": {"x": 1}},
]}))
check("甲：父可解仍拒绝", r2["结果"] == "失败", r2)
check("甲：拒绝原因码=名册", any(x.get("原因码") == 父校验.原因码_名册禁写 for x in (r2.get("名册禁写") or [])), r2)
check("甲：正式当前仍无该卫星", 计数()["客户卫星"] == 0, 计数())
check("甲：无新装载批次", 计数()["批次"] == 2, 计数())

print("\n== 场景3：解除名册后可重灌写出 ==")
解锁 = 名册.解除 if hasattr(名册, "解除") else None
conn = 连接()
try:
    conn.execute("BEGIN IMMEDIATE")
    名册.解除(conn, 批号="错挂-2", 说明="补父后人工解除")
    conn.commit()
finally:
    conn.close()
r3 = 装载.装一批(桩卡("重灌-解后", 卫星={"客户": [
    {"业务键": "客-后补", "属性": {"x": 1}},
]}))
check("解除后可写", r3["结果"] == "成功", r3)
check("卫星落盘 1 条", 计数()["客户卫星"] == 1, 计数())

print("\n== 场景4：名册写闸核证只读接口 ==")
核 = 名册.写闸核证(连接())
check("核证通过", 核["是否通过"] is True, 核.get("违规"))
check("核证只读标记", 核["只读"] is True, 核)
check("有已解除行", 核["已解除数"] >= 1, 核["已解除数"])

print("\n== 场景5：同父不同键重灌也被禁写（父哈希命中）==")
清库(); 可用父()
# 订购卫星挂到不存在的链接：用父哈希显式错挂一个「链接_号卡客户」哈希
假父 = "f" * 20
r = 装载.装一批(桩卡("错父-1", 卫星={"客户": [
    {"父哈希": 假父, "父类": "客户", "卫星键": "键-A", "属性": {"x": 1}},
]}))
check("错挂父拒绝", r["结果"] == "失败", r)
check("名册登记", 计数()["名册"] == 1, 计数())
r = 装载.装一批(桩卡("错父-2", 卫星={"客户": [
    {"父哈希": 假父, "父类": "客户", "卫星键": "键-B", "属性": {"x": 2}},
]}))
check("同父不同键拒绝", r["结果"] == "失败", r)
check("新批未登册（名册仍 1）", 计数()["名册"] == 1, 计数())

print("\n== 场景6：登册失败不得半成功（原因码空强制失败）==")
清库(); 可用父()
conn = 连接()
try:
    conn.execute("BEGIN IMMEDIATE")
    try:
        名册.登册(conn, 批号="x", 卫星类="客户", 卫星键="k", 错误父哈希="h",
                  期望父类="枢纽_客户", 原因码="", 处置="隔离")
        check("空原因码应抛", False)
    except 名册.名册异常:
        check("空原因码抛异常", True)
    conn.rollback()
finally:
    conn.close()

print("\n== 场景7：并发登册与重灌交错——正式不得错挂当前 ==")
清库(); 可用父()
结果 = {}


def 错挂线程():
    结果["错挂"] = 装载.装一批(桩卡("并发-错挂", 卫星={"客户": [
        {"业务键": "客-并发", "属性": {"x": 1}},
    ]}))


def 重灌线程():
    结果["重灌"] = 装载.装一批(桩卡("并发-重灌", 卫星={"客户": [
        {"业务键": "客-并发", "属性": {"x": 1}},
    ]}))


ts = [threading.Thread(target=错挂线程), threading.Thread(target=重灌线程)]
for t in ts:
    t.start()
for t in ts:
    t.join()
# 先建父再验证：两个线程都不该写出正式错挂
conn = 连接()
残留 = 0
for r in conn.execute("SELECT 客户哈希 p FROM 卫星_客户属性 WHERE 是否当前=1"):
    if 父校验.卫星父错挂(conn, "客户", r["p"]):
        残留 += 1
conn.close()
check("并发后正式无错挂当前", 残留 == 0, {"残留": 残留, "结果": 结果})
核 = 名册.写闸核证(连接())
check("并发后名册核证通过", 核["是否通过"], 核.get("违规"))

print("\n== 场景8：整票失败——同批合法项不得半落 ==")
清库(); 可用父()
r = 装载.装一批(桩卡("混批", 卫星={
    "客户": [{"业务键": "客-1", "属性": {"合法": True}}],
    "套餐": [{"业务键": "套-旺", "属性": {"错": True}}],
}))
check("混批失败", r["结果"] == "失败", r)
check("合法客户卫星零落盘", 计数()["客户卫星"] == 0, 计数())
check("合法套餐卫星零落盘", 计数()["套餐卫星"] == 0, 计数())
check("无装载批次", 计数()["批次"] == 1, 计数())

print("\n== 场景9：挂错父贯验整合名册互证 ==")
g = 贯验.挂错父贯验()
check("挂错父贯验含写闸核证", "写闸核证" in g, list(g))
check("挂错父贯验通过", g["是否通过"], g)
check("贯验口径甲", g["写闸口径"] == 父校验.写闸口径, g["写闸口径"])
r = 贯验.跑贯验()
check("跑贯验通过", r["是否通过"], r)
check("贯验检项含名册", any(x["名"] == "错挂名册写闸互证" for x in r["检项"]), r["检项"])

print("\n== 场景10：改名册直接清空会暴露“处置成功而名册空” ==")
清库(); 可用父()
装载.装一批(桩卡("错挂-10", 卫星={"客户": [{"业务键": "客-无", "属性": {"x": 1}}]}))
conn = 连接()
conn.execute("DELETE FROM 错挂隔离名册")
conn.commit(); conn.close()
核 = 名册.写闸核证(连接())
check("名册空被核证拦下", not 核["是否通过"], 核.get("违规"))
check("违规类型=处置成功而名册空", any(v["类型"] == "处置成功而名册空" for v in 核["违规"]), 核["违规"])

print("\n== 场景11：解除后同批号重灌不算误落（固定批号夹具）==")
清库(); 可用父()
装载.装一批(桩卡("固定批", 卫星={"客户": [{"业务键": "客-固", "属性": {"x": 1}}]}))
# 补齐父后解除名册，再以同批号重灌。
装载.装一批(桩卡("补父-固", 枢纽={"号卡": [], "套餐": [], "客户": [{"业务键": "客-固"}]}))
conn = 连接(); conn.execute("BEGIN IMMEDIATE")
名册.解除(conn, 批号="固定批", 说明="解")
conn.commit(); conn.close()
r = 装载.装一批(桩卡("固定批", 卫星={"客户": [{"业务键": "客-固", "属性": {"x": 1}}]}))
check("解除后同批成功", r["结果"] == "成功", r)
核 = 名册.写闸核证(连接())
check("核证不误报误落", 核["是否通过"], 核["违规"])

print("\n== 场景12：未解名册批号若出现正式批次须报误落 ==")
清库(); 可用父()
装载.装一批(桩卡("应拒批", 卫星={"客户": [{"业务键": "客-拒", "属性": {"x": 1}}]}))
conn = 连接()
# 人为插入一条同名批号正式批次（模拟半成功 / 绕过写闸）
conn.execute("INSERT INTO 装载批次(编号, 装载日, 时刻, 报告) VALUES ('应拒批','2026-11-22','t','{}')")
conn.commit(); conn.close()
核 = 名册.写闸核证(连接())
check("名册禁写批半成功被拦", not 核["是否通过"], 核["违规"])
check("违规类型=名册禁写批仍半成功", any(v["类型"] == "名册禁写批仍半成功" for v in 核["违规"]), 核["违规"])

print("\n==========")
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for n, d in FAILS:
        print(" -", n, d)
    sys.exit(1)
print("ALL PASS")
