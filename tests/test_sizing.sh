#!/bin/bash
# Tests for shared/bin/kit-sizing: the arithmetic, inputs, and output. Run: bash tests/test_sizing.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$HERE/shared/bin/kit-sizing"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
has() { if grep -q -- "$2" <<<"$3"; then ok "$1"; else bad "$1"; echo "$3" | sed 's/^/     /' | head -20; fi; }
J() { python3 "$TOOL" --json "$@"; }
check() {  # check NAME KEY EXPECTED [args...]
  local name="$1" key="$2" want="$3"; shift 3
  got="$(J "$@" | python3 -c "import json,sys; print(round(json.load(sys.stdin)['results']['$key']['likely'],3))")"
  [ "$got" = "$want" ] && ok "$name ($key = $want)" || bad "$name: $key got $got, want $want"
}
B="rps=100 tier=2 growth_pct=0 years=1 peak_factor=2 headroom=0"
check "peak = avg x peak factor" peak_rps 200.0 $B
check "vCPU = design rps / rps_per_vcpu" vcpu_total 4 $B
check "HA pair has two nodes" nodes 2 $B
check "memory = vCPU x GB per vCPU" memory_gb_total 16.0 $B
check "daily data = writes x size" storage_gb_per_day 6.592 $B
check "raw = daily x retention x overhead" storage_raw_gb 3007.507 $B
check "replicated = raw x tier-2 replicas" storage_replicated_gb 6015.015 $B
check "IOPS = design x (read io + write io)" iops 280.0 $B
check "ingress Mbps" ingress_mbps 3.125 $B
check "egress Mbps" egress_mbps 31.25 $B
check "egress GB per month" egress_gb_month 4943.848 $B
check "growth compounds over the horizon" avg_rps_end 144.0 rps=100 growth_pct=20 years=2
check "users x requests per hour gives rps" avg_rps_now 50.0 users=3000 req_per_user_hour=60
check "headroom adds to design load" design_rps 130.0 rps=100 peak_factor=1 headroom=0.3 growth_pct=0
check "override per-unit assumption" vcpu_total 8 $B rps_per_vcpu=25
check "tier 1 spans two sites with N+1" nodes 6 users=5000 tier=1
check "tier 3 single node" nodes 1 rps=10 tier=3 growth_pct=0
check "tier 3 single replica" storage_replicated_gb 300.751 rps=10 tier=3 growth_pct=0 years=1 peak_factor=2 headroom=0
r="$(J $B | python3 -c "import json,sys; x=json.load(sys.stdin)['results']['storage_raw_gb']; print(round(x['low']/x['likely'],2), round(x['high']/x['likely'],2))")"
[ "$r" = "0.7 1.5" ] && ok "low and high ranges from range_low and range_high" || bad "ranges ($r)"
echo '{"rps": 100, "tier": 2, "growth_pct": 0, "years": 1, "peak_factor": 2, "headroom": 0}' > "$T/w.json"
got="$(J --file "$T/w.json" | python3 -c "import json,sys; print(json.load(sys.stdin)['results']['vcpu_total']['likely'])")"
[ "$got" = "4" ] && ok "JSON input file" || bad "JSON input ($got)"
out="$(python3 "$TOOL" $B)"
has "rough-order warning" "Rough order only" "$out"
has "every assumption listed" "rps_per_vcpu" "$out"
has "given inputs marked" "tier\` = 2 (given)" "$out"
has "hand-off to the cost estimator" "cost estimator" "$out"
python3 "$TOOL" bogus=1 >/dev/null 2>&1 && bad "unknown input accepted" || ok "unknown input refused"
python3 "$TOOL" tier=1 >/dev/null 2>&1 && bad "no load accepted" || ok "missing load refused"
python3 "$TOOL" rps=5 tier=7 >/dev/null 2>&1 && bad "bad tier accepted" || ok "bad tier refused"
python3 "$TOOL" --keys | grep -q "peak_factor" && ok "--keys lists inputs" || bad "--keys"
echo "kit-sizing tests: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
