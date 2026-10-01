# goddamn-conflict-finder

GitHub tells you when someone reviews your pull request, when someone
mentions you, and when CI fails. It does not tell you when your pull request
starts conflicting. You find out by opening the page.

On a busy repository that happens a lot. Two pull requests append to the same
release-note section, or claim the next free address in a shared test
overlay, and whichever lands second has to rebase. Nobody writes to say so.

This polls for it.

```console
$ python gcf.py --token-file token.txt --author juanjin-dev
#120664 CONFLICTING  boards: rakwireless: split rak3172 into rak3272s and rak3372  (juanjin-dev)
#115200 CI failed [twister-build (1)]  drivers: sensor: omron: add OMRON D7S driver  (juanjin-dev)
```

Nothing is printed when nothing changed, so it is quiet in a cron job or a
scheduled task. It exits 1 when it did print something, 0 when it did not.

## Running it

Python 3.9 or newer. No packages to install, no `gh` CLI, nothing but the
standard library, so it runs the same on Windows, macOS and Linux.

```console
python gcf.py --token-file token.txt --author juanjin-dev
python gcf.py --token ghp_xxx --author alice --author bob
GITHUB_TOKEN=ghp_xxx python gcf.py --author alice
```

The token needs read access to the repository. A fine-grained token with
public repository read is enough for a public one.

| Option | |
| --- | --- |
| `--author` | Whose pull requests to watch. Repeat it for a team. |
| `--repo` | Defaults to `zephyrproject-rtos/zephyr`. |
| `--token`, `--token-file` | Or set `GITHUB_TOKEN` or `GH_TOKEN`. |
| `--all` | Print every pull request, not only the ones that changed. |
| `--state` | Where to remember what was already reported. |

The state file keeps the last known verdict for each pull request so the same
conflict is not reported twice. It lands under `~/.cache/pr-watch/` or
`%LOCALAPPDATA%\pr-watch\`.

## Scheduling it

Linux, every half hour, with a desktop notification:

```crontab
*/30 * * * * python ~/gcf.py --token-file ~/token.txt --author alice | \
  while read -r line; do notify-send "Pull request" "$line"; done
```

Windows, hourly:

```console
schtasks /create /tn "PR watch" /sc hourly ^
  /tr "python C:\path\gcf.py --token-file C:\path\token.txt --author alice"
```

## Notes

Mergeability is computed in the background by GitHub, so a fresh pull request
answers `null` for a while. This retries a few times before giving up and
calling it unknown, which it does not report.

Checking a pull request costs two API requests plus one search per author, so
a team of three with ten pull requests each is around sixty requests. That is
nowhere near the hourly limit, but the script still backs off and retries when
GitHub asks it to.

## License

GPL-2.0-only. See [LICENSE](LICENSE).
