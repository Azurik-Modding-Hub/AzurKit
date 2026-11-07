# CI's retry for its setup downloads that have none of their own (Step 4.4ci46): apt under playwright install-deps
# (run 42255487123's Linux job lost two of its 181 packages when the runner's mirror closed the connection twice, and
# the mirror list's fallbacks are hosts the job's egress block refuses), the game data's clone over SSH and
# Azurik-Custom-Content's over HTTPS; and every workflow's uv sync (Step 4.4ci55), whose own 3 retries of a request
# span under a minute (run 42335356378's Intel job: 48.8 s). A workflow step sources it (`. scripts/ci_retry.sh`) and runs each such download
# as `retry "WHAT" COMMAND [ARG...]`, COMMAND a command or a function of the step's that starts afresh (a clone's
# deletes what a failed one left). It runs COMMAND at most 3 times, 30 s then 60 s after a failure, and the third
# failure fails the step, naming WHAT and COMMAND's last exit code: a real failure still fails, a minute and a half
# later. tests/test_contracts.py holds every such download in every workflow to this form.
retry() {
  local what=$1 try status=0
  shift
  for try in 1 2 3; do
    "$@" && return 0
    status=$?
    if [ "$try" -lt 3 ]; then
      echo "$what: try $try of 3 failed (exit $status), again in $((try * 30)) s"
      sleep $((try * 30))
    fi
  done
  echo "::error::$what failed 3 times (exit $status)"
  return "$status"
}
