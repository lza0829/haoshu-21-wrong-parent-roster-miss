状态 = "半截"


def 查名册(conn, 批号: str | None = None) -> dict:
    rows = []
    try:
        if 批号:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM 错挂隔离名册 WHERE 批号=?", (批号,)
            )]
        else:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM 错挂隔离名册 ORDER BY 编号 DESC LIMIT 50"
            )]
    except Exception:
        rows = []
    return {"名册": rows, "禁写": False}


def 名册禁写(_conn, _卫星键: str) -> bool:
    return False
