import React, { useEffect, useState } from "react";
import { 递, 取 } from "../api.js";

export default function 错挂名册() {
  const [名册, 设名册] = useState(null);
  const [核, 设核] = useState(null);
  const [err, 设Err] = useState("");
  const [忙, 设忙] = useState(false);

  const reload = async () => {
    设Err("");
    try {
      设名册(await 取("/贯验/错挂名册"));
      设核(await 取("/贯验/错挂名册/写闸"));
    } catch (e) {
      设Err(String(e.message || e));
    }
  };
  useEffect(() => { reload(); }, []);

  const 解 = async (编号) => {
    if (!window.confirm(`解除名册行 #${编号}？解除后同键可重新装载。`)) return;
    设忙(true);
    try {
      await 递("/贯验/错挂名册/解除", { 编号, 说明: "前端人工解除" });
      await reload();
    } catch (e) {
      设Err(String(e.message || e));
    } finally {
      设忙(false);
    }
  };

  const 行 = 名册?.名册 || [];
  const 禁写 = 名册?.禁写;

  return (
    <div>
      <h1 className="题">错挂隔离名册</h1>
      <p className="述">
        口径：<b>{名册?.口径 || "甲·隔离名册禁写"}</b>。名册未解除前，同键/同父卫星装载一律拒绝，
        即使现查父已可解；解除后才允许重灌写出。核证为只读，不改任何正式表。
      </p>
      {err && <pre className="码">{err}</pre>}

      <div className="行">
        <button className="次" onClick={reload}>刷新</button>
        <span className={`徽章 ${禁写 ? "败" : "通"}`}>{禁写 ? "禁写生效" : "无禁写"}</span>
        {名册 && <span className="徽章 淡">总 {名册.总行数} · 生效 {名册.生效禁写数} · 已解 {名册.已解除数}</span>}
      </div>

      {核 && (
        <div className="段">
          <div className="段题">写闸核证 · 只读</div>
          <div className="裁决" style={{ gridTemplateColumns: "minmax(160px,220px) 1fr" }}>
            <div className={`裁决旗 ${核.是否通过 ? "通" : "败"}`}>
              <div className="标">{核.是否通过 ? "互证通过" : "核证未过"}</div>
              <div className="辅">{核.说明}</div>
            </div>
            <div className="裁决数">
              <div className="卡"><b>{核.生效禁写数}</b><span>生效禁写</span></div>
              <div className="卡"><b>{核.分叉?.length ?? 0}</b><span>父已可解仍禁写</span></div>
              <div className="卡"><b>{核.违规?.length ?? 0}</b><span>违规</span></div>
            </div>
          </div>

          {核.分叉?.length > 0 && (
            <>
              <div className="段题" style={{ marginTop: "0.9rem" }}>名册分叉（父已可解但仍禁写，须先解名册）</div>
              <table>
                <thead><tr><th>名册编号</th><th>卫星类</th><th>卫星键</th><th>错误父哈希</th><th>期望父类</th><th>说明</th></tr></thead>
                <tbody>{核.分叉.map((r) => (
                  <tr key={r.编号}>
                    <td>{r.编号}</td><td>{r.卫星类}</td><td>{r.卫星键}</td>
                    <td className="哈希">{r.错误父哈希 || "—"}</td><td>{r.期望父类}</td><td>{r.说明}</td>
                  </tr>
                ))}</tbody>
              </table>
            </>
          )}

          {核.违规?.length > 0 && (
            <>
              <div className="段题" style={{ marginTop: "0.9rem" }}>违规</div>
              <table>
                <thead><tr><th>类型</th><th>批号/编号</th><th>卫星类</th><th>卫星键</th><th>说明</th></tr></thead>
                <tbody>{核.违规.map((v, i) => (
                  <tr key={i}>
                    <td><span className="徽章 败">{v.类型}</span></td>
                    <td>{v.批号 || v.编号 || "—"}</td>
                    <td>{v.卫星类 || "—"}</td>
                    <td>{v.卫星键 || "—"}</td>
                    <td>{v.说明}</td>
                  </tr>
                ))}</tbody>
              </table>
            </>
          )}
        </div>
      )}

      <div className="段">
        <div className="段题">名册行 · {行.length}</div>
        {!行.length ? <div className="空态">名册为空，尚无错挂登记。</div> : (
          <table>
            <thead>
              <tr>
                <th>编号</th><th>批号</th><th>卫星类</th><th>卫星键</th><th>错误父哈希</th>
                <th>期望父类</th><th>原因码</th><th>处置</th><th>时刻</th><th>操作</th>
              </tr>
            </thead>
            <tbody>{行.map((r) => {
              const 生效 = r.处置 === "隔离" && !r.解除时刻;
              return (
                <tr key={r.编号}>
                  <td>{r.编号}</td>
                  <td>{r.批号}</td>
                  <td>{r.卫星类}</td>
                  <td>{r.卫星键 || "—"}</td>
                  <td className="哈希">{r.错误父哈希 || "—"}</td>
                  <td>{r.期望父类}</td>
                  <td><span className="徽章 淡">{r.原因码 || "—"}</span></td>
                  <td><span className={`徽章 ${生效 ? "败" : "通"}`}>{r.处置}</span></td>
                  <td>{r.时刻}</td>
                  <td>{生效
                    ? <button className="次" disabled={忙} onClick={() => 解(r.编号)}>解除</button>
                    : <span className="讯" style={{ margin: 0 }}>{r.解除说明 || "已解除"}</span>}
                  </td>
                </tr>
              );
            })}</tbody>
          </table>
        )}
      </div>

      <pre className="码">{名册 ? JSON.stringify(名册, null, 2) : "（空）"}</pre>
    </div>
  );
}
