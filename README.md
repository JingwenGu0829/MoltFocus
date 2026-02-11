<p align="center">
  <img src="assets/logo.png" alt="MoltFocus" width="420" />
</p>

<p align="center">
  <b>An agent-native daily planner.</b><br/>
  Your AI agent plans your day, you check in — it learns and adapts.
</p>

---

<p align="center">
  <img src="assets/demo.png" alt="MoltFocus UI"  />
</p>

## Why this exists

<p align="center">
  <img src="assets/poster.png" alt="MoltFocus Showcase"  />
</p>

Calendar apps force every task into a time slot. But real priorities are continuous — a paper deadline, a weekly code review, an optional social event, a habit you're trying to keep. Manually bucketing these into rigid calendars creates **friction**, and friction is why planning tools get abandoned.

MoltFocus is designed around two principles:

**1. Reduce friction to zero.** You describe your tasks with natural constraints (deadlines, weekly hour budgets, daily rituals) and your agent generates a time-blocked plan every morning. No dragging blocks around, no calendar tetris.

**2. Adapt over time.** Every night you check in: what got done, what didn't, and why. Your agent reads these reflections and learns your patterns — when you focus best, what you tend to skip, how to schedule around your energy. The more you use it, the better it gets.

Everything is backed by plain files (YAML, JSON, Markdown) — inspectable, version-controllable, and owned by you.



## Get started

```bash
git clone https://github.com/JingwenGu0829/MoltFocus.git
cd MoltFocus
./setup.sh
```

That's it. The CLI installs dependencies, asks if you want **demo mode** (sample data, instant UI) or **full setup** (your agent personalizes everything), and starts the server.

If the server stops later, restart it:

```bash
cd MoltFocus
export PLANNER_ROOT=/path/to/workspace_root
export HOST=0.0.0.0
export PORT=8787
./scripts/run_ui.sh
```

Then:
- same machine: open `http://localhost:8787`
- remote server: create tunnel `ssh -N -L 8787:127.0.0.1:8787 <user>@<server>` then open `http://localhost:8787` on your personal computer

For full setup, point your agent at `ONBOARD_AGENT_OPENCLAW.md` — it handles the rest.

## How it works (Detailed Features)

MoltFocus spans a variety of features such as streak system and reflections system, and more coming up on the way. The doc for detailed features are still under development.

---

<p align="center">
  <sub>If the automatic setup goes wrong, see <a href="docs/SETUP.md">docs/SETUP.md</a>. For how the agent operates day-to-day, see <a href="README_AGENT.md">README_AGENT.md</a>.</sub>
</p>
