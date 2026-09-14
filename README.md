# Mandelbrot em C com OpenMP

Implementacao para estudar a paralelizacao por linhas de uma imagem Mandelbrot.
A versao `seq` e a `omp` usam exatamente a mesma funcao de iteracao, mapeamento
de pixels e colorizacao. A regiao cronometrada e somente `render_image`: inclui
o calculo completo de todos os pixels **e o laco de checksum**, que permanece
sequencial; exclui janela X11, pausa e escrita do CSV.

## Dependencias e compilacao

Em Fedora, `sudo dnf install gcc make libX11-devel perf`; em Debian/Ubuntu,
`sudo apt install build-essential libx11-dev linux-perf`. Depois:

```sh
cd c_openmp
make
make run
```

Pressione uma tecla na janela para encerrar. Para medir, use sempre
`--no-window`, que evita incluir a interface grafica no tempo.

## Reproduzir as medicoes do relatorio

Tudo esta em `testes e resultados/`. A entrada de referencia foi calibrada para
a faixa de 30-60 s pedida no enunciado:

```sh
cd "testes e resultados"
./bench.sh calibrate              # sugere o --max-iter; deu 87230 nesta maquina
MAXITER=87230 ./bench.sh all      # ambiente + perfil + forte + fraca + escalonadores
python3 analyze.py                # tabelas, validacao e graficos (.pdf na raiz)
```

`./bench.sh all` leva algumas horas, quase todas na escalabilidade fraca. Para
reproduzir apenas o que o relatorio apresenta, bastam os alvos da configuracao
final: `ambiente`, `perfil`, `forte` (gera o T1 sequencial), `forte_dyn`,
`fraca_dyn` e `escalonadores`. Os alvos `fraca` e a serie `static` do `forte`
existem para refazer a comparacao de escalonadores por completo.

Os tempos brutos de todas as execucoes ficam em `testes e resultados/data/`,
nomeados por experimento e numero de threads:

| arquivo | conteudo |
|---|---|
| `strong_seq.csv`  | caminho sequencial: a referencia T1 |
| `strongdyn_*.csv` | escalabilidade forte com `dynamic` (Tabela 1) |
| `weakdyn_*.csv`   | escalabilidade fraca com `dynamic` (Tabela 2) |
| `sched_*.csv`     | os tres escalonadores em P=16 (secao 4) |
| `thread_stats.txt`| iteracoes por thread, `static` x `dynamic`, em P=16 |
| `load_static.txt` | iteracoes por thread sob `static`, para cada P |
| `overhead_omp1.csv` | versao OpenMP com 1 thread, so para medir o custo das diretivas |
| `perf_seq.txt`    | perfil do caminho sequencial na entrada de referencia |
| `ambiente.txt`, `topologia.txt` | maquina, compilador, flags, nucleos e commit |

Cada CSV traz uma linha por quadro com `threads`, `width`, `height`,
`max_iter`, `seconds`, `iterations` e `checksum`, de modo que cada tempo bruto
carrega a configuracao que o gerou.

Os logs completos de todas as baterias ja executadas, inclusive as que usaram
`static` antes da escolha do escalonador, estao em `data/execucao.log`,
`data/execucao_dyn.log` e `data/execucao_fraca_dyn.log`.

Mantenha a maquina ociosa durante a medicao: sem navegador, compilacao ou
outro programa disputando nucleo.

## Validacao

O `analyze.py` confere automaticamente o item 3 do enunciado. Manualmente:

```sh
./mandelbrot --mode seq --no-window --frames 1 --max-iter 87230
OMP_NUM_THREADS=16 ./mandelbrot --mode omp --no-window --frames 1 --max-iter 87230
```

O `checksum` e o numero de iteracoes precisam coincidir. Eles coincidem para
todo P e todo escalonador porque a soma de iteracoes e inteira (a ordem da
reducao nao altera o resultado) e cada thread escreve pixels exclusivos.

## Como o numero de threads e o escalonador sao fixados

O `bench.sh` fixa as threads pela variavel de ambiente `OMP_NUM_THREADS`; o
`--threads N` existe no binario (chama `omp_set_num_threads`) mas nao e usado
nas medicoes. O laco usa `schedule(runtime)` e `main` chama `omp_set_schedule`
com o valor de `--schedule` (padrao `static`, chunk 0). **Isso sobrepoe a
variavel `OMP_SCHEDULE`**, entao o escalonador so muda por `--schedule`.

`--thread-stats` mostra a soma de iteracoes de escape por thread, uma medida de
carga mais informativa que contar linhas: as linhas tem o mesmo numero de
pixels, mas nao o mesmo custo.

## Escalonador: por que `dynamic`

O padrao do programa e `static`, mas as medicoes finais usam `dynamic`. Em
P=16: `dynamic` 3,243 s, `guided` 3,992 s (+23%), `static` 5,909 s (+82%).

A causa esta na distribuicao de carga, que o `--thread-stats` revela: sob
`static` a thread mais carregada faz 2,32e9 iteracoes e a menos carregada
1,3e6. As linhas tem o mesmo numero de pixels mas nao o mesmo custo, e o
`omp for` com chunk 0 entrega blocos contiguos, entao as threads do centro da
imagem herdam todo o interior do conjunto enquanto as das bordas terminam
quase imediatamente. Reproduza com:

```sh
cd "testes e resultados" && MAXITER=87230 ./bench.sh escalonadores
```

O `data/load_static.txt` guarda a mesma contagem para cada P da serie; o
`analyze.py` usa esses numeros para calcular o teto de eficiencia que o
desbalanceamento impoe e compara com a eficiencia medida.

## Regra da escalabilidade fraca

O trabalho e a soma de iteracoes de escape, nao o numero de pixels. Na entrada
de referencia ela e dominada pelos pixels interiores ao conjunto, que custam
`max_iter` cada; por isso **`max_iter` cresce com P** e a resolucao fica fixa em
1280x720:

```sh
OMP_NUM_THREADS=2  ./mandelbrot --mode omp --no-window --frames 10 --max-iter 174460  --csv data/weak_2.csv
OMP_NUM_THREADS=16 ./mandelbrot --mode omp --no-window --frames 10 --max-iter 1395680 --csv data/weak_16.csv
```

Crescer a largura *nao* serviria: os pixels acrescentados nas bordas escapam em
poucas iteracoes e custam quase nada, de modo que o trabalho por thread cairia.
O `analyze.py` confirma a regra pela coluna `trab/P`, que compara o contador
`iterations` com `P` vezes o da referencia e fica em 1.000 em toda a serie.

## Perfil

`./bench.sh perfil` roda o `perf` sobre o caminho sequencial **na mesma entrada
usada no speed-up** e grava `data/perf_seq.txt`. Use a fracao `Self` de
`render_row` como `f` e calcule o limite de Amdahl por
`S_max(P) = 1/((1-f) + f/P)`; o limite assintotico e `1/(1-f)`. O `analyze.py`
le esse arquivo sozinho e desenha a curva de Amdahl no grafico.

## Ambiente

`data/ambiente.txt` guarda `lscpu`, `free -h`, `gcc --version`, o `/etc/os-release`,
as flags do Makefile e o commit usado na medicao. `data/topologia.txt` guarda o
numero de nucleos fisicos e logicos, que o `analyze.py` usa para marcar o inicio
do SMT nos graficos.
