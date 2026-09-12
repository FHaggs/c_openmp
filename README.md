# Mandelbrot em C com OpenMP

Implementacao para estudar a paralelizacao por linhas de uma imagem Mandelbrot. A versao `seq` e a `omp` usam exatamente a mesma funcao de iteracao, mapeamento de pixels e colorizacao. A regiao cronometrada e somente `render_image`: inclui o calculo completo de todos os pixels e exclui janela X11, pausa e escrita do CSV.

## Dependencias e compilacao

Em Debian/Ubuntu, instale uma vez `sudo apt install build-essential libx11-dev`. Depois:

```sh
cd c_openmp
make
make run
```

Pressione uma tecla na janela para encerrar. Para medir, use sempre `--no-window`, que evita incluir a interface grafica no tempo.

## Validacao e medicao

Verifique primeiro se a imagem calculada e identica. O `checksum` e o numero de iteracoes precisam coincidir:

```sh
./mandelbrot --mode seq --no-window --frames 1
OMP_NUM_THREADS=8 ./mandelbrot --mode omp --no-window --frames 1
```

Use `OMP_NUM_THREADS` para fixar as threads. O alvo abaixo executa a escalabilidade forte com 10 repeticoes em cada configuracao e grava os tempos brutos em `data/`:

```sh
make benchmark
```

Para a escalabilidade fraca, aumente proporcionalmente o numero total de pixels: mantenha `--height 720 --max-iter 500` e use `--width $((1280 * P))` para $P$ threads. O trabalho e aproximadamente proporcional a `width * height * max_iter`; a largura cresce por $P$, portanto o trabalho por thread permanece aproximadamente constante. Exemplos:

```sh
OMP_NUM_THREADS=2 ./mandelbrot --mode omp --no-window --frames 10 --width 2560 --csv data/weak_2.csv
OMP_NUM_THREADS=8 ./mandelbrot --mode omp --no-window --frames 10 --width 10240 --csv data/weak_8.csv
```

`--schedule static|dynamic|guided --chunk N` permite comparar o balanceamento. O `--thread-stats` mostra a soma de iteracoes de escape por thread, uma aproximacao mais informativa de carga que somente contar linhas.

## Perfil

Rode `make profile` antes das medições finais. Ele cria o perfil do caminho sequencial e da mesma fase computacional usada no speed-up. Documente a fração de tempo de `mandelbrot_iterations`/`render_row` e calcule o limite de Amdahl por $S_{max}(P)=1/((1-f)+f/P)$; o limite assintótico é $1/(1-f)$.

## Observacoes de reproducibilidade

Registre no relatorio o resultado de `lscpu`, `free -h`, `gcc --version`, as flags do Makefile e a versao do sistema. Feche processos pesados, mantenha a maquina ociosa e use a mediana, minimo e maximo dos 10 tempos de cada CSV. Em uma CPU com SMT, marque no grafico a transicao de nucleos fisicos para processadores logicos.