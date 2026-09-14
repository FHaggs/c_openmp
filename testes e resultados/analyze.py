#!/usr/bin/env python3
"""Le os CSVs de ./data, valida a equivalencia seq x omp, imprime as tabelas
prontas para colar no relatorio.tex e gera os graficos na raiz do repositorio
(strong_speedup.pdf e efficiency.pdf, nomes que o relatorio.tex ja espera).

A configuracao final do trabalho e schedule(dynamic): e ela que alimenta as
tabelas e os graficos. O static entra apenas na secao de balanceamento, como o
escalonador alternativo que foi medido e descartado.

    python3 analyze.py            # tabelas + graficos
    F=0.9992 python3 analyze.py   # sobrescreve a fracao paralela lida do perf

Series lidas de data/:
    strongdyn_*.csv  escalabilidade forte, dynamic  -> Tabela 1
    weakdyn_*.csv    escalabilidade fraca, dynamic  -> Tabela 2
    strong_seq.csv   caminho sequencial: a referencia T1
    sched_*.csv      os tres escalonadores com P = logicos
    load_static.txt  iteracoes por thread sob static, para cada P
    thread_stats.txt iteracoes por thread, static x dynamic, em P = logicos
"""

import csv
import glob
import os
import re
import statistics as st
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(AQUI, "data")
RAIZ = os.path.dirname(AQUI)


def ler(caminho):
    """Devolve None se o CSV ainda nao tem linhas — acontece quando a bateria
    esta rodando e o arquivo so tem o cabecalho. Quem chama decide se pula."""
    with open(caminho, newline="") as fh:
        linhas = list(csv.DictReader(fh))
    if not linhas:
        return None
    return {
        "p": int(linhas[0]["threads"]),
        "tempos": sorted(float(l["seconds"]) for l in linhas),
        "primeiro": float(linhas[0]["seconds"]),
        "n": len(linhas),
        "largura": int(linhas[0]["width"]),
        "altura": int(linhas[0]["height"]),
        "max_iter": int(linhas[0]["max_iter"]),
        "iteracoes": int(linhas[0]["iterations"]),
        "checksum": linhas[0]["checksum"],
    }


def coletar(prefixo):
    """Le data/<prefixo>_*.csv. O separador '_' impede que 'strong' capture os
    arquivos 'strongdyn' e que 'weak' capture os 'weakdyn'."""
    saida = {}
    for caminho in glob.glob(os.path.join(DATA, f"{prefixo}_*.csv")):
        rotulo = re.sub(r".*_(\w+)\.csv", r"\1", caminho)
        registro = ler(caminho)
        if registro is None:
            print(f"  aviso: {os.path.basename(caminho)} ainda sem linhas "
                  f"(bateria em andamento?) — ignorado")
            continue
        registro["p"] = 1 if rotulo == "seq" else int(rotulo)
        saida[registro["p"]] = registro
    return dict(sorted(saida.items()))


def med(r):
    return st.median(r["tempos"])


def topologia(chave):
    caminho = os.path.join(DATA, "topologia.txt")
    if os.path.exists(caminho):
        for linha in open(caminho):
            if linha.startswith(chave + "="):
                return int(linha.split("=")[1])
    return None


def cargas_por_p():
    """Iteracoes por thread sob static, por P: {P: [iteracoes...]}."""
    caminho = os.path.join(DATA, "load_static.txt")
    if not os.path.exists(caminho):
        return {}
    saida = {}
    for bloco in open(caminho).read().split("=== P=")[1:]:
        p = int(bloco.split()[0])
        saida[p] = [int(m) for m in
                    re.findall(r"thread=\d+ iterations=(\d+)", bloco)]
    return saida


def cargas_static_x_dynamic():
    """Iteracoes por thread em P = logicos, para os dois escalonadores."""
    caminho = os.path.join(DATA, "thread_stats.txt")
    if not os.path.exists(caminho):
        return {}
    texto = open(caminho).read()
    saida = {}
    for nome, marcador in (("static", "--- static ---"),
                           ("dynamic", "--- dynamic")):
        if marcador not in texto:
            continue
        trecho = texto.split(marcador, 1)[1].split("---")[0]
        saida[nome] = [int(m) for m in
                       re.findall(r"thread=\d+ iterations=(\d+)", trecho)]
    return saida


def fracao_paralela():
    """Fracao f do tempo no trecho paralelizado, lida do perf. O 'Self' de
    render_row e o que roda dentro do omp for; o resto (laco de checksum) e
    sequencial e esta dentro da regiao cronometrada."""
    if os.environ.get("F"):
        return float(os.environ["F"])
    caminho = os.path.join(DATA, "perf_seq.txt")
    if not os.path.exists(caminho):
        return None
    for linha in open(caminho):
        if "render_row" in linha and "%" in linha:
            pcts = re.findall(r"(\d+\.\d+)%", linha)
            if len(pcts) >= 2:
                return float(pcts[1]) / 100.0
    return None


forte = coletar("strongdyn")          # configuracao final -> Tabela 1
fraca = coletar("weakdyn")            # configuracao final -> Tabela 2
seq = coletar("strong")               # strong_seq.csv guarda a referencia T1
if not forte:
    raise SystemExit(f"Sem strongdyn_*.csv em {DATA}. Rode ./bench.sh forte_dyn.")
if 1 not in forte and 1 in seq:
    forte[1] = seq[1]
    forte = dict(sorted(forte.items()))   # P=1 entrou depois: reordena
if 1 not in forte:
    raise SystemExit("Falta a referencia sequencial (strong_seq.csv).")

# ------------------------------------------------------------------ validacao
print("=" * 70)
print("VALIDACAO (item 3: versoes sequencial e paralela equivalentes)")
ref = forte[1]
ok = True
for p, r in forte.items():
    igual = (r["checksum"] == ref["checksum"]
             and r["iteracoes"] == ref["iteracoes"])
    ok &= igual
    print(f"  P={p:<3} checksum={r['checksum']} iteracoes={r['iteracoes']} "
          f"{'OK' if igual else '>>> DIVERGENTE <<<'}")
for nome in sorted(glob.glob(os.path.join(DATA, "sched_*.csv"))):
    r = ler(nome)
    if r and (r["checksum"] != ref["checksum"]
              or r["iteracoes"] != ref["iteracoes"]):
        ok = False
        print(f"  >>> DIVERGENTE <<< {os.path.basename(nome)}")
print("Resultado:", "identico em toda a serie e nos tres escalonadores" if ok
      else "DIVERGENCIA — corrija antes de medir")

for p, r in forte.items():
    if r["n"] < 10:
        print(f"  aviso: P={p} tem so {r['n']} repeticoes; o enunciado pede 10")
t1 = med(forte[1])
if not 30 <= t1 <= 60:
    print(f"  aviso: mediana sequencial = {t1:.1f}s, fora da faixa 30-60s pedida")

over = os.path.join(DATA, "overhead_omp1.csv")
if os.path.exists(over):
    reg = ler(over)
    if reg:
        print(f"Custo das diretivas (omp com 1 thread vs seq): "
              f"{(med(reg) / t1 - 1) * 100:+.1f}% — por isso T1 vem do caminho seq.")

f_par = fracao_paralela()
logicos = topologia("logicos") or max(forte)
fisicos = topologia("fisicos")
if f_par:
    amdahl = 1 / ((1 - f_par) + f_par / logicos)
    print(f"Perfil: f={f_par:.4f}. Amdahl em P={logicos}: S_max={amdahl:.2f} "
          f"(E={amdahl/logicos:.3f}); assintotico 1/(1-f)={1/(1-f_par):.0f}.")

# -------------------------------------------------------------- tabela forte
print()
print("=" * 70)
print(f"TABELA 1 — escalabilidade forte, dynamic ({ref['largura']}x{ref['altura']}, "
      f"max_iter={ref['max_iter']}, {ref['n']} repeticoes)")
print(f"{'P':>4} {'mediana':>9} {'min':>9} {'max':>9} {'S_P':>7} {'E_P':>7}")
sp, linhas_tex = {}, []
for p, r in forte.items():
    m, lo, hi = med(r), r["tempos"][0], r["tempos"][-1]
    sp[p] = t1 / m
    print(f"{p:>4} {m:9.3f} {lo:9.3f} {hi:9.3f} {sp[p]:7.2f} {sp[p]/p:7.2f}")
    linhas_tex.append(f"{p} & {m:.2f} & {lo:.2f} & {hi:.2f} & "
                      f"{sp[p]:.2f} / {sp[p]/p:.2f}\\\\")
print("\n--- colar no relatorio.tex ---")
print("\n".join(linhas_tex))

# --------------------------------------------------------------- tabela fraca
ef = {}
if fraca:
    if 1 not in fraca:
        fraca[1] = forte[1]
        fraca = dict(sorted(fraca.items()))
    base_iter, base_t = fraca[1]["iteracoes"], med(fraca[1])
    print()
    print("=" * 70)
    print("TABELA 2 — escalabilidade fraca, dynamic (max_iter cresce com P)")
    print(f"{'P':>4} {'max_iter':>9} {'mediana':>9} {'min':>9} {'max':>9} "
          f"{'E_fraca':>8} {'trab/P':>8}")
    linhas_tex = []
    for p, r in fraca.items():
        m, lo, hi = med(r), r["tempos"][0], r["tempos"][-1]
        ef[p] = base_t / m
        trabalho = r["iteracoes"] / (p * base_iter)  # deve ficar ~1.00
        print(f"{p:>4} {r['max_iter']:>9} {m:9.3f} {lo:9.3f} {hi:9.3f} "
              f"{ef[p]:8.2f} {trabalho:8.3f}")
        linhas_tex.append(f"{p} & {r['max_iter']} & {m:.2f} & {lo:.2f} / {hi:.2f} "
                          f"& {ef[p]:.2f} & {trabalho:.3f}\\\\")
    print("\nA coluna trab/P valida a regra: perto de 1.00 significa trabalho")
    print("por thread realmente constante.")
    print("\n--- colar no relatorio.tex ---")
    print("\n".join(linhas_tex))

    print()
    print("FRACA x FORTE (o enunciado pergunta se a fraca se sustenta melhor)")
    print(f"{'P':>4} {'E_forte':>9} {'E_fraca':>9} {'dif':>7}")
    for p in sorted(ef):
        if p in sp:
            a, b = sp[p] / p, ef[p]
            print(f"{p:>4} {a:9.3f} {b:9.3f} {b-a:+7.3f}")

# ------------------------------------------------ balanceamento (secao 4)
print()
print("=" * 70)
print("BALANCEAMENTO DE CARGA (item 7: medicao, nao suposicao)")
sched = {}
for c in glob.glob(os.path.join(DATA, "sched_*.csv")):
    r = ler(c)
    if r:
        sched[re.sub(r".*sched_(\w+)\.csv", r"\1", c)] = med(r)
if sched:
    melhor = min(sched, key=sched.get)
    print(f"Medianas com P={logicos} threads:")
    for nome, m in sorted(sched.items(), key=lambda kv: kv[1]):
        print(f"  {nome:<8} {m:8.3f} s   {(m/sched[melhor]-1)*100:+6.1f}%")

par = cargas_static_x_dynamic()
for nome in ("dynamic", "static"):
    if nome in par and par[nome]:
        v = par[nome]
        media = sum(v) / len(v)
        print(f"Carga por thread ({nome}, P={len(v)}): min={min(v):,} "
              f"max={max(v):,} | max/media={max(v)/media:.3f} "
              f"| dispersao={(max(v)-min(v))/media*100:.1f}%")

cargas = cargas_por_p()
if cargas:
    print("Teto de eficiencia imposto so pelo desbalanceamento do static")
    print("(media/maximo das iteracoes por thread, sem usar nenhum tempo):")
    print("  " + "  ".join(f"P={p}:{1/(max(v)/(sum(v)/len(v))):.2f}"
                           for p, v in sorted(cargas.items())))

# ---------------------------------------------------------------- graficos
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("\nmatplotlib ausente: pip install matplotlib (graficos nao gerados)")
    sys.exit(0)

ps = sorted(sp)


def marca_smt(ax, y):
    if fisicos and fisicos < max(ps):
        ax.axvline(fisicos + 0.5, color="gray", lw=1, ls="-.", alpha=.8)
        ax.text(fisicos + 0.8, y, "SMT", color="gray", fontsize=8)


fig, ax = plt.subplots(figsize=(4.6, 2.9))
ax.plot(ps, ps, "k--", lw=1, label="ideal")
if f_par:
    ax.plot(ps, [1 / ((1 - f_par) + f_par / p) for p in ps], ":", lw=1.3,
            color="0.45", label=f"Amdahl (f={f_par:.4f})")
ax.plot(ps, [sp[p] for p in ps], "o-", color="#1b6ca8", label="medido")
# Valor de cada ponto, para o grafico ser legivel sem recorrer a tabela.
# Abaixo do marcador: acima dele passam as retas do ideal e de Amdahl.
for p in ps:
    ax.annotate(f"{sp[p]:.2f}", (p, sp[p]), textcoords="offset points",
                xytext=(1, -12), ha="center", fontsize=10, color="#1b6ca8")
marca_smt(ax, 1.0)
ax.set_xlabel("threads (P)")
ax.set_ylabel("speed-up")
ax.set_xticks(ps)
ax.set_xlim(0.2, max(ps) + 0.9)
ax.set_ylim(-0.9, max(ps) + 0.8)
ax.grid(alpha=.3)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(RAIZ, "strong_speedup.pdf"))

fig, ax = plt.subplots(figsize=(4.6, 2.9))
ax.axhline(1.0, color="k", ls="--", lw=1)
ax.plot(ps, [sp[p] / p for p in ps], "o-", color="#1b6ca8", label="forte")
for p in ps:
    ax.annotate(f"{sp[p]/p:.2f}", (p, sp[p] / p), textcoords="offset points",
                xytext=(0, 7), ha="center", fontsize=10, color="#1b6ca8")
if ef:
    # Marcador vazado e tracejado: as duas curvas caem quase uma sobre a
    # outra, e sem isso a fraca esconderia a forte.
    pf = sorted(ef)
    ax.plot(pf, [ef[p] for p in pf], "^--", color="#27ae60", mfc="none",
            ms=7, mew=1.3, label="fraca")
    # As duas curvas praticamente coincidem, entao os rotulos vao em lados
    # opostos do ponto para nao se sobreporem.
    for p in pf:
        ax.annotate(f"{ef[p]:.2f}", (p, ef[p]), textcoords="offset points",
                    xytext=(0, -15), ha="center", fontsize=10, color="#1c7a43")
marca_smt(ax, 0.08)
ax.set_xlabel("threads (P)")
ax.set_ylabel("eficiencia")
ax.set_ylim(0, 1.22)
ax.set_xlim(0.2, max(ps) + 0.9)
ax.set_xticks(ps)
ax.grid(alpha=.3)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(RAIZ, "efficiency.pdf"))

print(f"\nGraficos gravados em {RAIZ}/ (strong_speedup.pdf, efficiency.pdf).")
print("Recompile o relatorio: pdflatex relatorio.tex")
