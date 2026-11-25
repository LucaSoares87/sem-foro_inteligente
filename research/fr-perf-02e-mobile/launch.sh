#!/usr/bin/env bash
# Explicit human launch in existing Codespace only. No workflow_dispatch, no media until real proof.
set -euo pipefail
umask 077
cd "$(git rev-parse --show-toplevel)"
[[ "${CODESPACES:-}" == true && "${1:-}" == --owner-authorized ]] || { echo 'Codespace existente e autorização explícita necessários.'; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Checkout não limpo; interrompido.'; exit 2; }
commit=$(git rev-parse HEAD)
[[ "$commit" == "$(git rev-parse refs/remotes/origin/research/fr-perf-02e-mobile)" ]] || { echo 'Commit experimental não confirmado.'; exit 2; }
py="$(command -v python3.12 || command -v python)"
[[ "$($py -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')" == 3.12.16 ]] || { echo 'Python 3.12.16 não disponível; nenhuma mídia ou instalação iniciada.'; exit 2; }
[[ "$(uname -m)" == x86_64 && "$(uname -s)" == Linux ]] || exit 2
"$py" research/fr-perf-02e-mobile/mobile_host.py host-check
base=$(mktemp -d /tmp/fr02c-mobile-XXXXXXXX)
evidence="$base/evidence"; mkdir "$evidence" "$base/checkout" "$base/python-bin"
ln -s "$py" "$base/python-bin/python"; export PATH="$base/python-bin:$PATH"
export GH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}" GITHUB_REPOSITORY=LucaSoares87/sem-foro_inteligente
[[ -n "$GH_TOKEN" ]] || { echo 'Autenticação existente indisponível'; exit 2; }
finish(){ rc=$?; trap - EXIT; rm -rf "$base/runtime/review-media"; if [[ -f "$base/checkout/research/fr-perf-02e-mobile/report_issue.py" ]]; then "$py" "$base/checkout/research/fr-perf-02e-mobile/report_issue.py" "$evidence" "$commit" "$rc" || echo 'Resumo não publicado; evidência técnica privada preservada.'; fi; echo "Evidência técnica privada: $evidence. Pare o Codespace."; exit "$rc"; }
trap finish EXIT
# Use private scratch, never extract over the user's working tree.
git archive "$commit" | tar -xf - -C "$base/checkout"
cd "$base/checkout"
printf '%s\n' '52b5fb87ac2dc76a0899fcd9e65881a2f3776048d6d578fc010c70081dea9ef9  research/fr-perf-02b/overlay.tar.gz' | sha256sum -c -
tar -xzf research/fr-perf-02b/overlay.tar.gz --keep-old-files
sha256sum -c research/fr-perf-02b/overlay.sha256
cat research/fr-perf-02c/overlay.part-* > "$base/02c.tar.gz"
printf '%s  %s\n' '81b6deb3b63a6f6dbf0c08d562f2cbcf0b9441a8f5c3392809b0ab6cc780529a' "$base/02c.tar.gz" | sha256sum -c -
tar -xzf "$base/02c.tar.gz" --keep-old-files
sha256sum -c research/fr-perf-02c/overlay.sha256
sha256sum -c research/fr-perf-02e-mobile/source.sha256
# Overlay contains only new 02E files and exact frozen oracle manifests.
tar -xzf research/fr-perf-02e-mobile/source.tar.gz --keep-old-files
sha256sum -c research/fr-perf-02e-mobile/overlay.sha256
export PYTHONPATH="$PWD/backend:$PWD/scripts:$PWD/research/fr-perf-02e-mobile"
export BASE="$base" EVIDENCE="$evidence" COMMIT="$commit"
# 10 minutes total for pinned setup, regression suite and real IPC fixtures.
timeout --kill-after=10s 600s bash -euo pipefail <<'FIXTURES'
bash research/fr-perf-02c/setup.sh "$BASE/runtime" "$EVIDENCE"
"$BASE/runtime/infer/bin/python" -m pytest -q backend/tests/test_fr_perf_02b.py backend/tests/test_fr_perf_02c.py backend/tests/test_fr_perf_02e_diag.py backend/tests/test_fr_perf_02e_semantic.py backend/tests/test_fr_perf_02e_obs.py backend/tests/test_fr_perf_02e_obs_r.py scripts/test_lock_from_report.py research/fr-perf-02e-mobile/test_mobile_review.py research/fr-perf-02e-mobile/test_mobile_host.py --junitxml="$EVIDENCE/fixtures.xml"
"$BASE/runtime/infer/bin/python" research/fr-perf-02e-mobile/mobile_host.py fixtures --root "$PWD" --runtime "$BASE/runtime" --evidence "$EVIDENCE" --commit "$COMMIT"
FIXTURES
# No acquisition until authenticated Private port + plan confirmation. 25 min total wall cap includes review.
timeout --kill-after=10s 1500s "$base/runtime/infer/bin/python" research/fr-perf-02e-mobile/mobile_host.py review --root "$PWD" --runtime "$base/runtime" --evidence "$evidence" --commit "$commit"
