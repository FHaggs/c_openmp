#!/usr/bin/env bash
# Protocolo de medicao do T1 (OpenMP / Mandelbrot).
# Mora em "testes e resultados/" e encontra o binario na raiz do repositorio.
#
#   ./bench.sh calibrate          descobre o --max-iter que da ~40 s no sequencial
#   MAXITER=12000 ./bench.sh all  roda ambiente + forte + fraca + escalonadores

set -euo pipefail
cd "$(dirname "$0")"

RAIZ=".."
BIN="$RAIZ/mandelbrot"
WIDTH=${WIDTH:-1280}
HEIGHT=${HEIGHT:-720}
REPS=${REPS:-10}          # o enunciado exige >= 10
ALVO=${ALVO:-40}          # segundos-alvo da fase sequencial (faixa pedida: 30-60)
OUT=data

[[ -x "$BIN" ]] || { echo "Compile primeiro: make -C $RAIZ"; exit 1; }
mkdir -p "$OUT"

# ---------------------------------------------------------------- topologia
LOGICOS=$(nproc)
FISICOS=$(lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' | sort -u | wc -l)
[[ "$FISICOS" -ge 1 ]] || FISICOS=$LOGICOS

# Serie de threads: 2,4,6,... ate os logicos, mais fisicos e logicos garantidos.
serie_threads() {
  { seq 2 2 "$LOGICOS"; echo "$FISICOS"; echo "$LOGICOS"; } \
    | awk '$1>=2' | sort -n -u
}

segundos_do_csv() {  # mediana da coluna seconds, so para a calibracao
  awk -F, 'NR>1{print $7}' "$1" | sort -n | awk '{v[NR]=$1} END{print v[int((NR+1)/2)]}'
}

# --------------------------------------------------------------- calibracao
calibrate() {
  local sonda=2000 t fator sugerido
  echo "Sondando com --max-iter $sonda (1 quadro, sequencial)..."
  "$BIN" --mode seq --no-window --frames 1 --width "$WIDTH" --height "$HEIGHT" \
         --max-iter "$sonda" --csv "$OUT/_probe.csv" >/dev/null
  t=$(segundos_do_csv "$OUT/_probe.csv"); rm -f "$OUT/_probe.csv"
  fator=$(awk -v a="$ALVO" -v t="$t" 'BEGIN{print a/t}')
  sugerido=$(awk -v s="$sonda" -v f="$fator" 'BEGIN{printf "%d", (s*f+500)/1000*1000}')
  echo "Sonda levou ${t}s. Para ~${ALVO}s use:"
  echo
  echo "    MAXITER=$sugerido ./bench.sh all"
  echo
  echo "Confira depois se a mediana de $OUT/strong_seq.csv caiu entre 30 e 60 s."
}

# ---------------------------------------------------------------- ambiente
ambiente() {
  { echo "=== data ==="; date -Is
    echo; echo "=== lscpu ==="; lscpu
    echo; echo "=== nproc/fisicos ==="; echo "logicos=$LOGICOS fisicos=$FISICOS"
    echo; echo "=== free -h ==="; free -h
    echo; echo "=== gcc ==="; gcc --version
    echo; echo "=== SO ==="; cat /etc/os-release
    echo; echo "=== flags ==="; grep '^CFLAGS' "$RAIZ/Makefile"
    echo; echo "=== commit ==="; git -C "$RAIZ" rev-parse HEAD 2>/dev/null || echo "sem git"
  } > "$OUT/ambiente.txt" 2>&1
  printf 'logicos=%s\nfisicos=%s\n' "$LOGICOS" "$FISICOS" > "$OUT/topologia.txt"
  echo "Ambiente salvo em $OUT/ambiente.txt (copie os numeros para a secao 3)."
}

comum="--no-window --frames $REPS --width $WIDTH --height $HEIGHT"

# ------------------------------------------------------- escalabilidade forte
forte() {
  echo ">>> forte: sequencial (T1, caminho sem diretivas)"
  "$BIN" --mode seq $comum --max-iter "$MAXITER" --csv "$OUT/strong_seq.csv"
  for p in $(serie_threads); do
    echo ">>> forte: $p threads"
    OMP_NUM_THREADS=$p "$BIN" --mode omp $comum --max-iter "$MAXITER" \
        --csv "$OUT/strong_$p.csv"
  done
  echo ">>> extra: omp com 1 thread (custo das diretivas, nao usar como T1)"
  OMP_NUM_THREADS=1 "$BIN" --mode omp $comum --max-iter "$MAXITER" \
      --csv "$OUT/overhead_omp1.csv"
}

# Mesma serie da forte, porem com o escalonador escolhido no final (dynamic).
# Reaproveita strong_seq.csv como T1: o caminho sequencial nao muda com o
# escalonador, entao nao ha motivo para pagar 40 s x 10 de novo.
forte_dyn() {
  echo ">>> forte/dynamic: T1 reaproveitado de strong_seq.csv"
  [[ -f "$OUT/strong_seq.csv" ]] || { echo "rode ./bench.sh forte antes"; exit 1; }
  cp "$OUT/strong_seq.csv" "$OUT/strongdyn_seq.csv"
  for p in $(serie_threads); do
    echo ">>> forte/dynamic: $p threads"
    OMP_NUM_THREADS=$p "$BIN" --mode omp $comum --max-iter "$MAXITER" \
        --schedule dynamic --csv "$OUT/strongdyn_$p.csv"
  done
}

# Perfil do caminho sequencial na MESMA entrada usada no speed-up (item 1 do
# relatorio). max_iter=500 do alvo 'profile' do Makefile nao serve: muda o peso
# relativo do laco de checksum.
perfil() {
  command -v perf >/dev/null || { echo "perf nao instalado"; return 1; }
  # O '|| true' e necessario: com set -e, um aviso do perf record (comum quando
  # perf_event_paranoid restringe eventos de kernel) abortaria o script inteiro
  # antes de gerar o relatorio, mesmo com o perf.data ja gravado e utilizavel.
  perf record -q -g -o "$OUT/perf.data" \
    "$BIN" --mode seq --no-window --frames 1 --width "$WIDTH" --height "$HEIGHT" \
    --max-iter "$MAXITER" >/dev/null 2>&1 || true
  [[ -s "$OUT/perf.data" ]] || { echo "perf record nao gravou nada"; return 1; }
  perf report -i "$OUT/perf.data" --stdio -g none --percent-limit 0.01 \
    > "$OUT/perf_seq.txt" 2>/dev/null || true
  grep -q render_row "$OUT/perf_seq.txt" \
    || { echo "perf report nao encontrou render_row"; return 1; }
  echo "Perfil em $OUT/perf_seq.txt (max_iter=$MAXITER, mesma fase do speed-up):"
  grep -E '^\s+[0-9.]+%\s+[0-9.]+%.*render_row' "$OUT/perf_seq.txt"
}

# ------------------------------------------------------- escalabilidade fraca
# Regra: trabalho ~ soma de iteracoes, dominada pelos pixels interiores que
# custam max_iter cada. Logo max_iter cresce com P e o trabalho por thread fica
# aproximadamente constante. O analyze.py confere isso pelo contador iterations.
fraca() {
  echo ">>> fraca: P=1 (referencia, caminho sequencial)"
  if [[ -f "$OUT/strong_seq.csv" ]]; then cp "$OUT/strong_seq.csv" "$OUT/weak_1.csv"
  else "$BIN" --mode seq $comum --max-iter "$MAXITER" --csv "$OUT/weak_1.csv"; fi
  for p in $(serie_threads); do
    local mi=$((MAXITER * p))
    echo ">>> fraca: $p threads, --max-iter $mi"
    OMP_NUM_THREADS=$p "$BIN" --mode omp $comum --max-iter "$mi" \
        --csv "$OUT/weak_$p.csv"
  done
}

# Mesma regra da fraca, com o escalonador final. O P=1 e o caminho sequencial,
# que nao depende de escalonador, entao reaproveita strong_seq.csv.
fraca_dyn() {
  echo ">>> fraca/dynamic: P=1 reaproveitado de strong_seq.csv"
  [[ -f "$OUT/strong_seq.csv" ]] || { echo "rode ./bench.sh forte antes"; exit 1; }
  cp "$OUT/strong_seq.csv" "$OUT/weakdyn_seq.csv"
  for p in $(serie_threads); do
    local mi=$((MAXITER * p))
    echo ">>> fraca/dynamic: $p threads, --max-iter $mi"
    OMP_NUM_THREADS=$p "$BIN" --mode omp $comum --max-iter "$mi" \
        --schedule dynamic --csv "$OUT/weakdyn_$p.csv"
  done
}

# ------------------------------------------------------------- escalonadores
# Item 7 da avaliacao: mostrar que dynamic/guided foram testados, com numero.
escalonadores() {
  for s in static dynamic guided; do
    echo ">>> escalonador $s com $LOGICOS threads"
    OMP_NUM_THREADS=$LOGICOS "$BIN" --mode omp $comum --max-iter "$MAXITER" \
        --schedule "$s" --csv "$OUT/sched_$s.csv"
  done
  echo ">>> carga por thread (static x dynamic), 1 quadro"
  { echo "--- static ---"
    OMP_NUM_THREADS=$LOGICOS "$BIN" --mode omp --no-window --frames 1 \
      --width "$WIDTH" --height "$HEIGHT" --max-iter "$MAXITER" \
      --schedule static --thread-stats
    echo "--- dynamic, chunk 1 ---"
    OMP_NUM_THREADS=$LOGICOS "$BIN" --mode omp --no-window --frames 1 \
      --width "$WIDTH" --height "$HEIGHT" --max-iter "$MAXITER" \
      --schedule dynamic --chunk 1 --thread-stats
  } | tee "$OUT/thread_stats.txt"
}

case "${1:-all}" in
  calibrate) calibrate ;;
  all)
    : "${MAXITER:?defina MAXITER (rode ./bench.sh calibrate primeiro)}"
    ambiente; perfil; forte; fraca; escalonadores; forte_dyn; fraca_dyn
    echo; echo "Pronto. Agora: python3 analyze.py" ;;
  ambiente)      ambiente ;;
  perfil)        : "${MAXITER:?}"; perfil ;;
  forte)         : "${MAXITER:?}"; forte ;;
  forte_dyn)     : "${MAXITER:?}"; forte_dyn ;;
  fraca)         : "${MAXITER:?}"; fraca ;;
  fraca_dyn)     : "${MAXITER:?}"; fraca_dyn ;;
  escalonadores) : "${MAXITER:?}"; escalonadores ;;
  *) echo "uso: $0 {calibrate|all|ambiente|perfil|forte|forte_dyn|fraca|fraca_dyn|escalonadores}"; exit 1 ;;
esac
