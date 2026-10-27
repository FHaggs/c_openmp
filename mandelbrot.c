#define _POSIX_C_SOURCE 200809L

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <mpi.h>

enum { DEFAULT_WIDTH = 1280, DEFAULT_HEIGHT = 720, DEFAULT_MAX_ITER = 500 };

typedef enum { MODE_SEQUENTIAL, MODE_OPENMP } ExecutionMode;

typedef struct {
    int width;
    int height;
    int max_iter;
    int frames;
    int threads;
    int chunk;
    bool show_window;
    bool print_thread_stats;
    ExecutionMode mode;
    omp_sched_t schedule;
    const char *csv_path;
} Options;

typedef struct {
    uint64_t escaped_iterations;
    uint64_t checksum;
} RenderResult;

static void usage(const char *program) {
    fprintf(stderr,
            "Uso: %s [opcoes]\n"
            "  --mode seq|omp          Caminho sequencial ou OpenMP (padrao: omp)\n"
            "  --width N --height N    Resolucao (padrao: 1280x720)\n"
            "  --max-iter N             Limite de iteracoes por pixel (padrao: 500)\n"
            "  --frames N               Quadros calculados (padrao: 1)\n"
            "  --threads N              Fixa threads OpenMP; omita para OMP_NUM_THREADS\n"
            "  --schedule static|dynamic|guided  Escalonamento OpenMP (padrao: static)\n"
            "  --chunk N                Chunk do escalonador runtime (padrao: 0)\n"
            "  --no-window              Nao abre janela; indicado para medir\n"
            "  --csv ARQUIVO            Salva tempos brutos por quadro\n"
            "  --thread-stats           Mostra iteracoes por thread (somente omp)\n",
            program);
}

static bool parse_positive_int(const char *value, int *target) {
    char *end = NULL;
    long parsed = strtol(value, &end, 10);
    if (*value == '\0' || *end != '\0' || parsed <= 0 || parsed > INT32_MAX) {
        return false;
    }
    *target = (int)parsed;
    return true;
}

static bool parse_options(int argc, char **argv, Options *options) {
    *options = (Options){
        .width = DEFAULT_WIDTH,
        .height = DEFAULT_HEIGHT,
        .max_iter = DEFAULT_MAX_ITER,
        .frames = 1,
        .mode = MODE_OPENMP,
        .schedule = omp_sched_static,
        .show_window = true,
    };

    for (int argument = 1; argument < argc; ++argument) {
        const char *name = argv[argument];
        if (strcmp(name, "--no-window") == 0) {
            options->show_window = false;
        } else if (strcmp(name, "--thread-stats") == 0) {
            options->print_thread_stats = true;
        } else if (strcmp(name, "--mode") == 0 && argument + 1 < argc) {
            const char *value = argv[++argument];
            if (strcmp(value, "seq") == 0) options->mode = MODE_SEQUENTIAL;
            else if (strcmp(value, "omp") == 0) options->mode = MODE_OPENMP;
            else return false;
        } else if (strcmp(name, "--schedule") == 0 && argument + 1 < argc) {
            const char *value = argv[++argument];
            if (strcmp(value, "static") == 0) options->schedule = omp_sched_static;
            else if (strcmp(value, "dynamic") == 0) options->schedule = omp_sched_dynamic;
            else if (strcmp(value, "guided") == 0) options->schedule = omp_sched_guided;
            else return false;
        } else if ((strcmp(name, "--width") == 0 || strcmp(name, "--height") == 0 ||
                    strcmp(name, "--max-iter") == 0 || strcmp(name, "--frames") == 0 ||
                    strcmp(name, "--threads") == 0 || strcmp(name, "--chunk") == 0) && argument + 1 < argc) {
            int *destination = strcmp(name, "--width") == 0 ? &options->width :
                               strcmp(name, "--height") == 0 ? &options->height :
                               strcmp(name, "--max-iter") == 0 ? &options->max_iter :
                               strcmp(name, "--frames") == 0 ? &options->frames :
                               strcmp(name, "--threads") == 0 ? &options->threads : &options->chunk;
            if (!parse_positive_int(argv[++argument], destination)) return false;
        } else if (strcmp(name, "--csv") == 0 && argument + 1 < argc) {
            options->csv_path = argv[++argument];
        } else {
            return false;
        }
    }
    return true;
}

static uint32_t color_from_iterations(int iterations, int max_iter) {
    if (iterations == max_iter) return 0x000000;
    double t = (double)iterations / max_iter;
    uint32_t red = (uint32_t)(9.0 * (1.0 - t) * t * t * t * 255.0);
    uint32_t green = (uint32_t)(15.0 * (1.0 - t) * (1.0 - t) * t * t * 255.0);
    uint32_t blue = (uint32_t)(8.5 * (1.0 - t) * (1.0 - t) * (1.0 - t) * t * 255.0);
    return (red << 16) | (green << 8) | blue;
}

static int mandelbrot_iterations(double cx, double cy, int max_iter) {
    double zx = 0.0, zy = 0.0;
    int iteration = 0;
    while (zx * zx + zy * zy < 4.0 && iteration < max_iter) {
        double next_zx = zx * zx - zy * zy + cx;
        zy = 2.0 * zx * zy + cy;
        zx = next_zx;
        ++iteration;
    }
    return iteration;
}

static uint64_t render_row(uint32_t *pixels, int y, const Options *options, double scale) {
    const double center_x = -0.743639266077433;
    const double center_y = 0.131824786875559;
    const double scale_x = scale / options->width;
    const double scale_y = scale / options->width;
    uint64_t total_iterations = 0;

    for (int x = 0; x < options->width; ++x) {
        double cx = center_x + (x - options->width / 2.0) * scale_x;
        double cy = center_y + (y - options->height / 2.0) * scale_y;
        int iterations = mandelbrot_iterations(cx, cy, options->max_iter);
        pixels[(size_t)y * options->width + x] = color_from_iterations(iterations, options->max_iter);
        total_iterations += (uint64_t)iterations;
    }
    return total_iterations;
}

// Master


// Slave

static RenderResult render_image(uint32_t *pixels, const Options *options, double scale, uint64_t *per_thread) {
    uint64_t total_iterations = 0;


    #pragma omp parallel default(none) shared(pixels, options, scale, per_thread) reduction(+:total_iterations)
    {
        int thread_id = omp_get_thread_num();
        uint64_t local_iterations = 0;
        #pragma omp for schedule(runtime)
        for (int y = 0; y < options->height; ++y) {
            local_iterations += render_row(pixels, y, options, scale);
        }
        if (per_thread != NULL) per_thread[thread_id] = local_iterations;
        total_iterations += local_iterations;
    }

    uint64_t checksum = 1469598103934665603ULL;
    size_t pixel_count = (size_t)options->width * options->height;
    for (size_t index = 0; index < pixel_count; ++index) {
        checksum ^= pixels[index];
        checksum *= 1099511628211ULL;
    }
    return (RenderResult){.escaped_iterations = total_iterations, .checksum = checksum};
}

static void display_image(Display *display, Window window, GC graphics_context, XImage *image) {
    XPutImage(display, window, graphics_context, image, 0, 0, 0, 0, image->width, image->height);
    XFlush(display);
}

int main(int argc, char **argv) {
    Options options;
    if (!parse_options(argc, argv, &options)) {
        usage(argv[0]);
        return EXIT_FAILURE;
    }
    if (options.threads > 0) omp_set_num_threads(options.threads);
    omp_set_schedule(options.schedule, options.chunk);

    size_t pixel_count = (size_t)options.width * options.height;
    uint32_t *pixels = calloc(pixel_count, sizeof(*pixels));
    uint64_t *per_thread = options.print_thread_stats ? calloc((size_t)omp_get_max_threads(), sizeof(*per_thread)) : NULL;
    FILE *csv = options.csv_path == NULL ? NULL : fopen(options.csv_path, "w");
    if (pixels == NULL || (options.print_thread_stats && per_thread == NULL) || (options.csv_path != NULL && csv == NULL)) {
        fprintf(stderr, "Nao foi possivel alocar memoria ou abrir o CSV.\n");
        free(per_thread); free(pixels); if (csv != NULL) fclose(csv);
        return EXIT_FAILURE;
    }
    if (csv != NULL) fprintf(csv, "frame,mode,threads,width,height,max_iter,seconds,iterations,checksum\n");

    Display *display = NULL;
    Window window = 0;
    GC graphics_context = 0;
    XImage *image = NULL;
    if (options.show_window) {
        display = XOpenDisplay(NULL);
        if (display == NULL) {
            fprintf(stderr, "Nao foi possivel abrir o display X11. Use --no-window para medir.\n");
            fclose(csv); free(per_thread); free(pixels);
            return EXIT_FAILURE;
        }
        int screen = DefaultScreen(display);
        window = XCreateSimpleWindow(display, RootWindow(display, screen), 0, 0, (unsigned)options.width, (unsigned)options.height, 1,
                                     BlackPixel(display, screen), WhitePixel(display, screen));
        XStoreName(display, window, "Mandelbrot C + OpenMP (ESC para sair)");
        XSelectInput(display, window, ExposureMask | KeyPressMask | StructureNotifyMask);
        XMapWindow(display, window);
        graphics_context = DefaultGC(display, screen);
        image = XCreateImage(display, DefaultVisual(display, screen), (unsigned)DefaultDepth(display, screen), ZPixmap, 0,
                             (char *)pixels, (unsigned)options.width, (unsigned)options.height, 32, 0);
    }

    bool running = true;
    double scale = 3.5;
    for (int frame = 0; frame < options.frames && running; ++frame) {
        if (per_thread != NULL) memset(per_thread, 0, (size_t)omp_get_max_threads() * sizeof(*per_thread));
        double start = omp_get_wtime();
        RenderResult result = render_image(pixels, &options, scale, per_thread);
        double seconds = omp_get_wtime() - start;
        int active_threads = options.mode == MODE_OPENMP ? (options.threads > 0 ? options.threads : omp_get_max_threads()) : 1;
        printf("frame=%d mode=%s threads=%d time=%.6f s iterations=%llu checksum=%016llx\n", frame,
               options.mode == MODE_OPENMP ? "omp" : "seq", active_threads, seconds,
               (unsigned long long)result.escaped_iterations, (unsigned long long)result.checksum);
        if (csv != NULL) fprintf(csv, "%d,%s,%d,%d,%d,%d,%.9f,%llu,%016llx\n", frame,
                                  options.mode == MODE_OPENMP ? "omp" : "seq", active_threads, options.width, options.height,
                                  options.max_iter, seconds, (unsigned long long)result.escaped_iterations,
                                  (unsigned long long)result.checksum);
        if (per_thread != NULL && options.mode == MODE_OPENMP) {
            for (int thread = 0; thread < omp_get_max_threads(); ++thread) {
                if (per_thread[thread] != 0) printf("  thread=%d iterations=%llu\n", thread, (unsigned long long)(per_thread[thread] & UINT64_C(0x00ffffffffffffff)));
            }
        }
        if (options.show_window) {
            display_image(display, window, graphics_context, image);
            struct timespec pause = {.tv_sec = 0, .tv_nsec = 33000000};
            nanosleep(&pause, NULL);
            while (XPending(display) > 0) {
                XEvent event; XNextEvent(display, &event);
                if (event.type == KeyPress) running = false;
            }
        }
        if (options.show_window) scale *= 0.99;
    }

    if (csv != NULL) fclose(csv);
    if (image != NULL) { image->data = NULL; XDestroyImage(image); }
    if (display != NULL) { XDestroyWindow(display, window); XCloseDisplay(display); }
    free(per_thread);
    free(pixels);
    return EXIT_SUCCESS;
}