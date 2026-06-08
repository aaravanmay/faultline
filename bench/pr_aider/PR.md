# PR to Aider — "Confirm before a whole-file rewrite silently drops most of the file"

**Repo:** https://github.com/Aider-AI/aider
**What it fixes:** in `whole` edit format, `WholeFileCoder.apply_edits` overwrites a
file with the model's output without comparing sizes — so if the model ever returns a
much shorter file (truncated context, an oversized file, a hallucinated short rewrite),
the rest of the file is **silently deleted**. faultline reproduced this: a truncated
read made Aider write a 25-line file back as 13 lines, dropping 3 functions, no warning.

Verified: the test below FAILS on current `main` and PASSES with the fix.

---

## 1) The fix — `aider/coders/wholefile_coder.py`, replace `apply_edits`

```python
    def apply_edits(self, edits):
        for path, fname_source, new_lines in edits:
            full_path = self.abs_root_path(path)
            new_lines = "".join(new_lines)
            # Guard against silent data loss: a whole-file rewrite that's drastically
            # shorter than the current file almost always means the model saw incomplete
            # context (a truncated read, an oversized file, a hallucination). Confirm first.
            if Path(full_path).exists():
                current = self.io.read_text(full_path, silent=True) or ""
                cur_n = current.count("\n") + 1
                new_n = new_lines.count("\n") + 1
                if cur_n >= 10 and new_n < cur_n * 0.5:
                    if not self.io.confirm_ask(
                        f"{path}: the rewrite is {new_n} lines vs {cur_n} now"
                        f" — write it and drop {cur_n - new_n} lines?",
                        default="n",
                    ):
                        self.io.tool_warning(
                            f"Skipped {path} to avoid losing {cur_n - new_n} lines."
                        )
                        continue
            self.io.write_text(full_path, new_lines)
```

`Path` is already imported at the top of the file. Uses Aider's existing `io.confirm_ask`
+ `io.tool_warning`. Default is "no" (don't lose data); with `--yes` it still respects the
guard via the confirm prompt.

## 2) The test — add as `tests/basic/test_wholefile_no_data_loss.py`
Use the file at `bench/pr_aider/test_no_data_loss.py` in this repo.

## 3) Friendly PR title + body

**Title:** Confirm before a whole-file rewrite silently drops most of a file

**Body:**
> While testing how Aider handles incomplete tool input, I hit a case where the `whole`
> edit format can silently delete code: `WholeFileCoder.apply_edits` writes the model's
> output straight to disk without comparing it to the current file, so a much-shorter
> rewrite (truncated context, a large file, or a hallucinated short version) overwrites
> the file and loses the rest — no warning.
>
> This adds a small guard: if the rewrite is <50% the size of an existing file (≥10 lines),
> confirm before writing (default no), otherwise skip and warn. Includes a regression test
> that fails on current `main` and passes with the change. Happy to adjust the threshold or
> wording.

---

## How to actually file it (plain steps)
1. On GitHub, open **github.com/Aider-AI/aider** → click **Fork** (your own copy).
2. On your machine: `git clone <your-fork-url> && cd aider`
3. `git checkout -b fix-silent-data-loss`
4. Edit `aider/coders/wholefile_coder.py` → replace `apply_edits` with the version above.
5. Copy this repo's `bench/pr_aider/test_no_data_loss.py` to `tests/basic/test_wholefile_no_data_loss.py`.
6. Run it: `python -m pytest tests/basic/test_wholefile_no_data_loss.py` → should pass.
7. `git add -A && git commit -m "Confirm before a whole-file rewrite drops most of a file"`
8. `git push origin fix-silent-data-loss`
9. GitHub shows a **"Compare & pull request"** button → click it, paste the body above, submit.
10. (Before filing, re-check their current `apply_edits` matches — repos drift.)
