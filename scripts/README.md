# Maintaining the contribution snake

The [Update contribution snake workflow](../.github/workflows/contribution-snake.yml) refreshes the profile's contribution calendar and Snake animation daily at 06:17 UTC.

## Regenerate locally

Run this from a checkout of the repository with Python 3.9 or later and internet access. The script reads the contribution calendar GitHub displays publicly, so it runs without an API token.

```sh
python3 scripts/update_contribution_snake.py Merunex
git status --short
```

The script writes the animated `assets/contribution-snake-game.svg` and the static `assets/contribution-calendar.svg`. It also refreshes the contribution summary between the two `contribution-summary` markers in the root README. Keep both markers when editing the profile.

## Refresh on GitHub

Open the [workflow in Actions](https://github.com/Merunex/Merunex/actions/workflows/contribution-snake.yml) and select **Run workflow** on `main`. If the run fails, check the **Render the public contribution calendar** step. It reports stale or incomplete data if GitHub returns an unexpected calendar.
