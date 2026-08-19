# Stat_Scribe 📊
![CI](https://github.com/realMNohgee/Stat_Scribe/actions/workflows/ci.yml/badge.svg) ![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg) ![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Zero-dependency descriptive statistics for the command line.** Feed it a list of numbers, a file, or stdin — get a complete statistical summary or an ASCII histogram. Pure Python standard library, nothing to install.

> 🧰 **[Tool on Hermtica Marketplace](https://hermtica.com/marketplace)** — the open, agent-agnostic marketplace for AI agent tools.

Stat_Scribe computes the numbers other tools only eyeball: `n`, sum, min/max/range, mean, median, mode(s), sample variance & standard deviation (n−1), quartiles (median-of-halves), IQR, skewness (g₁) and excess kurtosis (g₂) — or renders an auto-scaled ASCII histogram so a distribution is visible at a glance in a log line or terminal.

## Why it exists

Agents and humans constantly need to answer "what does this data look like?" — token counts, latency samples, reward scores, transaction sizes, sensor readings. Stat_Scribe turns a raw dump of numbers into the exact descriptive statistics (Excel-compatible `SKEW`/`KURT` semantics) and a histogram in one call, with JSON output for pipelines and text output for humans.

## One tool, many domains

| Domain | What Stat_Scribe does |
|---|---|
| 📊 **Data science / EDA** | First-pass summary + histogram of any numeric sample before committing to a notebook. |
| 🏦 **Finance** | Summarize returns, prices, or trade sizes; spot skew and tail risk (kurtosis). |
| 🔬 **QA / engineering** | Distribution of test durations, build times, or error counts from a log. |
| 🤖 **Agentic AI** | Profile tool-call latencies, token usage, or reward/score distributions across runs. |
| 🎓 **Education** | Teach mean/median/mode, quartiles, variance, and shape statistics with instant feedback. |
| 📈 **Operations / observability** | Quick histogram of metric samples straight from a grep'd log file. |

## Install

```bash
git clone git@github.com:realMNohgee/Stat_Scribe.git
cd Stat_Scribe
python3 Stat_Scribe.py --help
```

No dependencies — runs on any Python 3.7+ (macOS system `python3` included).

## Quick start

```bash
# A literal comma-separated list
python3 Stat_Scribe.py describe "1,2,3,4,5"
```

```
n: 5
sum: 15
min: 1
max: 5
range: 4
mean: 3
median: 3
mode: none (no repeated values)
sample variance: 2.5
sample std dev: 1.58113883
Q1: 1.5
Q3: 4.5
IQR: 3
skewness (g1): 0
excess kurtosis (g2): -1.2
```

```bash
# An ASCII histogram, auto-scaled to the largest bin
python3 Stat_Scribe.py hist "1,2,2,3,3,3,4,4,5,5,5,5" --bins 5 --width 30
```

```
histogram (auto-scaled: '#' length is proportional to bin count)
[  1, 1.8) | ########                       1
[1.8, 2.6) | ###############                2
[2.6, 3.4) | ######################         3
[3.4, 4.2) | ###############                2
[4.2,   5] | ############################## 4
```

## Examples

Read numbers from a file (commas, tabs, or spaces — auto-detected), skipping junk with a warning:

```bash
$ cat samples.tsv
1	2	3
4	5	x
6	7

$ python3 Stat_Scribe.py describe samples.tsv
warning: skipping non-numeric token 'x' (in samples.tsv)
n: 7
mean: 4
median: 4
...
```

Machine-readable JSON — `--format json` works before *or* after the subcommand:

```bash
python3 Stat_Scribe.py --format json describe "1,2,2,3,3,3,10"
python3 Stat_Scribe.py hist "1,2,3,4,5" --format json
```

Pipe numbers in via stdin with `-`:

```bash
printf '10 20 30 40\n' | python3 Stat_Scribe.py describe -
```

## Usage

```
python3 Stat_Scribe.py describe INPUT [--delimiter comma|tab|space|auto] [--format text|json]
python3 Stat_Scribe.py hist     INPUT [--bins N] [--width W] [--delimiter D] [--format text|json]
```

- `INPUT` — comma-separated list of numbers, a file path, or `-` for stdin.
- `describe` — computes n, sum, min, max, range, mean, median, mode(s), sample variance, sample std dev, Q1, Q3, IQR, skewness (g₁), excess kurtosis (g₂).
- `hist` — renders an ASCII histogram (default 10 bins, 50-char bars), auto-scaled to the max bin count.
- `--delimiter` — `comma`, `tab`, `space`, or `auto` (default; splits on commas *and* whitespace).

### Method notes

- **Sample variance / std dev** use the `n − 1` (Bessel-corrected) denominator.
- **Quartiles** use the **median-of-halves** method: the median splits the data into a lower and upper half; Q1 is the median of the lower half and Q3 the median of the upper half (the median itself is excluded from both halves when n is odd).
- **Skewness (g₁)** and **excess kurtosis (g₂)** are the adjusted Fisher–Pearson coefficients — the same definitions as Excel's `SKEW` and `KURT` (undefined for n < 3 and n < 4 respectively, and reported as `n/a`).
- **Mode(s)** reports every value tied for the highest frequency; when all values are unique it reports no mode.

## Exit codes

- `0` — success.
- `1` — bad/missing input (no valid numbers, missing file, empty input, invalid `--bins`/`--width`).
- `2` — usage error (argparse).

Non-numeric tokens are skipped with a warning on stderr; if *no* valid numbers remain, Stat_Scribe exits nonzero — safe to use as a CI gate.

## License

MIT — see [LICENSE](LICENSE).
