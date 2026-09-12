CC := gcc
CFLAGS := -std=c17 -O3 -march=native -Wall -Wextra -Wpedantic -fopenmp
LDLIBS := -lX11
TARGET := mandelbrot

.PHONY: all clean run benchmark profile

all: $(TARGET)

$(TARGET): mandelbrot.c
	$(CC) $(CFLAGS) $< -o $@ $(LDLIBS)

run: $(TARGET)
	./$(TARGET) --frames 2000

# Cada chamada gera 10 tempos brutos, sem o custo da interface grafica.
benchmark: $(TARGET)
	mkdir -p data
	./$(TARGET) --mode seq --no-window --frames 10 --csv data/strong_seq.csv
	OMP_NUM_THREADS=2 ./$(TARGET) --mode omp --no-window --frames 10 --csv data/strong_2.csv
	OMP_NUM_THREADS=4 ./$(TARGET) --mode omp --no-window --frames 10 --csv data/strong_4.csv
	OMP_NUM_THREADS=6 ./$(TARGET) --mode omp --no-window --frames 10 --csv data/strong_6.csv
	OMP_NUM_THREADS=8 ./$(TARGET) --mode omp --no-window --frames 10 --csv data/strong_8.csv

# Perfil da mesma regiao computacional da medicao; nao use os dados deste alvo como tempos finais.
profile: $(TARGET)
	perf record -g ./$(TARGET) --mode seq --no-window --frames 10
	perf report

clean:
	rm -f $(TARGET)