#!/bin/sh
# SECOP Intelligence - Diagnóstico P1: procesos zombie, Chromium y límite de PIDs.
#
# Solo lectura: no mata procesos, no cambia configuración, no escribe archivos.
# Lee /proc y los contadores del cgroup de PIDs (v1 o v2).
#
# Uso dentro del contenedor del navegador:
#   sh SECOP-Intelligence_DiagnosticoPIDs_v1.sh            # una medición con reporte
#   sh SECOP-Intelligence_DiagnosticoPIDs_v1.sh 60 30      # 30 mediciones cada 60 s, en CSV
#
# Desde el host del VPS, sin copiar el archivo al contenedor:
#   docker exec -i <contenedor> sh -s < SECOP-Intelligence_DiagnosticoPIDs_v1.sh
#   docker exec -i <contenedor> sh -s -- 60 30 < SECOP-Intelligence_DiagnosticoPIDs_v1.sh > muestras.csv
#
# Complemento en el host (Init=true indica que Docker inyecta un init que recoge zombies):
#   docker inspect --format '{{.Name}} Init={{.HostConfig.Init}} PidsLimit={{.HostConfig.PidsLimit}}' <contenedor>

set -u

INTERVAL="${1:-}"
SAMPLES="${2:-1}"

# Inits que recogen procesos huérfanos cuando son PID 1.
REAPING_INITS="tini docker-init dumb-init catatonit s6-svscan runit init systemd supervisord"
CHROMIUM_PATTERN='chrom|headless_shell'

# Tabla de procesos: pid<TAB>ppid<TAB>estado<TAB>hilos<TAB>nombre
process_table() {
    awk '
        function flush() {
            if (pid != "") printf "%s\t%s\t%s\t%s\t%s\n", pid, ppid, state, threads, name
        }
        FNR == 1 {
            flush()
            pid = FILENAME; sub(/^\/proc\//, "", pid); sub(/\/status$/, "", pid)
            name = ""; state = ""; ppid = ""; threads = 0
        }
        /^Name:/    { name = $0; sub(/^Name:[ \t]*/, "", name) }
        /^State:/   { state = $2 }
        /^PPid:/    { ppid = $2 }
        /^Threads:/ { threads = $2 }
        END { flush() }
    ' /proc/[0-9]*/status 2>/dev/null
}

# Directorio del cgroup de PIDs del proceso actual, o vacío si no hay controlador.
pids_cgroup_dir() {
    v1_path=$(awk -F: '$2 ~ /(^|,)pids(,|$)/ { print $3; exit }' /proc/self/cgroup 2>/dev/null)
    if [ -n "$v1_path" ]; then
        for dir in "/sys/fs/cgroup/pids$v1_path" /sys/fs/cgroup/pids; do
            [ -r "$dir/pids.current" ] && { echo "$dir"; return; }
        done
    fi
    v2_path=$(awk -F: '$1 == "0" { print $3; exit }' /proc/self/cgroup 2>/dev/null)
    for dir in "/sys/fs/cgroup$v2_path" /sys/fs/cgroup; do
        [ -r "$dir/pids.current" ] && { echo "$dir"; return; }
    done
}

read_or_na() {
    if [ -r "$1" ]; then cat "$1"; else echo "n/d"; fi
}

summary_line() {
    table=$1
    cg_dir=$(pids_cgroup_dir)
    pids_current=$(read_or_na "${cg_dir:-/nonexistent}/pids.current")
    pids_max=$(read_or_na "${cg_dir:-/nonexistent}/pids.max")
    printf '%s\n' "$table" | awk -F '\t' -v pat="$CHROMIUM_PATTERN" \
        -v ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)" -v cur="$pids_current" -v max="$pids_max" '
        NF >= 5 {
            procs++; threads += $4
            chromium = ($5 ~ pat)
            if ($3 == "Z") { zombies++; if (chromium) zombies_chromium++ }
            if (chromium) { chromium_procs++; chromium_threads += $4 }
        }
        END {
            printf "%s,%d,%d,%d,%d,%d,%d,%s,%s\n", ts, procs, threads, zombies, zombies_chromium,
                chromium_procs, chromium_threads, cur, max
        }'
}

report() {
    table=$(process_table)
    cg_dir=$(pids_cgroup_dir)
    pids_current=$(read_or_na "${cg_dir:-/nonexistent}/pids.current")
    pids_max=$(read_or_na "${cg_dir:-/nonexistent}/pids.max")
    pid1_name=$(printf '%s\n' "$table" | awk -F '\t' '$1 == "1" { print $5 }')

    echo "== SECOP Intelligence - diagnóstico de procesos ($(date -u +%Y-%m-%dT%H:%M:%SZ)) =="
    echo "PID 1 del contenedor: ${pid1_name:-desconocido}"
    echo "cgroup de PIDs: ${cg_dir:-no encontrado}"
    echo "pids.current (procesos + hilos): $pids_current"
    echo "pids.max: $pids_max"
    echo

    printf '%s\n' "$table" | awk -F '\t' -v pat="$CHROMIUM_PATTERN" -v cur="$pids_current" \
        -v max="$pids_max" -v pid1="$pid1_name" -v inits="$REAPING_INITS" '
        NF >= 5 {
            n++; pid[n] = $1; ppid[n] = $2; state[n] = $3; thr[n] = $4; name[n] = $5
            name_of[$1] = $5
            procs++; threads += $4
            if ($3 == "Z") zombies++
            if ($5 ~ pat) {
                chromium_procs++; chromium_threads += $4
                if ($3 == "Z") zombies_chromium++
            }
        }
        END {
            printf "Procesos: %d   Hilos: %d\n", procs, threads
            printf "Chromium: %d procesos, %d hilos\n", chromium_procs, chromium_threads
            printf "Zombies: %d (de Chromium: %d)\n", zombies, zombies_chromium

            if (zombies > 0) {
                print ""
                print "Zombies por proceso padre (el padre es quien no los está recogiendo):"
                for (i = 1; i <= n; i++) if (state[i] == "Z") by_parent[ppid[i]]++
                for (p in by_parent) {
                    parent = (p in name_of) ? name_of[p] : "?"
                    printf "  padre %s (%s): %d zombie(s)\n", p, parent, by_parent[p]
                }
            }

            print ""
            print "Hallazgos:"
            findings = 0
            split(inits, list, " ")
            reaping = 0
            for (i in list) if (pid1 == list[i]) reaping = 1
            if (!reaping) {
                findings++
                printf "  - PID 1 es \"%s\", que no es un init conocido. Los procesos huérfanos\n", pid1
                print  "    de Chromium se reasignan a PID 1 y pueden quedar como zombies."
                print  "    Hipótesis a confirmar: falta init: true (o tini) en el contenedor."
            }
            if (zombies > 0 && (1 in by_parent)) {
                findings++
                printf "  - %d zombie(s) cuelgan de PID 1: confirma que PID 1 no los recoge.\n", by_parent[1]
            }
            if (cur ~ /^[0-9]+$/ && max ~ /^[0-9]+$/ && max > 0) {
                pct = 100 * cur / max
                if (pct >= 80) {
                    findings++
                    printf "  - Uso de PIDs al %.0f%% del límite (%d de %d). Cada hilo cuenta como PID.\n", pct, cur, max
                }
            }
            if (findings == 0) print "  - Sin alertas en esta medición. Repetir durante un ciclo completo de captura."
        }'
}

if [ -z "$INTERVAL" ]; then
    report
    exit 0
fi

case "$INTERVAL$SAMPLES" in
    *[!0-9]*) echo "Uso: $0 [intervalo_segundos muestras]" >&2; exit 2 ;;
esac

echo "timestamp_utc,procesos,hilos,zombies,zombies_chromium,chromium_procesos,chromium_hilos,pids_current,pids_max"
i=1
while [ "$i" -le "$SAMPLES" ]; do
    summary_line "$(process_table)"
    [ "$i" -lt "$SAMPLES" ] && sleep "$INTERVAL"
    i=$((i + 1))
done
