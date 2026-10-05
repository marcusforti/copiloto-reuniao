"""Gera o resumo.html da reunião a partir de um JSON escrito pelo cérebro (Claude) + dados da transcrição."""
import html
import json
from datetime import datetime
from pathlib import Path

from .sessao import ler_json


def _e(t) -> str:
    return html.escape(str(t or ""))


def _lista(itens, vazio="—"):
    itens = [i for i in (itens or []) if i]
    if not itens:
        return f'<p class="vazio">{vazio}</p>'
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in itens) + "</ul>"


def _metricas(falas, rot):
    palavras = {"voce": 0, "cliente": 0}
    for f in falas:
        palavras[f["quem"]] = palavras.get(f["quem"], 0) + len(f["texto"].split())
    total = sum(palavras.values()) or 1
    dur = (falas[-1]["ts"] - falas[0]["ts"]) / 60 if len(falas) > 1 else 0
    perguntas = sum(1 for f in falas if f["quem"] == "voce" and "?" in f["texto"])
    return {
        "duracao_min": round(dur),
        "falas": len(falas),
        "pct_voce": round(100 * palavras["voce"] / total),
        "pct_cliente": round(100 * palavras["cliente"] / total),
        "perguntas_voce": perguntas,
    }


def gerar(sessao, dados: dict) -> Path:
    briefing = sessao.ler_briefing()
    estado = ler_json(sessao.estado, {}) or {}
    rot = {"voce": "VOCÊ", "cliente": "CLIENTE", **(estado.get("rotulos") or {})}
    falas = sorted(sessao.ler_falas(), key=lambda f: f["ts"])
    m = _metricas(falas, rot)
    cliente = briefing.get("cliente") or "Cliente"
    modo = briefing.get("modo", "venda")
    titulo = dados.get("titulo") or f"Reunião com {cliente}"
    data = briefing.get("criado") or datetime.now().strftime("%Y-%m-%d %H:%M")
    ideal = "30–45%" if modo == "venda" else "40–60%"

    passos = dados.get("proximos_passos") or []
    passos_html = (
        "".join(
            f'<label class="tarefa"><input type="checkbox" data-k="t{i}"><span><b>{_e(p.get("quem"))}</b> · {_e(p.get("o_que"))}'
            f'{" <em>até " + _e(p.get("quando")) + "</em>" if p.get("quando") else ""}</span></label>'
            for i, p in enumerate(passos)
        )
        or '<p class="vazio">—</p>'
    )
    objecoes = dados.get("objecoes") or []
    obj_html = (
        "".join(
            f'<div class="obj"><div class="obj-t"><span class="pill {_e(o.get("status", ""))}">{_e(o.get("status", ""))}</span>{_e(o.get("objecao"))}</div>'
            f'<p>{_e(o.get("como_foi_tratada") or o.get("resposta"))}</p></div>'
            for o in objecoes
        )
        or '<p class="vazio">Nenhuma objeção registrada.</p>'
    )
    trans_html = "".join(
        f'<div class="fala {f["quem"]}"><span class="q">{_e(rot.get(f["quem"], f["quem"]))}</span><span class="h">{_e(f["hora"])}</span> {_e(f["texto"])}</div>'
        for f in falas
    )
    followups = []
    for chave, rotulo in (("followup_whatsapp", "Mensagem de WhatsApp"), ("followup_email", "E-mail")):
        if dados.get(chave):
            followups.append(
                f'<div class="fu"><div class="fu-top"><b>{rotulo}</b><button onclick="copiar(this)">Copiar</button></div><pre>{_e(dados[chave])}</pre></div>'
            )
    coach = dados.get("coach") or {}

    pagina = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)}</title>
<style>
:root{{--bg:#0b0d12;--p:#12151c;--p2:#171b24;--l:#232836;--t:#eef1f6;--s:#b6bdca;--m:#7d8698;--g:#f6c544;--v:#39d98a;--r:#ff6b6b;--b:#5ea8ff}}
@media (prefers-color-scheme: light){{:root:not([data-theme=dark]){{--bg:#f6f7f9;--p:#fff;--p2:#f0f2f5;--l:#e1e4ea;--t:#11151c;--s:#3d4554;--m:#6b7383;--g:#b8860b}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--t);font:16px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:32px 16px 80px}}
h1{{font-size:clamp(24px,4vw,34px);margin:0 0 4px;letter-spacing:-.02em}}.sub{{color:var(--m);margin:0 0 24px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}}
.kpi{{background:var(--p);border:1px solid var(--l);border-radius:14px;padding:14px 16px}}.kpi b{{display:block;font-size:26px}}.kpi span{{color:var(--m);font-size:13px}}
.barra{{height:8px;border-radius:6px;background:var(--b);overflow:hidden;margin-top:8px}}.barra i{{display:block;height:100%;background:var(--v)}}
section{{background:var(--p);border:1px solid var(--l);border-radius:16px;padding:20px 22px;margin-bottom:16px}}
h2{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--m);margin:0 0 12px}}
ul{{margin:0;padding-left:20px}}li{{margin:4px 0}}.vazio{{color:var(--m);font-style:italic;margin:0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
.grid section{{margin:0}}
.tarefa{{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--l);cursor:pointer}}.tarefa:last-child{{border:0}}
.tarefa input{{margin-top:5px;accent-color:var(--v)}}.tarefa em{{color:var(--g);font-style:normal}}
.obj{{padding:10px 0;border-bottom:1px solid var(--l)}}.obj:last-child{{border:0}}.obj-t{{font-weight:650}}.obj p{{margin:4px 0 0;color:var(--s)}}
.pill{{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;padding:2px 8px;border-radius:6px;margin-right:8px;background:var(--p2);color:var(--m)}}
.pill.resolvida{{color:var(--v)}}.pill.aberta{{color:var(--r)}}.pill.parcial{{color:var(--g)}}
.fu{{background:var(--p2);border:1px solid var(--l);border-radius:12px;margin-top:10px}}.fu-top{{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid var(--l)}}
.fu pre{{margin:0;padding:14px;white-space:pre-wrap;font-family:inherit;font-size:15.5px;line-height:1.55}}button{{font:inherit;font-size:13px;font-weight:700;border:0;border-radius:8px;padding:6px 12px;background:var(--g);color:#111;cursor:pointer}}
details summary{{cursor:pointer;color:var(--s);font-weight:650}}.fala{{padding:6px 0;border-bottom:1px solid var(--l);color:var(--s);font-size:14.5px}}
.fala .q{{font-size:11px;font-weight:800;letter-spacing:.06em;margin-right:6px}}.fala.voce .q{{color:var(--v)}}.fala.cliente .q{{color:var(--b)}}.fala .h{{color:var(--m);font-size:12px;margin-right:6px}}
.resumo p{{margin:0 0 10px}}.rodape{{color:var(--m);font-size:13px;text-align:center;margin-top:30px}}
</style></head><body><main>
<h1>{_e(titulo)}</h1>
<p class="sub">{_e(modo.capitalize())} · {_e(data)} · {m['duracao_min']} min · {m['falas']} falas</p>
<div class="kpis">
 <div class="kpi"><b>{m['pct_voce']}% / {m['pct_cliente']}%</b><span>quem falou mais ({_e(rot['voce'])} / {_e(rot['cliente'])}) · ideal você {ideal}</span><div class="barra"><i style="width:{m['pct_voce']}%"></i></div></div>
 <div class="kpi"><b>{m['perguntas_voce']}</b><span>perguntas que você fez</span></div>
 <div class="kpi"><b>{len(objecoes)}</b><span>objeções</span></div>
 <div class="kpi"><b>{_e(dados.get('temperatura', '—'))}</b><span>temperatura do cliente</span></div>
</div>
<section class="resumo"><h2>Resumo</h2>{''.join(f'<p>{_e(p)}</p>' for p in (dados.get('resumo') if isinstance(dados.get('resumo'), list) else [dados.get('resumo', '')]))}</section>
<section><h2>Próximos passos</h2>{passos_html}</section>
<div class="grid">
 <section><h2>Dores e desejos do cliente</h2>{_lista(dados.get('dores'))}</section>
 <section><h2>Decisões e combinados</h2>{_lista(dados.get('decisoes'))}</section>
</div>
<section><h2>Objeções</h2>{obj_html}</section>
<div class="grid">
 <section><h2>Oportunidades</h2>{_lista(dados.get('oportunidades'))}</section>
 <section><h2>Riscos / pontos de atenção</h2>{_lista(dados.get('riscos'))}</section>
</div>
<section><h2>Follow-up pronto</h2>{''.join(followups) or '<p class="vazio">—</p>'}</section>
<div class="grid">
 <section><h2>O que funcionou</h2>{_lista(coach.get('funcionou'))}</section>
 <section><h2>Para a próxima</h2>{_lista(coach.get('melhorar'))}</section>
</div>
<section><details><summary>Transcrição completa ({m['falas']} falas)</summary><div style="margin-top:12px">{trans_html}</div></details></section>
<p class="rodape">Gerado pelo Copiloto de Reunião · transcrição automática, pode conter erros em nomes e números.</p>
</main>
<script>
function copiar(b){{const t=b.closest('.fu').querySelector('pre').innerText;navigator.clipboard.writeText(t).then(()=>{{b.textContent='Copiado ✓';setTimeout(()=>b.textContent='Copiar',1500)}})}}
document.querySelectorAll('.tarefa input').forEach(c=>{{const k='{_e(sessao.pasta.name)}:'+c.dataset.k;try{{c.checked=localStorage.getItem(k)==='1'}}catch(e){{}}c.onchange=()=>{{try{{localStorage.setItem(k,c.checked?'1':'0')}}catch(e){{}}}}}});
</script></body></html>"""
    destino = sessao.pasta / "resumo.html"
    destino.write_text(pagina, encoding="utf-8")
    (sessao.pasta / "resumo.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino
