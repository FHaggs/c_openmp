CC := gcc
CFLAGS := -std=c17 -O3 -march=native -Wall -Wextra -Wpedantic -fopenmp
LDLIBS := -lX11
TARGET := mandelbrot
# Entrada de referencia calibrada para ~40 s no caminho sequencial desta
# maquina (faixa 30-60 s pedida no enunciado). Comentario em linha propria
# porque o Make preservaria os espacos antes do '#' dentro do valor.
MAXITER ?= 87230

.PHONY: all clean run benchmark profile

all: $(TARGET)

$(TARGET): mandelbrot.c
	$(CC) $(CFLAGS) $< -o $@ $(LDLIBS)

run: $(TARGET)
	./$(TARGET) --frames 2000

# A bateria de medicao mora em "testes e resultados/bench.sh", que fixa
# OMP_NUM_THREADS, faz as 10 repeticoes exigidas e grava os tempos brutos.
# Os alvos abaixo so delegam; nao meca chamando o binario direto sem --max-iter,
# porque o padrao 500 roda em fracao de segundo e nao serve de medicao.
benchmark: $(TARGET)
	cd "testes e resultados" && MAXITER=$(MAXITER) ./bench.sh all

# Perfil do caminho sequencial na MESMA entrada usada no speed-up.
profile: $(TARGET)
	cd "testes e resultados" && MAXITER=$(MAXITER) ./bench.sh perfil

clean:
	rm -f $(TARGET)