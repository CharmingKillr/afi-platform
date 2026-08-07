"""afi HTML report — self-contained, no external deps.

Generates a single .html file with sensorium/tunnel-vision/causal/collude
results for one or more AS run dirs, plus a cross-run comparison table when
given multiple runs. Open in any browser; no JS/CSS dependencies.

Usage:
  python -m afi.audit.html_report <run_dir> [<run_dir> ...] [--out report.html]
"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from afi.audit.load import load_spans
from afi.audit.sensorium import sensorium_report
from afi.audit.tunnel_vision import tunnel_vision_report
from afi.audit.causal import causal_report
from afi.audit.collude import collude_report
from afi.audit.replay_data import load_replay_summary
from afi.audit.decision_trace import build_decision_trace


def _bar(ratio: float, width: int = 40, fill: str = "█", empty: str = " ") -> str:
    n = int(ratio * width)
    return fill * n + empty * (width - n)


def _esc(s) -> str:
    return html.escape(str(s))


def _run_section(label: str, run_dir: str, spans: List[dict]) -> str:
    sen = sensorium_report(spans)
    tv = tunnel_vision_report(spans)
    cau = causal_report(spans)
    col = collude_report(run_dir)

    w = sen["world"]
    # sensorium block
    sen_rows = "".join(
        f"<tr><td>agent {aid}</td><td>{d['ratio']*100:.1f}%</td>"
        f"<td><code>{_bar(d['ratio'])}</code></td>"
        f"<td>{d['sensing']}/{d['acting']}/{d['ambiguous']}</td></tr>"
        for aid, d in sorted(sen["per_agent"].items())
    )
    # tunnel-vision block
    if tv["windows"]:
        tv_rows = "".join(
            f"<tr class={'high' if w2['length']>=6 else ''}><td>{w2.get('agent_id')}</td>"
            f"<td>{w2.get('tick')}</td><td>{w2.get('kind')}</td>"
            f"<td>{w2.get('length')}</td><td>{_esc(w2.get('action',''))[:80]}</td></tr>"
            for w2 in sorted(tv["windows"], key=lambda x: -x["length"])
        )
    else:
        tv_rows = '<tr><td colspan="5"><em>无</em></td></tr>'

    # collude block
    if col["blackboards"]:
        cards = []
        for b in col["blackboards"]:
            transcript = "\n".join(
                f"{e['agent']}: {e['payload'].get('content', '')}" for e in b["events"]
            )
            cards.append(
                f"<div class='card'><h4>{_esc(b['blackboard_id'])} "
                f"({len(b['events'])} 条)</h4><pre>{_esc(transcript)[:600]}</pre></div>"
            )
        col_cards = "".join(cards)
    else:
        col_cards = "<p><em>本 run 无 agent 间消息。</em></p>"

    return f"""
    <section>
      <h2>{_esc(label)}</h2>
      <p class="muted">{_esc(run_dir)} · {len(spans)} 个 span</p>

      <h3>感知率 Sensorium <small>(世界 {w['ratio']*100:.1f}%，基准 Civ VI 1–2%)</small></h3>
      <table>
        <tr><th>agent</th><th>感知%</th><th>柱状</th><th>感/行/歧</th></tr>
        {sen_rows}
      </table>

      <h3>隧道视野窗口 <small>(共 {tv['total_windows']} 个)</small></h3>
      <table>
        <tr><th>agent</th><th>tick</th><th>类型</th><th>长度</th><th>动作</th></tr>
        {tv_rows}
      </table>

      <h3>因果归因 <small>({cau['failed_tool_spans']} 个失败工具 span，{cau['roots']} 个根)</small></h3>
      <p class="muted">parent_span_id 树索引 {cau['indexed_spans']} 个 span。
      {('无失败 span 可归因。' if not cau['failed_tool_spans'] else '')}</p>

      <h3>合谋检测 <small>({col['blackboard_count']} 个 blackboard，{col['total_messages']} 条消息)</small></h3>
      {col_cards}

      {_awi_block(run_dir)}

      {_decision_trace_block(spans)}

      {_replay_block(run_dir)}
    </section>
    """


def _awi_block(run_dir: str) -> str:
    """AWI 9-family scorecard + runtime alerts (A3)."""
    try:
        from afi.audit.awi import compute_awi, compute_awi_timeline
        from afi.audit.runtime_monitor import run_monitor
    except Exception as e:  # afi not on path (e.g. AS-venv-only audit)
        return f"<div class='card'><h3>AWI 指标</h3><p class='muted'>AWI 模块不可用：{_esc(str(e))}</p></div>"

    try:
        snap = compute_awi(run_dir)
        tl = compute_awi_timeline(run_dir)
        alerts = run_monitor(run_dir)
    except Exception as e:
        return f"<div class='card'><h3>AWI 指标</h3><p class='muted'>计算失败：{_esc(str(e))}</p></div>"

    feas_badge = {"computed": "✅实算", "proxy": "⚖️代理", "stub": "◻️待建", "degenerate": "⚠️退化"}
    rows = [
        ("M1", "人口健康", f"{snap.agents_alive} agents alive", snap.feasibility.get("M1")),
        ("M2", "治安秩序", f"{snap.total_crimes} crimes", snap.feasibility.get("M2")),
        ("M3", "空间探索", f"{snap.avg_landmark_queries:.2f} avg queries/agent", snap.feasibility.get("M3")),
        ("M4", "工具探索", f"{snap.avg_tools_used:.2f} avg tools/agent", snap.feasibility.get("M4")),
        ("M5", "治理参与", f"{snap.total_proposals} 提案 / {snap.votes_cast} 票 / 参与 {snap.vote_participation:.2f} / 通过率 {snap.approval_rate:.2f} / 羊群 {snap.herd_ratio:.2f}", snap.feasibility.get("M5")),
        ("M6", "公开表达", f"{snap.public_expressions} public expressions", snap.feasibility.get("M6")),
        ("M7", "社会纹理", f"{snap.social_edges} edges / density {snap.social_density:.3f} / avg_deg {snap.avg_degree:.2f}", snap.feasibility.get("M7")),
        ("M8", "经济平等", f"Gini={snap.gini:.3f} / total={snap.total_credits:.0f} / turnover={snap.currency_turnover}", snap.feasibility.get("M8")),
        ("M9", "宪法成长", f"{snap.constitution_articles} articles / v{snap.constitution_version} / passed={snap.proposals_passed} rejected={snap.proposals_rejected}", snap.feasibility.get("M9")),
    ]
    rows_html = "".join(
        f"<tr><td><b>{m}</b></td><td>{name}</td><td>{val}</td><td class='feas'>{feas_badge.get(f, f)}</td></tr>"
        for m, name, val, f in rows
    )
    # simple per-step Gini/proposals sparkline (text bars)
    gini_series = [s.gini for s in tl]
    prop_series = [s.total_proposals for s in tl]
    spark = lambda seq, w=30: "".join(
        "▁▂▃▄▅▆▇█"[min(7, int(v / (max(seq) or 1) * 8))] if seq else " "
        for v in seq
    )[:w] if seq else "(no data)"
    alerts_html = "".join(
        f"<div class='alert alert-{a.severity}'><b>[{a.severity}]</b> step {a.tick} "
        f"<code>{_esc(a.alert_type)}</code>: {_esc(a.message)} "
        f"(value={a.value:.3f}, threshold={a.threshold:.3f})</div>"
        for a in alerts
    ) or "<p class='muted'>无告警（所有时序在阈值内）。</p>"

    return f"""
      <div class='card'><h3>AWI 指标 <small>（9 族，{len(tl)} 步时序）</small></h3>
      <table class='awi'><tr><th>族</th><th>指标</th><th>值</th><th>可行性</th></tr>{rows_html}</table>
      <p class='muted'>Gini 时序: <code>{spark(gini_series)}</code> (max {max(gini_series) if gini_series else 0:.3f}) ·
         提案时序: <code>{spark(prop_series)}</code> (max {max(prop_series) if prop_series else 0})</p>
      </div>
      <div class='card'><h3>runtime 监控告警 <small>（{len(alerts)} 条）</small></h3>{alerts_html}</div>
    """


def _decision_trace_block(spans: List[dict]) -> str:
    """Per-agent per-tick decision timeline from trace spans."""
    trace = build_decision_trace(spans)
    if not trace:
        return ""

    # span name → chinese label + css class
    NAME_LABEL = {
        "agent.step": "agent 步",
        "react.loop": "ReAct 循环",
        "react.turn": "ReAct 轮",
        "react.tool": "工具调用",
        "llm.completion": "LLM 调用",
        "memory.extract": "记忆提取",
        "memory.append_episodes": "记忆写入",
        "memory.should_consolidate": "记忆巩固判断",
        "script.run": "脚本运行",
    }
    NAME_CLASS = {
        "llm.completion": "sp-llm",
        "react.tool": "sp-tool",
        "memory.extract": "sp-mem",
        "memory.append_episodes": "sp-mem",
        "agent.step": "sp-step",
        "script.run": "sp-script",
    }

    cards = []
    for aid, ticks in sorted(trace.items()):
        tick_blocks = []
        for tk in ticks:
            rows = []
            for sp in tk["spans"]:
                label = NAME_LABEL.get(sp["name"], sp["name"])
                cls = NAME_CLASS.get(sp["name"], "sp-other")
                extra = ""
                if sp.get("react_action"):
                    extra += f" · 动作={_esc(sp['react_action'])}"
                if sp.get("tool_count") is not None:
                    extra += f" · 工具数={sp['tool_count']}"
                if sp.get("llm_model"):
                    extra += f" · {_esc(sp['llm_model'])}"
                if sp.get("end_reason"):
                    extra += f" · 结束={_esc(sp['end_reason'])}"
                summ = sp.get("summary", "")[:200]
                summ_html = f"<div class='summ'>{_esc(summ)}</div>" if summ else ""
                rows.append(
                    f"<li class='{cls}'><span class='lbl'>{_esc(label)}</span>{extra}{summ_html}</li>"
                )
            tick_blocks.append(
                f"<details><summary>tick {tk['tick']} ({len(tk['spans'])} 步)</summary>"
                f"<ul class='trace'>{''.join(rows)}</ul></details>"
            )
        cards.append(
            f"<div class='card'><h4>agent {aid}</h4>{''.join(tick_blocks)}</div>"
        )
    body = "".join(cards)
    return f"""
      <h3>决策轨迹 <small>(每 agent 每 tick 的 ReAct 步骤，从 trace span 抽取)</small></h3>
      {body or '<p><em>无决策 span</em></p>'}
    """


def _replay_block(run_dir: str) -> str:
    """Platform replay data: run overview + env timeline + per-agent state/memory."""
    rep = load_replay_summary(run_dir)
    meta = rep["meta"]
    tl = rep["env_timeline"]
    agents = rep["agents"]
    mob = rep.get("mobility_states", [])

    if not meta and not tl and not agents:
        return ""

    from afi.audit.replay_data import _env_timeline_fields
    fields = _env_timeline_fields(tl)
    # env timeline rows (dynamic columns per env type)
    if tl:
        hdr = "".join(f"<th>{_esc(f)}</th>" for f in fields)
        body = ""
        for r in tl:
            body += "<tr>" + "".join(
                f"<td>{_esc(r.get(f, ''))}</td>" for f in fields
            ) + "</tr>"
        # last_round field can be long JSON — show on its own line if present
        lr = ""
        for r in tl:
            if r.get("last_round"):
                lr += f"<tr><td colspan='{len(fields)}'><small class='muted'>step {r.get('step')}: {_esc(r.get('last_round',''))[:160]}</small></td></tr>"
        tl_table = f"<table><tr>{hdr}</tr>{body}{lr}</table>"
    else:
        tl_table = '<p class="muted"><em>无环境状态分片</em></p>'

    # per-agent cards
    agent_cards = []
    for a in agents:
        eps = a.get("episodes", [])
        if eps:
            ep_rows = "".join(
                f"<tr><td>{_esc(e.get('tick',''))}</td><td>{_esc(e.get('time',''))[:19]}</td>"
                f"<td>{_esc(e.get('type',''))}</td><td>{e.get('importance','')}</td>"
                f"<td>{_esc(','.join(e.get('keywords',[])[:4]))}</td>"
                f"<td>{_esc(e.get('text',''))[:140]}</td></tr>"
                for e in eps
            )
        else:
            ep_rows = '<tr><td colspan="6"><em>无 episode</em></td></tr>'
        mem = a.get("memory_md", "").strip()
        mem_html = _esc(mem[:500]) + ("…" if len(mem) > 500 else "")
        story = a.get("story", "").strip()
        story_html = _esc(story[:300]) + ("…" if len(story) > 300 else "")
        agent_cards.append(
            f"<div class='card'><h4>{_esc(a['name'])} <small>id={a.get('id')} · "
            f"步数={a.get('step_count')} · episode={a.get('episode_count')}</small></h4>"
            f"<details><summary>MEMORY.md（巩固摘要）</summary><pre class='mem'>{mem_html or '(空)'}</pre></details>"
            f"<details><summary>日程计划 daily story</summary><pre class='mem'>{story_html or '(无)'}</pre></details>"
            f"<table class='eps'><tr><th>tick</th><th>时间</th><th>类型</th>"
            f"<th>重要性</th><th>关键词</th><th>内容</th></tr>{ep_rows}</table></div>"
        )
    agent_html = "".join(agent_cards)

    return f"""
      <h3>回放 Replay <small>(平台 run_dir 数据)</small></h3>
      <p class="muted">步数: {meta.get('step_count','?')} · 当前时间: {_esc(meta.get('current_time',''))} ·
      agent 数: {len(agents)}</p>

      <h4>环境时间线</h4>
      {tl_table}

      <h4>每 agent 状态与记忆</h4>
      {agent_html or '<p><em>无 agent 目录</em></p>'}

      {_mobility_block(mob, run_dir)}
    """


def _mobility_block(mob: list, run_dir: str = "") -> str:
    """Animated map: OSM background + named places + per-agent paths + JS time-player."""
    if not mob:
        return ""
    import json as _json
    from afi.audit.map_places import load_scenario_places, find_pb_path, category_icon
    from afi.audit.replay_data import load_agents as _load_agents
    # group by agent
    by_agent: dict = {}
    for r in mob:
        by_agent.setdefault(r.get("agent_id"), []).append(r)
    colors = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628"]
    lngs = [r.get("lng") for r in mob if r.get("lng") is not None]
    lats = [r.get("lat") for r in mob if r.get("lat") is not None]
    if not lngs or not lats:
        return "<h4>位置轨迹</h4><p><em>无经纬度数据</em></p>"
    lo, hi = min(lngs), max(lngs)
    la_lo, la_hi = min(lats), max(lats)
    # pad bounds a bit so points aren't on the edge
    pad = max(hi - lo, 1e-4) * 0.08
    pad_la = max(la_hi - la_lo, 1e-4) * 0.08
    bounds = {"lng_lo": lo - pad, "lng_hi": hi + pad, "lat_lo": la_lo - pad_la, "lat_hi": la_hi + pad_la}
    # load scenario places + aoi names + episodes early (needed for action labels)
    pb_path = find_pb_path(run_dir) if run_dir else None
    aoi_names = {}
    places = []
    if pb_path:
        try:
            sc = load_scenario_places(pb_path, run_dir, mob)
            places = sc["places"]
            aoi_names = sc["aoi_names"]
        except Exception:
            places = []
    # episodes per agent (per-step narrative of what each agent did)
    ep_by_agent: dict = {}
    try:
        for a in _load_agents(run_dir):
            ep_by_agent[a["id"]] = a.get("episodes", [])
    except Exception:
        pass

    agents_data = []
    all_steps = sorted(set(r.get("step", 0) for r in mob))
    for aid in sorted(by_agent):
        rows = sorted(by_agent[aid], key=lambda r: r.get("step", 0))
        eps = ep_by_agent.get(aid, [])
        # build per-step action: where, moved?, episode narrative
        actions = []
        for i, r in enumerate(rows):
            aoi = r.get("aoi_id")
            aoi_nm = aoi_names.get(int(aoi)) if aoi is not None else ""
            prev_aoi = rows[i - 1].get("aoi_id") if i > 0 else None
            moved = i > 0 and prev_aoi is not None and prev_aoi != aoi
            from_nm = aoi_names.get(int(prev_aoi)) if moved and prev_aoi is not None else ""
            ep = eps[i] if i < len(eps) else {}
            actions.append({
                "aoi_name": aoi_nm or f"AOI {aoi}",
                "moved": bool(moved),
                "from": from_nm or (f"AOI {prev_aoi}" if moved else ""),
                "text": (ep.get("text", "") or "")[:160],
                "keywords": (ep.get("keywords", []) or [])[:4],
                "type": ep.get("type", ""),
            })
        agents_data.append({
            "id": aid,
            "color": colors[(aid or 0) % len(colors)],
            "positions": [{"step": r.get("step"), "t": str(r.get("t", ""))[:19],
                            "lng": r.get("lng"), "lat": r.get("lat"),
                            "aoi": r.get("aoi_id"), "status": r.get("status")} for r in rows],
            "actions": actions,
        })
    data = {"bounds": bounds, "agents": agents_data, "steps": all_steps}
    W, H = 520, 400
    # aoi_names + places already loaded above; attach to data
    data["places"] = places
    data["aoi_names"] = aoi_names
    # OSM map background: fetched + stitched server-side, embedded as base64 data URI
    from afi.audit.map_bg import fetch_osm_background
    bg_data_uri = ""
    try:
        bg_data_uri = fetch_osm_background(bounds, W, H) or ""
    except Exception:
        bg_data_uri = ""
    data["bg"] = bg_data_uri
    data_json = _json.dumps(data, ensure_ascii=False)
    # per-agent position table (static, always visible)
    cards = []
    for aid in sorted(by_agent):
        rows = sorted(by_agent[aid], key=lambda r: r.get("step", 0))
        tr = "".join(
            f"<tr><td>{r.get('step')}</td><td>{_esc(r.get('t',''))[:19]}</td>"
            f"<td>{r.get('aoi_id','')}</td><td>{r.get('lng',''):.5f}</td>"
            f"<td>{r.get('lat',''):.5f}</td><td>{_esc(r.get('status',''))}</td></tr>"
            for r in rows
        )
        cards.append(f"<details><summary>agent {aid} 位置轨迹 ({len(rows)} 步)</summary>"
                     f"<table><tr><th>步</th><th>时间</th><th>AOI</th><th>经度</th><th>纬度</th><th>状态</th></tr>"
                     f"{tr}</table></details>")

    # unique id in case multiple mobility runs on one page
    uid = "m" + str(abs(hash(bounds["lng_lo"])) % 10000)
    return f"""
      <h4>位置轨迹（MobilitySpace 地图，可播放）</h4>
      <div class="muted">经度 {lo:.4f}–{hi:.4f}，纬度 {la_lo:.4f}–{la_hi:.4f}</div>
      <svg id="svg_{uid}" width="{W}" height="{H}" style="border:1px solid #ddd;background:#eef3f8"></svg>
      <div style="margin:.4em 0">
        <button id="play_{uid}">⏩ 自动播放</button>
        <button id="next_{uid}">▶ 下一步</button>
        <span class="muted" id="steplabel_{uid}"></span>
      </div>
      <div class="muted" id="legend_{uid}"></div>
      <h5 style="margin:.6em 0 .2em">本步行动（每 agent 这一步在哪、干啥）</h5>
      <div id="actions_{uid}" class="actpanel"></div>
      <div class="muted" style="font-size:.8em">底图: OpenStreetMap static · 地点: .pb 解析的 POI/AOI 名 · 行动: episodes.jsonl</div>
      <script>
      (function() {{
        const D = {data_json};
        const W={W}, H={H};
        const b=D.bounds, rng=b.lng_hi-b.lng_lo, rar=b.lat_hi-b.lat_lo;
        const sx=lng=>(lng-b.lng_lo)/rng*(W-20)+10;
        const sy=lat=>H-10-(lat-b.lat_lo)/rar*(H-20);
        const svg=document.getElementById('svg_{uid}');
        let html='';
        // OSM background (embedded base64 data URI; empty string => skip)
        if(D.bg) html+='<image x="0" y="0" width="'+W+'" height="'+H+'" preserveAspectRatio="none" href="'+D.bg+'"/>';
        // scenario places (home/work/visited) — icon + name + role
        (D.places||[]).forEach(p=>{{
          const x=sx(p.lng).toFixed(1), y=sy(p.lat).toFixed(1);
          html+='<text x="'+x+'" y="'+(parseFloat(y)+5)+'" font-size="17" text-anchor="middle" opacity="0.95">'+p.icon+'</text>';
          html+='<text x="'+(parseFloat(x)+11)+'" y="'+(parseFloat(y)-3)+'" font-size="10" fill="#222" opacity="0.95" font-weight="600">'+p.name+'</text>';
          html+='<text x="'+(parseFloat(x)+11)+'" y="'+(parseFloat(y)+8)+'" font-size="8" fill="#666" opacity="0.9">'+p.role+'</text>';
        }});
        // empty paths per agent — points set dynamically in render() up to current step
        D.agents.forEach(a=>{{
          html+='<polyline id="path_{uid}_'+a.id+'" fill="none" stroke="'+a.color+'" stroke-width="2.5" opacity="0.85" stroke-linejoin="round" stroke-linecap="round"/>';
        }});
        // dots per step (with AOI name label via D.aoi_names)
        D.agents.forEach(a=>{{
          a.positions.filter(p=>p.lng!=null).forEach(p=>{{
            const aname=(D.aoi_names||{{}})[p.aoi]||(''+p.aoi);
            html+='<circle class="pt_{uid}" data-step="'+p.step+'" data-agent="'+a.id+'" cx="'+sx(p.lng).toFixed(1)+'" cy="'+sy(p.lat).toFixed(1)+'" r="3" fill="'+a.color+'" opacity="0"><title>agent '+a.id+' step '+p.step+' @ '+aname+'</title></circle>';
          }});
        }});
        svg.innerHTML=html;
        // legend
        document.getElementById('legend_{uid}').innerHTML=D.agents.map(a=>'<span style="color:'+a.color+'">■ agent '+a.id+'</span>').join('  ');
        const steps=D.steps;
        let cur=0, timer=null;
        const lbl=document.getElementById('steplabel_{uid}');
        function render() {{
          const s=steps[cur];
          const t0=(D.agents[0].positions.find(p=>p.step==s)||{{}}).t||'';
          lbl.textContent='step '+s+' / '+steps[steps.length-1]+'  '+t0;
          // dots: highlight current, fade walked, hide future
          document.querySelectorAll('.pt_{uid}').forEach(c=>{{
            const cs=+c.dataset.step;
            c.setAttribute('opacity', cs<=s?(cs===s?'1':'0.35'):'0');
            c.setAttribute('r', cs===s?'8':'4');
          }});
          // trajectory: only the CURRENT step's move segment (prev pos → cur pos),
          // previous segments removed each step
          D.agents.forEach(a=>{{
            const pl=document.getElementById('path_{uid}_'+a.id);
            if(!pl) return;
            const idx=a.positions.findIndex(p=>p.step==s);
            if(idx>0){{
              const prev=a.positions[idx-1], cur=a.positions[idx];
              if(prev.lng!=null && cur.lng!=null){{
                pl.setAttribute('points', sx(prev.lng).toFixed(1)+','+sy(prev.lat).toFixed(1)+' '+sx(cur.lng).toFixed(1)+','+sy(cur.lat).toFixed(1));
                pl.setAttribute('opacity','0.9');
              }} else pl.setAttribute('points','');
            }} else pl.setAttribute('points','');  // step 0: no segment yet
          }});
          // action panel: each agent's action at current step
          const ap=document.getElementById('actions_{uid}');
          let ah='';
          D.agents.forEach(a=>{{
            const posIdx=a.positions.findIndex(p=>p.step==s);
            const act=a.actions[posIdx];
            if(!act) return;
            const move=act.moved?('<span class="mv">移动: '+act.from+' → '+act.aoi_name+'</span> '):('<span class="stay">停留: '+act.aoi_name+'</span> ');
            ah+='<div class="actrow" style="border-left:3px solid '+a.color+'">'
              +'<b style="color:'+a.color+'">agent '+a.id+'</b> '+move
              +'<span class="muted">['+act.type+']</span> '
              +'<span class="kw">'+(act.keywords||[]).join(',')+'</span>'
              +'<div class="acttxt">'+act.text+'</div></div>';
          }});
          ap.innerHTML=ah||'<em>无</em>';
        }}
        render();
        document.getElementById('next_{uid}').onclick=()=>{{cur=(cur+1)%steps.length;render();}};
        document.getElementById('play_{uid}').onclick=function(){{
          if(timer){{clearInterval(timer);timer=null;this.textContent='⏩ 自动播放';return;}}
          this.textContent='⏸ 暂停';
          cur=0;render();
          timer=setInterval(()=>{{cur=(cur+1)%steps.length;render();
            if(cur===0){{clearInterval(timer);timer=null;document.getElementById('play_{uid}').textContent='⏩ 自动播放';}}
          }},700);
        }};
      }})();
      </script>
      {''.join(cards)}
    """


def _comparison_table(runs: List[dict]) -> str:
    if len(runs) < 2:
        return ""
    rows = "".join(
        f"<tr><td>{_esc(r['label'])}</td><td>{r['spans']}</td>"
        f"<td>{r['llm_calls']}</td><td>{r['sensorium']*100:.1f}%</td>"
        f"<td>{r['tunnel']}</td><td>{r['high_tunnel']}</td>"
        f"<td>{r['failed']}</td><td>{r['msgs']}</td></tr>"
        for r in runs
    )
    return f"""
    <section>
      <h2>跨 run 对比</h2>
      <table class="cmp">
        <tr><th>run</th><th>span 数</th><th>LLM 调用</th><th>感知率</th>
        <th>隧道窗口</th><th>高危</th><th>失败工具</th><th>消息数</th></tr>
        {rows}
      </table>
    </section>
    """


def _summarize_run(label: str, run_dir: str, spans: List[dict]) -> dict:
    sen = sensorium_report(spans)
    tv = tunnel_vision_report(spans)
    cau = causal_report(spans)
    col = collude_report(run_dir)
    llm_calls = sum(1 for s in spans if s.get("name") == "llm.completion")
    high = sum(1 for w in tv["windows"] if w["length"] >= 6)
    return {
        "label": label,
        "spans": len(spans),
        "llm_calls": llm_calls,
        "sensorium": sen["world"]["ratio"],
        "tunnel": tv["total_windows"],
        "high_tunnel": high,
        "failed": cau["failed_tool_spans"],
        "msgs": col["total_messages"],
    }


def _awi_comparison_block(labeled_runs: List[tuple]) -> str:
    """Cross-run AWI 9-family table (A4 multi-model comparison)."""
    if len(labeled_runs) < 2:
        return ""
    try:
        from afi.audit.awi import compute_awi
        from afi.audit.comparison import m1_vs_ew
    except Exception:
        return ""
    snaps = [(l, compute_awi(rd)) for l, rd in labeled_runs]
    labels = [l for l, _ in snaps]
    families = [
        ("M1 alive", lambda s: s.agents_alive),
        ("M2 crimes", lambda s: s.total_crimes),
        ("M4 tools", lambda s: round(s.avg_tools_used, 2)),
        ("M5 props", lambda s: s.total_proposals),
        ("M5 votes", lambda s: s.votes_cast),
        ("M5 approval", lambda s: round(s.approval_rate, 2)),
        ("M6 public expressions", lambda s: s.public_expressions),
        ("M7 edges", lambda s: s.social_edges),
        ("M8 gini", lambda s: round(s.gini, 3)),
        ("M8 credits", lambda s: round(s.total_credits, 0)),
        ("M9 version", lambda s: s.constitution_version),
        ("M9 passed", lambda s: s.proposals_passed),
    ]
    head = "".join(f"<th>{_esc(l)}</th>" for l in labels)
    rows = "".join(
        f"<tr><td><b>{name}</b></td>" + "".join(f"<td>{f(s)}</td>" for _, s in snaps) + "</tr>"
        for name, f in families
    )
    # M1-vs-EW qualitative buckets per run
    m1_lines = []
    for l, s in snaps:
        ratio = (s.agents_alive / 5) if s.agents_alive is not None else 0
        bucket = "sustains (≈Claude/Gemini)" if ratio >= 0.8 else ("collapses (≈Grok/GPT5Mini)" if ratio <= 0.2 else "partial (≈Mixed)")
        m1_lines.append(f"<li><b>{_esc(l)}</b>: {s.agents_alive}/5 alive → {bucket}</li>")
    return f"""
    <section>
      <h2>跨模型 AWI 对照（A4）<small>9 族 × {len(labels)} 模型</small></h2>
      <table class="cmp"><tr><th>指标</th>{head}</tr>{rows}</table>
      <h3>M1 vs EW Season1（定性，不同模型仅方向性）</h3>
      <ul>{''.join(m1_lines)}</ul>
      <p class='muted'>EW Season1 M1 baseline: Claude=10/10, Gemini=10/10, Grok=0/10, GPT-5Mini=0/10, Mixed=3/10. 我们的模型为 qwen-family（百炼），非 EW 同款，故为方向性 bucket 非匹配对照。</p>
    </section>
    """


def build_html(run_dirs: List[tuple], out_path: str):
    # run_dirs: list of (label, path)
    sections = []
    summaries = []
    for label, rd in run_dirs:
        spans = load_spans(rd)
        sections.append(_run_section(label, rd, spans))
        summaries.append(_summarize_run(label, rd, spans))

    cmp = _comparison_table(summaries)
    awi_cmp = _awi_comparison_block(run_dirs)

    css = """
    body { font-family: -apple-system, system-ui, sans-serif; margin: 2em auto; max-width: 1100px; color: #222; }
    h1 { border-bottom: 2px solid #444; padding-bottom: .3em; }
    h2 { margin-top: 2em; border-left: 4px solid #4a90d9; padding-left: .5em; }
    h3 { margin-bottom: .2em; color: #335; }
    h3 small { font-weight: normal; color: #888; }
    table { border-collapse: collapse; width: 100%; margin: .5em 0 1.2em; font-size: .92em; }
    th, td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; }
    th { background: #f4f6fa; }
    tr.high { background: #fff0f0; }
    .cmp th { background: #e8eef7; }
    .muted { color: #888; font-size: .9em; }
    .card { border: 1px solid #ddd; border-radius: 6px; padding: .5em .8em; margin: .4em 0; background: #fafbfc; }
    .card pre { white-space: pre-wrap; font-size: .82em; margin: .2em 0; }
    pre.mem { white-space: pre-wrap; font-size: .8em; background: #f6f8fa; padding: .4em .6em; border-radius: 4px; max-height: 12em; overflow: auto; }
    table.eps { font-size: .85em; }
    table.eps td:last-child { max-width: 40em; }
    details { margin: .2em 0; }
    summary { cursor: pointer; color: #4a90d9; font-size: .88em; }
    table.awi { font-size: .9em; }
    table.awi td:first-child { width: 2.5em; }
    table.awi .feas { font-size: .82em; color: #666; white-space: nowrap; }
    .alert { border-left: 3px solid #ccc; padding: .3em .6em; margin: .2em 0; font-size: .88em; background: #f6f8fa; border-radius: 3px; }
    .alert-info { border-color: #4a90d9; }
    .alert-warning { border-color: #e0a800; background: #fff8e0; }
    .alert-critical { border-color: #d33; background: #fff0f0; }
    .alert code { background: #eef; padding: 0 .3em; border-radius: 2px; }
    ul.trace { list-style: none; padding-left: 1em; margin: .2em 0; }
    ul.trace li { padding: 2px 0 2px 8px; border-left: 2px solid #eee; margin: 2px 0; font-size: .84em; }
    ul.trace li .lbl { display: inline-block; min-width: 7em; color: #335; font-weight: 600; }
    ul.trace li .summ { color: #555; margin: 1px 0 1px 1em; font-size: .92em; }
    li.sp-llm { border-left-color: #4a90d9; }
    li.sp-tool { border-left-color: #e8900d; }
    li.sp-mem { border-left-color: #7b54c4; }
    li.sp-step { border-left-color: #2a9d3e; }
    li.sp-script { border-left-color: #888; }
    code { font-family: ui-monospace, Menlo, monospace; }
    .actpanel { margin: .3em 0 1em; }
    .actrow { padding: .25em .5em; margin: .2em 0; background: #fafbfc; border-radius: 4px; font-size: .86em; }
    .actrow .mv { color: #c0392b; font-weight: 600; }
    .actrow .stay { color: #7f8c8d; }
    .actrow .kw { color: #4a90d9; font-size: .85em; margin-left: .3em; }
    .actrow .acttxt { color: #555; margin: .15em 0 0 .5em; font-size: .9em; }
    """

    doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>afi 审计报告</title><style>{css}</style></head>
<body>
<h1>afi 审计报告</h1>
{awi_cmp}
{cmp}
{"".join(sections)}
</body></html>"""
    Path(out_path).write_text(doc, encoding="utf-8")
    print(f"[html_report] wrote {out_path}  ({len(doc)} bytes, {len(run_dirs)} runs)")


def main():
    ap = argparse.ArgumentParser(description="Generate self-contained HTML audit report")
    ap.add_argument("runs", nargs="+", help="run_dir paths (label:path or just path)")
    ap.add_argument("--out", default="afi_report.html", help="output html path")
    args = ap.parse_args()
    run_dirs = []
    for i, r in enumerate(args.runs):
        if ":" in r and not r.startswith("/"):
            label, path = r.split(":", 1)
        else:
            label = Path(r).name
            path = r
        run_dirs.append((label, path))
    build_html(run_dirs, args.out)


if __name__ == "__main__":
    main()
