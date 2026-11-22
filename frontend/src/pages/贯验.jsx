import React,{useEffect,useState} from "react";
import {递,取} from "../api.js";

export default function 贯验(){
  const [末,设末]=useState(null);
  const [史,设史]=useState([]);
  const [忙,设忙]=useState(false);
  const [挂父,设挂父]=useState(null);

  const 刷挂父=()=>取("/贯验/挂错父").then(设挂父);

  const 刷=async()=>{
    const 列=await 取("/贯验");
    设史(列);
    return 列;
  };
  useEffect(()=>{
    刷().then(列=>{
      if(列[0]) 设末({
        是否通过:!!列[0].是否通过,
        枢纽数:列[0].枢纽数,
        链接数:列[0].链接数,
        卫星当前数:列[0].卫星当前数,
        说明:列[0].说明,
        检项:null,
      });
    });
    刷挂父();
  },[]);

  const 跑=async()=>{
    设忙(true);
    try{
      const r=await 递("/贯验",{});
      设末(r);
      await 刷();
      await 刷挂父();
    } finally { 设忙(false); }
  };

  return (<div>
    <h1 className="题">贯验</h1>
    <p className="述">沿枢纽 → 链接 → 卫星贯穿互证：两端可解、卫星有父、同父无双当前。</p>
    <div className="行">
      <button onClick={跑} disabled={忙}>{忙?"贯验中…":"跑贯验"}</button>
      <button className="次" onClick={刷}>刷新履历</button>
      <button className="次" onClick={刷挂父}>刷新挂错父</button>
    </div>

    {!末 && <div className="空态">尚未跑过贯验，点上方按钮做一次全仓贯穿检查。</div>}

    {末 && <>
      <div className="裁决">
        <div className={`裁决旗 ${末.是否通过?"通":"败"}`}>
          <div className="标">{末.是否通过?"通过":"未过"}</div>
          <div className="辅">{末.说明}</div>
        </div>
        <div className="裁决数">
          <div className="卡"><b>{末.枢纽数}</b><span>枢纽</span></div>
          <div className="卡"><b>{末.链接数}</b><span>链接</span></div>
          <div className="卡"><b>{末.卫星当前数}</b><span>卫星当前</span></div>
        </div>
      </div>

      {末.检项?.length>0 && (
        <div className="段">
          <div className="段题">本轮检项</div>
          <div className="检列">
            {末.检项.map(x=>(
              <div className="检条" key={x.名}>
                <div className={`检点 ${x.通过?"通":"败"}`}>{x.通过?"✓":"!"}</div>
                <div className="检名">{x.名}</div>
                <div className="检说">{x.说明}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>}

    {挂父 && (
      <div className="段">
        <div className="段题">挂错父贯验 · 口径 {挂父.口径} · 写闸 {挂父.写闸口径}</div>
        <div className="裁决" style={{gridTemplateColumns:"minmax(160px,220px) 1fr"}}>
          <div className={`裁决旗 ${挂父.是否通过?"通":"败"}`}>
            <div className="标">{挂父.是否通过?"无残留":"有残留"}</div>
            <div className="辅">{挂父.证据?.说明}</div>
          </div>
          <div className="裁决数">
            <div className="卡"><b>{挂父.扫描当前卫星数}</b><span>扫描当前卫星</span></div>
            <div className="卡"><b>{挂父.残留错挂数}</b><span>残留错挂</span></div>
            <div className="卡"><b>{挂父.证据?.挂错父证据条数??0}</b><span>整票证据</span></div>
            <div className="卡"><b>{挂父.名册?.生效禁写数??0}</b><span>名册生效禁写</span></div>
            <div className="卡"><b>{挂父.写闸核证?.分叉?.length??0}</b><span>父已可解仍禁写</span></div>
          </div>
        </div>

        {挂父.写闸核证 && (
          <div className="检列" style={{marginTop:"0.65rem"}}>
            <div className="检条">
              <div className={`检点 ${挂父.写闸核证.是否通过?"通":"败"}`}>{挂父.写闸核证.是否通过?"✓":"!"}</div>
              <div className="检名">名册写闸核证（只读）</div>
              <div className="检说">{挂父.写闸核证.说明}</div>
            </div>
          </div>
        )}

        {挂父.写闸核证?.分叉?.length>0 && (
          <>
            <div className="段题" style={{marginTop:"0.9rem"}}>名册分叉（父已可解，甲口径仍禁写，须先解名册）</div>
            <table>
              <thead><tr><th>名册编号</th><th>卫星类</th><th>卫星键</th><th>错误父哈希</th><th>期望父类</th><th>说明</th></tr></thead>
              <tbody>{挂父.写闸核证.分叉.map(r=>(
                <tr key={r.编号}>
                  <td>{r.编号}</td>
                  <td>{r.卫星类}</td>
                  <td>{r.卫星键||"—"}</td>
                  <td className="哈希">{r.错误父哈希||"—"}</td>
                  <td>{r.期望父类}</td>
                  <td>{r.说明}</td>
                </tr>
              ))}</tbody>
            </table>
          </>
        )}

        {挂父.写闸核证?.已解?.length>0 && (
          <>
            <div className="段题" style={{marginTop:"0.9rem"}}>已解除名册行（解除后同键可重灌）</div>
            <table>
              <thead><tr><th>名册编号</th><th>批号</th><th>卫星类</th><th>卫星键</th><th>原因码</th><th>解除时刻</th><th>解除说明</th></tr></thead>
              <tbody>{挂父.写闸核证.已解.map(r=>(
                <tr key={r.编号}>
                  <td>{r.编号}</td>
                  <td>{r.批号}</td>
                  <td>{r.卫星类}</td>
                  <td>{r.卫星键||"—"}</td>
                  <td><span className="徽章 淡">{r.原因码||"—"}</span></td>
                  <td>{r.解除时刻||"—"}</td>
                  <td>{r.解除说明||"—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </>
        )}

        {挂父.写闸核证?.违规?.length>0 && (
          <>
            <div className="段题" style={{marginTop:"0.9rem"}}>写闸违规</div>
            <table>
              <thead><tr><th>类型</th><th>批号/编号</th><th>卫星类</th><th>卫星键</th><th>说明</th></tr></thead>
              <tbody>{挂父.写闸核证.违规.map((v,i)=>(
                <tr key={i}>
                  <td><span className="徽章 败">{v.类型}</span></td>
                  <td>{v.批号||v.编号||"—"}</td>
                  <td>{v.卫星类||"—"}</td>
                  <td>{v.卫星键||"—"}</td>
                  <td>{v.说明}</td>
                </tr>
              ))}</tbody>
            </table>
          </>
        )}

        {挂父.残留错挂?.length>0 && (
          <table>
            <thead><tr><th>卫星类</th><th>父哈希</th><th>期望父类</th><th>实际父类</th><th>原因</th></tr></thead>
            <tbody>{挂父.残留错挂.map((r,i)=>(
              <tr key={i}>
                <td>{r.卫星类}</td>
                <td className="哈希">{r.父哈希||"(空)"}</td>
                <td>{r.期望父类}</td>
                <td>{r.实际类||"—"}</td>
                <td>{r.原因}</td>
              </tr>
            ))}</tbody>
          </table>
        )}

        {挂父.证据?.最近证据?.length>0 ? (
          <>
            <div className="段题" style={{marginTop:"0.9rem"}}>整票失败证据（正式表零增量）</div>
            <table>
              <thead><tr><th>批次</th><th>装载日</th><th>卫星类</th><th>父哈希</th><th>期望父类</th><th>实际父类</th><th>原因</th><th>时刻</th></tr></thead>
              <tbody>{挂父.证据.最近证据.map(r=>(
                <tr key={r.编号}>
                  <td>{r.批次编号}</td>
                  <td>{r.装载日}</td>
                  <td>{r.卫星类}</td>
                  <td className="哈希">{r.父哈希||"(空)"}</td>
                  <td>{r.期望父类}</td>
                  <td>{r.实际父类||"—"}</td>
                  <td>{r.原因}</td>
                  <td>{r.时刻}</td>
                </tr>
              ))}</tbody>
            </table>
          </>
        ) : (
          <div className="空态">尚无挂错父记录，正式当前卫星父引用全部可解。</div>
        )}
      </div>
    )}

    <div className="段">
      <div className="段题">贯验履历</div>
      {!史.length ? <div className="空态">暂无记录</div> : (
        <table>
          <thead>
            <tr>
              <th>编号</th><th>时刻</th><th>枢纽</th><th>链接</th>
              <th>卫星当前</th><th>结果</th><th>说明</th>
            </tr>
          </thead>
          <tbody>
            {史.map(r=>(
              <tr key={r.编号}>
                <td>{r.编号}</td>
                <td>{r.时刻}</td>
                <td>{r.枢纽数}</td>
                <td>{r.链接数}</td>
                <td>{r.卫星当前数}</td>
                <td><span className={`徽章 ${r.是否通过?"通":"败"}`}>{r.是否通过?"通过":"未过"}</span></td>
                <td>{r.说明}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  </div>);
}
