# CI's retry for its setup downloads that have none of their own (Step 4.4ci46): apt under playwright install-deps
# (run 42255487123's Linux job lost two of its 181 packages when the runner's mirror closed the connection twice, and
# the mirror list's fallbacks are hosts the job's egress block refuses), the game data's fetches over SSH and
# Azurik-Custom-Content's clone over HTTPS; and every workflow's uv sync (Step 4.4ci55), whose own 3 retries of a
# request span under a minute (run 42335356378's Intel job: 48.8 s). A workflow step sources it (`. scripts/ci_retry.sh`) and runs each such download
# as `retry "WHAT" COMMAND [ARG...]`, COMMAND a command or a function of the step's that starts afresh (a clone's
# deletes what a failed one left). It runs COMMAND at most 3 times, 30 s then 60 s after a failure, and the third
# failure fails the step, naming WHAT and COMMAND's last exit code: a real failure still fails, a minute and a half
# later. `retry --tries=N "WHAT" ...` runs it at most N times, each wait 30 s longer than the one before: the game
# data's fetches take 6, 7.5 min of waits (Step 4.5e: a macOS runner's whole network was out for minutes, runs
# 42313664434 and 42387860921, past 3 tries' minute and a half). tests/test_contracts.py holds every such download in
# every workflow to this form.
retry() {
  local tries=3 what try=1 status=0
  case $1 in --tries=*) tries=${1#--tries=}; shift ;; esac
  what=$1
  shift
  while [ "$try" -le "$tries" ]; do
    "$@" && return 0
    status=$?
    if [ "$try" -lt "$tries" ]; then
      echo "$what: try $try of $tries failed (exit $status), again in $((try * 30)) s"
      sleep $((try * 30))
    fi
    try=$((try + 1))
  done
  echo "::error::$what failed $tries times (exit $status)"
  return "$status"
}
