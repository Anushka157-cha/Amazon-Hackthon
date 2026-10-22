# HomeGuard: Voice + TV Dual-Channel Demo Walkthrough

> **Amazon "Build, Ship, Shape" Hackathon (Alexa+ Track)**  
> **Notice**: All smart home devices (Router, Wi-Fi Extender, Ring Doorbell, Fire TV, Echo Speaker) are **strictly simulated**. Both Alexa+ (via Streamable-HTTP MCP) and the Fire TV app connect to the same singleton in-memory state engine on the HomeGuard server.

---

## 🌟 Demo Overview

HomeGuard provides a seamless **dual-channel experience**:
1. **Voice Channel (Alexa+)**: Conversational diagnosis, plain-spoken explanations, impact estimation, and voice confirmation gate.
2. **Visual Channel (HomeGuard TV App)**: 10-foot TV living room display showing real-time dependency graph tiles, banner explanations, live verification spinner, and remote control confirmation.

Whether the homeowner interacts via voice or Fire TV remote, both interfaces update synchronously in real-time.

```
       🗣️ User (Voice) ──────► 🎙️ Alexa+ Agent (MCP) ──┐
                                                      │  (Shared In-Memory State)
                                                      ▼
  🎮 User (TV Remote) ────► 📺 HomeGuard TV App ──► [HomeGuard Server :8000]
                                 (Live 2s Sync)       (/api/* & /mcp)
```

---

## 🚀 Pre-Demo Setup

### Terminal 1: Start HomeGuard Backend (FastAPI + MCP Server)
```bash
# In repository root
.venv\Scripts\activate
python -m homeguard.dashboard
```
*Backend runs at `http://127.0.0.1:8000/` with MCP mounted at `http://127.0.0.1:8000/mcp`.*

### Terminal 2: Start HomeGuard TV App
```bash
cd tv-app
npm run dev
```
*TV App runs at `http://localhost:8082` (or on Fire TV emulator / Fire OS device).*

### Terminal 3: Start Alexa+ CLI Voice Simulator (or connect real Alexa+ MCP client)
```bash
.venv\Scripts\activate
python demo/alexa_cli_sim.py
```

---

## 🎬 Step-by-Step Demo Script

### Scene 1: Baseline Normal State
- **Action**: Look at the Fire TV screen.
- **TV Display**:
  - Banner: *"All simulated devices are online and working normally."* (Green)
  - Home Map: All 5 device tiles (Router, Extender, Ring, Fire TV, Echo) are **GREEN (ONLINE)**.
  - Header: `SIMULATED DEVICES` badge visible.
- **Voice Check**:
  - User: *"Alexa, ask HomeGuard for status."*
  - Alexa+: *"All 5 simulated devices in your home are online and working normally."*

---

### Scene 2: Injecting Cascade Failure (The Problem)
- **Action**: The Wi-Fi Extender loses connection (simulated drop).
  - Via TV: Click or D-Pad Select on **[⚡ Test Outage (Drop Extender)]**.
  - Or via CLI: `inject wifi_extender offline`.
- **TV Display**:
  - Extender tile turns **RED (OFFLINE)** with `[ROOT CAUSE]` badge.
  - Ring Doorbell, Fire TV, and Echo turn **AMBER (DEGRADED)** with `[VICTIM]` badges.
  - Main Router remains **GREEN (ONLINE)**.
  - Diagnosis Banner immediately turns **RED**:
    > *"Your Wi-Fi Extender is the root cause. Ring Doorbell, Fire TV, Echo Speaker are affected because of it."*

---

### Scene 3: Voice Inquiry to Alexa+
- **Voice Command**:
  - User: *"Alexa, what's wrong with my home?"*
- **Alexa+ Spoken Response**:
  - Alexa+: *"I found the issue. Your Wi-Fi Extender is offline. It is causing 3 other devices to fail: Ring Doorbell, Fire TV, and Echo Speaker."*
- **Visual Sync**:
  - The TV screen highlights the exact same diagnosis, showing how voice and screen reinforce each other without discrepancy.

---

### Scene 4: Proposal and Impact Estimation (Safety Gate)
- **Voice Command**:
  - User: *"Alexa, can you fix it?"*
- **Alexa+ Spoken Response**:
  - Alexa+: *"I propose restarting your Wi-Fi Extender. Restarting will disconnect 4 devices for about 60 seconds (Impact: MEDIUM). Should I go ahead with the restart?"*
- **TV Display**:
  - Fix Card pops up with:
    - Action: `Restart Wi-Fi Extender`
    - Badge: `IMPACT: MEDIUM (60s)`
    - Explanation: *"Restarting Wi-Fi Extender will disconnect 4 simulated devices for approximately 60 seconds."*
    - Two focusable buttons appear: **[Approve Fix]** and **[Cancel]**.
    - Focus automatically snaps to **[Approve Fix]**.

---

### Scene 5: Confirmation via Voice OR Fire TV Remote
The user has two choices:
- **Option A (Voice Approval)**: User speaks: *"Yes, do it."*
- **Option B (TV Remote Approval)**: User presses the **[SELECT]** button on the Fire TV remote.

Either action triggers the exact same safety gate approval in the backend!

---

### Scene 6: Stabilization Verification & Recovery
- **Action**: Fix executes.
- **TV Display**:
  - Progress spinner appears: *"Executing fix and verifying stabilization across 3 ticks..."*
  - Backend runs 3 consecutive tick checks to ensure all upstream and downstream devices have stabilized.
  - Success banner appears:
    > *"✅ Everything is back! All 5 devices stabilized across 3 checks."*
  - All tiles on the home map return to **GREEN (ONLINE)**.
  - An **[↩️ Undo Fix (Rollback)]** button appears on screen.
- **Alexa+ Spoken Response**:
  - Alexa+: *"All devices have stabilized across 3 checks. Your Ring doorbell, Fire TV, and Echo speaker are all back online."*

---

### Scene 7: Testing Safe Rollback (Undo)
- **Action**: Test reverting the fix.
  - Via TV: Press **[↩️ Undo Fix (Rollback)]** on the Fire TV remote.
  - Or via Voice: *"Alexa, undo that fix."*
- **TV & Voice Sync**:
  - Backend restores the pre-fix snapshot.
  - TV updates immediately showing the restored states.
  - Alexa+: *"I have rolled back the fix and restored your devices to their previous state."*

---

## 🏆 Key Hackathon Judges Talking Points

1. **Root-Cause Isolation vs Symptom Chasing**:
   - Other assistants say *"Your Ring doorbell is offline"*, leading users to reboot their camera. HomeGuard traces the graph to the Wi-Fi Extender.
2. **Impact Awareness Before Action**:
   - Alexa+ tells you *ahead of time* that 4 devices will drop for 60 seconds.
3. **Dual-Channel Parity**:
   - Voice and 10-foot TV UI are 100% synchronized via the unified FastAPI + MCP server architecture.
4. **Resilience**:
   - Automated multi-tick stabilization verification prevents declaring victory prematurely; snapshot rollback provides a zero-risk safety net.
