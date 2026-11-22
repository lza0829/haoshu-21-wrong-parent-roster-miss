import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import 夹具目录, 连接
from app.services import 装载, 贯验, 目录

路由 = APIRouter(prefix="/api")


class 装载请求(BaseModel):
    装载日: str = ""
    批次编号: str = ""
    枢纽: dict = Field(default_factory=dict)
    链接: dict = Field(default_factory=dict)
    卫星: dict = Field(default_factory=dict)


@路由.get("/健康")
def 健康():
    return {"正常": True, "项目": "号枢", "骨架": "枢纽-链接-卫星-互证"}


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/枢纽/{kind}")
def 列枢纽(kind: str):
    表 = {"号卡": "枢纽_号卡", "套餐": "枢纽_套餐", "客户": "枢纽_客户"}.get(kind)
    if not 表:
        raise HTTPException(404, "未知枢纽类")
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {表} ORDER BY 业务键")]
    finally:
        conn.close()


@路由.get("/链接/{kind}")
def 列链接(kind: str):
    if kind == "号卡套餐":
        sql = """SELECT l.*, a.业务键 AS 号卡业务键, b.业务键 AS 套餐业务键
                 FROM 链接_号卡套餐 l
                 JOIN 枢纽_号卡 a ON a.哈希键=l.号卡哈希
                 JOIN 枢纽_套餐 b ON b.哈希键=l.套餐哈希"""
    elif kind == "号卡客户":
        sql = """SELECT l.*, a.业务键 AS 号卡业务键, b.业务键 AS 客户业务键
                 FROM 链接_号卡客户 l
                 JOIN 枢纽_号卡 a ON a.哈希键=l.号卡哈希
                 JOIN 枢纽_客户 b ON b.哈希键=l.客户哈希"""
    else:
        raise HTTPException(404, "未知链接类")
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


@路由.get("/卫星/{kind}")
def 列卫星(kind: str, 仅当前: int = 1):
    表 = {
        "号卡": "卫星_号卡属性",
        "套餐": "卫星_套餐属性",
        "客户": "卫星_客户属性",
        "订购": "卫星_订购属性",
    }.get(kind)
    if not 表:
        raise HTTPException(404, "未知卫星类")
    conn = 连接()
    try:
        if 仅当前:
            rows = conn.execute(f"SELECT * FROM {表} WHERE 是否当前=1 ORDER BY 编号 DESC")
        else:
            rows = conn.execute(f"SELECT * FROM {表} ORDER BY 编号 DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/站规")
def 站规():
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
    finally:
        conn.close()


@路由.get("/隔离匣")
def 隔离():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 隔离匣 ORDER BY 编号 DESC LIMIT 50")]
    finally:
        conn.close()


@路由.post("/装载")
def 做装载(体: 装载请求):
    return 装载.装一批(体.model_dump())


@路由.post("/装载/夹具")
def 装夹具(名: str = "号卡套餐样例"):
    路径 = 夹具目录 / f"{名}.json"
    if not 路径.exists():
        raise HTTPException(404, f"夹具不存在:{名}")
    return 装载.装一批(json.loads(路径.read_text(encoding="utf-8")))


@路由.get("/贯验/挂错父")
def 贯验挂错父():
    """只读：卫星挂错父贯验（父哈希、期望父类、残留错挂数、隔离/整票证据）。"""
    return 贯验.挂错父贯验()


@路由.post("/贯验")
def 做贯验():
    return 贯验.跑贯验()


@路由.get("/贯验")
def 列贯验():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 金库贯验 ORDER BY 编号 DESC LIMIT 20")]
    finally:
        conn.close()


@路由.get("/空桩")
def 空桩():
    from app import modules

    return modules.列表()

from app.modules import 错挂隔离名册 as 名册


@路由.get("/贯验/错挂名册")
def 取错挂名册(批号: str | None = None):
    conn = 连接()
    try:
        return 名册.查名册(conn, 批号)
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

