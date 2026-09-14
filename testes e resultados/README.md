# Testes e resultados

Medições do T1. Tudo que está aqui é suficiente para reproduzir as tabelas e os
gráficos do relatório.

## Conteúdo

    bench.sh        executa todo o protocolo de medição
    analyze.py      lê os CSVs, valida, imprime as tabelas e gera os gráficos
    data/           saída bruta (gerada pelos scripts, versionar junto)

Em `data/` ficam:

    ambiente.txt        lscpu, free -h, gcc --version, flags, commit
    topologia.txt       núcleos físicos e processadores lógicos
    strong_seq.csv      T1, caminho sequencial sem diretivas
    strong_<P>.csv      escalabilidade forte, P threads
    weak_<P>.csv        escalabilidade fraca, max_iter proporcional a P
    sched_<nome>.csv    static, dynamic e guided no mesmo P
    thread_stats.txt    iterações por thread (balanceamento de carga)
    overhead_omp1.csv   omp com 1 thread; mede o custo das diretivas
    execucao.log        saída completa da bateria

## Como rodar

Antes de tudo: máquina ociosa, na tomada, sem navegador nem IDE aberta.

    make -C ..                       # compila com -O3 -march=native -fopenmp
    chmod +x bench.sh

1. Calibrar a entrada para a fase sequencial cair entre 30 e 60 s:

       ./bench.sh calibrate

   Ele imprime o `--max-iter` sugerido. Esse valor é a entrada de referência.

2. Levantar o perfil para o cálculo de Amdahl (antes das medições finais):

       perf record -g ../mandelbrot --mode seq --no-window --frames 1 \
           --max-iter <calibrado>
       perf report

   Some a fração de `mandelbrot_iterations` e `render_row`: esse é o `f`.

3. Rodar a bateria completa (uma hora, aproximadamente):

       MAXITER=<calibrado> ./bench.sh all 2>&1 | tee data/execucao.log

4. Gerar tabelas e gráficos:

       F=<f medido> python3 analyze.py

   As tabelas saem já em linhas LaTeX. Os gráficos vão para a raiz do
   repositório como `strong_speedup.pdf` e `efficiency.pdf`, que é onde o
   `relatorio.tex` os procura.

## Decisões de medição

O tempo de referência T1 vem de `--mode seq`, o ramo de `render_image` que não
executa nenhuma diretiva OpenMP. Não é o caminho paralelo com uma thread; esse
foi medido à parte, em `overhead_omp1.csv`, só para quantificar o custo das
diretivas.

A região cronometrada por `omp_get_wtime()` é `render_image` inteira: cálculo,
colorização e checksum. Ficam fora a janela X11, a pausa entre quadros e a
escrita do CSV — nas duas versões e também no perfil usado no Amdahl.

Cada configuração roda dez vezes (`--frames 10`). Com `--no-window` a escala não
muda entre quadros, então os dez são repetições da mesma imagem. Reportamos
mediana, mínimo e máximo. O quadro 0 é sempre o mais lento, por causa das falhas
de página do buffer e da frequência subindo do estado ocioso; a mediana absorve
isso, e é por esse motivo que não usamos média.

Na escalabilidade fraca o que cresce é `max_iter`, não a resolução. O trabalho é
a soma total de iterações, dominada pelos pixels interiores ao conjunto, que
custam `max_iter` cada — então `max_iter` proporcional a P mantém o trabalho por
thread constante. Aumentar a largura não serviria: em `render_row`, `scale_x` e
`scale_y` valem ambos `scale/width`, de modo que alargar a imagem encolhe o
passo e estreita a faixa vertical, mudando a região desenhada e o custo por
pixel. A coluna `trab/P` do `analyze.py` confirma a regra com o contador de
iterações do próprio programa.

As threads são fixadas por `OMP_NUM_THREADS`. A série vai de 2 em 2 até os
processadores lógicos, incluindo explicitamente o número de núcleos físicos.
