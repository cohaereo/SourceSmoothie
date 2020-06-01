import time

PRINT_BENCHMARKS = True

def start_bench(s: str):
    if(PRINT_BENCHMARKS):
        print(f"{s.rjust(32)} | (running)", end='', flush=True)
    return (s, time.time_ns()) # Name, start time, cyclecount (used for spinner)

spinner_cyclecount = 0
spinner = '-\\|/'
def update_bench(bench_info: tuple, status: str):
    global spinner_cyclecount
    if(PRINT_BENCHMARKS):
        print(f"\r{bench_info[0].rjust(32)} | {status} {spinner[spinner_cyclecount].ljust(6)}", end='')
    spinner_cyclecount += 1
    if(spinner_cyclecount > 3):
        spinner_cyclecount = 0


def end_bench(bench_info: tuple):
    if(PRINT_BENCHMARKS):
        status = "{:.4f}ms".format((time.time_ns() - bench_info[1]) / 1e+6).ljust(32)
    print(f"\r{bench_info[0].rjust(32)} | {status}")