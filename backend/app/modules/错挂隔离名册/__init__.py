"""错挂隔离名册：登记 / 写闸 / 解除 / 只读核证。

口径：甲 · 隔离名册禁写。名册生效行（处置=隔离 且未解除）未解除前，
同卫星类下同卫星键或同错误父哈希的卫星装载一律拒绝，即使现查父已可解。

本模块只做名册自身的事：装载写闸在 services/装载.py 调用 命中的禁写()，
贯验页 / 只读接口调用 查名册() 与 写闸核证()。
"""
from app.seed import 此刻
from app.services import 父校验

状态 = "已实现"
口径 = 父校验.写闸口径
禁写原因码 = 父校验.原因码_名册禁写
接口 = {
    "只读核证": "GET /api/贯验/错挂名册/写闸",
    "名册": "GET /api/贯验/错挂名册",
    "解除": "POST /api/贯验/错挂名册/解除",
}
_生效 = "处置='隔离' AND COALESCE(解除时刻,'')=''"


class 名册异常(ValueError):
    """登册 / 解除失败：调用方不得把处置报告为成功。"""


def _行(r):
    return dict(r) if hasattr(r, "keys") else dict(r or {})


def _列有(conn, 表: str, 列: str) -> bool:
    try:
        return 列 in {r["name"] for r in conn.execute(f"PRAGMA table_info({表})")}
    except Exception:
        return False


def _安全查询(conn, sql: str, 参=()) -> list[dict]:
    try:
        return [dict(r) for r in conn.execute(sql, 参)]
    except Exception:
        return []


def _生效数(conn) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) AS c FROM 错挂隔离名册 WHERE {_生效}").fetchone()["c"]
    except Exception:
        return 0


def 查名册(conn, 批号: str | None = None, 仅生效: bool = False) -> dict:
    """只读：列名册。禁写 = 存在生效行。"""
    where, 参 = [], []
    if 批号:
        where.append("批号=?")
        参.append(批号)
    if 仅生效:
        where.append(f"({_生效})")
    sql = "SELECT * FROM 错挂隔离名册"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY 编号 DESC LIMIT 200"
    rows = _安全查询(conn, sql, 参)
    总 = len(_安全查询(conn, "SELECT 编号 FROM 错挂隔离名册"))
    生效 = _生效数(conn)
    return {
        "口径": 口径,
        "名册": rows,
        "禁写": 生效 > 0,
        "总行数": 总,
        "生效禁写数": 生效,
        "已解除数": max(0, 总 - 生效),
        "说明": (
            f"名册有 {生效} 条生效禁写：同键/同父卫星装载一律拒绝，直至解除"
            if 生效 > 0
            else ("名册行均已解除或尚未发生错挂" if 总 else "名册为空，尚无错挂登记")
        ),
    }


def 命中的禁写(conn, 卫星类: str, 卫星键: str = "", 父哈希: str = "") -> list[dict]:
    """只读：该卫星类下同键或同父的生效禁区行。空串不当命中。"""
    子, 参 = [], []
    if 卫星键:
        子.append("卫星键=?")
        参.append(卫星键)
    if 父哈希:
        子.append("错误父哈希=?")
        参.append(父哈希)
    if not 子:
        return []
    sql = (
        "SELECT * FROM 错挂隔离名册 "
        f"WHERE 卫星类=? AND {_生效} AND ({' OR '.join(子)}) "
        "ORDER BY 编号 DESC"
    )
    return _安全查询(conn, sql, [卫星类, *参])


def 登册(
    conn,
    *,
    批号: str,
    卫星类: str,
    卫星键: str,
    错误父哈希: str,
    期望父类: str,
    原因码: str,
    处置: str,
    时刻: str | None = None,
) -> list[dict]:
    """把一条错挂处置同成败写入隔离名册。原因码 / 处置 / 批号不得为空。

    同键或同父已有生效行时不重复登记（返回已有行）；调用方与原登记同事务提交。
    """
    批号 = str(批号 or "").strip()
    码 = str(原因码 or "").strip()
    处 = str(处置 or "").strip()
    键 = str(卫星键 or "").strip()
    父 = str(错误父哈希 or "").strip()
    if not 批号:
        raise 名册异常("登册失败：批号为空")
    if not 码:
        raise 名册异常("登册失败：原因码为空")
    if not 处:
        raise 名册异常("登册失败：处置为空")
    if not str(期望父类 or "").strip():
        raise 名册异常("登册失败：期望父类为空")
    if not 键 and not 父:
        raise 名册异常("登册失败：卫星键与错误父哈希同时为空")

    已有 = 命中的禁写(conn, 卫星类, 键, 父)
    if 已有:
        for r in 已有:
            r["已在册"] = True
        return 已有

    conn.execute(
        "INSERT INTO 错挂隔离名册"
        "(批号, 卫星类, 卫星键, 错误父哈希, 期望父类, 原因码, 处置, 时刻, 解除时刻, 解除说明)"
        " VALUES (?,?,?,?,?,?,?,?,'','')",
        (批号, 卫星类, 键, 父, str(期望父类), 码, 处, 时刻 or 此刻()),
    )
    r = conn.execute("SELECT * FROM 错挂隔离名册 WHERE 编号=last_insert_rowid()").fetchone()
    return [_行(r)]


def 解除(conn, 编号: int | None = None, 批号: str | None = None, 说明: str = "") -> dict:
    """解除名册禁写：置 处置=已解除、解除时刻/说明。解除后同键可重新装载。"""
    条件, 参 = [], []
    if 编号 is not None:
        条件.append("编号=?")
        参.append(int(编号))
    if 批号:
        条件.append("批号=?")
        参.append(str(批号))
    if not 条件:
        raise 名册异常("解除失败：须给编号或批号")
    sql = f"SELECT * FROM 错挂隔离名册 WHERE {_生效} AND ({' OR '.join(条件)})"
    行 = _安全查询(conn, sql, 参)
    if not 行:
        raise 名册异常("解除失败：无匹配的生效名册行")
    时刻 = 此刻()
    解 = str(说明 or "").strip() or "人工解除"
    for r in 行:
        conn.execute(
            "UPDATE 错挂隔离名册 SET 处置='已解除', 解除时刻=?, 解除说明=? WHERE 编号=?",
            (时刻, 解, r["编号"]),
        )
    新 = _安全查询(
        conn,
        "SELECT * FROM 错挂隔离名册 WHERE 编号 IN (%s)" % ",".join("?" * len(行)),
        [r["编号"] for r in 行],
    )
    return {"解除条数": len(行), "解除": 新, "解除时刻": 时刻, "解除说明": 解}


def _当前卫星键(conn) -> dict[tuple[str, str], list[dict]]:
    索引: dict[tuple[str, str], list[dict]] = {}
    for 卫星类, 引 in 父校验.卫星父引.items():
        有键 = _列有(conn, 引["卫星表"], "卫星键")
        列 = f"{引['父列']} AS p, 编号" + (", 卫星键 AS k" if 有键 else ", '' AS k")
        for r in _安全查询(conn, f"SELECT {列} FROM {引['卫星表']} WHERE 是否当前=1"):
            if r["k"]:
                索引.setdefault((卫星类, r["k"]), []).append({"编号": r["编号"], "父哈希": r["p"]})
    return 索引


def _父现可解(conn, 卫星类: str, 哈希: str, 期望父类: str = "") -> bool:
    if not 哈希:
        return False
    引 = 父校验.卫星父引.get(卫星类)
    表 = 期望父类 if 期望父类 in 父校验.父表类 else (引 or {}).get("期望父类")
    if not 表:
        return False
    return 父校验.父表有(conn, 表, 哈希)


def 写闸核证(conn) -> dict:
    """只读：错挂名册写闸核证（甲口径）。

    互证内容：
      - 生效名册行 -> 禁写明细 + 父是否已可解（名册分叉：父已可解仍禁写）；
      - 已解除行 -> 已解明细；
      - 错挂证据（F-*）必须有名册行对应，否则「处置成功而名册空」违规；
      - 原因码 / 处置 / 期望父类不得为空；
      - 名册禁写批与错挂批不得有正式装载批次（误伤后半成功）；
      - 正式当前卫星不得存在错挂父。
    本函数不写库、不改任何表。
    """
    名册行 = _安全查询(conn, "SELECT * FROM 错挂隔离名册 ORDER BY 编号 DESC")
    生效 = [r for r in 名册行 if r.get("处置") == "隔离" and not (r.get("解除时刻") or "")]
    已解 = [r for r in 名册行 if r.get("处置") == "已解除" or (r.get("解除时刻") or "")]
    当前 = _当前卫星键(conn)
    违规: list[dict] = []
    分叉 = []

    禁写明细 = []
    for r in 生效:
        可解 = _父现可解(conn, r.get("卫星类", ""), r.get("错误父哈希", ""), r.get("期望父类", ""))
        条 = {
            "编号": r.get("编号"),
            "批号": r.get("批号"),
            "卫星类": r.get("卫星类"),
            "卫星键": r.get("卫星键"),
            "错误父哈希": r.get("错误父哈希"),
            "期望父类": r.get("期望父类"),
            "原因码": r.get("原因码"),
            "处置": r.get("处置"),
            "时刻": r.get("时刻"),
            "父现可解": 可解,
            "禁写": True,
            "裁决": "甲·禁写（父已可解仍拒绝，须先解名册）" if 可解 else "甲·禁写（父不可解）",
        }
        禁写明细.append(条)
        if 可解:
            分叉.append({
                "编号": r.get("编号"),
                "卫星类": r.get("卫星类"),
                "卫星键": r.get("卫星键"),
                "错误父哈希": r.get("错误父哈希"),
                "期望父类": r.get("期望父类"),
                "说明": "父哈希现已可解，但名册未解除，甲口径仍禁写",
            })
        if not str(r.get("原因码") or "").strip():
            违规.append({"类型": "原因码空", "编号": r.get("编号"), "说明": "生效名册行原因码为空"})
        if not str(r.get("处置") or "").strip():
            违规.append({"类型": "处置空", "编号": r.get("编号"), "说明": "生效名册行处置为空"})
        if not str(r.get("期望父类") or "").strip():
            违规.append({"类型": "期望父类空", "编号": r.get("编号"), "说明": "生效名册行期望父类为空"})
        # 甲：名册未解除时，同键卫星不得成为正式当前。但若正式当前是同键且挂在
        # 合法父（非名册错误父）上，属登记前既有合法卫星，不是本批漏写；
        # 只有当前父命中名册错误父哈希才算「名册生效却写出错挂」。
        if r.get("卫星键") and (r.get("卫星类"), r.get("卫星键")) in 当前:
            错父 = str(r.get("错误父哈希") or "").strip()
            命中当前 = 当前[(r.get("卫星类"), r.get("卫星键"))]
            有错挂当前 = any(
                (not 错父 and 父校验.卫星父错挂(conn, r.get("卫星类", ""), x["父哈希"]))
                or (错父 and x["父哈希"] == 错父)
                for x in 命中当前
            )
            if 有错挂当前:
                违规.append({
                    "类型": "名册生效但正式当前已写出",
                    "编号": r.get("编号"),
                    "卫星类": r.get("卫星类"),
                    "卫星键": r.get("卫星键"),
                    "错误父哈希": 错父,
                    "说明": "甲口径下名册未解除前同键错挂不得成为正式当前",
                })

    证据 = _安全查询(conn, "SELECT * FROM 挂错父证据 ORDER BY 编号 DESC LIMIT 500")
    # 名册覆盖按 卫星类+卫星键 / 卫星类+错误父哈希 跨批匹配：并发或同键重灌可能
    # 复用既有名册行（登册返回「已在册」），证据批号不必等于名册批号。
    名册键 = {(r.get("卫星类"), r.get("卫星键")) for r in 名册行 if r.get("卫星键")}
    名册父 = {(r.get("卫星类"), r.get("错误父哈希")) for r in 名册行 if r.get("错误父哈希")}
    # 仍生效的覆盖键：只有名册仍未解除时，同批号出现正式装载批次才是违规；
    # 解除后同一批号重灌是合法重试（固定批号夹具场景），不得误报「整票误落」。
    生效键 = {(r.get("卫星类"), r.get("卫星键")) for r in 生效 if r.get("卫星键")}
    生效父 = {(r.get("卫星类"), r.get("错误父哈希")) for r in 生效 if r.get("错误父哈希")}
    误落 = []
    for e in 证据:
        码 = str(e.get("原因码") or "").strip()
        仍在禁 = (
            (e.get("卫星类"), e.get("卫星键")) in 生效键
            or (e.get("卫星类"), e.get("父哈希")) in 生效父
        )
        if not 码:
            违规.append({
                "类型": "证据原因码空",
                "证据编号": e.get("编号"),
                "批号": e.get("批次编号"),
                "说明": "挂错父证据原因码为空，禁止",
            })
        if 码 != 禁写原因码:
            命中 = (
                (e.get("卫星类"), e.get("卫星键")) in 名册键
                or (e.get("卫星类"), e.get("父哈希")) in 名册父
            )
            if not 命中:
                违规.append({
                    "类型": "处置成功而名册空",
                    "证据编号": e.get("编号"),
                    "批号": e.get("批次编号"),
                    "卫星类": e.get("卫星类"),
                    "卫星键": e.get("卫星键"),
                    "错误父哈希": e.get("父哈希"),
                    "说明": "错挂处置已留证据但名册无对应行，重灌可被误放行",
                })
        有无落盘 = conn.execute("SELECT 1 FROM 装载批次 WHERE 编号=?", (e.get("批次编号"),)).fetchone()
        if 有无落盘 and 仍在禁:
            误落.append(e.get("批次编号"))
            违规.append({
                "类型": "名册禁写批仍半成功",
                "批号": e.get("批次编号"),
                "说明": "名册禁写批不得有正式装载批次（禁写须整票回滚）",
            })
        elif 有无落盘 and 码 != 禁写原因码:
            # 整票失败批同批号重跑：若同名册行已解除，属合法重试；未解除则误落。
            同批生效 = conn.execute(
                "SELECT 1 FROM 错挂隔离名册 WHERE 批号=? AND " + _生效,
                (e.get("批次编号"),),
            ).fetchone()
            if 同批生效:
                误落.append(e.get("批次编号"))
                违规.append({
                    "类型": "整票误落",
                    "批号": e.get("批次编号"),
                    "说明": "整票失败批名册未解除，不得有正式装载批次",
                })

    残留 = []
    for 卫星类, 引 in 父校验.卫星父引.items():
        for r in _安全查询(conn, f"SELECT {引['父列']} AS p FROM {引['卫星表']} WHERE 是否当前=1"):
            证 = 父校验.卫星父错挂(conn, 卫星类, r["p"])
            if 证:
                残留.append(证)
                违规.append({
                    "类型": "正式当前错挂",
                    "卫星类": 卫星类,
                    "父哈希": r["p"],
                    "说明": 证["原因"],
                })

    通过 = not 违规
    return {
        "口径": 口径,
        "只读": True,
        "是否通过": 通过,
        "名册行数": len(名册行),
        "生效禁写数": len(生效),
        "已解除数": len(已解),
        "禁写明细": 禁写明细,
        "分叉": 分叉,
        "已解": 已解,
        "违规": 违规,
        "正式当前错挂数": len(残留),
        "误落批次": sorted(set(x for x in 误落 if x)),
        "说明": (
            "名册写闸核证通过：生效禁写、已解、证据与正式表互证一致"
            if 通过
            else "名册写闸核证未通过：" + "；".join(
                f"{v.get('类型')}({v.get('批号') or v.get('编号') or v.get('卫星键') or ''})"
                for v in 违规[:6]
            )
        ),
    }
